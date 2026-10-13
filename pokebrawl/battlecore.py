"""Combat rules shared by the real-time arena and the turn-based engine."""
from . import abilities as AB
from .team import Member, best_ability, calc_stats
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
        self.gmaxed = False     # Gigantamax: bigger, more HP, G-Max moves (only Pokemon with a Gigantamax form)
        self._pre_gmax = None
        self.choice_lock = None
        self.fainted = False
        self.ability = member.ability or best_ability(self.entry)
        self.ability_suppressed = False
        self.flags = {}
        self.tera_type = member.tera or self.entry["types"][0]
        self.terastallized = False
        self.type_override = None
        if getattr(member, "cur_hp", None) is not None:   # Adventure: damage carried over
            self.hp = max(0, min(self.maxhp, int(member.cur_hp)))
            self.fainted = self.hp <= 0
            self.status = member.status if not self.fainted else None
        if getattr(member, "pp", None):
            self.pp = [min(m["pp"], p) for m, p in zip(self.moves, member.pp)] + self.pp[len(member.pp):]

    # --------------------------------------------------------------- info
    @property
    def name(self):
        return self.entry["name"]

    @property
    def orig_types(self):
        return self.entry["types"]

    @property
    def types(self):
        if self.terastallized:
            return [self.tera_type]
        return self.type_override or self.entry["types"]

    @property
    def can_mega(self):
        return (not self.megaed and self.item == "mega-stone" and self.member.mega in self.dex.all)

    @property
    def gmax_form(self):
        gid = self.base_entry.get("gmax")
        return self.dex.all.get(gid) if gid else None

    @property
    def can_gmax(self):
        return self.gmax_form is not None and not (self.gmaxed or self.megaed or self.terastallized)

    def gmax_move(self):
        """(G-Max move name, its type) for this Pokemon's Gigantamax form."""
        from .pokedex import GMAX_MOVES
        key = self.base_entry["key"].split("-")[0]
        return GMAX_MOVES.get(key, ("Max Strike", self.base_entry["types"][0]))

    def gigantamax(self, hp_mult=1.5):
        form = self.gmax_form
        self._pre_gmax = self.entry
        self.entry = form
        self.gmaxed = True
        self.maxhp = round(self.maxhp * hp_mult)
        self.hp = min(self.maxhp, round(self.hp * hp_mult))
        return form

    def end_gmax(self):
        if not self.gmaxed:
            return
        frac = self.hp_frac()
        self.entry = self._pre_gmax or self.base_entry
        self.gmaxed = False
        self.maxhp = self.stats["hp"]
        self.hp = 0 if self.hp <= 0 else max(1, round(self.maxhp * frac))

    def hp_frac(self):
        return max(0.0, self.hp / self.maxhp)

    def best_stat(self):
        return max(("atk", "def", "spa", "spd", "spe"), key=lambda k: self.stats[k])

    def stat(self, key, crit=False, attacking=True, weather=None, other=None, ignore_stages=False):
        v = self.stats[key]
        st = 0 if ignore_stages else self.stages.get(key, 0)
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
            if self.status == "par" and self.ability != "quick-feet":
                v *= 0.5
        elif key == "spd" and it == "assault-vest":
            v *= 1.5
        if key in ("def", "spd") and it == "eviolite" and not self.entry["fully_evolved"]:
            v *= 1.5
        if key == "spd" and weather == "sand" and "rock" in self.types:
            v *= 1.5
        if key == "def" and weather == "snow" and "ice" in self.types:
            v *= 1.5
        if not self.ability_suppressed:
            v *= AB.stat_mult(self, key, weather, other)
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
        if form["abilities"]:
            self.ability = form["abilities"][0][0]
        return form

    def terastallize(self):
        self.terastallized = True
        self.type_override = None
        return self.tera_type

    def apply_stages(self, changes, from_foe=False):
        """Applies stat changes through abilities (Contrary, Simple, Clear Body, Defiant...).
        Returns list of (stat, actual change)."""
        changes, extra, blocked = AB.adjust_stage_changes(self, dict(changes), from_foe)
        out = []
        for k, v in changes.items():
            if k not in self.stages:
                continue
            old = self.stages[k]
            self.stages[k] = max(-6, min(6, old + v))
            out.append((k, self.stages[k] - old))
        if extra and any(d < 0 for _, d in out):
            for k, v in extra.items():
                old = self.stages[k]
                self.stages[k] = max(-6, min(6, old + v))
                out.append((k, self.stages[k] - old))
        if blocked:
            self.flags["blocked_drop"] = blocked
        return out

    def can_status(self, status, weather=None, attacker=None):
        if self.status or self.fainted:
            return False
        if any(t in self.types for t in STATUS_IMMUNE.get(status, ())):
            return False
        if status == "frz" and weather == "sun":
            return False
        if AB.status_immune(self, status, attacker):
            return False
        return True

    def set_status(self, status, rng):
        self.status = status
        self.toxic_n = 0
        self.status_turns = rng.randint(1, 3) if status == "slp" else 0
        if self.item == "lum-berry":
            self.status = None
            self.lose_item()
            return "lum"
        return status

    def lose_item(self):
        if self.item not in ("none", "mega-stone"):
            self.item = "none"
            self.flags["item_lost"] = True
            self.choice_lock = None  # no Choice item, no lock

    def take(self, dmg, from_full_ok=True, attacker=None):
        """Apply damage honoring Focus Sash and Sturdy. Returns damage dealt."""
        dmg = max(0, int(dmg))
        if dmg >= self.hp and self.hp == self.maxhp and from_full_ok and self.maxhp > 1:
            if AB.sturdy(self, attacker):
                dmg = self.hp - 1
                self.flags["sturdy_hit"] = True
            elif self.item == "focus-sash":
                self.lose_item()
                dmg = self.hp - 1
        dmg = min(dmg, self.hp)
        self.hp -= dmg
        if self.hp <= 0:
            self.hp = 0
            self.fainted = True
        return dmg

    def indirect(self, dmg):
        """Damage from weather/status/recoil-type sources (blocked by Magic Guard)."""
        if AB.magic_guard(self):
            return 0
        return self.take(dmg, from_full_ok=False)

    def heal(self, amount):
        amount = max(0, min(int(amount), self.maxhp - self.hp))
        self.hp += amount
        return amount


