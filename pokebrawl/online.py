"""Zero-setup online play.

Room codes: the host opens a room on a free public MQTT broker (a message server many apps share) and gets a
5-letter code. The friend types the code and they're connected - no IP addresses, no port forwarding, no
server of your own. Several brokers are tried in order, so one being down doesn't stop you.
Rooms can also be listed publicly so friends can just pick yours from the room browser.

LAN discovery: hosts on the same Wi-Fi announce themselves over UDP broadcast; the join screen lists them.
"""
import json
import os
import random
import socket
import threading
import time
import zlib
from collections import deque

from .net import DEFAULT_PORT, PROTO, BaseConn

BROKERS = [("broker.emqx.io", 1883), ("broker.hivemq.com", 1883), ("test.mosquitto.org", 1883),
           ("mqtt.eclipseprojects.io", 1883)]
PREFIX = "pokebrawl/v2"
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LAN_PORT = 7779


def brokers():
    env = os.environ.get("POKEBRAWL_BROKERS")
    if env:
        out = []
        for part in env.split(","):
            h, _, p = part.strip().partition(":")
            out.append((h, int(p or 1883)))
        return out
    return list(BROKERS)


def new_code():
    return "".join(random.choice(CODE_CHARS) for _ in range(5))


def topic(room, leaf):
    return f"{PREFIX}/room/{room.upper()}/{leaf}"


def _mqtt():
    try:
        import paho.mqtt.client as mqtt
        return mqtt
    except ImportError as e:
        raise RuntimeError("Online rooms need paho-mqtt: run `pokebrawl update`") from e


def _connect(host, port, timeout=6.0, will=None):
    """Connect to a broker; returns a running paho client or raises."""
    mqtt = _mqtt()
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"pb-{random.getrandbits(48):x}",
                    protocol=mqtt.MQTTv311)
    done = threading.Event()
    res = {}

    def on_connect(client, userdata, flags, rc, props=None):
        res["rc"] = rc
        done.set()
    c.on_connect = on_connect
    if will:
        c.will_set(*will)
    c.connect_async(host, port, keepalive=15)
    c.loop_start()
    if not done.wait(timeout) or getattr(res.get("rc"), "is_failure", res.get("rc") not in (0, None)):
        c.loop_stop()
        try:
            c.disconnect()
        except Exception:  # noqa: BLE001
            pass
        raise ConnectionError(f"{host} unreachable")
    return c


def _pack(obj):
    return zlib.compress(json.dumps(obj, separators=(",", ":")).encode())


def _unpack(payload):
    if not payload:
        return None
    try:
        return json.loads(zlib.decompress(payload))
    except (zlib.error, ValueError):
        try:
            return json.loads(payload)
        except ValueError:
            return None


class MqttConn(BaseConn):
    """A game connection through an MQTT broker room."""

    def __init__(self, client, room, role, broker):
        super().__init__()
        self.kind = "room"
        self.client = client
        self.room = room
        self.role = role
        self.broker = broker
        self.seq = 0
        self.seen = deque(maxlen=1024)
        self.seen_set = set()
        self._lock = threading.Lock()
        self.in_topic = topic(room, "to-host" if role == "host" else "to-join")
        self.out_topic = topic(room, "to-join" if role == "host" else "to-host")
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        client.subscribe(self.in_topic, qos=1)
        self.start_heartbeat()

    def _on_message(self, client, userdata, msg):
        if msg.topic != self.in_topic:
            return
        data = _unpack(msg.payload)
        if not isinstance(data, dict):
            return
        s = data.pop("_s", None)
        if s is not None:  # QoS 1 can deliver twice
            if s in self.seen_set:
                return
            if len(self.seen) == self.seen.maxlen:
                self.seen_set.discard(self.seen[0])
            self.seen.append(s)
            self.seen_set.add(s)
        self._deliver(data)

    def _on_disconnect(self, client, userdata, flags, rc, props=None):
        # paho reconnects by itself; the heartbeat timeout decides if the game is lost
        pass

    def _send_raw(self, obj):
        with self._lock:
            self.seq += 1
            payload = _pack(dict(obj, _s=self.seq))
        qos = 0 if obj.get("t") in ("snap", "ping", "pong") else 1
        try:
            self.client.publish(self.out_topic, payload, qos=qos)
        except Exception as e:  # noqa: BLE001
            self.error = str(e)

    def _close_raw(self):
        def stop():
            time.sleep(0.3)  # let the "bye" go out
            try:
                self.client.disconnect()
                self.client.loop_stop()
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=stop, daemon=True).start()


