"""Turn-based 6v6 singles engine (Showdown-style, simplified: no abilities).

Usage:
    b = TurnBattle(dex, [team_a, team_b], seed)
    while not b.over:
        for side, req in b.requests().items():
            b.choose(side, some_choice_for(req))
        log = b.run()    # list of {"t": text, "a": animation hint}

Choices: {"type": "move", "slot": i, "mega": bool, "tera": bool, "gmax": bool} or {"type": "switch", "index": j}
"""
import random

from . import abilities as AB
from .battlecore import AILMENT_TO_STATUS, STATUS_NAMES, Mon, acc_mult, damage, move_type_and_power, type_eff
from .types import effectiveness

WEATHER_MOVES = {"rain-dance": "rain", "sunny-day": "sun", "sandstorm": "sand", "snowscape": "snow",
                 "hail": "snow", "chilly-reception": "snow"}
WEATHER_TEXT = {"rain": "It started to rain!", "sun": "The sunlight turned harsh!", "sand": "A sandstorm kicked up!",
                "snow": "It started to snow!"}
PRIMAL_WEATHER = {"kyogre-primal": "rain", "groudon-primal": "sun"}
PROTECTS = {"protect", "detect", "kings-shield", "spiky-shield", "baneful-bunker", "obstruct", "silk-trap"}
PIVOTS = {"u-turn", "volt-switch", "flip-turn", "parting-shot", "teleport", "baton-pass", "chilly-reception"}
BOOM = {"explosion", "self-destruct", "misty-explosion", "memento", "healing-wish"}
STAT_TEXT = {"atk": "Attack", "def": "Defense", "spa": "Sp. Atk", "spd": "Sp. Def", "spe": "Speed",
             "acc": "accuracy", "eva": "evasiveness"}


class Side:
    def __init__(self, dex, members, index, rng):
        self.index = index
        self.mons = [Mon(dex, m, uid=i, team=index) for i, m in enumerate(members)]
        self.active = None
        self.rocks = False
        self.spikes = 0
        self.tspikes = 0
        self.reflect = self.light_screen = self.veil = self.tailwind = 0
        self.mega_used = False
        self.tera_used = False
        self.gmax_used = False
        self.gmax_turns = 0     # turns of Gigantamax left for the active Pokemon
        self.wish = None  # (turns_left, amount)
        self.heal_next = False
        self.pass_stages = None

    @property
    def mon(self):
        return self.mons[self.active] if self.active is not None else None

    def bench(self):
        return [i for i, m in enumerate(self.mons) if not m.fainted and i != self.active]

    def alive(self):
        return [m for m in self.mons if not m.fainted]


BALLS = {"poke-ball": ("Poke Ball", 1.0), "great-ball": ("Great Ball", 1.5), "ultra-ball": ("Ultra Ball", 2.0),
         "master-ball": ("Master Ball", 999.0)}
# bag items usable in battle: (name, heal HP (-1 = full), cures status, revives)
MEDICINE = {"potion": ("Potion", 20, False, False), "super-potion": ("Super Potion", 60, False, False),
            "hyper-potion": ("Hyper Potion", 120, False, False), "max-potion": ("Max Potion", -1, False, False),
            "full-restore": ("Full Restore", -1, True, False), "full-heal": ("Full Heal", 0, True, False),
            "revive": ("Revive", 0.5, False, True), "max-revive": ("Max Revive", 1.0, False, True)}


