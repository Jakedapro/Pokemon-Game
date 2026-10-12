"""Networking: JSON messages over TCP, direct host/join, and a tiny relay server for playing over the internet
without port forwarding (run `pokebrawl relay` on any server both players can reach).

Every connection type (direct TCP, relay, online rooms in online.py) shares BaseConn: an inbox drained with
poll(), a heartbeat that measures ping and notices dead connections, and send()/close().
"""
import json
import queue
import socket
import threading
import time

PROTO = 2
DEFAULT_PORT = 7777
RELAY_PORT = 7778
HEARTBEAT = 2.0      # seconds between pings
TIMEOUT = 20.0       # no traffic for this long = connection lost


class BaseConn:
    def __init__(self):
        self.inbox = queue.Queue()
        self._unread = []
        self._closed = False
        self.error = None
        self.rtt = None           # seconds, measured by the heartbeat
        self.last_rx = time.time()
        self.kind = "direct"
        self._hb_started = False

    # subclasses implement _send_raw(obj) and _close_raw()
    def _deliver(self, msg):
        """Called by the receive thread for every incoming message."""
        self.last_rx = time.time()
        t = msg.get("t")
        if t == "ping":
            self.send({"t": "pong", "ts": msg.get("ts")})
        elif t == "pong":
            try:
                self.rtt = max(0.0, time.time() - float(msg.get("ts")))
            except (TypeError, ValueError):
                pass
        elif t == "bye":
            self.error = self.error or "Your opponent left"
            self._closed = True
        else:
            self.inbox.put(msg)

    def start_heartbeat(self):
        if self._hb_started:
            return
        self._hb_started = True

        def beat():
            while not self.closed:
                self.send({"t": "ping", "ts": time.time()})
                time.sleep(HEARTBEAT)
        threading.Thread(target=beat, daemon=True).start()

    @property
    def closed(self):
        if not self._closed and time.time() - self.last_rx > TIMEOUT:
            self.error = self.error or "Connection timed out"
            self._closed = True
        return self._closed

    @closed.setter
    def closed(self, v):
        self._closed = v

    def send(self, obj):
        if not self._closed:
            self._send_raw(obj)

    def unread(self, msgs):
        """Put messages back so the next poll() returns them first."""
        self._unread = list(msgs) + self._unread

    def poll(self):
        out, self._unread = self._unread, []
        while True:
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                return out

    def close(self):
        if not self._closed:
            try:
                self._send_raw({"t": "bye"})
            except Exception:  # noqa: BLE001
                pass
        self._closed = True
        self._close_raw()


class Conn(BaseConn):
    """A TCP connection carrying newline-delimited JSON."""

    def __init__(self, sock, buffered=b"", kind="direct"):
        super().__init__()
        self.kind = kind
        self.sock = sock
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._lock = threading.Lock()
        self._buf = buffered
        threading.Thread(target=self._reader, daemon=True).start()
        self.start_heartbeat()

    def _reader(self):
        buf = self._buf
        try:
            while True:
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line.strip():
                        self._deliver(json.loads(line))
                data = self.sock.recv(65536)
                if not data:
                    break
                buf += data
        except (OSError, ValueError) as e:
            self.error = self.error or str(e)
        if not self._closed:
            self.error = self.error or "Connection closed"
        self._closed = True

    def _send_raw(self, obj):
        data = (json.dumps(obj, separators=(",", ":")) + "\n").encode()
        try:
            with self._lock:
                self.sock.sendall(data)
        except OSError as e:
            self.error = str(e)
            self._closed = True

    def _close_raw(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


def _read_line(sock):
    buf = b""
    while b"\n" not in buf:
        data = sock.recv(4096)
        if not data:
            raise ConnectionError("connection closed")
        buf += data
    line, rest = buf.split(b"\n", 1)
    return json.loads(line), rest


class Host:
    """Waits (in the background) for one player to connect directly or through a relay."""

    def __init__(self, port=DEFAULT_PORT, relay=None, room=None):
        self.conn = None
        self.error = None
        self.port = port
        self._srv = None
        self.status = "Waiting for your friend to join..."
        if relay:
            threading.Thread(target=self._via_relay, args=(relay, room), daemon=True).start()
        else:
            self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._srv.bind(("0.0.0.0", port))
            self._srv.listen(1)
            threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        try:
            sock, _ = self._srv.accept()
            self.conn = Conn(sock)
        except OSError as e:
            self.error = str(e)

    def _via_relay(self, relay, room):
        try:
            self.conn = relay_connect(relay, room, "host")
        except Exception as e:  # noqa: BLE001 - surfaced in the lobby UI
            self.error = str(e)

    def close(self):
        if self._srv:
            self._srv.close()


def parse_addr(addr, default_port):
    addr = addr.strip()
    if addr.count(":") == 1:
        h, p = addr.split(":")
        return h, int(p)
    return addr, default_port


def connect(addr, timeout=8):
    host, port = parse_addr(addr, DEFAULT_PORT)
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.settimeout(None)
    return Conn(sock)


def relay_connect(relay_addr, room, role, timeout=8):
    host, port = parse_addr(relay_addr, RELAY_PORT)
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.settimeout(None)
    sock.sendall((json.dumps({"relay": role, "room": room.upper(), "v": PROTO}) + "\n").encode())
    msg, rest = _read_line(sock)  # blocks until the other player arrives
    if not msg.get("paired"):
        raise ConnectionError(msg.get("error", "relay refused"))
    return Conn(sock, rest, kind="relay")


def local_ips():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    ips.discard("127.0.0.1")
    return sorted(ips) or ["127.0.0.1"]


# ---------------------------------------------------------------------------- relay server

def run_relay(port=RELAY_PORT, log=print):
    """Pairs a host and a joiner by room code and pipes bytes between them."""
    waiting = {}
    lock = threading.Lock()

    def pipe(a, b):
        try:
            while True:
                data = a.recv(65536)
                if not data:
                    break
                b.sendall(data)
        except OSError:
            pass
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def handle(sock, addr):
        try:
            msg, rest = _read_line(sock)
            room, role = str(msg.get("room", ""))[:16], msg.get("relay")
            if not room or role not in ("host", "join"):
                raise ValueError("bad hello")
            with lock:
                other = waiting.get(room)
                if other and other[1] != role:
                    del waiting[room]
                else:
                    if other:  # same role twice: replace stale entry
                        other[0].close()
                    waiting[room] = (sock, role, rest)
                    log(f"[relay] {addr[0]} waiting in room {room} as {role}")
                    return
            osock, _, orest = other
            for s in (sock, osock):
                s.sendall(b'{"paired":true}\n')
            if rest:
                osock.sendall(rest)
            if orest:
                sock.sendall(orest)
            log(f"[relay] room {room} paired")
            threading.Thread(target=pipe, args=(sock, osock), daemon=True).start()
            pipe(osock, sock)
        except (OSError, ValueError, ConnectionError) as e:
            log(f"[relay] {addr[0]}: {e}")
            sock.close()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(64)
    log(f"[relay] listening on port {port}. Players use: <this server's address>:{port} + a room code")
    while True:
        sock, addr = srv.accept()
        threading.Thread(target=handle, args=(sock, addr), daemon=True).start()
