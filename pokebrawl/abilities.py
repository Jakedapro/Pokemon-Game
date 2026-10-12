"""Abilities. Both engines call these hooks; unsupported abilities simply do nothing.

Every hook takes Mon objects (see battlecore.Mon). `ab(mon, attacker)` returns the defender's ability unless the
attacker has Mold Breaker (or Teravolt / Turboblaze), which ignores it.
"""
MOLD = {"mold-breaker", "teravolt", "turboblaze"}
ATE = {"aerilate": "flying", "pixilate": "fairy", "refrigerate": "ice", "galvanize": "electric"}
PINCH = {"blaze": "fire", "torrent": "water", "overgrow": "grass", "swarm": "bug"}
WEATHER_SETTERS = {"drizzle": "rain", "drought": "sun", "sand-stream": "sand", "snow-warning": "snow",
                   "primordial-sea": "rain", "desolate-land": "sun", "orichalcum-pulse": "sun"}
PERMANENT_WEATHER = {"primordial-sea", "desolate-land"}
SPEED_WEATHER = {"swift-swim": "rain", "chlorophyll": "sun", "sand-rush": "sand", "slush-rush": "snow"}
SLICING = {"aerial-ace", "air-cutter", "air-slash", "aqua-cutter", "behemoth-blade", "bitter-blade",
           "ceaseless-edge", "cross-poison", "cut", "fury-cutter", "kowtow-cleave", "leaf-blade", "night-slash",
           "population-bomb", "psycho-cut", "razor-leaf", "razor-shell", "sacred-sword", "secret-sword",
           "slash", "solar-blade", "stone-axe", "x-scissor", "tachyon-cutter", "mighty-cleave"}
STATUS_IMMUNITY = {
    "limber": {"par"}, "insomnia": {"slp"}, "vital-spirit": {"slp"}, "sweet-veil": {"slp"},
    "immunity": {"psn", "tox"}, "pastel-veil": {"psn", "tox"}, "water-veil": {"brn"}, "water-bubble": {"brn"},
    "thermal-exchange": {"brn"}, "magma-armor": {"frz"}, "purifying-salt": {"brn", "par", "psn", "tox", "slp", "frz"},
    "comatose": {"brn", "par", "psn", "tox", "slp", "frz"},
}
NO_DROPS = {"clear-body", "white-smoke", "full-metal-body"}

