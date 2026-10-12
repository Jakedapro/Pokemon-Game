"""Battle sessions: the same screens drive a local bot match or an online match (as host or client).

Real-time sessions:  step(dt) -> list of snapshots,  command(cmd)
Turn sessions:       pump() -> list of updates {"log", "state", "req"},  choose(choice)
Online, the host always runs the engine; the client only renders what it receives.
"""
import random

from .bot import RealtimeBot, TurnBot
from .net import PROTO
from .sim import TICK, Sim
from .team import Member
from .turnsim import TurnBattle


INTRO_HOLD = 2.5  # seconds of "READY..." before a real-time battle starts


def rt_opts(mega_mode_0, mega_mode_1, ai0="normal", ai1="normal"):
    return dict(mega={0: mega_mode_0, 1: mega_mode_1}, mega_limit={0: 1, 1: 1}, ai={0: ai0, 1: ai1},
                radius=30, time_ramp=100, hp_mult=14)


# ---------------------------------------------------------------------------- real-time
class RTLocal:
    online = False

    def __init__(self, dex, my_team, bot_team, difficulty, seed=None):
        self.my_team = 0
        self.names = ["You", f"Bot ({difficulty})"]
        self.sim = Sim(dex, [[{"member": m} for m in my_team], [{"member": m} for m in bot_team]], seed=seed,
                       **rt_opts("manual", "manual", "normal", difficulty))
        self.bot = RealtimeBot(1, difficulty, seed)
        self.roster = self.sim.roster()
        self.acc = 0.0
        self.error = None
        self.hold = INTRO_HOLD

    def _tick(self):
        if self.hold > 0:
            self.hold -= TICK
        self.sim.paused = self.hold > 0

    def step(self, dt):
        snaps = []
        self.acc += dt
        while self.acc >= TICK:
            self.acc -= TICK
            self._tick()
            if not self.sim.paused:
                self.bot.update(self.sim, TICK)
            self.sim.step(TICK)
            snaps.append(self.sim.snapshot())
        return snaps

    def command(self, cmd):
        self.sim.command(self.my_team, cmd)

    def close(self):
        pass


class RTHost(RTLocal):
    online = True

    def __init__(self, dex, conn, my_team, their_team, names, seed=None):
        self.conn = conn
        self.my_team = 0
        self.names = names
        self.sim = Sim(dex, [[{"member": m} for m in my_team], [{"member": m} for m in their_team]], seed=seed,
                       **rt_opts("manual", "manual"))
        self.roster = self.sim.roster()
        self.acc = 0.0
        self.error = None
        self.hold = INTRO_HOLD
        conn.send({"t": "start", "style": "realtime", "you": 1, "names": names,
                   "roster": {str(k): v for k, v in self.roster.items()}})

    def step(self, dt):
        for msg in self.conn.poll():
            if msg.get("t") == "cmd":
                self.sim.command(1, msg["c"])
        if self.conn.closed and not self.sim.over:
            self.error = "Your opponent disconnected"
        snaps = []
        self.acc += dt
        while self.acc >= TICK:
            self.acc -= TICK
            self._tick()
            self.sim.step(TICK)
            snap = self.sim.snapshot()
            snaps.append(snap)
            self.conn.send({"t": "snap", "s": snap})
        return snaps

    def close(self):
        self.conn.close()


class RTClient:
    online = True

    def __init__(self, conn, start):
        self.conn = conn
        self.my_team = start["you"]
        self.names = start["names"]
        self.roster = {int(k): v for k, v in start["roster"].items()}
        self.error = None

    def step(self, dt):
        snaps = [m["s"] for m in self.conn.poll() if m.get("t") == "snap"]
        if self.conn.closed and not snaps:
            self.error = "Lost connection to the host"
        return snaps

    def command(self, cmd):
        self.conn.send({"t": "cmd", "c": cmd})

    def close(self):
        self.conn.close()


