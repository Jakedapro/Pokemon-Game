"""Adventure maps drawn with the FireRed / LeafGreen tile sets (see frlg.py), the way the handheld's field engine
draws them: a layer under the people and a layer over them (tree tops, roofs, the tips of tall grass).

Outdoors, the generated map's tile letters are turned into real metatiles (paths and ponds get their proper
edges and corners, forests their staggered two-wide trees) and every building is a piece cut from a real town.
Indoors, rooms ARE real interiors: their collision, counters, exits and where people stand all come from the
original map files.

Everything returns None when the files aren't available, and the overworld falls back to its own drawn art.
"""
import random
from collections import deque

import pygame

from . import frlg

S = 2   # the field is drawn at 2x, like the rest of Adventure mode
T = 16 * S

GROUND = "PalletTown_Layout"   # general tiles (+ Pallet Town's), used for every outdoor area

# pieces of real towns: (layout, x, y, w, h); the door cell inside is where the map's door letter sits
STAMPS = {
    "center": ("ViridianCity_Layout", 24, 23, 5, 4),
    "mart": ("ViridianCity_Layout", 34, 16, 4, 4),
    "gym": ("ViridianCity_Layout", 33, 6, 6, 5),
    "house": ("PalletTown_Layout", 5, 3, 5, 5),
    "lab": ("PalletTown_Layout", 13, 9, 7, 5),
    "league": ("IndigoPlateau_Exterior_Layout", 6, 0, 11, 7),
}

# nine-slice path sets: TL T TR / L C R / BL B BR, then inner corners missing NW NE SW SE
SAND = ((211, 212, 213), (219, 220, 221), (227, 228, 229), (258, 259, 260, 261))
PAVE = ((357, 358, 359), (365, 366, 367), (373, 374, 375), (405, 406, 413, 414))
POND = ((421, 422, 423), (429, 430, 431), (307, 307, 307))
GRASS = (1, 1, 1, 1, 8, 9, 16, 17)
TALL, FLOWER, SIGN, BUSH = 13, 4, 3, 5
TREE = {  # (row parity, half) -> (normal, edge-facing-grass)
    ("top", "L"): (28, 30), ("top", "R"): (29, 31),
    ("bot", "L"): (20, 22), ("bot", "R"): (21, 23),
    ("base", "L"): (36, 38), ("base", "R"): (37, 39),
}
TIP = (14, 15)
ROOF_ON_GROUND = {"house", "lab", "gym"}

# real interiors for each room kind
ROOM_MAPS = {
    "center": "ViridianCity_PokemonCenter_1F",
    "mart": "ViridianCity_Mart",
    "lab": "PalletTown_ProfessorOaksLab",
    "league": "PokemonLeague_ChampionsRoom",
}
HOUSES = ["ViridianCity_House", "PalletTown_RivalsHouse", "PewterCity_House1", "CeruleanCity_House1",
          "LavenderTown_House1", "VermilionCity_House1", "CeladonCity_House1", "FuchsiaCity_House1"]
# our 8 gyms are rock, water, electric, grass, poison, psychic, fire, ground - Kanto's order
GYM_MAPS = ["PewterCity_Gym", "CeruleanCity_Gym", "VermilionCity_Gym", "CeladonCity_Gym", "FuchsiaCity_Gym",
            "SaffronCity_Gym", "CinnabarIsland_Gym", "ViridianCity_Gym"]
LEADER_GFX = {"BROCK", "MISTY", "LT_SURGE", "ERIKA", "KOGA", "SABRINA", "BLAINE", "GIOVANNI", "PROF_OAK", "BLUE"}

MB_COUNTER, MB_BOOKSHELF, MB_MART_SHELF, MB_PC, MB_TV, MB_CABINET = 0x80, 0x81, 0x82, 0x83, 0x86, 0x89


def available():
    return frlg.is_ready() and frlg.layout(GROUND) is not None


