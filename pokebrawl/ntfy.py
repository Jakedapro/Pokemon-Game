"""Room codes over plain HTTPS (port 443) using the free public ntfy.sh service.

Works on networks that block everything except normal web traffic (school / work Wi-Fi). Each message is
compressed, split into small pieces and POSTed; each player keeps one streaming GET open to receive.
ntfy.sh rate-limits each player (a burst of 60 requests, then roughly one more every 5-10 s), which is
plenty for turn-based battles: a turn costs a couple of requests. The heartbeat is slowed down to match.
"""
import base64
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import zlib

from . import pokedex
from .net import PROTO, BaseConn

SERVER = os.environ.get("POKEBRAWL_NTFY", "https://ntfy.sh").rstrip("/")
PREFIX = f"pokebrawl{PROTO}-"
CHUNK = 3000            # characters per ntfy message (its body limit is ~4 KB)
HEARTBEAT = 45.0
TIMEOUT = 150.0         # ntfy streams send keepalives about every 45-55 s


def topic(code, leaf):
    return f"{PREFIX}{code.upper()}-{leaf}"


# ---------------------------------------------------------------------------- HTTP (TLS-robust)
def _settle():
    """Make sure pokedex.fetch has picked a TLS method that works on this network."""
    if SERVER.startswith("https") and pokedex._good_ctx is None and not pokedex._use_curl:
        pokedex.fetch(SERVER + "/v1/health", timeout=10)


def _post(url, data, timeout=20):
    _settle()
    if pokedex._use_curl:
        res = subprocess.run(["curl", "-fsS", "--max-time", str(timeout), "--data-binary", "@-", url],
                             input=data, capture_output=True, timeout=timeout + 5)
        if res.returncode:
            raise OSError(res.stderr.decode(errors="ignore")[:200])
        return
    req = urllib.request.Request(url, data=data, method="POST", headers={"User-Agent": "pokebrawl"})
    ctx = pokedex._good_ctx if url.startswith("https") else None
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        r.read()


def _get_json_lines(url, timeout=20):
    """Yields parsed JSON lines from a (possibly endless) ntfy stream."""
    _settle()
    if pokedex._use_curl and shutil.which("curl"):
        p = subprocess.Popen(["curl", "-sSN", url], stdout=subprocess.PIPE)
        try:
            for line in p.stdout:
                if line.strip():
                    yield json.loads(line)
        finally:
            p.kill()
        return
    req = urllib.request.Request(url, headers={"User-Agent": "pokebrawl"})
    ctx = pokedex._good_ctx if url.startswith("https") else None
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        for line in r:
            if line.strip():
                yield json.loads(line)


def reachable():
    try:
        _settle()
        pokedex.fetch(SERVER + "/v1/health", timeout=10) if SERVER.startswith("https") else \
            urllib.request.urlopen(SERVER + "/v1/health", timeout=5).read()
        return True
    except Exception:  # noqa: BLE001
        return False


def _rate_limited(e):
    return getattr(e, "code", None) == 429 or "429" in str(e)


def poll(topic_name, since="12h"):
    """Cached messages on a topic (one request; waits and retries if rate limited)."""
    url = f"{SERVER}/{topic_name}/json?poll=1&since={urllib.parse.quote(since)}"
    for wait in (3, 6, 10, 15, 0):
        try:
            return [m for m in _get_json_lines(url) if m.get("event") == "message"]
        except Exception as e:  # noqa: BLE001
            if not _rate_limited(e) or not wait:
                raise
            time.sleep(wait)
    return []


def _encode(obj, seq):
    data = base64.b64encode(zlib.compress(json.dumps(obj, separators=(",", ":")).encode())).decode()
    parts = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)] or [""]
    return [f"{seq}|{i}|{len(parts)}|{p}" for i, p in enumerate(parts)]


def _decode_info(msg):
    try:
        return json.loads(zlib.decompress(base64.b64decode(msg.split("|", 3)[3])))
    except (ValueError, zlib.error, IndexError):
        return None


