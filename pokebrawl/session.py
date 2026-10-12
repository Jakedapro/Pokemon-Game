"""Battle sessions: the same screens drive a local bot match or an online match (as host or client).

Real-time sessions:  step(dt) -> list of snapshots,  command(cmd)
Turn sessions:       pump() -> list of updates {"log", "state", "req"},  choose(choice)
Online, the host always runs the engine; the client only renders what it receives.
Every session can produce a replay (seed + teams + inputs) once the battle is over.
"""
import random
import time

from .bot import RealtimeBot, TurnBot
from .net import PROTO
from .sim import TICK, Sim
from .team import Member
from .turnsim import TurnBattle

INTRO_HOLD = 2.5   # seconds of "READY..." before a real-time battle starts
NET_EVERY = 2      # online: send one snapshot every N ticks (15 per second)
EMOTES = ["GG", "LOL", "NICE!", "EZ", "OOPS", "?!"]


def rt_opts(mega_mode_0, mega_mode_1, ai0="normal", ai1="normal"):
    return dict(mega={0: mega_mode_0, 1: mega_mode_1}, mega_limit={0: 1, 1: 1}, tera_limit={0: 1, 1: 1},
                ai={0: ai0, 1: ai1}, radius=30, time_ramp=100, hp_mult=14)


class _Online:
    """Emotes, rematches and the replay hand-off for online sessions."""
    online = True

    def _online_init(self, conn):
        self.conn = conn
        self.emotes = []          # [(team/side, text, time)]
        self.rematch_me = False
        self.rematch_them = False
        self.next_session = None
        self.replay_data = None

    @property
    def ping_ms(self):
        return None if self.conn.rtt is None else int(self.conn.rtt * 1000)

    def emote(self, text):
        self.conn.send({"t": "emote", "e": text})
        self.emotes.append((self.me_index, text, time.time()))

    def request_rematch(self):
        self.rematch_me = True
        self.conn.send({"t": "rematch"})

    def _control(self, msg):
        """Handle a non-game message. Returns True if consumed."""
        t = msg.get("t")
        if t == "emote":
            self.emotes.append((1 - self.me_index, str(msg.get("e", ""))[:12], time.time()))
        elif t == "rematch":
            self.rematch_them = True
        elif t == "replay":
            self.replay_data = msg.get("r")
        else:
            return False
        return True

    def close(self):
        if self.next_session is None:
            self.conn.close()


# ---------------------------------------------------------------------------- real-time
class RTLocal:
    online = False

    def __init__(self, dex, my_team, bot_team, difficulty, seed=None):
        self.dex = dex
        self.my_team = self.me_index = 0
        self.names = ["You", f"Bot ({difficulty})"]
        self.teams = [list(my_team), list(bot_team)]
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.opts = rt_opts("manual", "manual", "normal", difficulty)
        self.sim = Sim(dex, [[{"member": m} for m in t] for t in self.teams], seed=self.seed, **self.opts)
        self.bot = RealtimeBot(1, difficulty, self.seed)
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

    def replay(self):
        return {"style": "realtime", "v": PROTO, "names": self.names, "seed": self.seed, "opts": self.opts,
                "teams": [[m.to_dict() for m in t] for t in self.teams], "log": self.sim.cmd_log,
                "winner": self.sim.winner, "date": time.time()}

    def close(self):
        pass


class RTHost(_Online, RTLocal):
    def __init__(self, dex, conn, my_team, their_team, names, seed=None):
        self._online_init(conn)
        self.dex = dex
        self.my_team = self.me_index = 0
        self.names = names
        self.teams = [list(my_team), list(their_team)]
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.opts = rt_opts("manual", "manual")
        self.sim = Sim(dex, [[{"member": m} for m in t] for t in self.teams], seed=self.seed, **self.opts)
        self.roster = self.sim.roster()
        self.acc = 0.0
        self.error = None
        self.hold = INTRO_HOLD
        self.ticks = 0
        self.pending_events = []
        self.sent_replay = False
        conn.send({"t": "start", "style": "realtime", "you": 1, "names": names,
                   "roster": {str(k): v for k, v in self.roster.items()}})

    def step(self, dt):
        for msg in self.conn.poll():
            if self._control(msg):
                continue
            if msg.get("t") == "cmd":
                self.sim.command(1, msg["c"])
        if self.conn.closed and not self.sim.over:
            self.error = self.conn.error or "Your opponent disconnected"
        snaps = []
        self.acc += dt
        while self.acc >= TICK:
            self.acc -= TICK
            self._tick()
            self.sim.step(TICK)
            snap = self.sim.snapshot()
            snaps.append(snap)
            self.pending_events += snap["e"]
            self.ticks += 1
            if self.ticks % NET_EVERY == 0 or snap["over"]:
                self.conn.send({"t": "snap", "s": dict(snap, e=self.pending_events)})
                self.pending_events = []
        if self.sim.over and not self.sent_replay:
            self.sent_replay = True
            self.conn.send({"t": "replay", "r": self.replay()})
        if self.rematch_me and self.rematch_them and self.next_session is None:
            self.next_session = RTHost(self.dex, self.conn, self.teams[0], self.teams[1], self.names)
        return snaps