class TurnBattle:
    def __init__(self, dex, teams, seed=None, names=None, wild=False, bag=False, gimmicks=True, rift=None,
                 multi_mega=False):
        """rift: a battle inside a Mega Rift - {"anomaly", "turns", "boost", "catch"} (Adventure).
        multi_mega: every Pokemon holding its stone may Mega Evolve, not just one per side."""
        self.dex = dex
        self.wild = wild          # Adventure: a wild Pokemon (catchable, you can run)
        self.bag = bag            # Adventure: side 0 may use items
        self.gimmicks = gimmicks  # Mega / Tera / Gigantamax allowed
        self.caught = None        # index of the caught foe
        self.ran = False
        self.run_tries = 0
        self.names = list(names or ["Player 1", "Player 2"])
        self.rng = random.Random(seed)
        self.sides = [Side(dex, t, i, self.rng) for i, t in enumerate(teams)]
        self.turn = 0
        self.weather = None
        self.weather_turns = 0
        self.trick_room = 0
        self.log = []
        self.over = False
        self.winner = None
        self.choices = {}
        self.pending = {0: "lead", 1: "lead"}
        self.queue = []
        self.stage = "preview"
        self.vol = [self._fresh_vol(), self._fresh_vol()]
        self.choice_log = []   # [side, choice] in order - with the seed this replays the whole battle
        self.multi_mega = multi_mega
        self.rift = dict(rift) if rift else None
        self.anomaly = self.rift.get("anomaly") if self.rift else None
        self.turns_left = self.rift.get("turns") if self.rift else None
        self.collapsed = False
        if self.rift:
            for s in self.sides:
                for m in s.mons:
                    m.flags["field"] = self.anomaly
            for m in self.sides[1].mons:   # overflowing with rift energy
                m.flags["stat_mult"] = self.rift.get("boost", 1.0)

    # ------------------------------------------------------------------ public API
    def requests(self):
        """{side: request} for sides that still need to choose."""
        out = {}
        for side, kind in self.pending.items():
            if side in self.choices:
                continue
            s = self.sides[side]
            if kind in ("lead", "switch"):
                out[side] = {"kind": kind, "switches": s.bench() if kind == "switch" else
                             [i for i, m in enumerate(s.mons) if not m.fainted]}
            else:
                out[side] = self._move_request(side)
        return out

    def choose(self, side, choice):
        if side not in self.pending or side in self.choices:
            return False
        req = self.requests().get(side)
        if not self._valid(req, choice):
            return False
        self.choices[side] = choice
        self.choice_log.append([side, choice])
        return True

    def ready(self):
        return bool(self.pending) and all(s in self.choices for s in self.pending)

    def run(self):
        """Resolve as far as possible with the current choices. Returns new log entries."""
        self.log = []
        if not self.ready():
            return self.log
        choices, self.choices, self.pending = self.choices, {}, {}
        if self.stage == "preview":
            for side in (0, 1):
                self._switch_in(side, choices[side]["index"], first=True)
            self._after_switch_ins([0, 1])
            if self.rift:
                self._rift_start()
            self.stage = "turn"
            self._begin_turn()
            return self.log
        if self.stage == "midturn":
            side = next(iter(choices))
            self._switch_in(side, choices[side]["index"])
            self._after_switch_ins([side])
            self.stage = "turn"
            self._continue()
            return self.log
        if self.stage == "replace":
            sides = sorted(choices)
            for side in sides:
                self._switch_in(side, choices[side]["index"])
            self._after_switch_ins(sides)
            self._next_turn_or_replace()
            return self.log
        # a normal turn
        self.turn += 1
        self.emit(f"--- Turn {self.turn} ---", ["turn", self.turn])
        actions = []
        for side in (0, 1):
            c = choices[side]
            if c["type"] == "switch":
                actions.append(("switch", side, c["index"]))
            elif c["type"] in ("ball", "run", "item"):
                actions.append((c["type"], side, c))
            else:
                slot = c["slot"]
                v = self.vol[side]
                if v["charging"] is not None:
                    slot = v["charging"]
                if c.get("mega") and self.sides[side].mon.can_mega and (self.multi_mega or
                                                                         not self.sides[side].mega_used):
                    actions.append(("mega", side, None))
                elif c.get("gmax") and self.sides[side].mon.can_gmax and not self.sides[side].gmax_used:
                    actions.append(("gmax", side, None))
                elif c.get("tera") and not self.sides[side].tera_used and not self.sides[side].mon.megaed \
                        and not self.sides[side].mon.gmaxed:
                    actions.append(("tera", side, None))
                actions.append(("move", side, slot))
        self.queue = self._order(actions)
        self._continue()
        return self.log

    def state(self, viewer=None):
        """Public battle state for UIs."""
        out = {"turn": self.turn, "weather": self.weather, "trick_room": self.trick_room, "over": self.over,
               "winner": self.winner, "sides": [], "wild": self.wild, "caught": self.caught, "ran": self.ran,
               "rift": {"anomaly": self.anomaly, "turns": self.turns_left, "collapsed": self.collapsed}
               if self.rift else None}
        for s in self.sides:
            v = self.vol[s.index]
            out["sides"].append({
                "active": s.active,
                "mons": [{"id": m.entry["id"], "name": m.name, "hp": m.hp, "maxhp": m.maxhp,
                          "level": m.member.level,
                          "frac": round(m.hp_frac(), 4), "status": m.status, "fainted": m.fainted,
                          "types": m.types, "item": m.member.item_name(self.dex) if m.item != "none" else "",
                          "ability": AB.ability_name(m.ability) if viewer in (None, s.index) else "",
                          "tera": m.tera_type if (m.terastallized or viewer in (None, s.index)) else None,
                          "terastallized": m.terastallized,
                          "moves": [mv["name"] for mv in m.moves] if viewer in (None, s.index) else []}
                         for m in s.mons],
                "stages": {k: v_ for k, v_ in s.mon.stages.items() if v_} if s.mon else {},
                "rocks": s.rocks, "spikes": s.spikes, "tspikes": s.tspikes,
                "screens": [n for n, t in (("Reflect", s.reflect), ("Light Screen", s.light_screen),
                                           ("Aurora Veil", s.veil), ("Tailwind", s.tailwind)) if t],
                "sub": v["sub"] > 0, "mega_used": s.mega_used, "tera_used": s.tera_used,
                "gmax_turns": s.gmax_turns,
            })
        return out

    # ------------------------------------------------------------------ helpers
    def emit(self, text, anim=None):
        self.log.append({"t": text, "a": anim})

    def _fresh_vol(self):
        return {"protect_chain": 0, "protected": False, "sub": 0, "taunt": 0, "seeded": False, "flinch": False,
                "recharge": False, "charging": None, "turns_out": 0, "yawn": 0, "dbond": False, "moved": False,
                "used": None}

    def _move_request(self, side):
        s = self.sides[side]
        mon, v = s.mon, self.vol[side]
        moves = []
        for i, mv in enumerate(mon.moves):
            disabled = mon.pp[i] <= 0 or (mon.choice_lock is not None and mon.choice_lock != i) \
                or (v["taunt"] > 0 and mv["cls"] == "status") \
                or (mon.item == "assault-vest" and mv["cls"] == "status") \
                or (v["charging"] is not None and v["charging"] != i)
            shown = mv["name"]
            if mon.gmaxed and mv["cls"] != "status" and mv["type"] == mon.gmax_move()[1]:
                shown = "G-Max " + mon.gmax_move()[0]
            moves.append({"slot": i, "name": shown, "type": mv["type"], "pp": mon.pp[i], "maxpp": mv["pp"],
                          "power": mv["power"], "acc": mv["acc"], "cls": mv["cls"], "disabled": disabled})
        if all(m["disabled"] for m in moves):
            moves = [{"slot": -1, "name": "Struggle", "type": "normal", "pp": 1, "maxpp": 1, "power": 50,
                      "acc": 101, "cls": "phys", "disabled": False}]
        forced = v["charging"] is not None or v["recharge"]
        lock = None  # why some moves are greyed out, shown to the player
        if v["charging"] is not None:
            lock = f"{mon.name} is charging up {mon.moves[v['charging']]['name']}!"
        elif mon.choice_lock is not None and mon.item in ("choice-band", "choice-specs", "choice-scarf"):
            item = mon.item.replace("-", " ").title()
            lock = f"{item} locks {mon.name} into {mon.moves[mon.choice_lock]['name']} - switch out to pick another move"
        elif v["taunt"] > 0:
            lock = f"{mon.name} is taunted - no status moves"
        g = self.gimmicks is True                       # everything (PvP / practice)
        mg = g or self.gimmicks == "mega"               # Adventure: Mega Evolution only (with a Key Stone)
        return {"kind": "move", "moves": moves,
                "can_mega": mg and mon.can_mega and (self.multi_mega or not s.mega_used),
                "can_gmax": g and mon.can_gmax and not s.gmax_used and not mon.can_mega,
                "gmax_move": mon.gmax_move()[0] if mon.gmax_form else None,
                "can_tera": g and not s.tera_used and not mon.megaed and not mon.can_mega and not mon.gmaxed,
                "wild": self.wild and side == 0, "bag": self.bag and side == 0,
                "tera_type": mon.tera_type,
                "switches": [] if forced else s.bench(), "forced": forced, "lock": lock}

    def _valid(self, req, c):
        if not req or not isinstance(c, dict):
            return False
        if c.get("type") == "switch":
            return c.get("index") in req["switches"]
        if c.get("type") == "move" and req["kind"] == "move":
            return any(m["slot"] == c.get("slot") and not m["disabled"] for m in req["moves"])
        if req["kind"] != "move":
            return False
        if c.get("type") in ("ball", "run"):
            return req.get("wild") and (c["type"] == "run" or c.get("ball") in BALLS)
        if c.get("type") == "item":
            mons = self.sides[0].mons
            i = c.get("index")
            if not req.get("bag") or c.get("item") not in MEDICINE or not isinstance(i, int) or \
                    not 0 <= i < len(mons):
                return False
            revive = MEDICINE[c["item"]][3]
            return mons[i].fainted == revive
        return False

    def _speed(self, side):
        mon = self.sides[side].mon
        sp = mon.stat("spe", weather=self.weather)
        if self.sides[side].tailwind:
            sp *= 2
        return sp

    def _order(self, actions):
        def key(a):
            kind, side, arg = a
            if kind in ("ball", "run", "item"):
                pri = 8
            elif kind == "switch":
                pri = 7
            elif kind in ("mega", "tera", "gmax"):
                pri = 6
            else:
                mv = self._move_obj(side, arg)
                pri = mv["pri"] + AB.priority(self.sides[side].mon, mv)
            sp = self._speed(side)
            if self.trick_room and kind == "move":
                sp = -sp
            return (-pri, -sp, self.rng.random())
        return sorted(actions, key=key)

    def _move_obj(self, side, slot):
        if slot == -1:
            return self.dex.move("struggle")
        return self.sides[side].mon.moves[slot]

    def _continue(self):
        while self.queue:
            kind, side, arg = self.queue.pop(0)
            s = self.sides[side]
            if self.over:
                return
            if kind in ("ball", "run", "item"):
                {"ball": self._throw_ball, "run": self._run_away, "item": self._use_item}[kind](side, arg)
                if self.over:
                    return
            elif kind == "switch":
                self._switch_out(side)
                self._switch_in(side, arg)
                self._after_switch_ins([side])
            elif kind in ("mega", "tera", "gmax"):
                if s.mon and not s.mon.fainted:
                    {"mega": self._mega, "tera": self._tera, "gmax": self._gmax}[kind](side)
                # re-sort: megas can change speed
                self.queue = self._order(self.queue)
            elif kind == "move":
                if s.mon is None or s.mon.fainted:
                    continue
                self._use_move(side, arg)
            if self._check_over():
                return
            if self.pending:  # a pivot needs a mid-turn switch decision
                self.stage = "midturn"
                return
        self._end_of_turn()
        self._next_turn_or_replace()

    def _next_turn_or_replace(self):
        if self.over or self._check_over():
            return
        if self.turns_left is not None and self.stage != "replace":
            self.turns_left -= 1
            self.emit("", ["rift", max(0, self.turns_left)])
            if self.turns_left <= 0:   # the rift collapses: thrown back out, the Pokemon is gone
                self.collapsed = True
                self.over, self.winner = True, None
                self.pending, self.queue = {}, []
                self.emit("The rift is collapsing!!", ["rift", "collapse"])
                self.emit("You were thrown back into the normal world... The Mega Pokemon vanished into the void.")
                self.emit("", ["end", None])
                return
            if self.turns_left in (3, 1):
                self.emit(f"The rift is getting unstable! {self.turns_left} turn{'s' if self.turns_left > 1 else ''} "
                          f"until it collapses!", ["rift", self.turns_left])
        need = [side for side in (0, 1) if self.sides[side].mon.fainted and self.sides[side].bench()]
        if need:
            self.stage = "replace"
            for side in need:
                self.pending[side] = "switch"
            return
        self._begin_turn()

    def _begin_turn(self):
        self.stage = "turn"
        for side in (0, 1):
            v = self.vol[side]
            v["protected"] = False
            v["moved"] = False
            v["flinch"] = False
            self.pending[side] = "move"

    # ------------------------------------------------------------------ Adventure: balls, running, items
    def _throw_ball(self, side, c):
        name, mult = BALLS[c["ball"]]
        foe = self.sides[1 - side].mon
        self.emit(f"You threw a {name}!", ["ball", 1 - side, c["ball"]])
        rate = foe.base_entry.get("catch", 45)
        if self.rift:   # a raging rift Mega fights the ball
            rate *= self.rift.get("catch", 1.0)
        st = 2.5 if foe.status in ("slp", "frz") else 1.5 if foe.status else 1.0
        a = (3 * foe.maxhp - 2 * foe.hp) * rate * mult / (3 * foe.maxhp) * st
        if a >= 255:
            shakes, caught = 3, True
        else:
            b = 65536 / (255 / max(1.0, a)) ** 0.1875
            shakes = 0
            while shakes < 4 and self.rng.random() * 65536 < b:
                shakes += 1
            caught = shakes >= 4
            shakes = min(3, shakes)
        self.emit("", ["shake", 1 - side, shakes, caught])
        if caught:
            self.caught = self.sides[1 - side].active
            self.over, self.winner = True, side
            self.pending, self.queue = {}, []
            self.emit(f"Gotcha! {foe.name} was caught!", ["caught", 1 - side])
        else:
            self.emit(["Oh no! The Pokemon broke free!", "Aww! It appeared to be caught!",
                       "Aargh! Almost had it!", "Shoot! It was so close, too!"][shakes], ["breakfree", 1 - side])

    def _run_away(self, side, c):
        me, foe = self.sides[side].mon, self.sides[1 - side].mon
        self.run_tries += 1
        a, b = me.stat("spe"), max(1, foe.stat("spe"))
        if a >= b or self.rng.random() * 256 < (a * 128 / b + 30 * self.run_tries) % 256:
            self.ran = True
            self.over, self.winner = True, None
            self.pending, self.queue = {}, []
            self.emit("Got away safely!", ["run", side])
        else:
            self.emit("You couldn't get away!")

    def _use_item(self, side, c):
        name, heal, cure, revive = MEDICINE[c["item"]]
        s = self.sides[side]
        mon = s.mons[c["index"]]
        self.emit(f"You used a {name} on {mon.name}!", ["item", side])
        if revive:
            if not mon.fainted:
                return
            mon.fainted = False
            mon.hp = max(1, int(mon.maxhp * heal))
            self.emit(f"{mon.name} was revived!")
        elif heal:
            got = mon.heal(mon.maxhp if heal < 0 else heal)
            if got:
                self.emit(f"{mon.name} recovered {got} HP!",
                          ["hp", side, round(mon.hp_frac(), 4)] if mon is s.mon else None)
        if cure and mon.status:
            mon.status, mon.toxic_n = None, 0
            self.emit(f"{mon.name} was cured!", ["status", side, None] if mon is s.mon else None)

    def _check_over(self):
        alive = [bool(s.alive()) for s in self.sides]
        if not all(alive):
            self.over = True
            self.winner = 0 if alive[0] else 1 if alive[1] else None
            self.pending = {}
            self.queue = []
            name = "Nobody" if self.winner is None else self.names[self.winner]
            self.emit(f"{name} won the battle!", ["end", self.winner])
            return True
        return False

    # ------------------------------------------------------------------ switching
    def _switch_out(self, side):
        s = self.sides[side]
        if s.mon and s.mon.gmaxed:
            self._end_gmax(side, quiet=True)
        if s.mon:
            AB.on_switch_out(s.mon)
            s.mon.type_override = None
            s.mon.flags.pop("protean_used", None)
            s.mon.flags.pop("flash_fire", None)
            s.mon.choice_lock = None
            s.mon.stages = {k: 0 for k in s.mon.stages}
            if s.mon.status == "tox":
                s.mon.toxic_n = 0
        self.vol[side] = self._fresh_vol()

    def _switch_in(self, side, index, first=False):
        s = self.sides[side]
        if not first and s.mon and not s.mon.fainted:
            self.emit(f"{s.mon.name}, come back!", ["recall", side])
            self._switch_out(side)
        elif not first:
            self.vol[side] = self._fresh_vol()
        s.active = index
        mon = s.mon
        mon.choice_lock = None
        if s.pass_stages:
            mon.stages = dict(s.pass_stages)
            s.pass_stages = None
        self.emit(f"{self.names[side]} sent out {mon.name}!",
                  ["switch", side, index, mon.entry["id"]])
        if s.heal_next:
            s.heal_next = False
            mon.hp = mon.maxhp
            mon.status = None
            self.emit(f"{mon.name} was restored by the healing wish!", ["hp", side, 1.0])

    def _after_switch_ins(self, sides):
        for side in sides:
            s = self.sides[side]
            mon = s.mon
            if mon.item == "heavy-duty-boots":
                continue
            grounded = "flying" not in mon.types and mon.item != "air-balloon"
            if s.rocks:
                dmg = mon.maxhp * effectiveness("rock", mon.types) / 8
                mon.indirect(dmg)
                self.emit(f"Pointed stones dug into {mon.name}!", ["hp", side, mon.hp_frac()])
            if s.spikes and grounded:
                mon.indirect(mon.maxhp * {1: 1 / 8, 2: 1 / 6, 3: 1 / 4}[s.spikes])
                self.emit(f"{mon.name} was hurt by the spikes!", ["hp", side, mon.hp_frac()])
            if s.tspikes and grounded:
                if "poison" in mon.types:
                    s.tspikes = 0
                    self.emit(f"{mon.name} absorbed the toxic spikes!")
                elif mon.can_status("psn", self.weather):
                    st = "tox" if s.tspikes >= 2 else "psn"
                    self._inflict(side, st)
            if mon.fainted:
                self.emit(f"{mon.name} fainted!", ["faint", side])
        for side in sorted(sides, key=lambda i: -self._speed(i)):
            if not self.sides[side].mon.fainted:
                self._entry_ability(side)
        for side in sides:
            if self.sides[side].mon.item == "air-balloon" and not self.sides[side].mon.fainted:
                self.emit(f"{self.sides[side].mon.name} floats in the air with its Air Balloon!")

    def _entry_ability(self, side, weather_only=False):
        mon = self.sides[side].mon
        foe = self.sides[1 - side].mon
        if foe is not None and foe.fainted:
            foe = None
        for kind, payload in AB.entry_effects(mon, foe):
            name = AB.ability_name(mon.ability)
            if kind == "weather":
                w, turns = payload
                if self.weather == w or (self.weather_turns > 100 and turns < 100):
                    continue
                self.emit(f"[{mon.name}'s {name}]", ["ability", side, name])
                self._set_weather(w, turns)
            elif weather_only:
                continue
            elif kind == "intimidate":
                self.emit(f"[{mon.name}'s Intimidate]", ["ability", side, name])
                self._boost(1 - side, {"atk": -1}, from_foe=True)
            elif kind == "boost":
                self.emit(f"[{mon.name}'s {name}]", ["ability", side, name])
                self._boost(side, payload)

    GMAX_TURNS = 3

    def _gmax(self, side):
        s = self.sides[side]
        old = s.mon.name
        form = s.mon.gigantamax()
        s.gmax_used = True
        s.gmax_turns = self.GMAX_TURNS
        self.emit(f"{old} Gigantamaxed! It became {form['name']}!", ["gmax", side, form["id"], s.mon.hp_frac()])

    def _end_gmax(self, side, quiet=False):
        s = self.sides[side]
        if s.mon and s.mon.gmaxed:
            s.mon.end_gmax()
            if not quiet and not s.mon.fainted:
                self.emit(f"{s.mon.name} returned to its normal size.", ["ungmax", side, s.mon.entry["id"],
                                                                           s.mon.hp_frac()])
        s.gmax_turns = 0

    def _tera(self, side):
        s = self.sides[side]
        t = s.mon.terastallize()
        s.tera_used = True
        self.emit(f"{s.mon.name} has Terastallized into the {t.title()} type!", ["tera", side, t])

    def _mega(self, side):
        s = self.sides[side]
        old = s.mon.name
        form = s.mon.mega_evolve()
        s.mega_used = True
        verb = "reverted to its primal form" if "primal" in form["key"] else "Mega Evolved"
        self.emit(f"{old} has {verb}! It became {form['name']}!", ["mega", side, form["id"]])
        if getattr(s.mon.member, "corrupted", False):   # absolute power, at a price
            from .riftdex import CORRUPT_MULT
            s.mon.flags["stat_mult"] = max(s.mon.flags.get("stat_mult", 1.0), CORRUPT_MULT)
            s.mon.flags["corrupted"] = True
            self.emit(f"The corrupted stone pulses black... {form['name']}'s power is out of control!",
                      ["stat", side, True])
        if form["key"] in PRIMAL_WEATHER:
            self._set_weather(PRIMAL_WEATHER[form["key"]], 999)
        else:
            self._entry_ability(side, weather_only=True)

    def _rift_start(self):
        from .riftdex import ANOMALIES
        name, text = ANOMALIES.get(self.anomaly, ("", ""))
        if name:
            self.emit(f"The rift warps the battle: {name}!", ["rift", self.anomaly])
            self.emit(text)
        if self.anomaly == "time":
            self.trick_room = 999
        elif self.anomaly == "storm":
            self._set_weather(self.rng.choice(["rain", "sun", "sand", "snow"]), 999)
        foe = self.sides[1].mon
        if foe and not foe.fainted:
            self.emit(f"{foe.name} is overflowing with rift energy!")
            self._boost(1, {"atk": 1, "spa": 1})
        if self.turns_left:
            self.emit(f"The rift will collapse in {self.turns_left} turns!", ["rift", self.turns_left])

    def _set_weather(self, w, turns=5):
        self.weather = w
        self.weather_turns = turns
        self.emit(WEATHER_TEXT[w], ["weather", w])

    # ------------------------------------------------------------------ moves
    def _inflict(self, side, status, source_text=""):
        mon = self.sides[side].mon
        if not mon.can_status(status, self.weather) or self.vol[side]["sub"] > 0 and source_text != "self":
            return False
        res = mon.set_status(status, self.rng)
        text = {"brn": "was burned", "par": "is paralyzed! It may be unable to move",
                "psn": "was poisoned", "tox": "was badly poisoned", "slp": "fell asleep", "frz": "was frozen solid"}
        self.emit(f"{mon.name} {text[status]}!", ["status", side, status])
        if res == "lum":
            self.emit(f"{mon.name}'s Lum Berry cured its {STATUS_NAMES[status].lower()}!", ["status", side, None])
        return True

    def _boost(self, side, changes, from_foe=False):
        mon = self.sides[side].mon
        if mon.fainted:
            return
        res = mon.apply_stages(changes, from_foe)
        blocked = mon.flags.pop("blocked_drop", None)
        if blocked:
            self.emit(f"[{mon.name}'s {blocked}] Its stats were not lowered!", ["ability", side, blocked])
        for k, d in res:
            if d == 0:
                self.emit(f"{mon.name}'s {STAT_TEXT[k]} won't go any {'higher' if changes[k] > 0 else 'lower'}!")
                continue
            word = {1: "rose", 2: "rose sharply", 3: "rose drastically"}.get(d) if d > 0 else \
                {-1: "fell", -2: "harshly fell", -3: "severely fell"}.get(d, "fell")
            self.emit(f"{mon.name}'s {STAT_TEXT[k]} {word}!", ["stat", side, d > 0])
        if mon.item == "white-herb" and any(v < 0 for v in mon.stages.values()):
            mon.stages = {k: max(0, v) for k, v in mon.stages.items()}
            mon.lose_item()
            self.emit(f"{mon.name} returned its stats to normal using its White Herb!")

    def _can_act(self, side, mv):
        s, v = self.sides[side], self.vol[side]
        mon = s.mon
        if v["recharge"]:
            v["recharge"] = False
            self.emit(f"{mon.name} must recharge!")
            return False
        if mon.status == "slp":
            mon.status_turns -= 1
            if mon.status_turns >= 0:
                self.emit(f"{mon.name} is fast asleep.", ["status", side, "slp"])
                return False
            mon.status = None
            self.emit(f"{mon.name} woke up!", ["status", side, None])
        if mon.status == "frz":
            if self.rng.random() < 0.2 or mv["key"] in ("flare-blitz", "scald", "sacred-fire", "steam-eruption"):
                mon.status = None
                self.emit(f"{mon.name} thawed out!", ["status", side, None])
            else:
                self.emit(f"{mon.name} is frozen solid!", ["status", side, "frz"])
                return False
        if v["flinch"] and not mon.gmaxed:  # Gigantamax Pokemon can't flinch
            self.emit(f"{mon.name} flinched and couldn't move!")
            return False
        if mon.status == "par" and self.rng.random() < 0.25:
            self.emit(f"{mon.name} is paralyzed! It can't move!", ["status", side, "par"])
            return False
        if v["taunt"] and mv["cls"] == "status":
            self.emit(f"{mon.name} can't use {mv['name']} after the taunt!")
            return False
        return True

    def _use_move(self, side, slot):
        s, foe_i = self.sides[side], 1 - side
        foe = self.sides[foe_i]
        user, v, fv = s.mon, self.vol[side], self.vol[foe_i]
        mv = self._move_obj(side, slot)
        v["moved"] = True
        if not self._can_act(side, mv):
            v["charging"] = None
            v["protect_chain"] = 0
            return
        if slot >= 0 and v["charging"] is None:
            user.pp[slot] = max(0, user.pp[slot] - 1)
            if user.item in ("choice-band", "choice-specs", "choice-scarf"):
                user.choice_lock = slot
        key = mv["key"]
        v["used"] = key
        # two-turn moves
        if "charge" in mv["flags"] and v["charging"] is None and not (
                key in ("solar-beam", "solar-blade") and self.weather == "sun"):
            v["charging"] = slot
            self.emit(f"{user.name} is charging up {mv['name']}!", ["charge", side, mv["type"]])
            return
        v["charging"] = None
        mtype = move_type_and_power(user, mv, self.weather)[0]
        shown = mv["name"]
        if user.gmaxed and mv["cls"] != "status" and mtype == user.gmax_move()[1]:
            shown = "G-Max " + user.gmax_move()[0]
        self.emit(f"{user.name} used {shown}!", ["move", side, shown, mtype, mv["cls"]])
        if AB.protean(user, mtype):
            self.emit(f"[{user.name}'s {AB.ability_name(user.ability)}] It became the {mtype.title()} type!",
                      ["ability", side, AB.ability_name(user.ability)])
        if key not in PROTECTS:
            v["protect_chain"] = 0
        target = foe.mon
        hits_foe = mv["target"] not in ("user", "users-field", "entire-field", "user-or-ally", "all-allies",
                                        "user-and-allies", "opponents-field")
        if hits_foe and (target is None or target.fainted):
            self.emit("But there was no target...")
            return
        if hits_foe and fv["protected"] and key not in ("feint",):
            self.emit(f"{target.name} protected itself!", ["protect", foe_i])
            if key in ("high-jump-kick", "jump-kick"):
                user.take(user.maxhp / 2, False)
                self.emit(f"{user.name} kept going and crashed!", ["hp", side, user.hp_frac()])
            return
        if key == "sucker-punch" and (fv["moved"] or not self._foe_attacking(foe_i)):
            self.emit("But it failed!")
            return
        if key in ("fake-out", "first-impression") and v["turns_out"] > 0:
            self.emit("But it failed!")
            return
        if hits_foe and mv["cls"] == "status" and user.ability == "prankster" and "dark" in target.types:
            self.emit(f"It doesn't affect {target.name}...", ["immune", foe_i])
            return
        if hits_foe:
            imm = AB.immunity(target, user, mv, mtype, type_eff(mtype, target))
            if imm and self.anomaly == "gravity" and mtype == "ground":
                imm = None   # Levitate can't hold anyone up in here
            if imm:
                self._absorb(foe_i, imm)
                return
        # accuracy
        accm = AB.accuracy(user, target, mv) if hits_foe else None
        if hits_foe and mv["acc"] <= 100 and accm is not None:
            acc = mv["acc"] * accm
            if self.anomaly == "gravity":
                acc *= 5 / 3
            if self.weather == "rain" and key in ("thunder", "hurricane"):
                acc = 101
            if self.weather == "snow" and key == "blizzard":
                acc = 101
            if acc <= 100 and self.rng.random() * 100 >= acc * acc_mult(user.stages["acc"] - target.stages["eva"]):
                self.emit(f"{target.name} avoided the attack!", ["miss", foe_i])
                if key in ("high-jump-kick", "jump-kick"):
                    user.take(user.maxhp / 2, False)
                    self.emit(f"{user.name} kept going and crashed!", ["hp", side, user.hp_frac()])
                return
        if mv["cls"] == "status":
            self._status_move(side, mv)
        else:
            self._damage_move(side, mv)
        if user.item == "life-orb" and mv["power"] > 0 and not user.fainted and v.get("_hit") \
                and user.ability != "sheer-force" and user.indirect(user.maxhp / 10):
            self.emit(f"{user.name} lost some of its HP!", ["hp", side, user.hp_frac()])
            if user.fainted:
                self.emit(f"{user.name} fainted!", ["faint", side])
        v["_hit"] = False
        # pivots
        if key in PIVOTS and not user.fainted and s.bench() and not self.over and \
                any(not m.fainted for m in foe.mons):
            if key == "baton-pass":
                s.pass_stages = dict(user.stages)
            self.pending[side] = "switch"

    def _absorb(self, side, imm):
        mon = self.sides[side].mon
        verb, eff = imm
        self.emit(f"[{mon.name}'s {verb}]", ["ability", side, verb])
        if eff[0] == "heal":
            if mon.heal(mon.maxhp * eff[1]):
                self.emit(f"{mon.name} restored HP!", ["hp", side, mon.hp_frac()])
            else:
                self.emit(f"It doesn't affect {mon.name}...", ["immune", side])
        elif eff[0] == "boost":
            self._boost(side, eff[1])
        elif eff[0] == "flash_fire":
            mon.flags["flash_fire"] = True
            self.emit(f"{mon.name}'s Fire-type moves were powered up!")
        else:
            self.emit(f"It doesn't affect {mon.name}...", ["immune", side])

    def _foe_attacking(self, foe_i):
        for kind, side, arg in self.queue:
            if side == foe_i and kind == "move":
                return self._move_obj(side, arg)["cls"] != "status"
        return False

    def _damage_move(self, side, mv):
        s, foe_i = self.sides[side], 1 - side
        user, target = s.mon, self.sides[foe_i].mon
        v, fv = self.vol[side], self.vol[foe_i]
        key = mv["key"]
        hits = self.rng.randint(*mv["hits"]) if mv["hits"][1] > 1 else 1
        if mv["hits"] == [2, 5] and self.rng.random() < 0.5:
            hits = self.rng.choice([2, 3])
        hits = AB.hit_count(user, mv, hits)
        sec = AB.secondary_mult(user, mv)
        mtype = move_type_and_power(user, mv, self.weather)[0]
        total, landed = 0, 0
        eff = 1.0
        for h in range(hits):
            if target.fainted:
                break
            screen = 1.0
            crit_stage = mv["crit"] + AB.crit_bonus(user)
            crit = self.rng.random() < (1 / 24, 1 / 8, 1 / 2, 1, 1)[min(crit_stage, 4)]
            foe_side = self.sides[foe_i]
            if not crit and (foe_side.veil or (mv["cls"] == "phys" and foe_side.reflect) or
                             (mv["cls"] == "spec" and foe_side.light_screen)):
                screen = 0.5
            dmg, eff, crit = damage(user, target, mv, self.rng, self.weather, force_crit=crit, extra=screen,
                                    moved_last=fv["moved"])
            if eff == 0:
                self.emit(f"It doesn't affect {target.name}...", ["immune", foe_i])
                return
            if fv["sub"] > 0 and "sound" not in mv["flags"]:
                fv["sub"] -= dmg
                self.emit("The substitute took damage for it!", ["sub", foe_i])
                if fv["sub"] <= 0:
                    fv["sub"] = 0
                    self.emit(f"{target.name}'s substitute faded!", ["sub", foe_i])
                landed += 1
                continue
            if AB.ab(target, user) == "disguise" and not target.flags.get("busted"):
                target.flags["busted"] = True
                self.emit(f"[{target.name}'s Disguise] Its disguise served it as a decoy!", ["ability", foe_i, "Disguise"])
                target.indirect(target.maxhp / 8)
                self.emit("", ["hp", foe_i, target.hp_frac()])
                landed += 1
                continue
            had_full = target.hp == target.maxhp
            had_sash = target.item == "focus-sash"
            dealt = target.take(dmg, from_full_ok=True, attacker=user)
            if target.flags.pop("sturdy_hit", False):
                self.emit(f"[{target.name}'s Sturdy] It endured the hit!", ["ability", foe_i, "Sturdy"])
            if had_full and had_sash and target.item == "none" and not target.fainted and dealt == target.maxhp - 1:
                self.emit(f"{target.name} hung on using its Focus Sash!")
            total += dealt
            landed += 1
            if crit:
                self.emit("A critical hit!", ["crit", foe_i])
            self.emit("", ["hit", foe_i, target.hp_frac(), eff])
            if target.item == "air-balloon" and not target.fainted:
                target.lose_item()
                self.emit(f"{target.name}'s Air Balloon popped!")
            if "contact" in mv["flags"] and target.item == "rocky-helmet" and not user.fainted:
                if user.indirect(user.maxhp / 6):
                    self.emit(f"{user.name} was hurt by the Rocky Helmet!", ["hp", side, user.hp_frac()])
            if "contact" in mv["flags"] and not user.fainted:
                reacts, aname = AB.contact_reactions(user, target, self.rng)
                for kind, val in reacts:
                    if kind == "status" and user.can_status(val, self.weather):
                        self.emit(f"[{target.name}'s {AB.ability_name(aname)}]", ["ability", foe_i, aname])
                        self._inflict(side, val, "self")
                    elif kind == "damage" and user.indirect(user.maxhp * val):
                        self.emit(f"[{target.name}'s {AB.ability_name(aname)}] {user.name} was hurt!",
                                  ["hp", side, user.hp_frac()])
            if not target.fainted:
                hb = AB.on_hit(target, mtype, user)
                if hb:
                    self._boost(foe_i, hb)
        v["_hit"] = landed > 0
        if hits > 1:
            self.emit(f"The Pokemon was hit {landed} time(s)!")
        if eff > 1:
            self.emit("It's super effective!")
        elif 0 < eff < 1:
            self.emit("It's not very effective...")
        if landed and eff > 1 and target.item == "weakness-policy" and not target.fainted:
            target.lose_item()
            self.emit(f"{target.name}'s Weakness Policy activated!")
            self._boost(foe_i, {"atk": 2, "spa": 2})
        if total and mv["drain"] > 0 and not user.fainted:
            if user.heal(total * mv["drain"] / 100):
                self.emit(f"{target.name} had its energy drained!", ["hp", side, user.hp_frac()])
        if total and mv["drain"] < 0 and not user.fainted and user.ability != "rock-head":
            if user.indirect(total * -mv["drain"] / 100):
                self.emit(f"{user.name} is damaged by recoil!", ["hp", side, user.hp_frac()])
        if key == "struggle":
            user.take(user.maxhp / 4, False)
            self.emit(f"{user.name} is damaged by recoil!", ["hp", side, user.hp_frac()])
        if key in BOOM:
            user.take(user.hp, False)
        if key == "knock-off" and total and target.item not in ("none", "mega-stone") and not target.fainted:
            self.emit(f"{user.name} knocked off {target.name}'s {target.member.item_name(self.dex)}!")
            target.lose_item()
        if key in ("rapid-spin", "mortal-spin") and not user.fainted:
            s.rocks, s.spikes, s.tspikes = False, 0, 0
        if "recharge" in mv["flags"]:
            v["recharge"] = True
        if target.fainted:
            self.emit(f"{target.name} fainted!", ["faint", foe_i])
            kb = AB.on_ko(user) if not user.fainted else None
            if kb:
                self.emit(f"[{user.name}'s {AB.ability_name(user.ability)}]", ["ability", side, user.ability])
                self._boost(side, kb)
            if fv["dbond"] and not user.fainted:
                user.take(user.hp, False)
                self.emit(f"{target.name} took its attacker down with it!")
        else:
            if not landed:
                return
            st = AILMENT_TO_STATUS.get(mv["ailment"])
            if st and mv["ail_chance"] and self.rng.random() * 100 < mv["ail_chance"] * sec and fv["sub"] == 0:
                self._inflict(foe_i, st)
            if mv["flinch"] and not fv["moved"] and self.rng.random() * 100 < mv["flinch"] * sec \
                    and AB.ab(target, user) != "inner-focus":
                fv["flinch"] = True
            if target.item == "sitrus-berry" and target.hp_frac() <= 0.5:
                target.lose_item()
                target.heal(target.maxhp / 4)
                self.emit(f"{target.name} restored HP using its Sitrus Berry!", ["hp", foe_i, target.hp_frac()])
        to_self = mv["cat"] == "damage-raise" or key in ("rapid-spin",)
        chance = mv["stat_chance"] * (1 if to_self else sec)
        if mv["stats"] and landed and (mv["stat_chance"] == 0 or self.rng.random() * 100 < chance) and \
                (to_self or sec > 0):
            if to_self:
                if not user.fainted:
                    self._boost(side, mv["stats"])
            elif not target.fainted and fv["sub"] == 0:
                self._boost(foe_i, mv["stats"], from_foe=True)
        if user.fainted:
            self.emit(f"{user.name} fainted!", ["faint", side])

    def _status_move(self, side, mv):
        s, foe_i = self.sides[side], 1 - side
        foe = self.sides[foe_i]
        user, target = s.mon, foe.mon
        v, fv = self.vol[side], self.vol[foe_i]
        key = mv["key"]
        fail = lambda: self.emit("But it failed!")  # noqa: E731
        if key in PROTECTS:
            if self.rng.random() < (1 / 3) ** v["protect_chain"]:
                v["protected"] = True
                v["protect_chain"] += 1
                self.emit(f"{user.name} protected itself!", ["protect", side])
            else:
                v["protect_chain"] = 0
                fail()
            return
        if key in WEATHER_MOVES:
            if self.weather_turns > 100:
                return fail()
            self._set_weather(WEATHER_MOVES[key])
            return
        if key == "stealth-rock":
            if foe.rocks:
                return fail()
            foe.rocks = True
            self.emit("Pointed stones float in the air around the opposing team!", ["hazard", foe_i])
            return
        if key == "spikes":
            if foe.spikes >= 3:
                return fail()
            foe.spikes += 1
            self.emit("Spikes were scattered around the opposing team!", ["hazard", foe_i])
            return
        if key == "toxic-spikes":
            if foe.tspikes >= 2:
                return fail()
            foe.tspikes += 1
            self.emit("Poison spikes were scattered around the opposing team!", ["hazard", foe_i])
            return
        if key == "defog":
            for side_ in self.sides:
                side_.rocks, side_.spikes, side_.tspikes = False, 0, 0
            foe.reflect = foe.light_screen = foe.veil = 0
            self.emit("The hazards and screens were blown away!")
            self._boost(foe_i, {"eva": -1}, from_foe=True)
            return
        if key in ("reflect", "light-screen", "aurora-veil"):
            attr = {"reflect": "reflect", "light-screen": "light_screen", "aurora-veil": "veil"}[key]
            if getattr(s, attr):
                return fail()
            setattr(s, attr, 5)
            self.emit(f"{mv['name']} made the team stronger against attacks!", ["screen", side])
            return
        if key == "tailwind":
            if s.tailwind:
                return fail()
            s.tailwind = 4
            self.emit("The tailwind blew from behind the team!", ["screen", side])
            return
        if key == "trick-room":
            self.trick_room = 0 if self.trick_room else 5
            self.emit("The dimensions were twisted!" if self.trick_room else "The twisted dimensions returned to normal!")
            return
        if key == "substitute":
            if v["sub"] > 0 or user.hp <= user.maxhp // 4:
                return fail()
            user.take(user.maxhp // 4, False)
            v["sub"] = user.maxhp // 4
            self.emit(f"{user.name} put in a substitute!", ["sub", side])
            return
        if key == "taunt":
            if fv["taunt"]:
                return fail()
            fv["taunt"] = 3
            self.emit(f"{target.name} fell for the taunt!")
            return
        if key == "leech-seed":
            if fv["seeded"] or "grass" in target.types:
                return fail()
            fv["seeded"] = True
            self.emit(f"{target.name} was seeded!")
            return
        if key == "yawn":
            if target.status or fv["yawn"]:
                return fail()
            fv["yawn"] = 2
            self.emit(f"{user.name} made {target.name} drowsy!")
            return
        if key == "destiny-bond":
            v["dbond"] = True
            self.emit(f"{user.name} is hoping to take its attacker down with it!")
            return
        if key == "wish":
            if s.wish:
                return fail()
            s.wish = (2, user.maxhp / 2)
            self.emit(f"{user.name} made a wish!")
            return
        if key in ("roar", "whirlwind"):
            bench = foe.bench()
            if not bench:
                return fail()
            self._switch_out(foe_i)
            self._switch_in(foe_i, self.rng.choice(bench))
            self._after_switch_ins([foe_i])
            self.queue = [a for a in self.queue if a[1] != foe_i]
            return
        if key == "haze":
            for side_ in self.sides:
                if side_.mon:
                    side_.mon.stages = {k: 0 for k in side_.mon.stages}
            self.emit("All stat changes were eliminated!")
            return
        if key in ("trick", "switcheroo"):
            if "mega-stone" in (user.item, target.item) or user.item == target.item:
                return fail()
            user.item, target.item = target.item, user.item
            user.choice_lock = target.choice_lock = None
            self.emit(f"{user.name} switched items with its target!")
            return
        if key == "pain-split":
            avg = (user.hp + target.hp) // 2
            user.hp, target.hp = min(user.maxhp, avg), min(target.maxhp, avg)
            self.emit("The battlers shared their pain!", ["hp", side, user.hp_frac()])
            self.emit("", ["hp", foe_i, target.hp_frac()])
            return
        if key == "belly-drum":
            if user.hp <= user.maxhp // 2:
                return fail()
            user.take(user.maxhp // 2, False)
            user.stages["atk"] = 6
            self.emit(f"{user.name} cut its own HP and maximized its Attack!", ["stat", side, True])
            return
        if key in ("memento", "healing-wish"):
            if key == "memento":
                self._boost(foe_i, {"atk": -2, "spa": -2}, from_foe=True)
            else:
                s.heal_next = True
            user.take(user.hp, False)
            self.emit(f"{user.name} fainted!", ["faint", side])
            return
        if key in ("teleport", "baton-pass", "chilly-reception", "parting-shot"):
            if key == "chilly-reception":
                self._set_weather("snow")
            if key == "parting-shot":
                self._boost(foe_i, {"atk": -1, "spa": -1}, from_foe=True)
            return
        if key == "curse" and "ghost" in user.types:
            user.take(user.maxhp // 2, False)
            self.emit(f"{user.name} cut its own HP and laid a curse!")
            return
        # generic categories from the move data
        if mv["cat"] == "heal" or mv["healing"]:
            frac = (mv["healing"] or 50) / 100
            if key in ("moonlight", "morning-sun", "synthesis"):
                frac = 2 / 3 if self.weather == "sun" else 0.25 if self.weather else 0.5
            if key == "rest":
                if user.hp == user.maxhp:
                    return fail()
                user.status = "slp"
                user.status_turns = 2
                frac = 1
                self.emit(f"{user.name} slept and became healthy!", ["status", side, "slp"])
            if not user.heal(user.maxhp * frac):
                self.emit(f"{user.name}'s HP is full!")
            else:
                self.emit(f"{user.name} restored its HP.", ["hp", side, user.hp_frac()])
            return
        st = AILMENT_TO_STATUS.get(mv["ailment"])
        if key == "toxic":
            st = "tox"
        if st:
            if "powder" in mv["flags"] and "grass" in target.types:
                return self.emit(f"It doesn't affect {target.name}...")
            if st == "par" and key == "thunder-wave" and "ground" in target.types:
                return self.emit(f"It doesn't affect {target.name}...")
            if not self._inflict(foe_i, st):
                fail()
            return
        if mv["stats"]:
            to_self = mv["target"] == "user" or mv["cat"] == "net-good-stats"
            self._boost(side if to_self else foe_i, mv["stats"], from_foe=not to_self)
            return
        fail()

    # ------------------------------------------------------------------ end of turn
    def _end_of_turn(self):
        for s in self.sides:  # Gigantamax lasts three turns
            if s.gmax_turns > 0:
                s.gmax_turns -= 1
                if s.gmax_turns == 0:
                    self._end_gmax(s.index)
        if self.weather:
            if self.weather_turns < 100:
                self.weather_turns -= 1
                if self.weather_turns <= 0:
                    self.emit({"rain": "The rain stopped.", "sun": "The harsh sunlight faded.",
                               "sand": "The sandstorm subsided.", "snow": "The snow stopped."}[self.weather],
                              ["weather", None])
                    self.weather = None
            if self.weather == "sand":
                for side in (0, 1):
                    mon = self.sides[side].mon
                    if mon and not mon.fainted and not any(t in mon.types for t in ("rock", "ground", "steel")) \
                            and mon.ability not in ("sand-force", "sand-rush", "sand-veil", "overcoat") \
                            and mon.indirect(mon.maxhp / 16):
                        self.emit(f"{mon.name} is buffeted by the sandstorm!", ["hp", side, mon.hp_frac()])
                        if mon.fainted:
                            self.emit(f"{mon.name} fainted!", ["faint", side])
        if self.trick_room:
            self.trick_room -= 1
            if not self.trick_room:
                self.emit("The twisted dimensions returned to normal!")
        for side in sorted((0, 1), key=lambda i: -self._speed(i) if self.sides[i].mon else 0):
            s, v = self.sides[side], self.vol[side]
            mon = s.mon
            if mon is None or mon.fainted:
                continue
            v["turns_out"] += 1
            if s.wish:
                t, amt = s.wish
                if t <= 1:
                    s.wish = None
                    if mon.heal(amt):
                        self.emit("The wish came true!", ["hp", side, mon.hp_frac()])
                else:
                    s.wish = (t - 1, amt)
            if mon.item == "leftovers" or (mon.item == "black-sludge" and "poison" in mon.types):
                if mon.heal(mon.maxhp / 16):
                    self.emit(f"{mon.name} restored a little HP using its {mon.member.item_name(self.dex)}!",
                              ["hp", side, mon.hp_frac()])
            elif mon.item == "black-sludge" and mon.indirect(mon.maxhp / 8):
                self.emit(f"{mon.name} is hurt by its Black Sludge!", ["hp", side, mon.hp_frac()])
            if v["seeded"] and not mon.fainted:
                foe = self.sides[1 - side].mon
                drained = mon.indirect(mon.maxhp / 8)
                self.emit(f"{mon.name}'s health is sapped by Leech Seed!", ["hp", side, mon.hp_frac()])
                if foe and not foe.fainted:
                    foe.heal(drained)
                    self.emit("", ["hp", 1 - side, foe.hp_frac()])
            if mon.status == "brn" and not mon.fainted:
                if mon.indirect(mon.maxhp / 16):
                    self.emit(f"{mon.name} was hurt by its burn!", ["hp", side, mon.hp_frac()])
            elif mon.status in ("psn", "tox") and not mon.fainted:
                if mon.ability == "poison-heal":
                    if mon.heal(mon.maxhp / 8):
                        self.emit(f"[{mon.name}'s Poison Heal]", ["hp", side, mon.hp_frac()])
                else:
                    if mon.status == "tox":
                        mon.toxic_n = min(mon.toxic_n + 1, 15)
                        frac = mon.toxic_n / 16
                    else:
                        frac = 1 / 8
                    if mon.indirect(mon.maxhp * frac):
                        self.emit(f"{mon.name} was hurt by poison!", ["hp", side, mon.hp_frac()])
            if not mon.fainted:
                for kind, val, msg in AB.end_of_turn(mon, self.weather, self.rng):
                    if kind == "boost" and v["turns_out"] > 0:
                        self.emit(f"[{mon.name}'s {AB.ability_name(mon.ability)}]", ["ability", side, mon.ability])
                        self._boost(side, val)
                    elif kind == "heal" and mon.heal(mon.maxhp * val):
                        self.emit(f"[{mon.name}'s {msg}]", ["hp", side, mon.hp_frac()])
                    elif kind == "damage" and mon.indirect(mon.maxhp * val):
                        self.emit(f"[{mon.name}'s {msg}]", ["hp", side, mon.hp_frac()])
                    elif kind == "cure":
                        mon.status = None
                        self.emit(f"[{mon.name}'s {msg}] It was cured!", ["status", side, None])
            if mon.flags.get("corrupted") and not mon.fainted:
                if mon.indirect(mon.maxhp / 8):
                    self.emit(f"{mon.name} is being eaten away by the corrupted stone!", ["hp", side, mon.hp_frac()])
                if not mon.fainted and not mon.status and self.rng.random() < 0.25:
                    st = self.rng.choice(["psn", "par", "brn"])
                    if mon.can_status(st, self.weather):
                        self.emit("The corruption lashes out!")
                        self._inflict(side, st, "self")
            if self.anomaly == "entropy" and not mon.fainted and mon.indirect(mon.maxhp / 16):
                self.emit(f"The rift is eating away at {mon.name}!", ["hp", side, mon.hp_frac()])
            if v["yawn"]:
                v["yawn"] -= 1
                if v["yawn"] == 0 and not mon.fainted:
                    self._inflict(side, "slp")
            if v["taunt"]:
                v["taunt"] -= 1
            for attr in ("reflect", "light_screen", "veil", "tailwind"):
                if getattr(s, attr):
                    setattr(s, attr, getattr(s, attr) - 1)
            if mon.fainted:
                self.emit(f"{mon.name} fainted!", ["faint", side])
            v["dbond"] = False
