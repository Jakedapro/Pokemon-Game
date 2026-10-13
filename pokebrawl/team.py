"""Teams: held items, natures, EV builds, stat calculation, Showdown import/export and team generation."""
import json
import os
import random
import re

from .pokedex import HOME
from .types import TYPES, effectiveness

TEAMS_FILE = os.path.join(HOME, "teams.json")

ITEMS = {
    "none": ("(no item)", ""),
    "leftovers": ("Leftovers", "Heals 1/16 HP each turn"),
    "life-orb": ("Life Orb", "1.3x damage, loses 10% HP per attack"),
    "choice-band": ("Choice Band", "1.5x Attack, locked into one move"),
    "choice-specs": ("Choice Specs", "1.5x Sp. Atk, locked into one move"),
    "choice-scarf": ("Choice Scarf", "1.5x Speed, locked into one move"),
    "focus-sash": ("Focus Sash", "Survives one hit at 1 HP from full"),
    "assault-vest": ("Assault Vest", "1.5x Sp. Def, attacking moves only"),
    "rocky-helmet": ("Rocky Helmet", "Contact attackers lose 1/6 HP"),
    "sitrus-berry": ("Sitrus Berry", "Heals 25% once below half HP"),
    "lum-berry": ("Lum Berry", "Cures a status condition once"),
    "expert-belt": ("Expert Belt", "1.2x damage on super-effective hits"),
    "eviolite": ("Eviolite", "1.5x Def/Sp. Def if not fully evolved"),
    "weakness-policy": ("Weakness Policy", "+2 Atk/Sp. Atk when hit super-effectively"),
    "heavy-duty-boots": ("Heavy-Duty Boots", "Immune to entry hazards"),
    "black-sludge": ("Black Sludge", "Heals Poison types 1/16, hurts others"),
    "air-balloon": ("Air Balloon", "Immune to Ground until hit"),
    "white-herb": ("White Herb", "Restores lowered stats once"),
    "mega-stone": ("Mega Stone", "Lets this Pokemon Mega Evolve / go Primal"),
}
COMP_ITEMS = [k for k in ITEMS if k not in ("none", "mega-stone")]

NATURES = {
    "Hardy": (None, None), "Lonely": ("atk", "def"), "Brave": ("atk", "spe"), "Adamant": ("atk", "spa"),
    "Naughty": ("atk", "spd"), "Bold": ("def", "atk"), "Docile": (None, None), "Relaxed": ("def", "spe"),
    "Impish": ("def", "spa"), "Lax": ("def", "spd"), "Timid": ("spe", "atk"), "Hasty": ("spe", "def"),
    "Serious": (None, None), "Jolly": ("spe", "spa"), "Naive": ("spe", "spd"), "Modest": ("spa", "atk"),
    "Mild": ("spa", "def"), "Quiet": ("spa", "spe"), "Bashful": (None, None), "Rash": ("spa", "spd"),
    "Calm": ("spd", "atk"), "Gentle": ("spd", "def"), "Sassy": ("spd", "spe"), "Careful": ("spd", "spa"),
    "Quirky": (None, None),
}

STAT_NAMES = {"hp": "HP", "atk": "Atk", "def": "Def", "spa": "SpA", "spd": "SpD", "spe": "Spe"}
BUILDS = {
    "Fast Physical": ({"atk": 252, "spe": 252, "hp": 4}, "Jolly"),
    "Fast Special": ({"spa": 252, "spe": 252, "hp": 4}, "Timid"),
    "Strong Physical": ({"atk": 252, "hp": 252, "spe": 4}, "Adamant"),
    "Strong Special": ({"spa": 252, "hp": 252, "spe": 4}, "Modest"),
    "Physical Wall": ({"hp": 252, "def": 252, "spd": 4}, "Bold"),
    "Special Wall": ({"hp": 252, "spd": 252, "def": 4}, "Calm"),
    "Balanced": ({"hp": 84, "atk": 84, "def": 84, "spa": 84, "spd": 84, "spe": 84}, "Serious"),
}