def needed_files():
    """Every decomp file Adventure mode draws with (downloaded in the background when it starts)."""
    from . import gbaart
    lays = frlg.layouts()
    if not lays:
        return []
    maps = list(ROOM_MAPS.values()) + HOUSES + GYM_MAPS + ["PalletTown_PlayersHouse_1F"]
    frlg.prefetch([f"data/maps/{m}/map.json" for m in maps])
    names = {GROUND} | {spec[0] for spec in STAMPS.values()}
    gfx = set(gbaart.FRLG_PEOPLE.values())
    for m in maps:
        j = frlg.map_json(m)
        if not j:
            continue
        names |= {n for n, l in lays.items() if l.get("id") == j.get("layout")}
        gfx |= {o.get("graphics_id", "").replace("OBJ_EVENT_GFX_", "").lower() for o in j.get("object_events", [])}
    files = []
    sets = set()
    for n in names:
        l = lays.get(n)
        if not l:
            continue
        files.append(l["blockdata_filepath"])
        sets.add("primary/" + frlg._tileset_name(l["primary_tileset"]))
        sets.add("secondary/" + frlg._tileset_name(l["secondary_tileset"]))
    for t in sets:
        d = f"data/tilesets/{t}/"
        files += [d + "tiles.png", d + "metatiles.bin", d + "metatile_attributes.bin"]
        files += [d + f"palettes/{i:02d}.pal" for i in range(16)]
    files += [f"graphics/object_events/pics/people/{g}.png" for g in sorted(gfx) if g]
    files.append("graphics/object_events/pics/misc/item_ball.png")
    return files


def warm():
    """Downloads everything (call in a background thread)."""
    frlg.prefetch(["data/layouts/layouts.json"])
    from . import battlegfx
    frlg.prefetch(needed_files() + battlegfx.files() + EXTRA_FILES)


EXTRA_FILES = []    # battle graphics etc. register themselves here