class RTClient(_Online):
    def __init__(self, conn, start):
        self._online_init(conn)
        self.my_team = self.me_index = start["you"]
        self.names = start["names"]
        self.roster = {int(k): v for k, v in start["roster"].items()}
        self.error = None
        self.smooth = True

    def step(self, dt):
        snaps = []
        msgs = self.conn.poll()
        for i, m in enumerate(msgs):
            if self._control(m):
                continue
            t = m.get("t")
            if t == "snap":
                snaps.append(m["s"])
            elif t == "start" and self.next_session is None:
                self.next_session = make_client(self.conn, m)
                self.conn.unread(msgs[i + 1:])
                break
        if self.conn.closed and not snaps:
            self.error = self.conn.error or "Lost connection to the host"
        return snaps

    def command(self, cmd):
        self.conn.send({"t": "cmd", "c": cmd})

    def replay(self):
        return self.replay_data


# ---------------------------------------------------------------------------- turn-based
class TurnLocal:
    online = False

    def __init__(self, dex, my_team, bot_team, difficulty, seed=None):
        self.dex = dex
        self.my_side = self.me_index = 0
        self.names = ["You", f"Bot ({difficulty})"]
        self.teams = [list(my_team), list(bot_team)]
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.battle = TurnBattle(dex, self.teams, self.seed, names=self.names)
        self.bot = TurnBot(difficulty, self.seed)
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

    def replay(self):
        return {"style": "turn", "v": PROTO, "names": self.names, "seed": self.seed,
                "teams": [[m.to_dict() for m in t] for t in self.teams], "log": self.battle.choice_log,
                "winner": self.battle.winner, "date": time.time()}

    def close(self):
        pass


class TurnHost(_Online, TurnLocal):
    def __init__(self, dex, conn, my_team, their_team, names, seed=None):
        self._online_init(conn)
        self.dex = dex
        self.my_side = self.me_index = 0
        self.names = names
        self.teams = [list(my_team), list(their_team)]
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.battle = TurnBattle(dex, self.teams, self.seed, names=names)
        self.out = []
        self.error = None
        self.sent_replay = False
        conn.send({"t": "start", "style": "turn", "you": 1, "names": names})
        self._broadcast([])

    def _broadcast(self, log):
        reqs = self.battle.requests()
        self.out.append({"log": log, "state": self.battle.state(0), "req": reqs.get(0)})
        self.conn.send({"t": "turn", "u": {"log": log, "state": self.battle.state(1), "req": reqs.get(1)}})
        if self.battle.over and not self.sent_replay:
            self.sent_replay = True
            self.conn.send({"t": "replay", "r": self.replay()})

    def _advance(self):
        if self.battle.ready():
            log = []
            while self.battle.ready():
                log += self.battle.run()
            self._broadcast(log)

    def choose(self, choice):
        if self.battle.choose(0, choice):
            self._advance()
            return True
        return False

    def pump(self):
        for msg in self.conn.poll():
            if self._control(msg):
                continue
            if msg.get("t") == "choose":
                if not self.battle.choose(1, msg["c"]):
                    self.conn.send({"t": "turn", "u": {"log": [], "state": self.battle.state(1),
                                                       "req": self.battle.requests().get(1)}})
                self._advance()
        if self.conn.closed and not self.battle.over:
            self.error = self.conn.error or "Your opponent disconnected"
        if self.rematch_me and self.rematch_them and self.next_session is None:
            self.next_session = TurnHost(self.dex, self.conn, self.teams[0], self.teams[1], self.names)
        out, self.out = self.out, []
        return out


class TurnClient(_Online):
    def __init__(self, conn, start):
        self._online_init(conn)
        self.my_side = self.me_index = start["you"]
        self.names = start["names"]
        self.error = None

    def choose(self, choice):
        self.conn.send({"t": "choose", "c": choice})
        return True

    def pump(self):
        out = []
        msgs = self.conn.poll()
        for i, m in enumerate(msgs):
            if self._control(m):
                continue
            t = m.get("t")
            if t == "turn":
                out.append(m["u"])
            elif t == "start" and self.next_session is None:
                self.next_session = make_client(self.conn, m)
                self.conn.unread(msgs[i + 1:])
                break
        if self.conn.closed and not out:
            self.error = self.conn.error or "Lost connection to the host"
        return out

    def replay(self):
        return self.replay_data


def make_client(conn, start):
    return RTClient(conn, start) if start["style"] == "realtime" else TurnClient(conn, start)


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
                    self.error = "Your friend is on a different game version (both run: pokebrawl update)"
                    return None
                their = [Member.from_dict(d) for d in msg["team"]][:6]
                names = [self.my_name, msg.get("name", "Friend")]
                seed = random.randrange(1 << 30)
                if self.style == "realtime":
                    self.session = RTHost(self.dex, self.conn, self.my_team, their, names, seed)
                else:
                    self.session = TurnHost(self.dex, self.conn, self.my_team, their, names, seed)
            elif t == "start" and self.role == "join":
                self.session = make_client(self.conn, msg)
                self.style = msg["style"]
        if self.conn.closed and not self.session:
            self.error = self.conn.error or "Connection closed"
        return self.session
