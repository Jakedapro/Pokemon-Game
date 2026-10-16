"""Adventure mode: the rules and the world. Your party (levels, XP, moves, evolution), the bag, money, badges,
the save file, and the Brawl region - 20 towns joined by routes, 18 gyms, Victory Road and the Pokemon League.

Everything here is plain data + logic (no drawing), so it can be tested headless. The screens live in
overworld.py and adventure_ui.py.
"""
import json
import math
import os
import random
import time

from .pokedex import HOME
from .team import Member, NATURES, best_ability

SAVE_FILE = os.path.join(HOME, "adventure.json")
MAX_LEVEL = 100
SHINY_ODDS = 200     # 1 in 200: rare, but you'll see some

STARTERS = {1: [1, 4, 7]}   # Bulbasaur, Charmander, Squirtle

# ====================================================================== new-game options
OPTION_DEFS = [("difficulty", "DIFFICULTY", ["EASY", "NORMAL", "HARD", "INSANE"]),
               ("gender", "PLAYER", ["BOY", "GIRL"]),
               ("text", "TEXT SPEED", ["SLOW", "MID", "FAST"]),
               ("scene", "BATTLE SCENE", ["ON", "OFF"]),
               ("sound", "SOUND", ["ON", "OFF"])]
# unlocked by becoming World Champion once
RANDOM_DEFS = [("random", "RANDOMIZER", ["OFF", "ON"]),
               ("r_wild", "WILD ENCOUNTERS", ["SIMILAR", "ANY"]),
               ("r_starters", "STARTERS", ["RANDOM", "KANTO"]),
               ("r_trainers", "TRAINER TEAMS", ["RANDOM", "SAME"]),
               ("r_types", "GYM TYPES", ["KEEP", "RANDOM"]),
               ("r_legends", "WILD LEGENDS", ["NO", "YES"])]
DIFFICULTY = {   # EXP multiplier, trainer level bonus, wild level bonus, AI step, shop prices
    "EASY": {"exp": 0.9, "lv": -2, "wild": 0, "ai": -1, "price": 1.0},
    "NORMAL": {"exp": 0.6, "lv": 2, "wild": 0, "ai": 0, "price": 1.0},
    "HARD": {"exp": 0.5, "lv": 5, "wild": 2, "ai": 1, "price": 1.25},
    "INSANE": {"exp": 0.42, "lv": 9, "wild": 4, "ai": 2, "price": 1.5},
}
AI_STEPS = ["easy", "normal", "hard", "insane"]
OPTS = {}    # the options of the game being played (set by use_options)


def default_options():
    o = {k: vals[1 if k in ("difficulty", "text") else 0] for k, _, vals in OPTION_DEFS + RANDOM_DEFS}
    o["rseed"] = random.randrange(1 << 30)
    return o