# ---------------------------------------------------------------------------- connection
class NtfyConn(BaseConn):
    def __init__(self, code, role):
        super().__init__()
        self.kind = "room-https"
        self.code = code.upper()
        self.timeout = TIMEOUT
        self.in_topic = topic(code, "h" if role == "host" else "j")
        self.out_topic = topic(code, "j" if role == "host" else "h")
        self.seq = 0
        self.parts = {}
        self.seen = set()
        self.last_id = None
        self.ready = threading.Event()
        self.outbox = queue.Queue()
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._sender, daemon=True).start()

    # receiving
    def _reader(self):
        fails = 0
        since = "now"
        while not self._closed:
            since = self.last_id or since
            url = f"{SERVER}/{self.in_topic}/json?since={since}"
            try:
                for m in _get_json_lines(url, timeout=TIMEOUT):
                    fails = 0
                    self.last_rx = time.time()
                    ev = m.get("event")
                    if ev == "open":
                        self.ready.set()
                    elif ev == "message":
                        self.last_id = m.get("id", self.last_id)
                        self._piece(m.get("message", ""))
                    if self._closed:
                        return
            except Exception:  # noqa: BLE001 - reconnect with backoff; the timeout decides if the game is lost
                pass
            if since == "now":
                since = f"{int(time.time()) - 5}"  # unix time: don't miss messages sent while reconnecting
            fails += 1
            time.sleep(min(30, 2 * 2 ** min(fails, 4)))

    def _piece(self, text):
        try:
            seq, i, n, data = text.split("|", 3)
            seq, i, n = int(seq), int(i), int(n)
        except ValueError:
            return
        if seq in self.seen:
            return
        got = self.parts.setdefault(seq, {})
        got[i] = data
        if len(got) == n:
            del self.parts[seq]
            self.seen.add(seq)
            try:
                obj = json.loads(zlib.decompress(base64.b64decode("".join(got[k] for k in range(n)))))
            except (ValueError, zlib.error):
                return
            self._deliver(obj)

    # sending (in order, off the UI thread, retrying when rate limited)
    def _send_raw(self, obj):
        self.seq += 1
        for piece in _encode(obj, self.seq):
            self.outbox.put(piece)

    def _sender(self):
        url = f"{SERVER}/{self.out_topic}"
        while True:
            piece = self.outbox.get()
            if piece is None:
                return
            for attempt in range(6):
                try:
                    _post(url, piece.encode())
                    break
                except Exception:  # noqa: BLE001 - 429 rate limit or a blip: back off and retry
                    time.sleep(min(30, 2 + attempt * 4))

    def start_heartbeat(self):
        if self._hb_started:
            return
        self._hb_started = True

        def beat():
            time.sleep(3)
            while not self.closed:
                self.send({"t": "ping", "ts": time.time()})
                time.sleep(HEARTBEAT)
        threading.Thread(target=beat, daemon=True).start()

    def _close_raw(self):
        def stop():
            time.sleep(1.5)  # let the "bye" go out
            self.outbox.put(None)
        threading.Thread(target=stop, daemon=True).start()


# ---------------------------------------------------------------------------- rooms
class NtfyRoom:
    """Host side: open a room and wait for the friend's join request."""

    def __init__(self, code, name, style, public, status_cb):
        self.code, self.name, self.style, self.public = code, name, style, public
        self.status = status_cb

    def run(self, stop):
        conn = NtfyConn(self.code, "host")
        if not conn.ready.wait(15):
            conn.close()
            raise ConnectionError("HTTPS room server didn't answer")
        info = {"name": self.name, "style": self.style, "code": self.code, "v": PROTO, "ts": time.time(),
                "via": "https"}
        _post(f"{SERVER}/{topic(self.code, 'open')}", _encode(info, 0)[0].encode())
        if self.public:
            _post(f"{SERVER}/{PREFIX}lobby", _encode(info, 0)[0].encode())
        self.status("Room open! Send your friend the code")
        last = time.time()
        while not stop():
            for msg in conn.poll():
                if msg.get("t") == "join":
                    if msg.get("v") != PROTO:
                        conn.send({"t": "refused", "why": "version"})
                        raise ConnectionError("Your friend is on a different game version (both: pokebrawl update)")
                    conn.send({"t": "accepted", "name": self.name})
                    conn.start_heartbeat()
                    if self.public:  # take the room off the public list
                        info["closed"] = True
                        _post(f"{SERVER}/{PREFIX}lobby", _encode(info, 0)[0].encode())
                    return conn
            if self.public and time.time() - last > 240:
                info["ts"] = time.time()
                _post(f"{SERVER}/{PREFIX}lobby", _encode(info, 0)[0].encode())
                last = time.time()
            time.sleep(0.3)
        conn.close()
        return None


def join(code, name, timeout=30):
    code = code.strip().upper()
    found = [m for m in poll(topic(code, "open")) if _decode_info(m.get("message", ""))]
    if not found:
        return None
    conn = NtfyConn(code, "join")
    if not conn.ready.wait(15):
        conn.close()
        raise ConnectionError("HTTPS room server didn't answer")
    conn.send({"t": "join", "name": name, "v": PROTO})
    t0 = time.time()
    while time.time() - t0 < timeout:
        for msg in conn.poll():
            if msg.get("t") == "refused":
                conn.close()
                raise ConnectionError("Different game versions - both of you run: pokebrawl update")
            if msg.get("t") == "accepted":
                conn.start_heartbeat()
                return conn
        time.sleep(0.2)
    conn.close()
    raise ConnectionError("The host didn't answer - is their game still open on the code screen?")


def list_rooms():
    out = {}
    for m in poll(f"{PREFIX}lobby", since="10m"):
        info = _decode_info(m.get("message", ""))
        if info and info.get("closed"):
            out.pop(info.get("code"), None)
        elif info and info.get("v") == PROTO and time.time() - info.get("ts", 0) < 600:
            info["broker"] = "https"
            out[info["code"]] = info
    return list(out.values())