# What the team builder shows. Anything not listed still appears (as "no battle effect yet").
DESCRIPTIONS = {
    "intimidate": "Lowers the foe's Attack on entry", "levitate": "Immune to Ground moves",
    "drizzle": "Summons rain on entry", "drought": "Summons harsh sun on entry",
    "sand-stream": "Summons a sandstorm on entry", "snow-warning": "Summons snow on entry",
    "primordial-sea": "Permanent heavy rain", "desolate-land": "Permanent harsh sun",
    "speed-boost": "Speed rises every turn", "huge-power": "Doubles Attack", "pure-power": "Doubles Attack",
    "adaptability": "STAB is 2x instead of 1.5x", "technician": "Moves with 60 power or less do 1.5x",
    "multiscale": "Half damage at full HP", "shadow-shield": "Half damage at full HP",
    "sturdy": "Survives any hit from full HP", "magic-guard": "Only takes damage from attacks",
    "regenerator": "Heals 1/3 HP when switching out", "flash-fire": "Immune to Fire; powers up Fire moves",
    "water-absorb": "Water moves heal it", "volt-absorb": "Electric moves heal it", "dry-skin": "Water heals it",
    "storm-drain": "Water moves raise Sp. Atk", "lightning-rod": "Electric moves raise Sp. Atk",
    "motor-drive": "Electric moves raise Speed", "sap-sipper": "Grass moves raise Attack",
    "earth-eater": "Ground moves heal it", "well-baked-body": "Fire moves raise Defense",
    "thick-fat": "Halves Fire and Ice damage", "guts": "1.5x Attack when statused",
    "swift-swim": "2x Speed in rain", "chlorophyll": "2x Speed in sun", "sand-rush": "2x Speed in sand",
    "slush-rush": "2x Speed in snow", "tough-claws": "Contact moves do 1.3x", "sheer-force": "1.3x power, no secondary effects",
    "iron-fist": "Punches do 1.2x", "strong-jaw": "Bites do 1.5x", "mega-launcher": "Pulse moves do 1.5x",
    "pixilate": "Normal moves become Fairy (1.2x)", "aerilate": "Normal moves become Flying (1.2x)",
    "refrigerate": "Normal moves become Ice (1.2x)", "galvanize": "Normal moves become Electric (1.2x)",
    "protean": "Becomes the type of its move", "libero": "Becomes the type of its move",
    "poison-heal": "Heals from poison instead", "unaware": "Ignores the foe's stat changes",
    "moxie": "Attack rises after a KO", "beast-boost": "Best stat rises after a KO",
    "chilling-neigh": "Attack rises after a KO", "grim-neigh": "Sp. Atk rises after a KO",
    "prankster": "Status moves get +1 priority", "gale-wings": "Flying moves +1 priority at full HP",
    "triage": "Healing moves get +3 priority", "static": "Contact may paralyze",
    "flame-body": "Contact may burn", "poison-point": "Contact may poison", "effect-spore": "Contact may sleep/poison/paralyze",
    "rough-skin": "Contact attackers lose 1/8 HP", "iron-barbs": "Contact attackers lose 1/8 HP",
    "natural-cure": "Cures status on switch-out", "clear-body": "Stats can't be lowered",
    "contrary": "Stat changes are reversed", "simple": "Stat changes are doubled",
    "solid-rock": "Super-effective hits do 0.75x", "filter": "Super-effective hits do 0.75x",
    "prism-armor": "Super-effective hits do 0.75x", "marvel-scale": "1.5x Defense when statused",
    "hustle": "1.5x Attack, less accurate", "sniper": "Crits do 2.25x", "super-luck": "Crits more often",
    "skill-link": "Multi-hit moves hit max times", "serene-grace": "Doubles secondary effect chances",
    "blaze": "Fire moves 1.5x below 1/3 HP", "torrent": "Water moves 1.5x below 1/3 HP",
    "overgrow": "Grass moves 1.5x below 1/3 HP", "swarm": "Bug moves 1.5x below 1/3 HP",
    "mold-breaker": "Ignores the foe's ability", "teravolt": "Ignores the foe's ability",
    "turboblaze": "Ignores the foe's ability", "download": "Raises Atk or SpA on entry",
    "intrepid-sword": "Attack rises on entry", "dauntless-shield": "Defense rises on entry",
    "no-guard": "Every move hits", "compound-eyes": "1.3x accuracy", "tinted-lens": "Not-very-effective hits do 2x",
    "wonder-guard": "Only super-effective moves hit it", "fur-coat": "Doubles Defense",
    "fluffy": "Halves contact damage, weak to Fire", "ice-scales": "Halves special damage",
    "punk-rock": "Sound moves 1.3x, takes half from sound", "transistor": "Electric moves 1.3x",
    "dragons-maw": "Dragon moves 1.5x", "steelworker": "Steel moves 1.5x", "rocky-payload": "Rock moves 1.5x",
    "sharpness": "Slicing moves 1.5x", "reckless": "Recoil moves 1.2x", "sand-force": "Rock/Ground/Steel 1.3x in sand",
    "water-bubble": "Water moves 2x, halves Fire damage", "solar-power": "1.5x Sp. Atk in sun, loses HP",
    "gorilla-tactics": "1.5x Attack, locked into one move", "heatproof": "Halves Fire damage",
    "bulletproof": "Immune to ball/bomb moves", "soundproof": "Immune to sound moves",
    "good-as-gold": "Immune to status moves", "overcoat": "Immune to powder moves",
    "purifying-salt": "No status, halves Ghost damage", "armor-tail": "Blocks priority moves",
    "queenly-majesty": "Blocks priority moves", "dazzling": "Blocks priority moves",
    "magic-bounce": "Blocks status moves", "rain-dish": "Heals in rain", "ice-body": "Heals in snow",
    "shed-skin": "May cure status each turn", "hydration": "Cures status in rain",
    "unburden": "2x Speed after using its item", "quick-feet": "1.5x Speed when statused",
    "stamina": "Defense rises when hit", "justified": "Attack rises when hit by Dark",
    "defiant": "Attack sharply rises when stats are lowered", "competitive": "Sp. Atk sharply rises when stats are lowered",
    "aftermath": "Hurts the attacker that KOs it with contact", "disguise": "Blocks the first hit",
    "orichalcum-pulse": "Sets sun; 1.33x Attack in sun", "hadron-engine": "1.33x Sp. Atk",
    "protosynthesis": "Best stat 1.3x in sun", "sword-of-ruin": "Lowers others' Defense",
    "beads-of-ruin": "Lowers others' Sp. Def", "tablets-of-ruin": "Lowers others' Attack",
    "vessel-of-ruin": "Lowers others' Sp. Atk", "analytic": "1.3x power when moving last",
    "limber": "Can't be paralyzed", "insomnia": "Can't fall asleep", "vital-spirit": "Can't fall asleep",
    "immunity": "Can't be poisoned", "water-veil": "Can't be burned", "magma-armor": "Can't be frozen",
    "comatose": "Immune to status", "inner-focus": "Never flinches", "steadfast": "Speed rises when it flinches",
    "white-smoke": "Stats can't be lowered", "full-metal-body": "Stats can't be lowered",
    "thermal-exchange": "Can't be burned; Fire hits raise Attack", "pastel-veil": "Can't be poisoned",
    "sweet-veil": "Can't fall asleep",
}