def migrate(game):
    """Saves from the first, 8-gym region: move them to the same places on the 18-gym map."""
    if game.get("keystone") and "mega-radar" not in game.get("bag", {}):   # the radar came out after the Key Stone
        game.setdefault("bag", {})["mega-radar"] = 1
    if game.get("world", 1) >= 2:
        return

    def new_index(a):
        if a % 2 == 0:
            return 2 * LEGACY.get(a // 2, a // 2)
        return 2 * LEGACY.get((a + 1) // 2, (a + 1) // 2) - 1
    game["area"] = new_index(game.get("area", 0))
    if game.get("center"):
        game["center"][0] = new_index(game["center"][0])
    if game.get("room"):
        game["room"]["area"] = new_index(game["room"]["area"])
    game["world"] = 2


def use_options(game):
    """Make this save's options the current ones (text speed, sound, the player's look...)."""
    OPTS.clear()
    OPTS.update(default_options())
    OPTS.update(game.get("opts") or {"difficulty": "EASY"})   # saves from before options were easy-going
    from . import cast, gbaui
    from .audio import AUDIO
    gbaui.TEXT_SPEED = {"SLOW": 30, "MID": 60, "FAST": 150}[OPTS["text"]]
    on = OPTS["sound"] == "ON"
    AUDIO.set_volumes(sfx=0.8 if on else 0.0, music=0.5 if on else 0.0, cry=0.8 if on else 0.0)
    cast.set_player(OPTS["gender"])


def diff():
    return DIFFICULTY.get(OPTS.get("difficulty", "NORMAL"), DIFFICULTY["NORMAL"])


def randomized(part=None):
    if OPTS.get("random") != "ON":
        return False
    return part is None or OPTS.get(part) in ("RANDOM", "ANY", "SIMILAR")


def starters(dex):
    """The three starters for this game: Kanto's, or three random ones with the randomizer."""
    if not randomized("r_starters"):
        return STARTERS[1]
    rng = random.Random(OPTS["rseed"] + 1)
    pool = [e["id"] for e in dex.all.values() if e["default"] and not e["transform"] and e.get("lvl") and
            not (e["legendary"] or e["mythical"]) and e["species"] not in SPECIAL_IDS and e.get("evo") and
            sum(e["stats"].values()) <= 330]
    return rng.sample(sorted(pool), 3)

def rival_starter(dex, mine):
    """The rival always takes the starter with the type advantage over yours (FireRed: Charmander beats
    Bulbasaur, Squirtle beats Charmander, Bulbasaur beats Squirtle) - by real type matchups, so it also works with
    the randomizer's starters."""
    from .types import effectiveness
    trio = starters(dex)
    if mine not in trio:
        return None
    me = dex.all[mine]["types"]

    def edge(pid):
        them = dex.all[pid]["types"]
        attack = max(effectiveness(t, me) for t in them)
        defend = max(effectiveness(t, them) for t in me)
        return (attack - defend, attack, -defend, -trio.index(pid))
    return max((p for p in trio if p != mine), key=edge)


# shop: key -> (name, price, description)
SHOP = {
    "poke-ball": ("Poke Ball", 200, "Catches wild Pokemon"),
    "great-ball": ("Great Ball", 600, "Better catch rate"),
    "ultra-ball": ("Ultra Ball", 1200, "Even better catch rate"),
    "potion": ("Potion", 300, "Restores 20 HP"),
    "super-potion": ("Super Potion", 700, "Restores 60 HP"),
    "hyper-potion": ("Hyper Potion", 1200, "Restores 120 HP"),
    "full-heal": ("Full Heal", 400, "Cures any status problem"),
    "revive": ("Revive", 1500, "Revives a fainted Pokemon"),
    "max-potion": ("Max Potion", 2500, "Fully restores HP"),
    "full-restore": ("Full Restore", 3000, "Full HP and cures status"),
    "max-revive": ("Max Revive", 4000, "Revives with full HP"),
    "master-ball": ("Master Ball", 0, "Never fails"),
    "rare-candy": ("Rare Candy", 4800, "Raises a Pokemon's level by 1"),
}
# what the Mart sells after N badges
MART_STOCK = [(0, ["poke-ball", "potion", "full-heal"]), (1, ["super-potion", "revive"]),
              (2, ["great-ball"]), (4, ["ultra-ball", "hyper-potion"]), (6, ["max-potion", "full-restore"]),
              (7, ["max-revive"])]
BALL_KEYS = ["poke-ball", "great-ball", "ultra-ball", "master-ball"]

GYMS = [  # (town, leader, type, ace level, intro line, defeat line, badge) - one Gym for every type
    ("Pebblecrest City", "Petra", "rock", 13, "My Pokemon are as hard as the mountain. Can you crack them?",
     "You shattered my defence! The Crest Badge is yours.", "Crest Badge"),
    ("Mossgrove Town", "Hive", "bug", 16, "Every bug in this forest answers to me. Buzz off - or battle!",
     "My swarm... scattered! Here, the Hive Badge.", "Hive Badge"),
    ("Tidewater City", "Coral", "water", 19, "The tide is turning... against you!",
     "You rode the wave. The Tide Badge is yours.", "Tide Badge"),
    ("Hearthvale Town", "Patty", "normal", 22, "Nothing fancy here. Just good, honest, NORMAL power!",
     "Well, aren't you something special. The Hearth Badge.", "Hearth Badge"),
    ("Voltara City", "Zappa", "electric", 25, "Hope you like getting shocked, kid!",
     "Whoa, you're charged up! Take the Spark Badge.", "Spark Badge"),
    ("Gustcliff City", "Skye", "flying", 28, "Up here, the wind decides who wins. Today it's blowing my way!",
     "You flew higher than me. The Gale Badge is yours.", "Gale Badge"),
    ("Bloomfield City", "Fern", "grass", 31, "Let's see if you can weather my garden.",
     "Your team bloomed beautifully. The Bloom Badge.", "Bloom Badge"),
    ("Brawlport City", "Knox", "fighting", 34, "Talk is cheap. Fists up!",
     "Hah! Now THAT was a fight! The Fist Badge, champ.", "Fist Badge"),
    ("Toxmire Town", "Nox", "poison", 37, "Breathe in. Now panic.", "Tch. Fine. The Venom Badge.",
     "Venom Badge"),
    ("Glimmerdell Town", "Pixie", "fairy", 40, "Aww, you're adorable! My Pokemon are going to destroy you~",
     "Hmph! Cute AND strong? Take the Charm Badge.", "Charm Badge"),
    ("Mindspire City", "Sage", "psychic", 43, "I already know how this ends.",
     "...I did not see that coming. The Mind Badge.", "Mind Badge"),
    ("Duskmoor Town", "Wren", "ghost", 46, "Shh... the spirits here don't like noise. Or visitors.",
     "The spirits... have chosen you. The Shade Badge.", "Shade Badge"),
    ("Emberpeak City", "Blaze", "fire", 49, "Hope you packed water. You'll need it!",
     "You put out my fire! The Ember Badge.", "Ember Badge"),
    ("Steelhaven City", "Ferris", "steel", 52, "My team is forged, tempered and polished. Yours?",
     "You found a crack in the armour. The Forge Badge.", "Forge Badge"),
    ("Frostmere Town", "Nieve", "ice", 55, "Cold hands, colder Pokemon. Shall we?",
     "You melted my heart... a little. The Glacier Badge.", "Glacier Badge"),
    ("Shadegate City", "Raven", "dark", 58, "Nobody beats me in the dark. Lights out.",
     "...You see well in the dark. The Eclipse Badge.", "Eclipse Badge"),
    ("Duneholt City", "Terra", "ground", 60, "Only the strongest reach the League. Show me.",
     "You are ready. Take the Earth Badge.", "Earth Badge"),
    ("Wyrmspire City", "Draco", "dragon", 62, "Dragons are the last test before the League. Most fail it.",
     "A true dragon tamer. The Wyrm Badge - the League awaits.", "Wyrm Badge"),
]
LEAGUE_TOWN = len(GYMS) + 1                   # town index of the Pokemon League
NUM_ROUTES = len(GYMS) + 1                    # the last one is Victory Road
# where the towns and routes of the first (8-gym) region ended up: old town / route number -> new one
LEGACY = {1: 1, 2: 3, 3: 5, 4: 7, 5: 9, 6: 11, 7: 13, 8: 17, 9: LEAGUE_TOWN}
CHAMPION = ("Aurelia", 72, "So you're the one who beat all eighteen gyms. I'm the Champion. Let's make it a "
            "battle worth remembering!", "Incredible... You are the new Champion of the Brawl region!")


def route_types(r):
    """The types of wild Pokemon on route r: the next Gym's type, the last one's, and a common mix."""
    if r >= NUM_ROUTES:
        return ["dragon", "steel", "fighting", "ice", "ghost", "dark"]
    ahead = GYMS[r - 1][2]
    behind = GYMS[r - 2][2] if r >= 2 else "normal"
    common = [["normal", "bug", "flying"], ["grass", "water", "normal"], ["rock", "ground", "fighting"],
              ["psychic", "dark", "steel"]][min(3, (r - 1) // 5)]
    return list(dict.fromkeys([ahead, behind] + common))


TRAINER_CLASSES = ["Youngster", "Lass", "Bug Catcher", "Hiker", "Swimmer", "Ace Trainer", "Psychic", "Black Belt",
                   "Picnicker", "Fisher", "Biker", "Beauty"]
TRAINER_NAMES = ["Joey", "Mia", "Leo", "Ava", "Sam", "Kai", "Zoe", "Ben", "Ivy", "Max", "Lily", "Tom", "Nia", "Eli",
                 "Ruby", "Finn", "Jade", "Owen", "Rosa", "Dex", "Luna", "Jax", "Cleo", "Rex"]


# ====================================================================== Pokemon in your party
# Ultra Beasts and Paradox Pokemon don't show up on ordinary trainers' teams or in the wild
SPECIAL_IDS = set(range(793, 800)) | set(range(803, 807)) | set(range(984, 996)) | set(range(1005, 1011)) | \
    set(range(1020, 1026))


def xp_for(level):
    """Total experience needed for a level (the 'medium fast' curve)."""
    return level ** 3 if level > 1 else 0


def moves_at(dex, entry, level):
    """The 4 moves a wild Pokemon knows at a level: its most recent level-up moves."""
    learned = [m for lv, m in entry.get("lvl", []) if lv <= level and m in dex.moves]
    seen, out = set(), []
    for m in reversed(learned):
        if m not in seen:
            seen.add(m)
            out.append(m)
    out = out[:4][::-1]
    if not any(dex.moves[m]["power"] for m in out):  # always something that does damage
        tackle = dex.move("tackle")
        if tackle:
            out = (out + [tackle["id"]])[-4:]
    return out or [dex.move("tackle")["id"]]


def make_mon(dex, entry, level, rng, shiny=None, origin=""):
    level = max(1, min(MAX_LEVEL, int(level)))
    abil = [a for a, hidden in entry.get("abilities", []) if not hidden] or [best_ability(entry)]
    return {"species": entry["id"], "level": level, "xp": xp_for(level), "moves": moves_at(dex, entry, level),
            "cur_hp": None, "status": None, "pp": None, "nature": rng.choice(sorted(NATURES)),
            "ability": rng.choice(abil), "shiny": rng.randrange(SHINY_ODDS) == 0 if shiny is None else shiny,
            "nick": None, "origin": origin, "met": level}


def mega_form_for(dex, mon, game):
    """The Mega form this Pokemon can use: you need the Key Stone and its Mega Stone (or a corrupted one)."""
    if not game or not game.get("keystone"):
        return None
    owned = set(game.get("megastones", [])) | set(game.get("corrupted", []))
    for fid in dex.all[mon["species"]].get("megas", []):
        f = dex.all.get(fid)
        if f and "primal" not in f["key"] and f["key"] in owned:
            return fid
    return None


def uses_corrupted(game, key):
    """A corrupted stone is used when it's the only one you have, or you switched it on in the MEGA STONES list."""
    if key not in game.get("corrupted", []):
        return False
    return key not in game.get("megastones", []) or key in game.get("corrupt_on", [])


def member(mon, game=None, dex=None):
    """A battle-engine Member for a party Pokemon (no EVs, like a real playthrough). With the game state, a
    Pokemon whose Mega Stone you own holds it."""
    if dex is not None:
        from .riftdex import RIFT_MOVE_ID, install
        install(dex)
    mega = mega_form_for(dex, mon, game) if dex is not None else None
    m = Member(mon["species"], mon["moves"], "mega-stone" if mega else "none", mon.get("nature", "Serious"),
               {"hp": 0}, mega, mon["level"], mon.get("ability"))
    m.cur_hp, m.status, m.pp = mon.get("cur_hp"), mon.get("status"), mon.get("pp")
    if mega and game:
        m.corrupted = uses_corrupted(game, dex.all[mega]["key"])
    if mon.get("rift_born") and dex is not None:
        m.rift_move = RIFT_MOVE_ID
    return m


def stats(dex, mon):
    from .team import calc_stats
    return calc_stats(dex.all[mon["species"]], member(mon))


def max_hp(dex, mon):
    return stats(dex, mon)["hp"]


def hp_of(dex, mon):
    mx = max_hp(dex, mon)
    return mx if mon.get("cur_hp") is None else max(0, min(mx, mon["cur_hp"])), mx


def fainted(dex, mon):
    return hp_of(dex, mon)[0] <= 0


def heal(mon):
    mon["cur_hp"], mon["status"], mon["pp"] = None, None, None


def name_of(dex, mon):
    if mon.get("nick"):
        return mon["nick"]
    from .tournament import short_name
    return short_name(dex.all[mon["species"]])


def xp_yield(dex, foe_species, foe_level, my_level, trainer=False):
    """Experience for defeating a Pokemon (Gen 5 style: more for beating stronger Pokemon), scaled by
    the difficulty."""
    b = dex.all[foe_species].get("bxp", 60)
    gain = (b * foe_level / 5) * ((2 * foe_level + 10) / (foe_level + my_level + 10)) ** 2.5 + 1
    return int(gain * (1.5 if trainer else 1.0) * diff()["exp"])


def move_score(dex, mid):
    mv = dex.moves[mid]
    return (mv["power"] or 35) * (min(100, mv["acc"]) / 100)


def gain_xp(dex, mon, amount):
    """Adds experience. Returns what happened, in order: ('level', n), ('learn', move, forgot or None),
    ('evolve', new species id)."""
    events = []
    if mon["level"] >= MAX_LEVEL:
        return events
    mon["xp"] += amount
    while mon["level"] < MAX_LEVEL and mon["xp"] >= xp_for(mon["level"] + 1):
        old_max = max_hp(dex, mon)
        mon["level"] += 1
        if mon.get("cur_hp") is not None:   # leveling up adds the HP it gained
            mon["cur_hp"] = min(max_hp(dex, mon), mon["cur_hp"] + max_hp(dex, mon) - old_max)
        events.append(("level", mon["level"]))
        events += learn_new(dex, mon, mon["level"])
    evo = evolution_for(dex, mon)
    if evo:
        events.append(("evolve", evo))
    return events


def learn_new(dex, mon, level, entry=None):
    entry = entry or dex.all[mon["species"]]
    out = []
    for lv, mid in entry.get("lvl", []):
        if lv != level or mid in mon["moves"] or mid not in dex.moves:
            continue
        if len(mon["moves"]) < 4:
            mon["moves"].append(mid)
            if mon.get("pp"):
                mon["pp"].append(dex.moves[mid]["pp"])
            out.append(("learn", mid, None))
            continue
        # full: forget the weakest move if the new one is better (a damaging move always beats a status move)
        worst = min(range(4), key=lambda i: move_score(dex, mon["moves"][i]))
        new_dmg = bool(dex.moves[mid]["power"])
        damaging = [m for m in mon["moves"] if dex.moves[m]["power"]]
        if move_score(dex, mid) > move_score(dex, mon["moves"][worst]) and (new_dmg or len(damaging) > 2):
            forgot = mon["moves"][worst]
            mon["moves"][worst] = mid
            if mon.get("pp"):
                mon["pp"][worst] = dex.moves[mid]["pp"]
            out.append(("learn", mid, forgot))
    return out


def evolution_for(dex, mon):
    entry = dex.all[mon["species"]]
    for to, lv in entry.get("evo", []):
        if mon["level"] >= lv and to in dex.all:
            return to
    return None


def evolve(dex, mon, to):
    hp, mx = hp_of(dex, mon)
    mon["species"] = to
    if mon.get("cur_hp") is not None:
        mon["cur_hp"] = hp + max_hp(dex, mon) - mx
    return learn_new(dex, mon, mon["level"])  # moves an evolution learns right away


def grown_species(dex, entry, level):
    """The species a Pokemon would be at this level (Charmander at 40 -> Charizard)."""
    seen = set()
    while entry["id"] not in seen:
        seen.add(entry["id"])
        nxt = [dex.all[t] for t, lv in entry.get("evo", []) if lv <= level and t in dex.all]
        if not nxt:
            break
        entry = nxt[0]
    return entry


# ====================================================================== the world
TILE = 48
COLS = 15


def _empty(h, fill="."):
    return [[fill] * COLS for _ in range(h)]


def _put(grid, x, y, block):
    for dy, row in enumerate(block):
        for dx, ch in enumerate(row):
            if ch != " " and 0 <= y + dy < len(grid) and 0 <= x + dx < COLS:
                grid[y + dy][x + dx] = ch


def _bld(body, door, w, h, dx, dy):
    return [body * w if y != dy else body * dx + door + body * (w - dx - 1) for y in range(h)]


# footprints match the FireRed buildings they're drawn with (see fieldmap.STAMPS)
BUILDINGS = {
    "C": _bld("c", "C", 5, 4, 2, 3),   # Pokemon Center
    "M": _bld("m", "M", 4, 4, 2, 3),   # Poke Mart
    "G": _bld("g", "G", 6, 5, 3, 4),   # Gym
    "H": _bld("h", "D", 5, 5, 1, 4),   # house
    "L": _bld("l", "L", 11, 7, 5, 6),  # Pokemon League
    "P": _bld("p", "P", 7, 5, 3, 4),   # Professor's lab
}


def town_map(i, rng):
    """A town: path down the middle, Center + Mart + houses, a gym (except the hometown)."""
    h = 28
    g = _empty(h)
    for y in range(h):
        g[y][0] = g[y][COLS - 1] = "#"
        for x in (6, 7, 8):
            g[y][x] = "="
    for x in range(1, COLS - 1):  # a cross street
        g[13][x] = "="
    if i == 0:
        _put(g, 1, 3, BUILDINGS["H"])
        _put(g, 9, 3, BUILDINGS["H"])
        _put(g, 1, 15, BUILDINGS["P"])
        _put(g, 9, 21, BUILDINGS["H"])
        _put(g, 5, 9, ["S"])
        g[8][2] = g[8][10] = g[20][4] = g[26][10] = "="   # doorsteps
        g[h - 1] = ["#"] * COLS     # the hometown is the south end of the region
    elif i == LEAGUE_TOWN:
        _put(g, 2, 1, BUILDINGS["L"])
        _put(g, 1, 15, BUILDINGS["C"])
        _put(g, 10, 15, BUILDINGS["M"])
        g[0] = ["#"] * COLS
        g[19][3] = g[19][12] = "="
    else:
        _put(g, 1, 1, BUILDINGS["C"])
        _put(g, 10, 1, BUILDINGS["M"])
        _put(g, 8, 8, BUILDINGS["G"])
        _put(g, 1, 7, BUILDINGS["H"])
        _put(g, 1, 16, BUILDINGS["H"])
        _put(g, 9, 16, BUILDINGS["H"])
        _put(g, 5, 14, ["S"])
        for x in range(3, 13):        # a little square in front of the Center and Mart
            g[5][x] = "="
        g[12][2] = g[21][2] = g[21][10] = "="
    # decoration: flowers and the odd tree on empty ground
    for y in range(h):
        for x in range(1, COLS - 1):
            if g[y][x] == "." and rng.random() < 0.12:
                g[y][x] = ","
            elif g[y][x] == "." and rng.random() < 0.03 and x not in (5, 9):
                g[y][x] = "t"
    _theme(i, g, rng)
    _clear_doorsteps(g)
    return ["".join(r) for r in g]


def _clear_doorsteps(g):
    """Whatever a town's look added (water, trees, rocks, fences, ledges), every door keeps a way to the road."""
    for y, row in enumerate(g):
        for x, ch in enumerate(row):
            if ch in "CMGDPL" and y + 1 < len(g):
                step = y + 1
                if g[step][x] in "~#rfv":
                    g[step][x] = "="
                d = 1 if x < 7 else -1
                xx = x
                while 0 < xx < COLS - 1 and g[step][xx] not in "=" or xx == x:
                    if g[step][xx] in "~#rfv":
                        g[step][xx] = "."
                    if xx in (6, 7, 8):
                        break
                    xx += d


def _theme(i, g, rng):
    """Every town looks like itself: a seaside, a power town, flower fields, a swamp, a desert..."""
    h = len(g)

    def paint(ch, x0, y0, x1, y1, odds=1.0, over=".,t"):
        for y in range(max(0, y0), min(h, y1 + 1)):
            for x in range(max(1, x0), min(COLS - 1, x1 + 1)):
                if g[y][x] in over and rng.random() < odds:
                    g[y][x] = ch

    def at(ch, *cells):
        for x, y in cells:
            if 0 <= y < h and g[y][x] in ".,t":
                g[y][x] = ch
    look = "home" if i == 0 else "league" if i == LEAGUE_TOWN else GYMS[i - 1][2]
    if look == "home":       # Rootleaf: little fenced gardens and a pond
        paint("f", 1, 10, 4, 10), paint("f", 10, 10, 13, 10)
        paint(",", 1, 11, 4, 12), paint(",", 10, 11, 13, 12)
        paint("~", 1, 22, 4, 24)
    elif look == "rock":     # Pebblecrest: boulders everywhere and ledges down the hill
        at("r", (1, 0), (2, 0), (12, 0), (11, 6), (2, 6), (12, 14), (11, 15), (12, 22), (2, 24), (3, 26), (11, 26))
        paint("v", 1, 23, 5, 23), paint("v", 9, 23, 13, 23)
    elif look == "water":    # Tidewater: a beach and the open sea
        paint("_", 9, 14, 9, h - 1, over=".,thD="), paint("~", 10, 14, 13, h - 1, over=".,thD=")
        for y in range(14, h):
            g[y][COLS - 1] = "~"      # the sea runs off the edge of the map
        paint("_", 1, 24, 5, h - 1)
    elif look == "electric":  # Voltara: fenced power lots and a wide plaza
        paint("f", 1, 22, 5, 22), paint("f", 9, 22, 13, 22), paint("f", 9, 6, 13, 6)
        paint("=", 1, 14, 5, 15), paint("=", 9, 14, 13, 15)
        at("r", (1, 24), (13, 24), (1, 26), (13, 26))
    elif look == "grass":    # Bloomfield: flower fields
        paint(",", 1, 0, 13, h - 1, 0.75, over=".")
        paint("t", 1, 14, 2, 15)
    elif look == "poison":   # Toxmire: a swamp
        paint("~", 1, 22, 4, 25), paint("~", 10, 23, 13, 26), paint("~", 11, 14, 13, 15)
        paint('"', 1, 26, 5, h - 1, 0.7), paint('"', 9, 21, 13, 22, 0.7)
    elif look == "psychic":  # Mindspire: neat and symmetrical
        for y in range(14, h, 2):
            at("t", (5, y), (9, y))
        paint(",", 1, 22, 4, 26, 0.6), paint(",", 10, 22, 13, 26, 0.6)
    elif look == "fire":     # Emberpeak: rocky ground and ash
        paint("_", 9, 22, 13, h - 1), paint("r", 1, 22, 5, h - 1, 0.25), paint("r", 9, 22, 13, h - 1, 0.2)
        paint("v", 1, 21, 5, 21)
    elif look == "ground":   # Duneholt: a desert town
        paint("_", 1, 0, 13, h - 1, over=".,t")
        paint("r", 1, 0, 13, h - 1, 0.06, over="_")
    elif look == "bug":      # Mossgrove: a town in the woods, tall grass growing right up to the houses
        paint('"', 1, 21, 5, h - 1, 0.8), paint('"', 9, 21, 13, h - 1, 0.8)
        paint("t", 1, 0, 13, h - 1, 0.18, over=".,")
    elif look == "normal":   # Hearthvale: a tidy village green
        paint("f", 1, 22, 5, 22), paint("f", 9, 22, 13, 22)
        paint(",", 2, 24, 4, 26, 0.5), paint(",", 10, 24, 12, 26, 0.5)
    elif look == "flying":   # Gustcliff: windswept terraces - ledges stepping down the cliff
        for y in (15, 19, 23):
            paint("v", 1, y, 5, y), paint("v", 9, y, 13, y)
    elif look == "fighting":  # Brawlport: a dojo yard of rocks and sand
        paint("_", 1, 21, 5, h - 1), paint("_", 9, 21, 13, h - 1)
        paint("r", 1, 21, 13, h - 1, 0.12, over="_")
    elif look == "fairy":    # Glimmerdell: flower gardens around a pond
        paint("~", 10, 23, 12, 25), paint(",", 1, 0, 13, h - 1, 0.45, over=".")
    elif look == "ghost":    # Duskmoor: crooked fences and lonely rocks
        paint("f", 1, 21, 4, 21), paint("f", 10, 24, 13, 24)
        paint("r", 1, 22, 13, h - 1, 0.1), paint('"', 1, 25, 5, h - 1, 0.5)
    elif look == "steel":    # Steelhaven: paved, fenced industrial lots
        paint("=", 1, 14, 5, 15), paint("=", 9, 14, 13, 15)
        paint("f", 1, 22, 5, 22), paint("f", 9, 22, 13, 22), paint("f", 1, 26, 5, 26)
    elif look == "ice":      # Frostmere: frozen lakes
        paint("~", 1, 21, 5, 25), paint("~", 9, 22, 13, 26), paint("_", 1, 26, 5, h - 1)
    elif look == "dark":     # Shadegate: hemmed in by the forest
        paint("#", 1, 22, 3, h - 1), paint("#", 10, 22, 13, h - 1)   # whole 2x2 trees (even columns / rows)
    elif look == "dragon":   # Wyrmspire: crags and a mountain lake
        paint("r", 1, 21, 5, h - 1, 0.3), paint("~", 9, 22, 13, 25), paint("v", 9, 26, 13, 26)
    elif look == "league":   # the League: a formal garden
        paint("f", 1, 9, 4, 9), paint("f", 10, 9, 13, 9)
        paint(",", 1, 10, 4, 11), paint(",", 10, 10, 13, 11)


def route_map(i, rng):
    """Route i (1-based): a winding path north with tall grass, trees, a pond and trainers."""
    h = 48 + 6 * min(i, 6)
    g = _empty(h, "#")
    x = 7
    path = []
    for y in range(h):
        if y > 2 and y < h - 3 and rng.random() < 0.35:
            x = max(3, min(11, x + rng.choice((-1, 1))))
        path.append(x)
    for y, px in enumerate(path):
        for xx in range(px - 1, px + 2):
            g[y][xx] = "="
        for xx in range(max(1, px - 4), min(COLS - 1, px + 5)):  # open ground beside the path
            if g[y][xx] == "#":
                g[y][xx] = "."
    for y in range(h):  # the exits line up with the towns' main street
        if y < 3 or y >= h - 3:
            for xx in (6, 7, 8):
                g[y][xx] = "="
    # tall grass patches
    for _ in range(4 + i // 2):
        w, hh = rng.randint(3, 6), rng.randint(3, 6)
        gx, gy = rng.randint(1, COLS - 1 - w), rng.randint(4, h - 5 - hh)
        for yy in range(gy, gy + hh):
            for xx in range(gx, gx + w):
                if g[yy][xx] in ".#":
                    g[yy][xx] = '"'
    for y in range(4, h - 4):  # some grass right on the path's edges so you can't always dodge it
        if rng.random() < 0.25:
            px = path[y]
            for xx in range(px - 1, px + 2):
                g[y][xx] = '"'
    # a pond
    if rng.random() < 0.7:
        px, py = rng.choice((1, 10)), rng.randint(6, h - 10)
        for yy in range(py, py + 3):
            for xx in range(px, px + 4):
                if 0 < xx < COLS - 1 and g[yy][xx] != "=":
                    g[yy][xx] = "~"
    # flowers on open ground
    for y in range(h):
        for xx in range(1, COLS - 1):
            if g[y][xx] == "." and rng.random() < 0.08:
                g[y][xx] = ","
    for y in range(h):
        g[y][0] = g[y][COLS - 1] = "#"
    _pair_trees(g)
    # ledges you can hop down (never across the path itself), and boulders further along
    for y in range(9, h - 6, 9):
        if rng.random() < 0.8:
            for xx in range(1, COLS - 1):
                if g[y][xx] in '.,"' and abs(xx - path[y]) > 1 and g[y + 1][xx] in '.,"':
                    g[y][xx] = "v"
    for y in range(4, h - 4):
        for xx in range(1, COLS - 1):
            if i >= 3 and g[y][xx] == "." and abs(xx - path[y]) > 1 and rng.random() < 0.025:
                g[y][xx] = "r"
    return ["".join(r) for r in g], path


def _pair_trees(g):
    """FireRed's trees are two tiles wide and two tall, on even columns and rows: grow every lone tree tile into
    its 2x2 block (only over open ground), so forests have clean edges."""
    h = len(g)
    for y0 in range(0, h - 1, 2):
        for x0 in range(0, COLS - 1, 2):
            cells = [(x0, y0), (x0 + 1, y0), (x0, y0 + 1), (x0 + 1, y0 + 1)]
            if any(g[y][x] == "#" for x, y in cells):
                for x, y in cells:
                    if g[y][x] in ".,":
                        g[y][x] = "#"


class World:
    """The whole region, generated from a fixed seed so every player gets the same map."""

    def __init__(self, dex, seed=2024):
        from .riftdex import install
        install(dex)   # our own Megas and the Rift Breaker move
        self.dex = dex
        self.areas = []      # list of dicts: name, kind, rows, npcs, items, music, level range, pool
        self._rcache = {}
        self.rand_wild = randomized("r_wild")
        self.rand_trainers = randomized("r_trainers")
        self.rseed = OPTS.get("rseed", 0)
        self.gym_types = [g[2] for g in GYMS]
        if randomized() and OPTS.get("r_types") == "RANDOM":
            types = ["normal", "fire", "water", "grass", "electric", "ice", "fighting", "poison", "ground", "flying",
                     "psychic", "bug", "rock", "ghost", "dragon", "dark", "steel", "fairy"]
            self.gym_types = random.Random(self.rseed + 7).sample(types, 8)
        rng = random.Random(seed)
        towns = ["Rootleaf Town"] + [g[0] for g in GYMS] + ["Pokemon League"]
        self._parents = {}
        for e in dex.all.values():
            for to, lv in e.get("evo", []):
                self._parents[to] = (e["id"], lv)
        for i, name in enumerate(towns):
            rows = town_map(i, random.Random(seed * 7 + i))
            area = {"name": name, "kind": "town", "rows": rows, "town": i, "npcs": self._town_npcs(i, rows, rng),
                    "items": [], "music": "town",
                    "ground": "sand" if 0 < i <= len(GYMS) and GYMS[i - 1][2] == "ground" else "grass"}
            self.areas.append(area)
            if i < len(towns) - 1:
                rows, path = route_map(i + 1, random.Random(seed * 13 + i))
                rname = f"Route {i + 1}" if i + 1 < NUM_ROUTES else "Victory Road"
                lo, hi = self.route_levels(i + 1)
                area = {"name": rname, "kind": "route", "rows": rows, "route": i + 1, "music": "route",
                        "levels": (lo, hi), "pool": self._pool(i + 1, random.Random(
                            seed * 31 + i + (self.rseed if self.rand_wild else 0)))}
                area["npcs"] = self._route_trainers(i + 1, rows, path, area, random.Random(
                    seed * 17 + i + (self.rseed if self.rand_trainers else 0)))
                area["items"] = self._route_items(i + 1, rows, path, random.Random(seed * 19 + i))
                self.areas.append(area)
        # areas run south (index 0) to north: walking off the top goes to index + 1

    @staticmethod
    def route_levels(r):
        if r >= NUM_ROUTES:   # Victory Road
            return (60, 66)
        lo = 2 + round(3.2 * (r - 1))
        return (lo, lo + 3)

    def base_form(self, pid):
        seen = set()
        while pid in self._parents and pid not in seen:
            seen.add(pid)
            pid = self._parents[pid][0]
        return pid

    def _pool(self, r, rng):
        lo, hi = self.route_levels(r)
        cand = []
        types = route_types(r)
        cap = 330 + 16 * r
        starters = {i for trio in STARTERS.values() for i in trio}
        for e in self.dex.all.values():
            if e["id"] in starters or e["species"] in SPECIAL_IDS:
                continue
            if not e["default"] or e["transform"] or e["legendary"] or e["mythical"] or not e.get("lvl"):
                continue
            if not any(t in types for t in e["types"]):
                continue
            par = self._parents.get(e["id"])
            if par is None:            # a first-stage Pokemon
                if sum(e["stats"].values()) <= cap:
                    cand.append(e["id"])
            elif par[1] <= hi and self._parents.get(par[0]) is None and r >= 7:   # middle stages later on
                cand.append(e["id"])
        rng.shuffle(cand)
        pool = sorted(set(cand[:14 + r // 2]))
        if self.rand_wild:   # the randomizer: every slot becomes something else
            pool = sorted({self._random_species(p, rng) for p in pool})
        return pool or [16, 19]

    # -------------------------------------------------------------- the randomizer
    def _random_choices(self, legends):
        key = ("rc", legends)
        if key not in self._rcache:
            self._rcache[key] = sorted(e["id"] for e in self.dex.all.values()
                                       if e["default"] and not e["transform"] and e.get("lvl") and
                                       e["species"] not in SPECIAL_IDS and
                                       (legends or not (e["legendary"] or e["mythical"])))
        return self._rcache[key]

    def _random_species(self, pid, rng, legends=None):
        """A random replacement: of similar strength (within about 12% total stats), or anything."""
        legends = OPTS.get("r_legends") == "YES" if legends is None else legends
        choices = self._random_choices(legends)
        if OPTS.get("r_wild") == "ANY":
            return rng.choice(choices)
        bst = sum(self.dex.all[pid]["stats"].values())
        near = [c for c in choices if abs(sum(self.dex.all[c]["stats"].values()) - bst) <= bst * 0.12]
        return rng.choice(near or choices)

    def wild_species(self, area, rng):
        return rng.choice(area["pool"])

    def team_for(self, types, level, size, rng, strong=False):
        """A trainer's team of `size` Pokemon of these types, grown up to the right stage for their level."""
        if self.rand_trainers:   # the randomizer: any type at all
            types = None
        pool = [e for e in self.dex.all.values() if e["default"] and not e["transform"] and e.get("lvl") and
                not (e["legendary"] or e["mythical"]) and (types is None or any(t in types for t in e["types"])) and
                self.base_form(e["id"]) == e["id"] and e["species"] not in SPECIAL_IDS]
        if strong:
            pool.sort(key=lambda e: -sum(grown_species(self.dex, e, 100)["stats"].values()))
            pool = pool[:30]
        rng.shuffle(pool)
        out = []
        for k, e in enumerate(pool[:size]):
            lv = max(2, level - (size - 1 - k) * (2 if strong else 1))
            grown = grown_species(self.dex, e, lv + (8 if strong else 0))
            out.append(make_mon(self.dex, grown, lv, rng, shiny=False))
        return out

    def _route_trainers(self, r, rows, path, area, rng):
        lo, hi = area["levels"]
        npcs = []
        h = len(rows)
        count = {1: 0, 2: 1}.get(r, 2 + r // 6)   # FireRed: no trainers on the first route, then it builds up
        ys = sorted(rng.sample(range(6, h - 6), min(h - 12, count)))
        last = -9
        for y in ys:
            if y - last < 4:
                continue
            last = y
            px = path[y]
            side = rng.choice((-1, 1))
            x = px + side * 2
            if not (1 <= x <= COLS - 2) or rows[y][x] in "~#vrf":
                continue
            cls = rng.choice(TRAINER_CLASSES)
            nm = rng.choice(TRAINER_NAMES)
            size = rng.randint(1, min(3, 1 + r // 2))
            team = self.team_for(self.dex.all[self.wild_species(area, rng)]["types"], hi + (1 if r > 2 else 0),
                                 size, rng)
            npcs.append({"id": f"r{r}-{y}", "kind": "trainer", "x": x, "y": y, "face": "left" if side > 0 else "right",
                         "name": f"{cls} {nm}", "cls": cls, "team": team, "sight": 4,
                         "intro": rng.choice(["Hey! Our eyes met - that means battle!", "You look tough. Let's see!",
                                              "I just caught a new Pokemon. Wanna see?", "Don't go easy on me!",
                                              "My Pokemon have been training all day!"]),
                         "lose": rng.choice(["Aww, I lost!", "You're really strong!", "Back to training...",
                                             "How did you do that?!"]),
                         "money": 30 * (hi + 1) * size})
        return npcs

    def _route_items(self, r, rows, path, rng):
        items = []
        loot = ["potion", "poke-ball", "super-potion", "great-ball", "revive", "full-heal", "hyper-potion",
                "ultra-ball", "max-potion", "full-restore"]
        for k in range(2):
            for _ in range(30):
                y = rng.randint(4, len(rows) - 5)
                x = rng.randint(1, COLS - 2)
                if rows[y][x] in ".,\"" and abs(x - path[y]) > 1:
                    item = loot[min(len(loot) - 1, (r - 1) // 2 + k + rng.randint(0, 1))]
                    items.append({"id": f"i{r}-{k}", "x": x, "y": y, "item": item, "count": rng.randint(1, 3)})
                    break
        return items

    def _town_npcs(self, i, rows, rng):
        lines = [
            "Tall grass is full of wild Pokemon. Walk through it and they'll jump out!",
            "Weaken a wild Pokemon before you throw a Poke Ball. Sleep and paralysis help too!",
            "The Pokemon Center heals your team for free. Go there if you're hurt!",
            "Trainers on the routes battle you if you walk into their line of sight.",
            "Pokemon evolve when they reach the right level. Keep battling!",
            "Super effective moves do double damage. Water beats Fire, Fire beats Grass...",
            "The gym leader here is tough. Bring Pokemon with a type advantage!",
            "Shiny Pokemon have different colors. They're super rare!",
            "Press Esc to open your menu - party, bag, Pokedex and saving.",
        ]
        npcs = []
        spots = [(x, y) for y in range(len(rows)) for x in range(1, COLS - 1) if rows[y][x] in ".," and
                 4 < y < len(rows) - 2]
        rng.shuffle(spots)
        for k, (x, y) in enumerate(spots[:2]):
            npcs.append({"id": f"t{i}-{k}", "kind": "talk", "x": x, "y": y, "face": rng.choice(("down", "left",
                                                                                              "right")),
                         "name": "", "lines": [rng.choice(lines)]})
        if i == 0:
            npcs = [n for n in npcs][:1] + [{"id": "mom", "kind": "talk", "x": 3, "y": 8, "face": "down",
                                             "name": "Mom", "lines": ["Good luck out there, sweetie!",
                                                                      "Come home if you need a rest."],
                                             "heal": True}]
        return npcs

    # -------------------------------------------------------------- gyms / league
    def gym_team(self, k):
        town, leader, typ, ace, *_ = GYMS[k]
        rng = random.Random(1000 + k + (self.rseed if self.rand_trainers else 0))
        size = min(6, 2 + (k + 2) // 3)
        team = self.team_for([self.gym_types[k]], ace, size, rng, strong=True)
        if k >= 3:   # the rifts broke the one-Mega rule: from the fourth Gym on, leaders Mega Evolve twice
            self._megafy(team, [self.gym_types[k]], rng, 2)
        return team

    def _megafy(self, team, types, rng, n):
        """Swap the last n Pokemon of a team for Mega-capable ones of these types, holding their stones."""
        cands = [e for e in self.dex.all.values() if e["default"] and not (e["legendary"] or e["mythical"]) and
                 e["species"] not in SPECIAL_IDS and any("primal" not in self.dex.all[f]["key"]
                                                         for f in e.get("megas", []) if f in self.dex.all) and
                 (types is None or self.rand_trainers or any(t in types for t in e["types"]))]
        rng.shuffle(cands)
        used = {m["species"] for m in team}
        for i in range(1, n + 1):
            if i > len(team):
                break
            mon = team[-i]
            e = self.dex.all[mon["species"]]
            if not e.get("megas"):
                pick = next((c for c in cands if c["id"] not in used), None)
                if pick is None:
                    continue
                used.add(pick["id"])
                mon = make_mon(self.dex, pick, mon["level"], rng, shiny=False)
                team[-i] = mon
                e = pick
            mon["mega"] = next(f for f in e["megas"] if f in self.dex.all and "primal" not in self.dex.all[f]["key"])

    def champion_team(self):
        rng = random.Random(4242)
        out = []
        for typ in ["dragon", "steel", "water", "fire", "psychic", "dark"]:
            out += self.team_for([typ], CHAMPION[1] - 3 + len(out), 1, rng, strong=True)
        out[-1]["level"] = CHAMPION[1] + 1
        return out


# ====================================================================== the save file
def new_game(name, starter_id, dex):
    """A fresh save. starter_id None: you choose your first Pokemon in Hazel's lab."""
    rng = random.Random()
    party = [make_mon(dex, dex.all[starter_id], 5, rng, origin="Rootleaf Town")] if starter_id else []
    got = [starter_id] if starter_id else []
    return {"v": 1, "world": 2, "name": name or "Trainer", "party": party, "box": [], "money": 3000,
            "bag": {"poke-ball": 5, "potion": 3}, "badges": [], "area": 0, "x": 7, "y": 12, "face": "up",
            "center": [0, 7, 12], "seen": list(got), "caught": list(got), "beaten": [], "picked": [],
            "playtime": 0.0, "started": int(time.time()), "champion": False}


def load():
    try:
        with open(SAVE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if data.get("name") and isinstance(data.get("party"), list) else None
    except (OSError, ValueError):
        return None


def save(data):
    os.makedirs(HOME, exist_ok=True)
    tmp = SAVE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, SAVE_FILE)


def mart_stock(badges):
    out = []
    for need, items in MART_STOCK:
        if badges >= need:
            out += items
    return out


def add_caught(game, dex, mon):
    """A new Pokemon: into the party, or the box when the party is full. Returns 'party' or 'box'."""
    for lst in ("seen", "caught"):
        if mon["species"] not in game[lst]:
            game[lst].append(mon["species"])
    if len(game["party"]) < 6:
        game["party"].append(mon)
        return "party"
    game["box"].append(mon)
    return "box"


def heal_party(game):
    for m in game["party"]:
        heal(m)


def playtime_text(seconds):
    h, m = int(seconds // 3600), int(seconds % 3600 // 60)
    return f"{h}:{m:02d}"


def lead_alive(game, dex):
    return next((m for m in game["party"] if not fainted(dex, m)), None)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ====================================================================== building interiors
ROOMS = {
    "center": ["WWWWWWWWWWWWWWW",
               "WWWWWWWWWWWWWWW",
               "f____m_______pf",
               "___ccccccccc___",
               "_______________",
               "_______________",
               "aat_________taa",
               "_______________",
               "_______________",
               "_______x_______"],
    "mart": ["WWWWWWWWWWWWWWW",
             "WWWWWWWWWWWWWWW",
             "f_k___________f",
             "__k____ss_ss___",
             "__k____ss_ss___",
             "__k____________",
             "_______ss_ss___",
             "_______ss_ss___",
             "_______________",
             "_______x_______"],
    "house": ["WWWWWWWWWWWWWWW",
              "WWWWWWWWWWWWWWW",
              "b___v_____rr_f_",
              "_______________",
              "_______________",
              "____att________",
              "_______________",
              "f_____________f",
              "_______________",
              "_______x_______"],
    "lab": ["WWWWWWWWWWWWWWW",
            "WWWWWWWWWWWWWWW",
            "rrr_mm___mm_rrr",
            "_______________",
            "_______________",
            "___t_______t___",
            "_______________",
            "f_____________f",
            "_______________",
            "_______x_______"],
    "gym": ["WWWWWWWWWWWWWWW",
            "WWWWWWWWWWWWWWW",
            "f_____________f",
            "_______________",
            "___o_______o___",
            "_______________",
            "_______________",
            "___o_______o___",
            "_______________",
            "_______________",
            "_______________",
            "f_____________f",
            "_____o___o_____",
            "_______x_______"],
    "league": ["WWWWWWWWWWWWWWW",
               "WWWWWWWWWWWWWWW",
               "o_____________o",
               "_______________",
               "o_____________o",
               "_______________",
               "o_____________o",
               "_______________",
               "o_____________o",
               "_______________",
               "o_____________o",
               "_______x_______"],
}
ROOM_WALK = set("_x")


def room(world, kind, area_index):
    """The inside of a building: its tiles and the people in it."""
    area = world.areas[area_index]
    rows = ROOMS[kind]
    t = area.get("town", 0)
    npcs = []
    if kind == "center":
        npcs.append({"id": "nurse", "kind": "nurse", "x": 7, "y": 2, "face": "down", "name": "Nurse", "look": "nurse"})
        npcs.append({"id": f"c{t}a", "kind": "talk", "x": 3, "y": 6, "face": "right", "name": "", "look": "villager",
                     "lines": ["The Pokemon Center heals your team for free. Come back any time!"]})
    elif kind == "mart":
        npcs.append({"id": "clerk", "kind": "clerk", "x": 1, "y": 3, "face": "right", "name": "Clerk", "look": "clerk"})
        npcs.append({"id": f"m{t}a", "kind": "talk", "x": 9, "y": 5, "face": "up", "name": "", "look": "Lass",
                     "lines": ["Poke Balls work better when the Pokemon is weak. Try making it fall asleep!"]})
    elif kind == "house":
        rng = random.Random(t * 7 + 1)
        npcs.append({"id": f"h{t}", "kind": "talk", "x": 8, "y": 5, "face": "down", "name": "",
                     "look": rng.choice(["villager", "mom", "Hiker", "Picnicker"]),
                     "lines": [rng.choice([
                         "My kid wants to be a Pokemon trainer just like you!",
                         "Have you seen a shiny Pokemon? They sparkle when they come out!",
                         "Trainers who look at you will want to battle. Watch out on the routes!",
                         "If your Pokemon all faint, you'll wake up at the last Pokemon Center you used.",
                         "Some Pokemon only evolve at a high level. Be patient!",
                         "Type matchups matter. Electric moves don't touch Ground types at all!"])]})
    elif kind == "lab":
        npcs.append({"id": "prof", "kind": "prof", "x": 7, "y": 4, "face": "down", "name": "Prof. Hazel",
                     "look": "prof"})
    elif kind == "gym":
        k = t - 1
        town, leader, typ, ace, intro, lose, badge = GYMS[k]
        rng = random.Random(500 + k)
        npcs.append({"id": f"gym{k}", "kind": "leader", "x": 7, "y": 3, "face": "down", "name": leader,
                     "look": f"leader{k}", "gym": k})
        for j, (x, y, face) in enumerate(((4, 6, "right"), (10, 9, "left"))):
            team = world.team_for([typ], ace - 6 + j * 2, 1 + (k > 2) + (k > 5), rng)
            npcs.append({"id": f"gym{k}-t{j}", "kind": "trainer", "x": x, "y": y, "face": face,
                         "name": f"{rng.choice(['Ace Trainer', 'Black Belt', 'Psychic', 'Hiker', 'Lass'])} "
                                 f"{rng.choice(TRAINER_NAMES)}", "cls": "Ace Trainer", "team": team, "sight": 4,
                         "intro": f"You want to see {leader}? You'll have to beat me first!",
                         "lose": f"{leader} is way stronger than me...", "money": 40 * ace})
    elif kind == "league":
        npcs.append({"id": "champion", "kind": "champion", "x": 7, "y": 2, "face": "down", "name": CHAMPION[0],
                     "look": "rival"})
    return {"name": {"center": "Pokemon Center", "mart": "Poke Mart", "house": area["name"], "lab": "Hazel's Lab",
                     "gym": f"{area['name']} Gym", "league": "Pokemon League"}[kind],
            "kind": "room", "room": kind, "rows": rows, "npcs": npcs, "items": [], "music": "gym" if kind in
            ("gym", "league") else "town"}