# moves the auto-builder avoids (gimmicky or self-destructive)
AUTO_AVOID = {"explosion", "self-destruct", "misty-explosion", "final-gambit", "memento", "healing-wish",
              "lunar-dance", "focus-punch", "dream-eater", "belch", "last-resort", "snore", "sleep-talk",
              "steel-roller", "synchronoise", "natural-gift", "fling", "spit-up", "stockpile", "rollout",
              "ice-ball", "future-sight", "doom-desire", "struggle", "chilly-reception", "shed-tail",
              "court-change", "trick-room", "substitute", "destiny-bond", "curse", "pain-split", "teleport",
              "hyperspace-fury", "dark-void", "relic-song", "aura-wheel", "hyperspace-hole", "thrash", "uproar",
              "petal-dance", "outrage", "raging-fury", "hyper-beam", "giga-impact", "sky-attack", "solar-blade"}
SETUP = ["swords-dance", "dragon-dance", "nasty-plot", "calm-mind", "quiver-dance", "shell-smash", "bulk-up",
         "shift-gear", "victory-dance", "tidy-up", "coil"]
UTILITY = ["u-turn", "volt-switch", "flip-turn", "stealth-rock", "will-o-wisp", "toxic", "thunder-wave",
           "recover", "roost", "slack-off", "soft-boiled", "moonlight", "synthesis", "protect", "knock-off",
           "spikes", "defog", "rapid-spin", "parting-shot", "spore", "leech-seed", "wish"]


def mega_item_name(dex, form):
    """'Charizardite X', 'Blue Orb', etc. for a transformation form."""
    if "primal" in form["key"]:
        return "Blue Orb" if "kyogre" in form["key"] else "Red Orb"
    base = dex.all[form["base"]]["name"] if form.get("base") else form["name"]
    stem = base.split()[0]
    stem = stem[:-1] if stem.endswith("e") else stem
    suffix = form["key"].rsplit("-", 1)[-1]
    return f"{stem}ite" + (f" {suffix.upper()}" if suffix in ("x", "y", "z") else "")


class Member:
    """One Pokemon on a team."""

    def __init__(self, species, moves, item="none", nature="Serious", evs=None, mega=None, level=100,
                 ability=None, tera=None):
        self.species = species          # dex id of the (non-mega) form
        self.moves = list(moves)[:4]    # move ids
        self.item = item
        self.nature = nature
        self.evs = dict(evs or BUILDS["Balanced"][0])
        self.mega = mega                # dex id of the mega/primal form the stone unlocks
        self.level = level
        self.ability = ability          # ability key; None = the species' best ability
        self.tera = tera                # Tera type; None = its first type

    def to_dict(self):
        return {"species": self.species, "moves": self.moves, "item": self.item, "nature": self.nature,
                "evs": self.evs, "mega": self.mega, "level": self.level, "ability": self.ability,
                "tera": self.tera}

    @classmethod
    def from_dict(cls, d):
        return cls(d["species"], d.get("moves", []), d.get("item", "none"), d.get("nature", "Serious"),
                   d.get("evs"), d.get("mega"), d.get("level", 100), d.get("ability"), d.get("tera"))

    def item_name(self, dex):
        if self.item == "mega-stone" and self.mega and self.mega in dex.all:
            return mega_item_name(dex, dex.all[self.mega])
        return ITEMS.get(self.item, ITEMS["none"])[0]


