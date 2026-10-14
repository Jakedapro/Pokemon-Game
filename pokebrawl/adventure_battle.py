"""Adventure battles: a wild Pokemon or a trainer vs your party, played on the normal 1v1 battle screen.
Keeps track of which of your Pokemon fought each foe (for experience) and writes HP / PP back to the party."""
import random

from . import adventure as A
from .bot import TurnBot
from .turnsim import BALLS, MEDICINE, TurnBattle


class AdventureSession:
    online = False
    adventure = True

    def __init__(self, game, dex, foes, kind="wild", trainer=None, seed=None):
        """kind: 'wild', 'trainer', 'gym' or 'champion'. foes: list of party-style dicts."""
        self.game = game
        self.dex = dex
        self.kind = kind
        self.trainer = trainer or {}
        self.my_side = self.me_index = 0
        self.party_idx = [i for i, m in enumerate(game["party"])]
        d = A.diff()   # the difficulty: trainers are stronger (and smarter) on HARD and INSANE
        bonus = d["wild"] if kind == "wild" else d["lv"]
        if bonus:
            foes = [dict(f, level=max(2, min(100, f["level"] + bonus)), cur_hp=None) for f in foes]
        self.foes = foes
        foe_name = (f"Wild {A.name_of(dex, foes[0])}" if kind == "wild" else self.trainer.get("name", "Trainer"))
        self.names = [game.get("name", "You"), foe_name]
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        foe_members = [A.member(m) for m in foes]
        for fm, f in zip(foe_members, foes):   # story bosses and the Elite Four can Mega Evolve too
            if f.get("mega"):
                fm.item, fm.mega = "mega-stone", f["mega"]
        rift = None
        if self.trainer.get("rift"):   # inside a Mega Rift: a countdown, an anomaly, a raging Mega
            from . import riftdex as R
            rift = {"anomaly": self.trainer.get("anomaly"), "turns": self.trainer.get("turns") or
                    R.RIFT_TURNS.get(A.OPTS.get("difficulty", "NORMAL"), 8),
                    "boost": R.RIFT_BOOST, "catch": R.RIFT_CATCH}
        self.battle = TurnBattle(dex, [[A.member(m, game, dex) for m in game["party"]], foe_members],
                                 self.seed, names=self.names, wild=kind == "wild", bag=True, gimmicks="mega",
                                 rift=rift, multi_mega=True)   # the rifts broke the one-Mega-per-battle rule
        level = self.trainer.get("ai") or {"wild": "easy", "trainer": "normal", "gym": "hard",
                                           "champion": "insane"}.get(kind, "hard")
        if kind != "wild":
            step = A.AI_STEPS.index(level) + d["ai"] if level in A.AI_STEPS else 2
            level = A.AI_STEPS[max(0, min(len(A.AI_STEPS) - 1, step))]
        self.bot = TurnBot(level, self.seed)
        self.out = []
        self.error = None
        self.teams = None
        self.participants = {}    # foe index -> set of my party indexes that fought it
        self.defeated = []        # foe indexes knocked out
        self.cur_foe = None
        self.cur_me = None
        self.finished = False
        self.awarded = set()      # foes whose experience was already handed out during the battle
        self.evolutions = []      # (party mon, new species) to show after the battle
        # leads: your first healthy Pokemon, the foe's first
        lead = next(i for i, m in enumerate(game["party"]) if not A.fainted(dex, m))
        self.battle.choose(0, {"type": "switch", "index": lead})
        self.battle.choose(1, {"type": "switch", "index": 0})
        intro = {"wild": (f"The rift tore open! A raging {A.name_of(dex, foes[0]).upper()} burst out!"
                          if self.trainer.get("rift") else f"A wild {A.name_of(dex, foes[0])} appeared!"),
                 "gym": f"Gym Leader {self.trainer.get('leader', '')} wants to battle!",
                 "champion": f"Champion {self.trainer.get('leader', '')} wants to battle!"}.get(
            kind, f"{self.names[1]} wants to battle!")
        self._advance([{"t": intro, "a": None}])

    # ------------------------------------------------------------------ the session API the battle screen uses
    def _bots(self):
        for side, req in self.battle.requests().items():
            if side != 0:
                self.battle.choose(side, self.bot.choose(self.battle, side, req))

    def _advance(self, log=None):
        log = list(log or [])
        self._bots()
        while self.battle.ready():
            entries = self.battle.run()
            self._track(entries)
            log += entries
            self._bots()
        self.out.append({"log": log, "state": self.battle.state(0), "req": self.battle.requests().get(0)})

    def _track(self, entries):
        for e in entries:
            a = e.get("a") or []
            if not a:
                continue
            if a[0] == "switch":
                if a[1] == 0:
                    self.cur_me = a[2]
                else:
                    self.cur_foe = a[2]
                if self.cur_me is not None and self.cur_foe is not None:
                    self.participants.setdefault(self.cur_foe, set()).add(self.cur_me)
            elif a[0] == "faint" and a[1] == 1 and self.cur_foe is not None:
                self.defeated.append(self.cur_foe)

    def choose(self, choice):
        t = choice.get("type")
        key = choice.get("ball") if t == "ball" else choice.get("item") if t == "item" else None
        if key and self.game["bag"].get(key, 0) <= 0:
            return False
        if t == "ball" and self.kind != "wild":
            return False
        if self.battle.choose(0, choice):
            if key:
                self.game["bag"][key] -= 1
                if self.game["bag"][key] <= 0:
                    del self.game["bag"][key]
            self._advance()
            return True
        return False

    def pump(self):
        out, self.out = self.out, []
        return out

    def replay(self):
        return None

    def close(self):
        pass

    def bag_items(self):
        """(key, name, count) for the bag menu in battle."""
        out = []
        for key, n in sorted(self.game["bag"].items(), key=lambda kv: list(A.SHOP).index(kv[0])
                             if kv[0] in A.SHOP else 99):
            if n <= 0:
                continue
            if key in BALLS and self.kind == "wild":
                out.append((key, BALLS[key][0], n, "ball"))
            elif key in MEDICINE:
                out.append((key, MEDICINE[key][0], n, "revive" if MEDICINE[key][3] else "heal"))
        return out

    # ------------------------------------------------------------------ experience during the battle
    def award(self, foe_index):
        """Hand out experience for a foe that just fainted (or was caught). Updates the party and the Pokemon
        in battle (a level-up raises its stats right away). Returns [(party index, gain, events)]."""
        if foe_index in self.awarded or foe_index is None:
            return []
        self.awarded.add(foe_index)
        dex = self.dex
        foe = self.foes[foe_index]
        fought = self.participants.get(foe_index, set())
        out = []
        trainer = self.kind != "wild"
        for i, p in enumerate(self.game["party"]):
            bm = self.battle.sides[0].mons[i]
            if bm.fainted:
                continue
            gain = A.xp_yield(dex, foe["species"], foe["level"], p["level"], trainer)
            if i not in fought:
                gain //= 2
            gain = max(1, gain)
            before = p["level"]
            p["cur_hp"] = bm.hp
            events = A.gain_xp(dex, p, gain)
            if p["level"] != before:   # grow the battling Pokemon's stats, keeping the damage it has taken
                from .team import calc_stats
                bm.member.level = p["level"]
                old_max = bm.maxhp
                bm.stats = calc_stats(bm.entry, bm.member)
                bm.maxhp = bm.stats["hp"]
                bm.hp = min(bm.maxhp, bm.hp + bm.maxhp - old_max)
                if any(ev[0] == "learn" for ev in events):   # new moves: full PP, old ones keep theirs
                    left = {mv["id"]: pp for mv, pp in zip(bm.moves, bm.pp)}
                    bm.moves = [dex.moves[m] for m in p["moves"]]
                    bm.pp = [left.get(mv["id"], mv["pp"]) for mv in bm.moves]
            for ev in events:
                if ev[0] == "evolve" and all(m is not p for m, _ in self.evolutions):
                    self.evolutions.append((p, ev[1]))
            out.append((i, gain, [e for e in events if e[0] != "evolve"]))
        return out

    # ------------------------------------------------------------------ after the battle
    def results(self):
        """Write HP/PP/status back to the party and work out experience. Returns a dict for the overworld."""
        b = self.battle
        dex = self.dex
        game = self.game
        for i, mon in enumerate(b.sides[0].mons):
            p = game["party"][i]
            p["cur_hp"] = mon.hp if mon.hp < mon.maxhp else None
            p["status"] = mon.status
            p["pp"] = list(mon.pp) if any(pp < mv["pp"] for pp, mv in zip(mon.pp, mon.moves)) else None
            if mon.megaed or mon.entry["id"] != p["species"]:
                pass  # forms revert after battle; the party keeps its species
        trainer = self.kind != "wild"
        foes_done = list(self.defeated)
        if b.caught is not None and b.caught not in foes_done:
            foes_done.append(b.caught)
        xp = {}   # party index -> experience
        for f in foes_done:
            if f in self.awarded:
                continue
            foe = self.foes[f]
            fought = self.participants.get(f, set())
            for i, p in enumerate(game["party"]):
                if A.fainted(dex, p):
                    continue
                gain = A.xp_yield(dex, foe["species"], foe["level"], p["level"], trainer)
                if i not in fought:
                    gain //= 2      # the rest of the party learns by watching (like the Exp. Share)
                xp[i] = xp.get(i, 0) + max(1, gain)
        out = {"won": b.winner == 0, "lost": b.winner == 1, "ran": b.ran, "caught": None, "xp": xp,
               "kind": self.kind, "trainer": self.trainer, "collapsed": b.collapsed}
        if b.caught is not None:
            mon = dict(self.foes[b.caught])
            cm = b.sides[1].mons[b.caught]
            mon["cur_hp"] = cm.hp if cm.hp < cm.maxhp else None
            mon["status"] = cm.status
            mon["pp"] = None
            out["caught"] = mon
        for f in self.foes:
            if f["species"] not in game["seen"]:
                game["seen"].append(f["species"])
        return out
