"""Adventure mode: the rules and the world. Your party (levels, XP, moves, evolution), the bag, money, badges,
the save file, and the Brawl region - 9 towns joined by routes, 8 gyms, Victory Road and the Pokemon League.

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
SHINY_ODDS = 512

STARTERS = {1: [1, 4, 7], 2: [152, 155, 158], 3: [252, 255, 258], 4: [387, 390, 393], 5: [495, 498, 501],
            6: [650, 653, 656], 7: [722, 725, 728], 8: [810, 813, 816], 9: [906, 909, 912]}

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
}
# what the Mart sells after N badges
MART_STOCK = [(0, ["poke-ball", "potion", "full-heal"]), (1, ["super-potion", "revive"]),
              (2, ["great-ball"]), (4, ["ultra-ball", "hyper-potion"]), (6, ["max-potion", "full-restore"]),
              (7, ["max-revive"])]
BALL_KEYS = ["poke-ball", "great-ball", "ultra-ball", "master-ball"]

GYMS = [  # (town, leader, type, ace level, intro line, defeat line, badge)
    ("Pebblecrest City", "Petra", "rock", 13, "My Pokemon are as hard as the mountain. Can you crack them?",
     "You shattered my defence! The Crest Badge is yours.", "Crest Badge"),
    ("Tidewater City", "Coral", "water", 19, "The tide is turning... against you!",
     "You rode the wave. The Tide Badge is yours.", "Tide Badge"),
    ("Voltara City", "Zappa", "electric", 25, "Hope you like getting shocked, kid!",
     "Whoa, you're charged up! Take the Spark Badge.", "Spark Badge"),
    ("Bloomfield City", "Fern", "grass", 31, "Let's see if you can weather my garden.",
     "Your team bloomed beautifully. The Bloom Badge.", "Bloom Badge"),
    ("Toxmire Town", "Nox", "poison", 37, "Breathe in. Now panic.", "Tch. Fine. The Venom Badge.",
     "Venom Badge"),
    ("Mindspire City", "Sage", "psychic", 43, "I already know how this ends.",
     "...I did not see that coming. The Mind Badge.", "Mind Badge"),
    ("Emberpeak City", "Blaze", "fire", 49, "Hope you packed water. You'll need it!",
     "You put out my fire! The Ember Badge.", "Ember Badge"),
    ("Duneholt City", "Terra", "ground", 55, "Only the strongest reach the League. Show me.",
     "You are ready. Take the Earth Badge and go.", "Earth Badge"),
]
CHAMPION = ("Aurelia", 64, "So you're the one who beat all eight gyms. I'm the Champion. Let's make it a battle "
            "worth remembering!", "Incredible... You are the new Champion of the Brawl region!")
ROUTE_TYPES = [["normal", "bug", "flying"], ["normal", "grass", "bug", "rock"], ["water", "normal", "flying"],
               ["electric", "normal", "grass", "poison"], ["grass", "bug", "fairy", "normal"],
               ["poison", "dark", "ghost", "bug"], ["psychic", "fairy", "normal", "fighting"],
               ["fire", "dragon", "rock", "fighting"], ["ground", "steel", "rock", "dark"],
               ["dragon", "steel", "fighting", "ice", "ghost"]]
TRAINER_CLASSES = ["Youngster", "Lass", "Bug Catcher", "Hiker", "Swimmer", "Ace Trainer", "Psychic", "Black Belt",
                   "Picnicker", "Fisher", "Biker", "Beauty"]
TRAINER_NAMES = ["Joey", "Mia", "Leo", "Ava", "Sam", "Kai", "Zoe", "Ben", "Ivy", "Max", "Lily", "Tom", "Nia", "Eli",
                 "Ruby", "Finn", "Jade", "Owen", "Rosa", "Dex", "Luna", "Jax", "Cleo", "Rex"]


# ====================================================================== Pokemon in your party
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


def member(mon):
    """A battle-engine Member for a party Pokemon (no EVs, like a real playthrough)."""
    m = Member(mon["species"], mon["moves"], "none", mon.get("nature", "Serious"), {"hp": 0}, None,
               mon["level"], mon.get("ability"))
    m.cur_hp, m.status, m.pp = mon.get("cur_hp"), mon.get("status"), mon.get("pp")
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
    """Experience for defeating a Pokemon (Gen 5 style: more for beating stronger Pokemon)."""
    b = dex.all[foe_species].get("bxp", 60)
    gain = (b * foe_level / 5) * ((2 * foe_level + 10) / (foe_level + my_level + 10)) ** 2.5 + 1
    return int(gain * (1.5 if trainer else 1.0))


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


BUILDINGS = {
    "C": ["cccc", "cccc", "cCcc"],          # Pokemon Center (door C)
    "M": ["mmm", "mmm", "mMm"],              # Poke Mart (door M)
    "G": ["ggggg", "ggggg", "ggggg", "ggGgg"],  # Gym (door G)
    "H": ["hhh", "hhh", "hDh"],              # house (door D)
    "L": ["lllllll", "lllllll", "lllllll", "lllllll", "lllLlll"],  # Pokemon League
    "P": ["pppp", "pppp", "pPpp"],           # Professor's lab
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
        _put(g, 10, 3, BUILDINGS["H"])
        _put(g, 1, 15, BUILDINGS["P"])
        _put(g, 10, 15, BUILDINGS["H"])
        _put(g, 5, 9, ["S"])
        g[h - 1] = ["#"] * COLS     # the hometown is the south end of the region
    elif i == 9:
        _put(g, 4, 2, BUILDINGS["L"])
        _put(g, 1, 15, BUILDINGS["C"])
        _put(g, 11, 15, BUILDINGS["M"])
        g[0] = ["#"] * COLS
        for x in (5, 6, 7, 8, 9):
            g[7][x] = "="
    else:
        _put(g, 1, 2, BUILDINGS["C"])
        _put(g, 10, 2, BUILDINGS["M"])
        _put(g, 9, 7, BUILDINGS["G"])
        _put(g, 1, 7, BUILDINGS["H"])
        _put(g, 1, 16, BUILDINGS["H"])
        _put(g, 10, 16, BUILDINGS["H"])
        _put(g, 5, 9, ["S"])
        for y in range(5, 7):
            g[y][2] = "="
            g[y][11] = "="
        g[11][11] = "="
        g[12][11] = "="
    # decoration: flowers and the odd tree on empty ground
    for y in range(h):
        for x in range(1, COLS - 1):
            if g[y][x] == "." and rng.random() < 0.12:
                g[y][x] = ","
            elif g[y][x] == "." and rng.random() < 0.03 and x not in (5, 9):
                g[y][x] = "t"
    return ["".join(r) for r in g]


def route_map(i, rng):
    """Route i (1-based): a winding path north with tall grass, trees, a pond and trainers."""
    h = 34 + 4 * min(i, 6)
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
    return ["".join(r) for r in g], path


class World:
    """The whole region, generated from a fixed seed so every player gets the same map."""

    def __init__(self, dex, seed=2024):
        self.dex = dex
        self.areas = []      # list of dicts: name, kind, rows, npcs, items, music, level range, pool
        rng = random.Random(seed)
        towns = ["Rootleaf Town"] + [g[0] for g in GYMS] + ["Pokemon League"]
        self._parents = {}
        for e in dex.all.values():
            for to, lv in e.get("evo", []):
                self._parents[to] = (e["id"], lv)
        for i, name in enumerate(towns):
            rows = town_map(i, random.Random(seed * 7 + i))
            area = {"name": name, "kind": "town", "rows": rows, "town": i, "npcs": self._town_npcs(i, rows, rng),
                    "items": [], "music": "town"}
            self.areas.append(area)
            if i < len(towns) - 1:
                rows, path = route_map(i + 1, random.Random(seed * 13 + i))
                rname = f"Route {i + 1}" if i < 8 else "Victory Road"
                lo, hi = self.route_levels(i + 1)
                area = {"name": rname, "kind": "route", "rows": rows, "route": i + 1, "music": "route",
                        "levels": (lo, hi), "pool": self._pool(i + 1, random.Random(seed * 31 + i))}
                area["npcs"] = self._route_trainers(i + 1, rows, path, area, random.Random(seed * 17 + i))
                area["items"] = self._route_items(i + 1, rows, path, random.Random(seed * 19 + i))
                self.areas.append(area)
        # areas run south (index 0) to north: walking off the top goes to index + 1

    @staticmethod
    def route_levels(r):
        return (2 + 6 * (r - 1), 5 + 6 * (r - 1)) if r < 9 else (50, 56)

    def base_form(self, pid):
        seen = set()
        while pid in self._parents and pid not in seen:
            seen.add(pid)
            pid = self._parents[pid][0]
        return pid

    def _pool(self, r, rng):
        lo, hi = self.route_levels(r)
        cand = []
        types = ROUTE_TYPES[min(r, len(ROUTE_TYPES) - 1)]
        cap = 330 + 30 * r
        starters = {i for trio in STARTERS.values() for i in trio}
        for e in self.dex.all.values():
            if e["id"] in starters:
                continue
            if not e["default"] or e["transform"] or e["legendary"] or e["mythical"] or not e.get("lvl"):
                continue
            if not any(t in types for t in e["types"]):
                continue
            par = self._parents.get(e["id"])
            if par is None:            # a first-stage Pokemon
                if sum(e["stats"].values()) <= cap:
                    cand.append(e["id"])
            elif par[1] <= hi and self._parents.get(par[0]) is None and r >= 4:   # middle stages later on
                cand.append(e["id"])
        rng.shuffle(cand)
        pool = sorted(set(cand[:9 + r // 2]))
        return pool or [16, 19]

    def wild_species(self, area, rng):
        return rng.choice(area["pool"])

    def team_for(self, types, level, size, rng, strong=False):
        """A trainer's team of `size` Pokemon of these types, grown up to the right stage for their level."""
        pool = [e for e in self.dex.all.values() if e["default"] and not e["transform"] and e.get("lvl") and
                not (e["legendary"] or e["mythical"]) and any(t in types for t in e["types"]) and
                self.base_form(e["id"]) == e["id"]]
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
        ys = sorted(rng.sample(range(6, h - 6), min(h - 12, 2 + r // 2)))
        last = -9
        for y in ys:
            if y - last < 4:
                continue
            last = y
            px = path[y]
            side = rng.choice((-1, 1))
            x = px + side * 2
            if not (1 <= x <= COLS - 2) or rows[y][x] in "~":
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
        rng = random.Random(1000 + k)
        size = min(6, 2 + k // 2 + (1 if k >= 6 else 0))
        return self.team_for([typ], ace, size, rng, strong=True)

    def champion_team(self):
        rng = random.Random(4242)
        out = []
        for typ in ["dragon", "steel", "water", "fire", "psychic", "dark"]:
            out += self.team_for([typ], CHAMPION[1] - 3 + len(out), 1, rng, strong=True)
        out[-1]["level"] = CHAMPION[1] + 1
        return out


# ====================================================================== the save file
def new_game(name, starter_id, dex):
    rng = random.Random()
    starter = make_mon(dex, dex.all[starter_id], 5, rng, origin="Rootleaf Town")
    return {"v": 1, "name": name or "Trainer", "party": [starter], "box": [], "money": 3000,
            "bag": {"poke-ball": 5, "potion": 3}, "badges": [], "area": 0, "x": 7, "y": 12, "face": "up",
            "center": [0, 7, 12], "seen": [starter_id], "caught": [starter_id], "beaten": [], "picked": [],
            "playtime": 0.0, "started": int(time.time()), "champion": False}


def load():
    try:
        with open(SAVE_FILE) as f:
            data = json.load(f)
        return data if data.get("party") else None
    except (OSError, ValueError):
        return None


def save(data):
    os.makedirs(HOME, exist_ok=True)
    tmp = SAVE_FILE + ".tmp"
    with open(tmp, "w") as f:
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