# ---------------------------------------------------------------------------- turn-based
class TurnLocal:
    online = False

    def __init__(self, dex, my_team, bot_team, difficulty, seed=None):
        self.my_side = 0
        self.names = ["You", f"Bot ({difficulty})"]
        self.battle = TurnBattle(dex, [my_team, bot_team], seed, names=self.names)
        self.bot = TurnBot(difficulty, seed)
        self.out = []
        self.error = None
        self._advance()

    def _bots(self):
        for side, req in self.battle.requests().items():
            if side != self.my_side:
                self.battle.choose(side, self.bot.choose(self.battle, side, req))

    def _advance(self):
        log = []
        self._bots()
        while self.battle.ready():
            log += self.battle.run()
            self._bots()
        self.out.append({"log": log, "state": self.battle.state(self.my_side),
                         "req": self.battle.requests().get(self.my_side)})

    def choose(self, choice):
        if self.battle.choose(self.my_side, choice):
            self._advance()
            return True
        return False

    def pump(self):
        out, self.out = self.out, []
        return out

    def close(self):
        pass


class TurnHost:
    online = True

    def __init__(self, dex, conn, my_team, their_team, names, seed=None):
        self.conn = conn
        self.my_side = 0
        self.names = names
        self.battle = TurnBattle(dex, [my_team, their_team], seed, names=names)
        self.out = []
        self.error = None
        conn.send({"t": "start", "style": "turn", "you": 1, "names": names})
        self._broadcast([])

    def _broadcast(self, log):
        reqs = self.battle.requests()
        self.out.append({"log": log, "state": self.battle.state(0), "req": reqs.get(0)})
        self.conn.send({"t": "turn", "u": {"log": log, "state": self.battle.state(1), "req": reqs.get(1)}})

    def _advance(self):
        if self.battle.ready():
            log = []
            while self.battle.ready():
                log += self.battle.run()
            self._broadcast(log)

    def choose(self, choice):
        if self.battle.choose(0, choice):
            self.conn.send({"t": "wait"})
            self._advance()
            return True
        return False

    def pump(self):
        for msg in self.conn.poll():
            if msg.get("t") == "choose":
                if not self.battle.choose(1, msg["c"]):
                    self.conn.send({"t": "turn", "u": {"log": [], "state": self.battle.state(1),
                                                       "req": self.battle.requests().get(1)}})
                self._advance()
        if self.conn.closed and not self.battle.over:
            self.error = "Your opponent disconnected"
        out, self.out = self.out, []
        return out

    def close(self):
        self.conn.close()


class TurnClient:
    online = True

    def __init__(self, conn, start):
        self.conn = conn
        self.my_side = start["you"]
        self.names = start["names"]
        self.error = None
        self.pending = []

    def choose(self, choice):
        self.conn.send({"t": "choose", "c": choice})
        return True

    def pump(self):
        out = [m["u"] for m in self.conn.poll() if m.get("t") == "turn"]
        if self.conn.closed and not out:
            self.error = "Lost connection to the host"
        return out

    def close(self):
        self.conn.close()


# ---------------------------------------------------------------------------- lobby handshake
class Lobby:
    """Runs the hello/start handshake once a connection exists. Call poll() each frame."""

    def __init__(self, dex, conn, role, style, my_team, my_name):
        self.dex = dex
        self.conn = conn
        self.role = role
        self.style = style
        self.my_team = my_team
        self.my_name = my_name
        self.session = None
        self.error = None
        conn.send({"t": "hello", "v": PROTO, "name": my_name, "team": [m.to_dict() for m in my_team],
                   "style": style})

    def poll(self):
        if self.session or self.error:
            return self.session
        msgs = self.conn.poll()
        for i, msg in enumerate(msgs):
            if self.session:
                self.conn.unread(msgs[i:])
                break
            t = msg.get("t")
            if t == "hello" and self.role == "host":
                if msg.get("v") != PROTO:
                    self.error = "Your friend is on a different game version (update both: pokebrawl update)"
                    return None
                their = [Member.from_dict(d) for d in msg["team"]][:6]
                names = [self.my_name, msg.get("name", "Friend")]
                seed = random.randrange(1 << 30)
                if self.style == "realtime":
                    self.session = RTHost(self.dex, self.conn, self.my_team, their, names, seed)
                else:
                    self.session = TurnHost(self.dex, self.conn, self.my_team, their, names, seed)
            elif t == "start" and self.role == "join":
                if msg["style"] == "realtime":
                    self.session = RTClient(self.conn, msg)
                else:
                    self.session = TurnClient(self.conn, msg)
                self.style = msg["style"]
        if self.conn.closed and not self.session:
            self.error = self.conn.error or "Connection closed"
        return self.session