def move_type_and_power(user, move, weather=None):
    t, p = move["type"], move["power"]
    if move["key"] == "weather-ball" and weather:
        t = {"rain": "water", "sun": "fire", "sand": "rock", "snow": "ice"}[weather]
        p = 100
    if move["key"] == "tera-blast" and user.terastallized:
        t = user.tera_type
    t, m = AB.move_type(user, move, t)
    return t, p * m


def damage(user, target, move, rng, weather=None, level=None, spread=False, force_crit=None, extra=1.0,
           moved_last=False):
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
    power *= AB.power_mult(user, target, move, mtype, weather, moved_last)
    if user.gmaxed and mtype == user.gmax_move()[1]:  # G-Max move
        power *= 1.3
    stage = move["crit"] + AB.crit_bonus(user)
    crit = force_crit if force_crit is not None else rng.random() < (1 / 24, 1 / 8, 1 / 2, 1, 1)[min(stage, 4)]
    phys = move["cls"] == "phys"
    tgt_unaware = AB.ab(target, user) == "unaware"
    usr_unaware = user.ability == "unaware"
    if move["key"] == "body-press":
        a = user.stat("def", crit, True, weather, target, tgt_unaware)
    elif move["key"] == "foul-play":
        a = target.stat("atk", crit, True, weather, user, tgt_unaware)
    else:
        a = user.stat("atk" if phys else "spa", crit, True, weather, target, tgt_unaware)
    dkey = "def" if phys or move["key"] in ("psyshock", "psystrike", "secret-sword") else "spd"
    d = target.stat(dkey, crit, False, weather, user, usr_unaware)
    level = level or user.member.level
    base = ((2 * level / 5 + 2) * power * a / max(1, d)) / 50 + 2
    if spread:
        base *= 0.75
    if weather == "rain":
        base *= 1.5 if mtype == "water" else 0.5 if mtype == "fire" else 1
    elif weather == "sun":
        base *= 1.5 if mtype == "fire" else 0.5 if mtype == "water" else 1
    if crit:
        base *= AB.crit_mult(user)
    base *= rng.uniform(0.85, 1.0)
    base *= AB.stab(user, mtype)
    base *= eff
    if phys and user.status == "brn" and move["key"] != "facade" and user.ability != "guts":
        base *= 0.5
    if user.item == "life-orb":
        base *= 1.3
    if user.item == "expert-belt" and eff > 1:
        base *= 1.2
    base *= AB.defense_mult(target, user, move, mtype, eff)
    base *= extra
    return max(1, int(base)), eff, crit
