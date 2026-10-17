"""Practice bots for both battle styles, with difficulty levels."""
import random

from .battlecore import AILMENT_TO_STATUS, damage
from .team import random_team
from .types import effectiveness

DIFFICULTIES = ["easy", "normal", "hard", "insane"]
DIFF_INFO = {
    "easy": "Random moves, weak team",
    "normal": "Picks good moves, solid team",
    "hard": "Switches smart, sets up, uses hazards",
    "insane": "No mistakes + legendary team",
}
TEAM_RANGES = {"easy": (350, 470, False), "normal": (450, 560, False), "hard": (500, 620, False),
               "insane": (560, 720, True)}


def bot_team(dex, difficulty, rng=None, level=100):
    lo, hi, legend = TEAM_RANGES[difficulty]
    return random_team(dex, rng or random.Random(), 6, lo, hi, legend, level)


class _Avg:
    """Deterministic stand-in RNG: average damage roll, no crits."""

    def uniform(self, a, b):
        return (a + b) / 2

    def random(self):
        return 0.99


AVG = _Avg()


def est_damage(user, target, move, weather=None):
    """Expected fraction of the target's current HP this move removes (0..1+)."""
    if move["power"] <= 0:
        return 0.0
    dmg, eff, _ = damage(user, target, move, AVG, weather, force_crit=False)
    hits = sum(move["hits"]) / 2
    return dmg * hits * min(move["acc"], 100) / 100 / max(1, target.hp)


def best_damage(user, target, weather=None):
    return max((est_damage(user, target, m, weather) for m in user.moves), default=0.0)


def _pointless(me, foe, mv):
    """A status move that can't do anything right now: lowering a stat already at -6 (or -2 for an easy
    trainer - nobody spams Growl in FireRed), raising one already maxed, or a status the foe already has."""
    if mv.get("cls") == "status" and (mv.get("cat") == "heal" or mv.get("healing")) and mv.get("key") != "rest":
        return me.hp_frac() > 0.9   # healing at (nearly) full HP does nothing
    if mv.get("cls") != "status" or not mv.get("stats"):
        return False
    target = me if mv.get("target") == "user" or mv.get("cat") == "net-good-stats" else foe
    stages = getattr(target, "stages", {}) or {}
    for k, v in mv["stats"].items():
        cur = stages.get(k, 0)
        if (v < 0 and cur > -2) or (v > 0 and cur < 6):
            return False
    return True