def ability_name(key):
    return " ".join(p.title() for p in (key or "").split("-")) if key else "(none)"


def ab(mon, attacker=None):
    if mon is None or mon.ability_suppressed:
        return None
    if attacker is not None and attacker is not mon and attacker.ability in MOLD:
        return None
    return mon.ability


# ---------------------------------------------------------------------------- move modifiers
def move_type(user, move, mtype):
    """(type, power multiplier) after -ate abilities."""
    if user.ability in ATE and mtype == "normal" and move["power"] > 0:
        return ATE[user.ability], 1.2
    return mtype, 1.0


def priority(user, move):
    a = user.ability
    if a == "prankster" and move["cls"] == "status":
        return 1
    if a == "gale-wings" and move["type"] == "flying" and user.hp == user.maxhp:
        return 1
    if a == "triage" and (move["healing"] > 0 or move["drain"] > 0 or move["cat"] == "heal"):
        return 3
    return 0


def has_secondary(move):
    return bool(move["ail_chance"] or move["flinch"] or (move["stats"] and move["cat"] == "damage-lower"))


def power_mult(user, target, move, mtype, weather=None, moved_last=False):
    a, m, flags = user.ability, 1.0, move["flags"]
    if a == "technician" and move["power"] <= 60:
        m *= 1.5
    elif a == "iron-fist" and "punch" in flags:
        m *= 1.2
    elif a == "strong-jaw" and "bite" in flags:
        m *= 1.5
    elif a == "mega-launcher" and "pulse" in flags:
        m *= 1.5
    elif a == "tough-claws" and "contact" in flags:
        m *= 1.3
    elif a == "sheer-force" and has_secondary(move):
        m *= 1.3
    elif a == "punk-rock" and "sound" in flags:
        m *= 1.3
    elif a == "transistor" and mtype == "electric":
        m *= 1.3
    elif a in ("dragons-maw",) and mtype == "dragon":
        m *= 1.5
    elif a == "steelworker" and mtype == "steel":
        m *= 1.5
    elif a == "rocky-payload" and mtype == "rock":
        m *= 1.5
    elif a == "sharpness" and move["key"] in SLICING:
        m *= 1.5
    elif a == "reckless" and move["drain"] < 0:
        m *= 1.2
    elif a == "water-bubble" and mtype == "water":
        m *= 2.0
    elif a == "sand-force" and weather == "sand" and mtype in ("rock", "ground", "steel"):
        m *= 1.3
    elif a == "analytic" and moved_last:
        m *= 1.3
    elif a in PINCH and mtype == PINCH[a] and user.hp * 3 <= user.maxhp:
        m *= 1.5
    if user.flags.get("flash_fire") and mtype == "fire":
        m *= 1.5
    return m