def calc_stats(entry, member=None, level=None):
    """Real stat formula with 31 IVs. Without a member: neutral nature, balanced EVs."""
    level = level or (member.level if member else 50)
    evs = member.evs if member else {}
    up, down = NATURES.get(member.nature if member else "Serious", (None, None))
    out = {}
    for k, base in entry["stats"].items():
        ev = evs.get(k, 0)
        core = (2 * base + 31 + ev // 4) * level // 100
        if k == "hp":
            out[k] = 1 if entry["key"] == "shedinja" else core + level + 10
        else:
            v = core + 5
            if k == up:
                v = v * 11 // 10
            elif k == down:
                v = v * 9 // 10
            out[k] = v
    return out


def validate(dex, members):
    """Returns a list of problems (empty if the team is legal)."""
    errs = []
    if not 1 <= len(members) <= 6:
        errs.append("Teams need 1-6 Pokemon")
    species = [dex.all[m.species]["species"] for m in members if m.species in dex.all]
    if len(species) != len(set(species)):
        errs.append("Species Clause: no duplicate Pokemon")
    legends = [dex.all[m.species]["name"] for m in members
               if m.species in dex.all and (dex.all[m.species]["legendary"] or dex.all[m.species]["mythical"])]
    if len(legends) > 1:
        errs.append(f"Legend Clause: only one legendary per team ({', '.join(legends)})")
    if sum(1 for m in members if m.item == "mega-stone") > 1:
        errs.append("Only one Mega Stone / Orb per team")
    items = [m.item for m in members if m.item not in ("none", "mega-stone")]
    if len(items) != len(set(items)):
        errs.append("Item Clause: no duplicate items")
    for m in members:
        e = dex.all.get(m.species)
        if not e:
            errs.append(f"Unknown Pokemon #{m.species}")
            continue
        if not m.moves:
            errs.append(f"{e['name']} has no moves")
        legal = set(e["learn"])
        for mv in m.moves:
            if mv not in legal:
                errs.append(f"{e['name']} can't learn {dex.moves.get(mv, {}).get('name', mv)}")
        if m.item == "mega-stone" and m.mega not in e["megas"]:
            errs.append(f"{e['name']} can't use that Mega Stone")
        if sum(m.evs.values()) > 510 or any(v > 252 for v in m.evs.values()):
            errs.append(f"{e['name']} has too many EVs")
        if m.ability and e["abilities"] and m.ability not in [a for a, _ in e["abilities"]]:
            errs.append(f"{e['name']} can't have {m.ability.replace('-', ' ').title()}")
        if m.tera and m.tera not in TYPES:
            errs.append(f"{e['name']} has an unknown Tera type")
    return errs


BAD_ABILITIES = {"truant", "slow-start", "defeatist", "klutz", "stall", "normalize", "comatose", "zen-mode",
                 "imposter", "illusion", "rivalry", "forewarn", "run-away", "honey-gather", "pickup"}


def best_ability(entry, rng=None):
    """The ability the auto-builder picks: the strongest one this game models."""
    from .abilities import DESCRIPTIONS
    opts = [a for a, _ in entry["abilities"]]
    if not opts:
        return None
    good = [a for a in opts if a in DESCRIPTIONS and a not in BAD_ABILITIES]
    tier1 = {"huge-power", "pure-power", "speed-boost", "adaptability", "intimidate", "multiscale", "drought",
             "drizzle", "sand-stream", "snow-warning", "regenerator", "magic-guard", "protean", "libero",
             "technician", "tough-claws", "levitate", "moxie", "beast-boost", "sheer-force", "unaware",
             "pixilate", "aerilate", "refrigerate", "galvanize", "prankster", "poison-heal", "skill-link",
             "intrepid-sword", "disguise", "primordial-sea", "desolate-land", "gorilla-tactics", "sharpness",
             "tinted-lens", "contrary", "dragons-maw", "transistor", "orichalcum-pulse", "hadron-engine",
             "sword-of-ruin", "beads-of-ruin", "tablets-of-ruin", "vessel-of-ruin", "good-as-gold", "guts"}
    best = [a for a in good if a in tier1]
    pool = best or good or [a for a in opts if a not in BAD_ABILITIES] or opts
    return pool[0] if rng is None else rng.choice(pool)


def best_tera(entry, moves, dex):
    """Tera into the type of its strongest attacking move (or its first type)."""
    best, score = entry["types"][0], 0
    for mid in moves:
        mv = dex.moves.get(mid)
        if mv and mv["power"] * (1.5 if mv["type"] in entry["types"] else 1) > score:
            best, score = mv["type"], mv["power"] * (1.5 if mv["type"] in entry["types"] else 1)
    return best


# ---------------------------------------------------------------- auto building

def move_score(dex, entry, mv, prefer=None):
    if mv["power"] <= 0 or mv["key"] in AUTO_AVOID:
        return 0
    p = mv["power"] * (sum(mv["hits"]) / 2) * min(mv["acc"], 100) / 100
    if mv["type"] in entry["types"]:
        p *= 1.5
    if "charge" in mv["flags"] or "recharge" in mv["flags"]:
        p *= 0.45
    if mv["drain"] < 0:
        p *= 0.9
    if mv["cat"] == "damage-raise" and any(v < 0 for v in mv["stats"].values()):
        p *= 0.9
    if prefer and mv["cls"] != prefer:
        p *= 0.55
    if mv["pri"] > 0:
        p *= 1.1
    return p


def auto_moves(dex, entry, rng, comp=True):
    """Pick a sensible 4-move set from the real learnset."""
    learn = dex.learnset(entry if entry["learn"] else dex.all.get(entry.get("base"), entry))
    s = entry["stats"]
    prefer = "phys" if s["atk"] >= s["spa"] else "spec"
    attacks = sorted((m for m in learn if move_score(dex, entry, m, prefer) > 0),
                     key=lambda m: -move_score(dex, entry, m, prefer) * rng.uniform(0.85, 1.15))
    chosen = []
    for t in entry["types"]:  # best STAB of each type
        for m in attacks:
            if m["type"] == t and m not in chosen:
                chosen.append(m)
                break
    covered = {m["type"] for m in chosen}
    for m in attacks:  # coverage that hits something new
        if len(chosen) >= 3:
            break
        if m["type"] not in covered and move_score(dex, entry, m, prefer) > 60:
            chosen.append(m)
            covered.add(m["type"])
    learn_keys = {m["key"]: m for m in learn}
    if comp:
        setup = [learn_keys[k] for k in SETUP if k in learn_keys and
                 (("atk" in learn_keys[k]["stats"]) == (prefer == "phys") or "spe" in learn_keys[k]["stats"])]
        util = [learn_keys[k] for k in UTILITY if k in learn_keys]
        extra = setup if setup and rng.random() < 0.55 else util
        if extra and len(chosen) < 4:
            chosen.append(rng.choice(extra[:4]))
    for m in attacks:
        if len(chosen) >= 4:
            break
        if m not in chosen:
            chosen.append(m)
    if not chosen:
        chosen = [dex.move("struggle") or dex.move("tackle")]
    return [m["id"] for m in chosen[:4] if m]


def auto_build(entry):
    s = entry["stats"]
    phys = s["atk"] >= s["spa"]
    bulky = s["hp"] + s["def"] + s["spd"] > 3 * s["spe"] + 60
    if bulky:
        return "Strong Physical" if phys else "Strong Special"
    return "Fast Physical" if phys else "Fast Special"


def auto_member(dex, entry, rng, item_pool=None, allow_mega=True, level=100, comp=True):
    build = auto_build(entry)
    evs, nature = BUILDS[build]
    moves = auto_moves(dex, entry, rng, comp)
    mega = None
    item = "none"
    if allow_mega and entry["megas"]:
        item, mega = "mega-stone", rng.choice(entry["megas"])
    elif item_pool:
        s = entry["stats"]
        prefs = []
        if not entry["fully_evolved"]:
            prefs.append("eviolite")
        if "Fast" in build:
            prefs += ["choice-scarf", "life-orb", "focus-sash", "choice-band" if s["atk"] > s["spa"] else "choice-specs"]
        else:
            prefs += ["leftovers", "assault-vest", "rocky-helmet", "sitrus-berry"]
        prefs += ["expert-belt", "lum-berry", "weakness-policy", "heavy-duty-boots"]
        for p in prefs:
            if p in item_pool:
                item = p
                item_pool.remove(p)
                break
    return Member(entry["id"], moves, item, nature, evs, mega, level, best_ability(entry),
                  best_tera(entry, moves, dex))


def random_team(dex, rng=None, size=6, min_bst=480, max_bst=720, legendary=False, level=100):
    rng = rng or random.Random()
    pool = [e for e in dex.selectable() if e["fully_evolved"] and e["default"] and min_bst <= sum(e["stats"].values()) <= max_bst
            and (legendary or not (e["legendary"] or e["mythical"])) and e["learn"]]
    picks, seen = [], set()
    rng.shuffle(pool)
    legend_used = False
    for e in pool:
        if e["species"] in seen:
            continue
        is_legend = e["legendary"] or e["mythical"]
        if is_legend and legend_used:  # Legend Clause
            continue
        # keep teams type-diverse
        if sum(1 for p in picks if set(p["types"]) & set(e["types"])) >= 2:
            continue
        picks.append(e)
        seen.add(e["species"])
        legend_used |= is_legend
        if len(picks) == size:
            break
    items = list(COMP_ITEMS)
    rng.shuffle(items)
    out, mega_used = [], False
    for e in picks:
        m = auto_member(dex, e, rng, items, allow_mega=not mega_used, level=level)
        mega_used |= m.item == "mega-stone"
        out.append(m)
    return out


# ---------------------------------------------------------------- Showdown import/export

def export_showdown(dex, members):
    blocks = []
    for m in members:
        e = dex.all[m.species]
        lines = [f"{e['name']}" + (f" @ {m.item_name(dex)}" if m.item != "none" else "")]
        if m.ability:
            lines.append(f"Ability: {m.ability.replace('-', ' ').title()}")
        if m.level != 100:
            lines.append(f"Level: {m.level}")
        if m.tera:
            lines.append(f"Tera Type: {m.tera.title()}")
        evs = " / ".join(f"{v} {STAT_NAMES[k]}" for k, v in m.evs.items() if v)
        if evs:
            lines.append(f"EVs: {evs}")
        lines.append(f"{m.nature} Nature")
        lines += [f"- {dex.moves[mv]['name']}" for mv in m.moves if mv in dex.moves]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def _find_item(dex, name, entry):
    low = name.strip().lower()
    for k, (n, _) in ITEMS.items():
        if n.lower() == low or k == low.replace(" ", "-"):
            return k, None
    for form_id in entry["megas"]:
        if mega_item_name(dex, dex.all[form_id]).lower() == low:
            return "mega-stone", form_id
    return "none", None


def import_showdown(dex, text):
    """Parse Pokemon Showdown team text. Unknown moves/items are skipped. Returns (members, warnings)."""
    members, warnings = [], []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue
        head = lines[0]
        item_name = None
        if "@" in head:
            head, item_name = [x.strip() for x in head.split("@", 1)]
        head = re.sub(r"\((M|F)\)", "", head).strip()
        m = re.search(r"\(([^)]+)\)", head)
        species_name = m.group(1) if m else head
        entry = dex.get(species_name)
        if entry is None:
            warnings.append(f"Unknown Pokemon: {species_name}")
            continue
        if entry["transform"] and entry.get("base"):
            entry = dex.all[entry["base"]]
        item, mega = _find_item(dex, item_name, entry) if item_name else ("none", None)
        if item_name and item == "none":
            warnings.append(f"Item not supported: {item_name}")
        evs, nature, moves, level, ability, tera = {}, "Serious", [], 100, None, None
        for l in lines[1:]:
            if l.startswith("Ability:"):
                key = l.split(":", 1)[1].strip().lower().replace(" ", "-").replace("'", "")
                if key in [a for a, _ in entry["abilities"]]:
                    ability = key
                else:
                    warnings.append(f"{entry['name']}: ability not available: {l.split(':', 1)[1].strip()}")
            elif l.startswith("Tera Type:"):
                t = l.split(":", 1)[1].strip().lower()
                tera = t if t in TYPES else None
            elif l.startswith("EVs:"):
                for part in l[4:].split("/"):
                    num, stat = part.strip().split(" ", 1)
                    for k, n in STAT_NAMES.items():
                        if n.lower() == stat.strip().lower():
                            evs[k] = int(num)
            elif l.endswith("Nature"):
                nature = l.split()[0] if l.split()[0] in NATURES else "Serious"
            elif l.startswith("Level:"):
                level = max(1, min(100, int(l.split(":")[1])))
            elif l.startswith("-"):
                mv = dex.move(l[1:].strip().split("[")[0].strip())
                if mv and mv["id"] in entry["learn"]:
                    moves.append(mv["id"])
                else:
                    warnings.append(f"{entry['name']}: move not supported: {l[1:].strip()}")
        if not moves:
            moves = auto_moves(dex, entry, random.Random(entry["id"]))
        members.append(Member(entry["id"], moves, item, nature, evs or None, mega, level,
                              ability or best_ability(entry), tera))
    return members[:6], warnings


# ---------------------------------------------------------------- saving

def load_saved():
    try:
        with open(TEAMS_FILE) as f:
            data = json.load(f)
        return {name: [Member.from_dict(d) for d in team] for name, team in data.items()}
    except (OSError, ValueError, KeyError):
        return {}


def save_team(name, members):
    teams = load_saved()
    teams[name] = members
    os.makedirs(HOME, exist_ok=True)
    with open(TEAMS_FILE, "w") as f:
        json.dump({n: [m.to_dict() for m in t] for n, t in teams.items()}, f, indent=1)


def delete_team(name):
    teams = load_saved()
    teams.pop(name, None)
    with open(TEAMS_FILE, "w") as f:
        json.dump({n: [m.to_dict() for m in t] for n, t in teams.items()}, f, indent=1)


def type_matchup_summary(types_list):
    """For the team builder: how many team members are weak to each attacking type."""
    return {t: sum(1 for ts in types_list if effectiveness(t, ts) > 1) for t in TYPES}