class RoomHost:
    """Opens a room and waits for a friend. Same interface as net.Host (conn / error / status / close)."""

    def __init__(self, name, style, public=False, code=None):
        self.code = (code or new_code()).upper()
        self.name, self.style, self.public = name, style, public
        self.conn = None
        self.error = None
        self.status = "Opening room..."
        self.broker = None
        self._stop = False
        self._client = None
        threading.Thread(target=self._run, daemon=True).start()

    def _info(self):
        return {"name": self.name, "style": self.style, "code": self.code, "v": PROTO, "ts": time.time()}

    def _run(self):
        errors = []
        for host, port in brokers():
            if self._stop:
                return
            self.status = f"Opening room on {host}..."
            try:
                lobby_topic = f"{PREFIX}/lobby/{self.code}"
                c = _connect(host, port, will=(lobby_topic, b"", 1, True) if self.public else None)
            except Exception as e:  # noqa: BLE001
                errors.append(str(e))
                continue
            self._client = c
            self.broker = host
            break
        else:
            self.error = "Couldn't reach any online server (" + "; ".join(errors[:2]) + ")"
            return
        c = self._client
        joined = threading.Event()
        joiner = {}

        def on_message(client, userdata, msg):
            data = _unpack(msg.payload)
            if isinstance(data, dict) and data.get("t") == "join":
                joiner.update(data)
                joined.set()
        c.on_message = on_message
        c.subscribe(topic(self.code, "to-host"), qos=1)
        c.publish(topic(self.code, "open"), _pack(self._info()), qos=1, retain=True)
        if self.public:
            c.publish(f"{PREFIX}/lobby/{self.code}", _pack(self._info()), qos=1, retain=True)
        self.status = "Room open! Send your friend the code"
        last = time.time()
        while not joined.wait(0.5):
            if self._stop:
                self._clear(c)
                c.disconnect()
                c.loop_stop()
                return
            if self.public and time.time() - last > 60:  # keep the public listing fresh
                c.publish(f"{PREFIX}/lobby/{self.code}", _pack(self._info()), qos=1, retain=True)
                last = time.time()
        if joiner.get("v") != PROTO:
            c.publish(topic(self.code, "to-join"), _pack({"t": "refused", "why": "version"}), qos=1)
            self.error = "Your friend is on a different game version (both run: pokebrawl update)"
            return
        self._clear(c)
        conn = MqttConn(c, self.code, "host", self.broker)
        conn.send({"t": "accepted", "name": self.name})
        self.conn = conn

    def _clear(self, c):
        c.publish(topic(self.code, "open"), b"", qos=1, retain=True)
        if self.public:
            c.publish(f"{PREFIX}/lobby/{self.code}", b"", qos=1, retain=True)

    def close(self):
        self._stop = True