def stat_mult(mon, key, weather=None, other=None):
    """Ability multiplier on the mon's own stat. `other` is the opposing mon (for Ruin abilities)."""
    a, m = mon.ability, 1.0
    if key == "atk":
        if a in ("huge-power", "pure-power"):
            m *= 2
        elif a in ("hustle", "gorilla-tactics"):
            m *= 1.5
        elif a == "guts" and mon.status:
            m *= 1.5
        elif a == "orichalcum-pulse" and weather == "sun":
            m *= 4 / 3
    elif key == "spa":
        if a == "solar-power" and weather == "sun":
            m *= 1.5
        elif a == "hadron-engine":
            m *= 4 / 3
    elif key == "def":
        if a == "fur-coat":
            m *= 2
        elif a == "marvel-scale" and mon.status:
            m *= 1.5
    elif key == "spe":
        if SPEED_WEATHER.get(a) and SPEED_WEATHER[a] == weather:
            m *= 2
        elif a == "unburden" and mon.flags.get("item_lost"):
            m *= 2
        elif a == "quick-feet" and mon.status:
            m *= 1.5
    if a == "protosynthesis" and weather == "sun" and key == mon.best_stat():
        m *= 1.5 if key == "spe" else 1.3
    if other is not None and other.ability and not other.ability_suppressed:
        ruin = {"atk": "tablets-of-ruin", "spa": "vessel-of-ruin", "def": "sword-of-ruin", "spd": "beads-of-ruin"}
        if ruin.get(key) == other.ability and mon.ability != other.ability:
            m *= 0.75
    return m


def stab(user, mtype):
    orig = user.orig_types
    if user.terastallized:
        base = 1.0
        if mtype == user.tera_type and mtype in orig:
            base = 2.0
        elif mtype == user.tera_type or mtype in orig:
            base = 1.5
        if user.ability == "adaptability" and base > 1:
            base = 2.25 if base == 2.0 else 2.0
        return base
    if mtype in user.types:
        return 2.0 if user.ability == "adaptability" else 1.5
    return 1.0


def defense_mult(target, attacker, move, mtype, eff):
    a = ab(target, attacker)
    m = 1.0
    if a in ("multiscale", "shadow-shield") and target.hp == target.maxhp:
        m *= 0.5
    if a in ("filter", "solid-rock") and eff > 1:
        m *= 0.75
    if target.ability == "prism-armor" and eff > 1:
        m *= 0.75
    if a == "thick-fat" and mtype in ("fire", "ice"):
        m *= 0.5
    if a in ("heatproof", "water-bubble") and mtype == "fire":
        m *= 0.5
    if a == "fluffy":
        if "contact" in move["flags"]:
            m *= 0.5
        if mtype == "fire":
            m *= 2
    if a == "ice-scales" and move["cls"] == "spec":
        m *= 0.5
    if a == "purifying-salt" and mtype == "ghost":
        m *= 0.5
    if a == "punk-rock" and "sound" in move["flags"]:
        m *= 0.5
    if a == "dry-skin" and mtype == "fire":
        m *= 1.25
    if attacker.ability == "tinted-lens" and 0 < eff < 1:
        m *= 2
    return m


