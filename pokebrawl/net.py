"""Networking: JSON-lines over TCP, direct host/join, and a tiny relay server for playing over the internet
without port forwarding (run `pokebrawl relay` on any server both players can reach)."""
import json
import queue
import socket
import threading

PROTO = 1
DEFAULT_PORT = 7777
RELAY_PORT = 7778


class Conn:
    """A message connection. Incoming messages are queued; `poll()` drains them."""

    def __init__(self, sock, buffered=b""):
        self.sock = sock
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.inbox = queue.Queue()
        self.closed = False
        self.error = None
        self._lock = threading.Lock()
        self._buf = buffered
        self._unread = []
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        buf = self._buf
        try:
            while True:
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line.strip():
                        self.inbox.put(json.loads(line))
                data = self.sock.recv(65536)
                if not data:
                    break
                buf += data
        except (OSError, ValueError) as e:
            self.error = str(e)
        self.closed = True

    def send(self, obj):
        if self.closed:
            return
        data = (json.dumps(obj, separators=(",", ":")) + "\n").encode()
        try:
            with self._lock:
                self.sock.sendall(data)
        except OSError as e:
            self.error = str(e)
            self.closed = True

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
        self.closed = True
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
    return Conn(sock, rest)


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