def join_room(code, name, timeout=10.0, broker=None):
    """Find the room on the brokers and join it. Returns a MqttConn (blocking - run in a thread)."""
    code = code.strip().upper()
    tried = []
    for host, port in ([broker] if broker else brokers()):
        try:
            c = _connect(host, port)
        except Exception:  # noqa: BLE001
            tried.append(f"{host} (offline)")
            continue
        found = threading.Event()
        accepted = threading.Event()
        info = {}
        early = []  # game messages that arrive before the connection object exists

        def on_message(client, userdata, msg):
            data = _unpack(msg.payload)
            if not isinstance(data, dict):
                return
            if msg.topic.endswith("/open"):
                info.update(data)
                found.set()
            elif data.get("t") in ("accepted", "refused") and not accepted.is_set():
                info["answer"] = data
                accepted.set()
                early.append(msg)
            elif accepted.is_set():
                early.append(msg)
        c.on_message = on_message
        c.subscribe(topic(code, "open"), qos=1)
        c.subscribe(topic(code, "to-join"), qos=1)
        if not found.wait(3.0):
            tried.append(host)
            c.disconnect()
            c.loop_stop()
            continue
        c.publish(topic(code, "to-host"), _pack({"t": "join", "name": name, "v": PROTO}), qos=1)
        if not accepted.wait(timeout):
            c.disconnect()
            c.loop_stop()
            raise ConnectionError("The host didn't answer - is their game still open?")
        ans = info["answer"]
        if ans.get("t") == "refused":
            c.disconnect()
            c.loop_stop()
            raise ConnectionError("Different game versions - both of you run: pokebrawl update")
        c.unsubscribe(topic(code, "open"))
        conn = MqttConn(c, code, "join", host)  # takes over on_message from here
        for msg in list(early):
            conn._on_message(c, None, msg)
        return conn
    raise ConnectionError(f"No room {code} found. Check the code (tried {', '.join(tried) or 'no servers'})")


def list_public_rooms(wait=2.5):
    """Returns open public rooms from every reachable broker: [{name, style, code, broker}]."""
    rooms = {}
    lock = threading.Lock()

    def scan(host, port):
        try:
            c = _connect(host, port, timeout=4.0)
        except Exception:  # noqa: BLE001
            return

        def on_message(client, userdata, msg):
            data = _unpack(msg.payload)
            if isinstance(data, dict) and data.get("v") == PROTO and time.time() - data.get("ts", 0) < 300:
                data["broker"] = (host, port)
                with lock:
                    rooms.setdefault(data["code"], data)
        c.on_message = on_message
        c.subscribe(f"{PREFIX}/lobby/+", qos=1)
        time.sleep(wait)
        c.disconnect()
        c.loop_stop()
    threads = [threading.Thread(target=scan, args=b, daemon=True) for b in brokers()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(wait + 5)
    return sorted(rooms.values(), key=lambda r: -r.get("ts", 0))


# ---------------------------------------------------------------------------- LAN discovery

class LanBeacon:
    """While hosting directly, tell other PokeBrawl games on the network we're here."""

    def __init__(self, name, style, port=DEFAULT_PORT):
        self.msg = json.dumps({"pokebrawl": PROTO, "name": name, "style": style, "port": port}).encode()
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while self.running:
            for addr in ("255.255.255.255", "127.0.0.1"):
                try:
                    s.sendto(self.msg, (addr, LAN_PORT))
                except OSError:
                    pass
            time.sleep(1.0)
        s.close()

    def close(self):
        self.running = False


class LanScanner:
    """Collects hosts announced on the local network. `games` maps 'ip:port' -> info."""

    def __init__(self):
        self.games = {}
        self.running = True
        self.error = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            s.bind(("", LAN_PORT))
            s.settimeout(0.5)
        except OSError as e:
            self.error = str(e)
            return
        while self.running:
            try:
                data, addr = s.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                info = json.loads(data)
            except ValueError:
                continue
            if info.get("pokebrawl") == PROTO:
                info["seen"] = time.time()
                self.games[f"{addr[0]}:{info.get('port', DEFAULT_PORT)}"] = info
        s.close()

    def current(self):
        now = time.time()
        live = {k: v for k, v in self.games.items() if now - v["seen"] < 4}
        # a game on this same computer is heard twice (LAN + loopback): keep the LAN address
        lan_names = {(v.get("name"), v.get("port")) for k, v in live.items() if not k.startswith("127.")}
        return {k: v for k, v in live.items()
                if not (k.startswith("127.") and (v.get("name"), v.get("port")) in lan_names)}

    def close(self):
        self.running = False