def immunity(target, attacker, move, mtype, eff=1.0):
    """Returns None, or (verb, effect) where effect is one of:
    ('heal', frac) | ('boost', {stat: n}) | ('flash_fire',) | ('block',)"""
    a = ab(target, attacker)
    if not a or target is attacker:
        return None
    status_move = move["cls"] == "status"
    if a == "levitate" and mtype == "ground" and move["power"] > 0:
        return ("Levitate", ("block",))
    if a == "flash-fire" and mtype == "fire":
        return ("Flash Fire", ("flash_fire",))
    if a in ("water-absorb", "dry-skin") and mtype == "water":
        return (ability_name(a), ("heal", 0.25))
    if a == "storm-drain" and mtype == "water":
        return ("Storm Drain", ("boost", {"spa": 1}))
    if a == "volt-absorb" and mtype == "electric":
        return ("Volt Absorb", ("heal", 0.25))
    if a == "lightning-rod" and mtype == "electric":
        return ("Lightning Rod", ("boost", {"spa": 1}))
    if a == "motor-drive" and mtype == "electric":
        return ("Motor Drive", ("boost", {"spe": 1}))
    if a == "sap-sipper" and mtype == "grass":
        return ("Sap Sipper", ("boost", {"atk": 1}))
    if a == "earth-eater" and mtype == "ground":
        return ("Earth Eater", ("heal", 0.25))
    if a == "well-baked-body" and mtype == "fire":
        return ("Well-Baked Body", ("boost", {"def": 2}))
    if a == "bulletproof" and "ballistics" in move["flags"]:
        return ("Bulletproof", ("block",))
    if a == "soundproof" and "sound" in move["flags"]:
        return ("Soundproof", ("block",))
    if a == "overcoat" and "powder" in move["flags"]:
        return ("Overcoat", ("block",))
    if a == "wonder-guard" and move["power"] > 0 and eff <= 1:
        return ("Wonder Guard", ("block",))
    if status_move and a in ("good-as-gold", "magic-bounce"):
        return (ability_name(a), ("block",))
    if a in ("armor-tail", "queenly-majesty", "dazzling") and (move["pri"] + priority(attacker, move)) > 0:
        return (ability_name(a), ("block",))
    return None


def status_immune(mon, status, attacker=None):
    a = ab(mon, attacker)
    return bool(a and status in STATUS_IMMUNITY.get(a, ()))


def crit_bonus(user):
    return 1 if user.ability == "super-luck" else 0


def crit_mult(user):
    return 2.25 if user.ability == "sniper" else 1.5


def accuracy(user, target, move):
    """Accuracy multiplier, or None = can't miss."""
    if user.ability == "no-guard" or (target is not None and target.ability == "no-guard"):
        return None
    m = 1.0
    if user.ability == "compound-eyes":
        m *= 1.3
    if user.ability == "hustle" and move["cls"] == "phys":
        m *= 0.8
    return m


def hit_count(user, move, rolled):
    if user.ability == "skill-link" and move["hits"][1] > 1:
        return move["hits"][1]
    return rolled


def secondary_mult(user, move):
    if user.ability == "sheer-force" and has_secondary(move):
        return 0.0
    return 2.0 if user.ability == "serene-grace" else 1.0


def contact_reactions(attacker, defender, rng):
    """Effects on the attacker after it makes contact: list of ('status', st) | ('damage', frac) and the ability."""
    a = ab(defender, attacker)
    out = []
    if a == "static" and rng.random() < 0.3:
        out.append(("status", "par"))
    elif a == "flame-body" and rng.random() < 0.3:
        out.append(("status", "brn"))
    elif a == "poison-point" and rng.random() < 0.3:
        out.append(("status", "psn"))
    elif a == "effect-spore" and rng.random() < 0.3 and "grass" not in attacker.types:
        out.append(("status", rng.choice(["slp", "psn", "par"])))
    elif a in ("rough-skin", "iron-barbs"):
        out.append(("damage", 1 / 8))
    if a == "aftermath" and defender.fainted:
        out.append(("damage", 1 / 4))
    return out, a