# ====================================================================== outdoors
def _nine(kind_set, rows, x, y, same):
    def ok(xx, yy):
        if not (0 <= yy < len(rows)):
            return True
        if not (0 <= xx < len(rows[0])):
            return True
        return rows[yy][xx] in same
    n, e, s, w = ok(x, y - 1), ok(x + 1, y), ok(x, y + 1), ok(x - 1, y)
    top, mid, bot, inner = kind_set
    row = top if not n else bot if not s else mid
    col = 0 if not w else 2 if not e else 1
    mid_id = row[col]
    if n and s and e and w:   # surrounded: maybe an inner corner
        for k, (dx, dy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
            if not ok(x + dx, y + dy):
                return inner[k]
    return mid_id


def _tree(rows, x, y):
    def tree(xx, yy):
        if not (0 <= xx < len(rows[0])):
            return True
        if not (0 <= yy < len(rows)):
            return True
        return rows[yy][xx] == "#"
    half = "L" if x % 2 == 0 else "R"
    right_open, left_open = not tree(x + 1, y), not tree(x - 1, y)
    if right_open and left_open:
        return BUSH
    if half == "L" and right_open:
        half, edge = "R", True       # a left half with nothing beside it reads as a tree's right side
    elif half == "R" and left_open:
        half, edge = "L", True
    else:
        edge = (half == "L" and left_open) or (half == "R" and right_open)
    if not tree(x, y + 1):
        part = "base"
    else:
        part = "top" if y % 2 == 0 else "bot"
    return TREE[(part, half)][1 if edge else 0]


def area_cells(area):
    """The metatile id for every cell of an outdoor area (buildings are added separately)."""
    rows = area["rows"]
    town = area.get("kind") == "town"
    path_set = PAVE if town else SAND
    doors = "CMGDPL"
    out = []
    for y, row in enumerate(rows):
        line = []
        for x, ch in enumerate(row):
            if ch == "#":
                mid = _tree(rows, x, y)
            elif ch == "=" or ch in doors:
                mid = _nine(path_set, rows, x, y, "=" + doors + "cmgdhpl")
            elif ch == '"':
                mid = TALL
            elif ch == ",":
                mid = FLOWER
            elif ch == "~":
                mid = _nine((POND[0], POND[1], POND[2], (430,) * 4), rows, x, y, "~")
            elif ch == "t":
                mid = BUSH
            elif ch == "S":
                mid = SIGN
            else:
                below = rows[y + 1][x] if y + 1 < len(rows) else "."
                if below == "#" and (y + 1) % 2 == 0 and _tree(rows, x, y + 1) not in (BUSH,):
                    mid = TIP[x % 2]             # the tip of a tree crown poking into the grass above
                else:
                    mid = GRASS[(x * 7 + y * 13 + (x * y) % 5) % len(GRASS)]
            line.append(mid)
        out.append(line)
    return out


def _stamp(kind):
    spec = STAMPS.get(kind)
    return frlg.render(*spec, scale=S) if spec else None


def render_area(area, buildings):
    """(under, over) surfaces for an outdoor area, or None. buildings: overworld.buildings_of(area)."""
    lay = frlg.layout(GROUND)
    if not lay:
        return None
    ts = lay["tiles"]
    rows = area["rows"]
    w, h = len(rows[0]), len(rows)
    under = pygame.Surface((w * 16, h * 16), pygame.SRCALPHA)
    over = pygame.Surface((w * 16, h * 16), pygame.SRCALPHA)
    for y, line in enumerate(area_cells(area)):
        for x, mid in enumerate(line):
            under.blit(ts.metatile(mid, "under"), (x * 16, y * 16))
            top = ts.metatile(mid, "over")
            if top is not None:
                over.blit(top, (x * 16, y * 16))
    under = pygame.transform.scale_by(under, S)
    over = pygame.transform.scale_by(over, S)
    missing = []
    for kind, bx, by, bw, bh, door in buildings:
        st = _stamp(kind)
        spec = STAMPS.get(kind)
        if st is None or (spec[3], spec[4]) != (bw, bh):
            missing.append((kind, bx, by, bw, bh, door))
            continue
        su, so, _ = st
        under.blit(su, (bx * T, by * T))
        over.blit(so, (bx * T, by * T))
        if kind in ROOF_ON_GROUND:   # the roof's top edge sits on the source town's ground: put ours under it
            src = frlg.layout(spec[0])
            for cx in range(bw):
                b = src["blocks"][spec[2] * src["w"] + spec[1] + cx] & 0x3FF
                gx, gy = (bx + cx) * T, by * T
                g = pygame.transform.scale_by(ts.metatile(GRASS[(bx + cx) % 4], "under"), S)
                under.blit(g, (gx, gy))
                top = src["tiles"].metatile(b, "top")
                under.blit(pygame.transform.scale_by(top, S), (gx, gy))
    return under, over, missing


# ====================================================================== indoors
def _map_for(kind, area_index, world, door):
    if kind == "gym":
        k = world.areas[area_index].get("town", 1) - 1
        return GYM_MAPS[k % len(GYM_MAPS)]
    if kind == "house":
        rng = random.Random(area_index * 31 + (door[0] if door else 0) * 7 + (door[1] if door else 0))
        if area_index == 0 and door is not None:
            first = min((x, y) for y, r in enumerate(world.areas[0]["rows"]) for x, ch in enumerate(r) if ch == "D")
            if tuple(door) == first:
                return "PalletTown_PlayersHouse_1F"
        return rng.choice(HOUSES)
    return ROOM_MAPS.get(kind)


def _reachable(rows, start, goal_cells):
    q, seen = deque([start]), {start}
    while q:
        x, y = q.popleft()
        if (x, y) in goal_cells:
            return True
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= ny < len(rows) and 0 <= nx < len(rows[0]) and (nx, ny) not in seen and rows[ny][nx] in "_x":
                seen.add((nx, ny))
                q.append((nx, ny))
    return False


def room(kind, area_index, world, door=None):
    """A real interior: {'rows', 'field': (under, over), 'entry', 'spots': {role: [(x, y, face)]}} or None."""
    name = _map_for(kind, area_index, world, door)
    out = _room_from(name)
    if out is None and kind == "house":
        out = _room_from("ViridianCity_House")
    if out is None and kind == "gym":
        out = _room_from("PewterCity_Gym")
    if out is not None and kind == "gym" and not out["spots"].get("leader"):
        out = _room_from("PewterCity_Gym")
    if out is not None and kind == "gym":
        lx, ly = out["spots"]["leader"][0][:2]
        if not _reachable(out["rows"], out["entry"], {(lx, ly + 1), (lx - 1, ly), (lx + 1, ly)}):
            out = _room_from("PewterCity_Gym")   # puzzle gyms (teleporters, locked doors) need their scripts
    return out


def _room_from(name):
    j = frlg.map_json(name)
    if not j:
        return None
    lid = j.get("layout", "")
    lay_name = next((n for n, l in frlg.layouts().items() if l.get("id") == lid), None)
    if not lay_name:
        return None
    r = frlg.render(lay_name, scale=S)
    lay = frlg.layout(lay_name)
    if not r or not lay:
        return None
    under, over, blocked = r
    ts = lay["tiles"]
    w, h = lay["w"], lay["h"]
    warps = [(wp["x"], wp["y"]) for wp in j.get("warp_events", [])]
    exit_y = max((y for _, y in warps), default=h - 1)
    exits = {(x, y) for x, y in warps if y == exit_y}
    rows = []
    for y in range(h):
        line = []
        for x in range(w):
            b = lay["blocks"][y * w + x]
            beh = ts.behavior(b & 0x3FF)
            if (x, y) in exits:
                ch = "x"
            elif (x, y) in warps:
                ch = "W"           # stairs and teleporters elsewhere in the building stay shut
            elif beh == MB_COUNTER:
                ch = "c"
            elif beh == MB_PC:
                ch = "p"
            elif beh in (MB_BOOKSHELF, MB_MART_SHELF, MB_CABINET):
                ch = "s"
            elif beh == MB_TV:
                ch = "v"
            elif blocked[y][x]:
                ch = "W"
            else:
                ch = "_"
            line.append(ch)
        rows.append("".join(line))
    ex = sorted(exits)
    entry = ex[len(ex) // 2] if ex else (w // 2, h - 1)
    spots = {"people": [], "trainers": [], "leader": []}
    for o in j.get("object_events", []):
        gfx = o.get("graphics_id", "").replace("OBJ_EVENT_GFX_", "")
        x, y = o.get("x", 0), o.get("y", 0)
        if not (0 <= x < w and 0 <= y < h):
            continue
        face = {"FACE_UP": "up", "FACE_LEFT": "left", "FACE_RIGHT": "right"}.get(
            o.get("movement_type", "").replace("MOVEMENT_TYPE_", ""), "down")
        if gfx == "NURSE":
            spots["nurse"] = [(x, y, face)]
        elif gfx == "CLERK":
            spots["clerk"] = [(x, y, face)]
        elif gfx in LEADER_GFX:
            spots["leader"].append((x, y, face, gfx.lower()))
        elif o.get("trainer_type", "TRAINER_TYPE_NONE") != "TRAINER_TYPE_NONE":
            spots["trainers"].append((x, y, face, gfx.lower()))
        elif gfx not in ("ITEM_BALL", "POKEDEX") and not gfx.startswith(("VAR_", "CUT_", "ROCK", "STRENGTH")):
            spots["people"].append((x, y, face, gfx.lower()))
    return {"rows": rows, "field": (under, over), "entry": entry, "spots": spots, "map": name, "w": w}
