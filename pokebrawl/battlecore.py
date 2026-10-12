"""Combat rules shared by the real-time arena and the turn-based engine."""
from .team import Member, calc_stats
from .types import effectiveness

STAGE_KEYS = ("atk", "def", "spa", "spd", "spe", "acc", "eva")
STATUS_NAMES = {"brn": "BURN", "par": "PARALYSIS", "psn": "POISON", "tox": "TOXIC", "slp": "SLEEP", "frz": "FREEZE"}
AILMENT_TO_STATUS = {"burn": "brn", "paralysis": "par", "poison": "psn", "sleep": "slp", "freeze": "frz"}
STATUS_IMMUNE = {"brn": ("fire",), "par": ("electric",), "psn": ("poison", "steel"), "tox": ("poison", "steel"),
                 "frz": ("ice",), "slp": ()}


def stage_mult(stage):
    return (2 + stage) / 2 if stage >= 0 else 2 / (2 - stage)


def acc_mult(stage):
    return (3 + stage) / 3 if stage >= 0 else 3 / (3 - stage)


class Mon:
    """A Pokemon in battle (used by both engines)."""

    def __init__(self, dex, member, uid=0, team=0):
        if not isinstance(member, Member):
            member = Member.from_dict(member)
        self.dex = dex
        self.member = member
        self.uid = uid
        self.team = team
        self.base_entry = dex.all[member.species]
        self.entry = self.base_entry
        self.moves = [dex.moves[m] for m in member.moves if m in dex.moves] or [dex.move("struggle")]
        self.pp = [m["pp"] for m in self.moves]
        self.item = member.item
        self.stats = calc_stats(self.entry, member)
        self.maxhp = self.stats["hp"]
        self.hp = self.maxhp
        self.status = None
        self.status_turns = 0
        self.toxic_n = 0
        self.stages = {k: 0 for k in STAGE_KEYS}
        self.megaed = False
        self.choice_lock = None
        self.fainted = False

    # --------------------------------------------------------------- info
    @property
    def name(self):
        return self.entry["name"]

    @property
    def types(self):
        return self.entry["types"]

    @property
    def can_mega(self):
        return (not self.megaed and self.item == "mega-stone" and self.member.mega in self.dex.all)

    def hp_frac(self):
        return max(0.0, self.hp / self.maxhp)

    def stat(self, key, crit=False, attacking=True, weather=None):
        v = self.stats[key]
        st = self.stages.get(key, 0)
        if crit:  # crits ignore bad stages for the attacker and good stages for the defender
            st = max(st, 0) if attacking else min(st, 0)
        v *= stage_mult(st)
        it = self.item
        if key == "atk" and it == "choice-band":
            v *= 1.5
        elif key == "spa" and it == "choice-specs":
            v *= 1.5
        elif key == "spe":
            if it == "choice-scarf":
                v *= 1.5
            if self.status == "par":
                v *= 0.5
        elif key == "spd" and it == "assault-vest":
            v *= 1.5
        if key in ("def", "spd") and it == "eviolite" and not self.entry["fully_evolved"]:
            v *= 1.5
        if key == "spd" and weather == "sand" and "rock" in self.types:
            v *= 1.5
        return v

    # --------------------------------------------------------------- changes
    def mega_evolve(self):
        form = self.dex.all[self.member.mega]
        frac = self.hp_frac()
        self.entry = form
        new = calc_stats(form, self.member)
        new["hp"] = self.stats["hp"]  # HP never changes on mega evolution
        self.stats = new
        self.hp = max(1, round(self.maxhp * frac))
        self.megaed = True
        return form

    def apply_stages(self, changes):
        """Returns list of (stat, actual change)."""
        out = []
        for k, v in changes.items():
            if k not in self.stages:
                continue
            old = self.stages[k]
            self.stages[k] = max(-6, min(6, old + v))
            out.append((k, self.stages[k] - old))
        return out

    def can_status(self, status, weather=None):
        if self.status or self.fainted:
            return False
        if any(t in self.types for t in STATUS_IMMUNE.get(status, ())):
            return False
        if status == "frz" and weather == "sun":
            return False
        return True

    def set_status(self, status, rng):
        self.status = status
        self.toxic_n = 0
        self.status_turns = rng.randint(1, 3) if status == "slp" else 0
        if self.item == "lum-berry":
            self.status = None
            self.item = "none"
            return "lum"
        return status

    def take(self, dmg, from_full_ok=True):
        """Apply damage honoring Focus Sash. Returns damage dealt."""
        dmg = max(0, int(dmg))
        if dmg >= self.hp and self.hp == self.maxhp and self.item == "focus-sash" and from_full_ok and self.maxhp > 1:
            self.item = "none"
            dmg = self.hp - 1
        dmg = min(dmg, self.hp)
        self.hp -= dmg
        if self.hp <= 0:
            self.hp = 0
            self.fainted = True
        return dmg

    def heal(self, amount):
        amount = max(0, min(int(amount), self.maxhp - self.hp))
        self.hp += amount
        return amount


def move_type_and_power(user, move, weather=None):
    t, p = move["type"], move["power"]
    if move["key"] == "weather-ball" and weather:
        t = {"rain": "water", "sun": "fire", "sand": "rock", "snow": "ice"}[weather]
        p = 100
    return t, p


def damage(user, target, move, rng, weather=None, level=None, spread=False, force_crit=None, extra=1.0):
    """Returns (damage, effectiveness, crit). Does not apply it."""
    mtype, power = move_type_and_power(user, move, weather)
    if power <= 0:
        return 0, 1.0, False
    eff = effectiveness(mtype, target.types)
    if mtype == "ground" and target.item == "air-balloon":
        eff = 0.0
    if eff == 0:
        return 0, 0.0, False
    if move["key"] == "knock-off" and target.item not in ("none", "mega-stone"):
        power *= 1.5
    if move["key"] == "facade" and user.status:
        power *= 2
    if move["key"] == "hex" and target.status:
        power *= 2
    if move["key"] in ("eruption", "water-spout"):
        power = max(1, 150 * user.hp_frac())
    stage = move["crit"]
    crit = force_crit if force_crit is not None else rng.random() < (1 / 24, 1 / 8, 1 / 2, 1, 1)[min(stage, 4)]
    phys = move["cls"] == "phys"
    if move["key"] == "body-press":
        a = user.stat("def", crit, True, weather)
    elif move["key"] == "foul-play":
        a = target.stat("atk", crit, True, weather)
    else:
        a = user.stat("atk" if phys else "spa", crit, True, weather)
    d = target.stat("def" if phys or move["key"] in ("psyshock", "psystrike", "secret-sword") else "spd",
                    crit, False, weather)
    level = level or user.member.level
    base = ((2 * level / 5 + 2) * power * a / max(1, d)) / 50 + 2
    if spread:
        base *= 0.75
    if weather == "rain":
        base *= 1.5 if mtype == "water" else 0.5 if mtype == "fire" else 1
    elif weather == "sun":
        base *= 1.5 if mtype == "fire" else 0.5 if mtype == "water" else 1
    if crit:
        base *= 1.5
    base *= rng.uniform(0.85, 1.0)
    if mtype in user.types:
        base *= 1.5
    base *= eff
    if phys and user.status == "brn" and move["key"] != "facade":
        base *= 0.5
    if user.item == "life-orb":
        base *= 1.3
    if user.item == "expert-belt" and eff > 1:
        base *= 1.2
    base *= extra
    return max(1, int(base)), eff, crit