class TurnBot:
    def __init__(self, difficulty="normal", seed=None):
        self.level = difficulty
        self.rng = random.Random(seed)
        self.last_switch = {}

    def choose(self, battle, side, req):
        if req["kind"] in ("lead", "switch"):
            return {"type": "switch", "index": self._pick_switch(battle, side, req["switches"], lead=req["kind"] == "lead")}
        return self._pick_move(battle, side, req)

    # ---------------------------------------------------------------- switching
    def _matchup(self, battle, side, idx):
        me = battle.sides[side].mons[idx]
        foe = battle.sides[1 - side].mon
        if foe is None:
            return 0
        offense = best_damage(me, foe, battle.weather)
        defense = best_damage(foe, me, battle.weather) if foe.moves else 0.3
        faster = me.stat("spe") > foe.stat("spe")
        return offense * (1.3 if faster else 1.0) - defense * 0.9 + me.hp_frac() * 0.3

    def _pick_switch(self, battle, side, options, lead=False):
        if self.level == "easy" or lead and self.level != "insane":
            return self.rng.choice(options)
        if lead:
            return max(options, key=lambda i: sum(battle.sides[side].mons[i].stats.values()))
        scored = sorted(options, key=lambda i: -self._matchup(battle, side, i))
        if self.level == "normal" and len(scored) > 1 and self.rng.random() < 0.35:
            return scored[1]
        return scored[0]

    # ---------------------------------------------------------------- moves
    def _pick_move(self, battle, side, req):
        s = battle.sides[side]
        me, foe = s.mon, battle.sides[1 - side].mon
        usable = [m for m in req["moves"] if not m["disabled"]]
        mega = req["can_mega"] and self.level != "easy"
        if self.level == "easy":
            if req["can_mega"] and self.rng.random() < 0.3:
                mega = True
            useful = [m for m in usable if m["slot"] == -1 or not _pointless(me, foe, me.moves[m["slot"]])] or usable
            if self.rng.random() < 0.75:
                return {"type": "move", "slot": self.rng.choice(useful)["slot"], "mega": mega}
        if usable[0]["slot"] == -1:
            return {"type": "move", "slot": -1, "mega": False}
        w = battle.weather
        my_best = best_damage(me, foe, w)
        foe_best = best_damage(foe, me, w)
        faster = me.stat("spe") >= foe.stat("spe")
        # hard+: switch out when we'd lose the exchange and a teammate walls the foe
        if self.level in ("hard", "insane") and req["switches"] and not req["forced"] \
                and battle.turn - self.last_switch.get(side, -9) > 1:
            losing = foe_best >= 0.8 and not ((faster and my_best >= 1.0) or my_best >= 1.5)
            if losing:
                walls = []
                for i in req["switches"]:
                    mon = s.mons[i]
                    taken = best_damage(foe, mon, w) * mon.hp / max(1, mon.maxhp)
                    dealt = best_damage(mon, foe, w)
                    if taken < 0.4 and dealt >= 0.25:
                        walls.append((dealt - taken, i))
                if walls and (self.level == "insane" or self.rng.random() < 0.8):
                    self.last_switch[side] = battle.turn
                    return {"type": "switch", "index": max(walls)[1]}
        foe_side = battle.sides[1 - side]
        scores = []
        for m in usable:
            mv = me.moves[m["slot"]]
            key = mv["key"]
            sc = est_damage(me, foe, mv, w) * 100
            if sc >= 100:
                sc += 60 + (40 if faster or mv["pri"] > 0 else 0)
            if mv["pri"] > 0 and foe.hp_frac() < 0.3:
                sc += 30
            if "recharge" in mv["flags"] and sc < 100:
                sc *= 0.6
            if mv["drain"] < 0:
                sc *= 0.92
            if mv["cls"] == "status":
                sc = 0
                safe = foe_best < 0.45
                st = AILMENT_TO_STATUS.get(mv["ailment"]) or ("tox" if key == "toxic" else None)
                if st and foe.can_status(st, w) and battle.vol[1 - side]["sub"] == 0:
                    sc = {"slp": 85, "par": 55 if foe.stat("spe") > me.stat("spe") else 35, "brn":
                          60 if foe.stat("atk") > foe.stat("spa") else 30, "tox": 50, "psn": 35, "frz": 40}[st]
                    if "powder" in mv["flags"] and "grass" in foe.types:
                        sc = 0
                elif mv["cat"] == "heal" or mv["healing"]:
                    sc = 90 if me.hp_frac() < 0.5 else -50 if me.hp_frac() > 0.9 else 0
                elif mv["stats"] and (mv["target"] == "user" or mv["cat"] == "net-good-stats"):
                    up = sum(v for v in mv["stats"].values() if v > 0)
                    cur = max(me.stages.values())
                    sc = (45 * up if safe and me.hp_frac() > 0.55 and cur < 2 else 0)
                elif key == "stealth-rock":
                    sc = 75 if not foe_side.rocks and len(foe_side.alive()) > 2 else 0
                elif key in ("spikes", "toxic-spikes"):
                    sc = 45 if (foe_side.spikes if key == "spikes" else foe_side.tspikes) < 2 else 0
                elif key in ("protect", "detect"):
                    sc = 25 if battle.vol[side]["protect_chain"] == 0 and (foe.status in ("psn", "tox", "brn")) else 0
                elif key in ("reflect", "light-screen", "tailwind", "aurora-veil"):
                    sc = 40 if battle.turn < 4 else 10
                elif key in ("defog", "rapid-spin"):
                    sc = 55 if s.rocks or s.spikes else 0
                elif key == "taunt":
                    sc = 20
                elif key == "substitute":
                    sc = 30 if me.hp_frac() > 0.6 and safe else 0
                else:
                    sc = 10
                if self.level == "normal":
                    sc *= 0.6
            if self.level == "normal":
                sc *= self.rng.uniform(0.7, 1.3)
            elif self.level == "hard":
                sc *= self.rng.uniform(0.92, 1.08)
            elif self.level == "easy":
                sc *= self.rng.uniform(0.3, 1.7)
            scores.append((sc, m["slot"]))
        scores.sort(reverse=True)
        gmax = bool(req.get("can_gmax")) and not mega and self.level != "easy" and me.hp_frac() > 0.5 \
            and self.rng.random() < (0.9 if self.level in ("hard", "insane") else 0.6)
        return {"type": "move", "slot": scores[0][1], "mega": mega, "gmax": gmax,
                "tera": not mega and not gmax and self._want_tera(battle, side, req, me, foe, scores[0][1])}

    def _want_tera(self, battle, side, req, me, foe, slot):
        if not req.get("can_tera") or self.level == "easy":
            return False
        if self.level == "normal":
            return self.rng.random() < 0.15
        w = battle.weather
        before_off = est_damage(me, foe, me.moves[slot], w) if slot >= 0 else 0
        before_def = best_damage(foe, me, w)
        me.terastallized = True
        try:
            after_off = est_damage(me, foe, me.moves[slot], w) if slot >= 0 else 0
            after_def = best_damage(foe, me, w)
        finally:
            me.terastallized = False
        # tera to secure a KO, or to survive a hit we otherwise wouldn't
        if after_off >= 1.0 > before_off:
            return True
        if before_def >= 1.0 > after_def * 1.15:
            return True
        alive = len(battle.sides[side].alive())
        return self.level == "insane" and alive <= 3 and after_off > before_off * 1.2


def type_threat(attacker_types, defender_types):
    return max(effectiveness(t, defender_types) for t in attacker_types)