def on_ko(mon):
    a = mon.ability
    if a in ("moxie", "chilling-neigh"):
        return {"atk": 1}
    if a == "grim-neigh":
        return {"spa": 1}
    if a == "beast-boost":
        return {mon.best_stat(): 1}
    return None


def on_hit(mon, mtype, attacker):
    """Stat changes when hit by a damaging move."""
    a = ab(mon, attacker)
    if a == "stamina":
        return {"def": 1}
    if a == "justified" and mtype == "dark":
        return {"atk": 1}
    if a == "thermal-exchange" and mtype == "fire":
        return {"atk": 1}
    return None


def adjust_stage_changes(mon, changes, from_foe):
    """Returns (changes to apply, extra boosts triggered, blocked message)."""
    a = mon.ability
    if a == "contrary":
        changes = {k: -v for k, v in changes.items()}
    elif a == "simple":
        changes = {k: v * 2 for k, v in changes.items()}
    if from_foe and a in NO_DROPS:
        if any(v < 0 for v in changes.values()):
            return {k: v for k, v in changes.items() if v > 0}, None, ability_name(a)
    extra = None
    if from_foe and any(v < 0 for v in changes.values()):
        if a == "defiant":
            extra = {"atk": 2}
        elif a == "competitive":
            extra = {"spa": 2}
    return changes, extra, None


def entry_effects(mon, foe):
    """Things that happen when the mon enters battle: list of (kind, payload)."""
    a = mon.ability
    out = []
    if a in WEATHER_SETTERS:
        out.append(("weather", (WEATHER_SETTERS[a], 999 if a in PERMANENT_WEATHER else 5)))
    if a == "intimidate" and foe is not None:
        out.append(("intimidate", None))
    if a == "download" and foe is not None:
        out.append(("boost", {"atk": 1} if foe.stat("def") < foe.stat("spd") else {"spa": 1}))
    if a == "intrepid-sword":
        out.append(("boost", {"atk": 1}))
    if a == "dauntless-shield":
        out.append(("boost", {"def": 1}))
    return out


def end_of_turn(mon, weather, rng):
    """Returns list of (kind, value, message)."""
    a = mon.ability
    out = []
    if a == "speed-boost":
        out.append(("boost", {"spe": 1}, None))
    if a == "rain-dish" and weather == "rain":
        out.append(("heal", 1 / 16, "Rain Dish"))
    if a == "ice-body" and weather == "snow":
        out.append(("heal", 1 / 16, "Ice Body"))
    if a == "dry-skin":
        if weather == "rain":
            out.append(("heal", 1 / 8, "Dry Skin"))
        elif weather == "sun":
            out.append(("damage", 1 / 8, "Dry Skin"))
    if a == "solar-power" and weather == "sun":
        out.append(("damage", 1 / 8, "Solar Power"))
    if mon.status and ((a == "shed-skin" and rng.random() < 0.33) or (a == "hydration" and weather == "rain")):
        out.append(("cure", None, ability_name(a)))
    return out


def magic_guard(mon):
    return mon.ability == "magic-guard"


def sturdy(mon, attacker=None):
    return ab(mon, attacker) == "sturdy"


def on_switch_out(mon):
    if mon.ability == "regenerator" and not mon.fainted:
        mon.heal(mon.maxhp / 3)
    if mon.ability == "natural-cure":
        mon.status = None


def protean(mon, mtype):
    """Protean/Libero: become the move's type once per switch-in. Returns True if it changed."""
    if mon.ability in ("protean", "libero") and not mon.flags.get("protean_used") and not mon.terastallized \
            and mon.types != [mtype]:
        mon.flags["protean_used"] = True
        mon.type_override = [mtype]
        return True
    return False
