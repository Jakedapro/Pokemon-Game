"""Battle sessions: the same screen drives a local bot match or an online match (as host or client).

pump() -> list of updates {"log", "state", "req"},  choose(choice)
Online, the host always runs the engine; the client only renders what it receives.
Every session can produce a replay (seed + teams + inputs) once the battle is over.
"""
import random
import time

from .bot import TurnBot
from .net import PROTO
from .team import Member, validate
from .turnsim import TurnBattle

EMOTES = ["GG", "LOL", "NICE!", "EZ", "OOPS", "?!"]


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
    return TurnClient(conn, start)


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
                errs = validate(self.dex, their)
                if errs:
                    self.conn.send({"t": "badteam", "why": errs[0]})
                    self.error = f"Your friend's team isn't legal: {errs[0]}"
                    return None
                names = [self.my_name, msg.get("name", "Friend")]
                seed = random.randrange(1 << 30)
                self.session = TurnHost(self.dex, self.conn, self.my_team, their, names, seed)
            elif t == "badteam" and self.role == "join":
                self.error = f"The host says your team isn't legal: {msg.get('why', '')}"
                return None
            elif t == "start" and self.role == "join":
                self.session = make_client(self.conn, msg)
                self.style = msg["style"]
        if self.conn.closed and not self.session:
            self.error = self.conn.error or "Connection closed"
        return self.session
