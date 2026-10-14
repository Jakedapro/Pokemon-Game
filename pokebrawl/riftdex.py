"""PokeBrawl's own Mega material: Mega Evolutions the official games never made, the Rift-Born move, the
anomalies that warp battles inside a Mega Rift, corrupted Mega Stones and the dig sites the Mega Radar finds.

Everything here is added to the dex at runtime (install), so the base data stays the PokeAPI one."""
import random

# ---------------------------------------------------------------------- our own Mega Evolutions
# (base Pokemon, types, stat changes (+100 in total), ability, sprite recolour rules, energy outline colour)
# recolour rule = (hue from, hue to, new hue, saturation x, brightness x[, min saturation]) - see frlg.recolor_palette
CUSTOM_MEGAS = [
    ("flygon", ["ground", "dragon"], {"atk": 30, "def": 20, "spa": 20, "spd": 10, "spe": 20}, "tough-claws",
     ((80, 170, 350, 1.1, 0.9), (330, 30, 48, 1.0, 1.1)), (255, 96, 64)),
    ("luxray", ["electric", "dark"], {"atk": 40, "def": 20, "spd": 20, "spe": 20}, "strong-jaw",
     ((185, 255, 275, 1.1, 0.8),), (255, 230, 90)),
    ("arcanine", ["fire", "dragon"], {"atk": 20, "def": 20, "spa": 20, "spd": 15, "spe": 25}, "tough-claws",
     ((12, 48, 250, 0.9, 0.85, 0.35),), (120, 160, 255)),
    ("milotic", ["water", "fairy"], {"atk": 10, "def": 20, "spa": 30, "spd": 20, "spe": 20}, "multiscale",
     ((180, 260, 328, 1.0, 1.05), (330, 20, 172, 1.0, 1.0, 0.3)), (255, 180, 230)),
    ("typhlosion", ["fire", "ghost"], {"atk": 10, "def": 15, "spa": 40, "spd": 15, "spe": 20}, "drought",
     ((180, 250, 280, 0.9, 0.6), (0, 55, 285, 1.0, 1.0, 0.4)), (200, 120, 255)),
    ("snorlax", ["normal", "fighting"], {"atk": 40, "def": 40, "spd": 10, "spe": 10}, "iron-fist",
     ((160, 240, 355, 0.9, 0.85),), (255, 90, 90)),
    ("lapras", ["water", "ice"], {"def": 30, "spa": 30, "spd": 25, "spe": 15}, "snow-warning",
     ((175, 250, 192, 0.6, 1.15),), (180, 240, 255)),
    ("ninetales", ["fire", "fairy"], {"def": 20, "spa": 40, "spd": 20, "spe": 20}, "drought",
     ((35, 65, 330, 0.8, 1.05, 0.15),), (255, 200, 240)),
    ("machamp", ["fighting", "steel"], {"atk": 40, "def": 30, "spd": 20, "spe": 10}, "iron-fist",
     ((150, 260, 215, 0.25, 1.05, 0.1),), (220, 220, 240)),
    ("togekiss", ["fairy", "flying"], {"def": 20, "spa": 30, "spd": 20, "spe": 30}, "serene-grace",
     ((330, 30, 50, 1.0, 1.15), (190, 260, 300, 1.0, 1.0)), (255, 240, 160)),
]
CUSTOM_BASE_ID = 30001
_custom = {}        # form id -> (base id, rules, outline colour)

# ---------------------------------------------------------------------- the Rift-Born move
RIFT_MOVE_ID = 9901
RIFT_MOVE = {"id": RIFT_MOVE_ID, "key": "rift-breaker", "name": "Rift Breaker", "type": "normal", "power": 90,
             "acc": 100, "pp": 8, "pri": 0, "cls": "spec", "target": "selected-pokemon", "cat": "damage",
             "ailment": "none", "ail_chance": 0, "drain": 0, "healing": 0, "crit": 1, "flinch": 0, "stat_chance": 0,
             "hits": [1, 1], "stats": {}, "flags": []}
RIFT_ABILITY = "rift-heart"

# ---------------------------------------------------------------------- what a rift does to a battle
ANOMALIES = {
    "gravity": ("GRAVITY DISTORTION", "Everything is pinned to the ground! Flying Pokemon can be hit by Ground "
                                      "moves, and attacks rarely miss."),
    "time": ("TIME DISTORTION", "Time is running backwards! Slower Pokemon move first."),
    "inverse": ("TYPE INVERSION", "The type matchups are flipped! Super effective is now not very effective..."),
    "surge": ("MEGA SURGE", "Raw Mega energy floods the rift! Every attack hits much harder."),
    "entropy": ("ENTROPY FIELD", "The rift is eating away at everything! All Pokemon lose HP each turn."),
    "storm": ("ELEMENTAL STORM", "The rift is raging with wild weather!"),
}
RIFT_TURNS = {"EASY": 10, "NORMAL": 8, "HARD": 7, "INSANE": 6}
RIFT_BOOST = 1.25      # stats of a Mega born in a rift
RIFT_CATCH = 0.35      # ...and how much harder it is to catch
CORRUPT_MULT = 2.0     # a corrupted Mega Stone doubles every stat, at a price


def install(dex):
    """Adds our Megas and the Rift Breaker move to a loaded dex (once)."""
    if getattr(dex, "_rift_installed", False):
        return
    dex._rift_installed = True
    dex.moves[RIFT_MOVE_ID] = RIFT_MOVE
    if hasattr(dex, "move_by_key"):
        dex.move_by_key[RIFT_MOVE["key"]] = RIFT_MOVE
    for k, (base_key, types, delta, ability, rules, glow) in enumerate(CUSTOM_MEGAS):
        base = dex.get(base_key)
        if base is None:
            continue
        fid = CUSTOM_BASE_ID + k
        key = f"{base['key']}-mega"
        stats = {s: base["stats"][s] + delta.get(s, 0) for s in base["stats"]}
        entry = dict(base, id=fid, key=key, name=f"Mega {base['name']}", default=False, transform=True,
                     types=list(types), stats=stats, megas=[], gmax=None, base=base["id"],
                     abilities=[[ability, False]], evo=[], bxp=base.get("bxp", 200) + 50, custom=True)
        dex.all[fid] = entry
        if hasattr(dex, "by_key"):
            dex.by_key[key] = entry
        if fid not in base["megas"]:
            base["megas"].append(fid)
        _custom[fid] = (base["id"], rules, glow)


def is_custom(pid):
    return pid in _custom


def custom_stones(dex):
    """(stone key, name, base id) for our own Megas - only ever found by digging."""
    from .team import mega_item_name
    install(dex)
    return [(dex.all[f]["key"], mega_item_name(dex, dex.all[f]), b) for f, (b, _, _) in sorted(_custom.items())]


def sprite_for(pid, base_img):
    """Our Mega's battle picture: its base sprite in its Mega colours with a crackling energy outline."""
    import pygame
    from . import frlg
    _, rules, glow = _custom[pid]
    w, h = base_img.get_size()
    src = base_img.copy()
    cols = {}
    px = pygame.PixelArray(src)
    for y in range(h):
        for x in range(w):
            c = src.unmap_rgb(px[x, y])
            if c.a:
                cols.setdefault((c.r, c.g, c.b), None)
    del px
    keys = list(cols)
    for k, v in zip(keys, frlg.recolor_palette(keys, rules)):
        cols[k] = v
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        for x in range(w):
            c = src.get_at((x, y))
            if c.a:
                out.set_at((x, y), (*cols[(c.r, c.g, c.b)], 255))
    mask = pygame.mask.from_surface(out)
    edge = pygame.Surface((w, h), pygame.SRCALPHA)
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):   # a 1-pixel (at 2x) glow around the body
        edge.blit(mask.to_surface(setcolor=(*glow, 255), unsetcolor=(0, 0, 0, 0)), (dx, dy))
    final = pygame.Surface((w, h), pygame.SRCALPHA)
    final.blit(edge, (0, 0))
    final.blit(out, (0, 0))
    return final


def base_of(pid):
    return _custom[pid][0] if pid in _custom else pid


# ---------------------------------------------------------------------- dig sites (the Mega Radar)
def dig_pool(dex):
    """What's buried, in site order: our own Megas' stones and corrupted copies of the ordinary ones."""
    from . import story as S
    install(dex)
    custom = [("stone", k) for k, _, _ in custom_stones(dex)]
    ordinary = [s[0] for s in S._ordinary_stones(dex)]
    rng = random.Random(1337)
    rng.shuffle(ordinary)
    corrupt = [("corrupt", k) for k in ordinary]
    out = []
    while custom or corrupt:   # a custom stone every few sites, corrupted stones in between
        for _ in range(2):
            if corrupt:
                out.append(corrupt.pop(0))
        if custom:
            out.append(custom.pop(0))
    return out


def dig_sites(dex, area, route):
    """[(site id, x, y, (kind, stone key))] buried on a route."""
    from . import adventure as A
    pool = dig_pool(dex)
    rows = area["rows"]
    rng = random.Random(route * 991)
    spots = [(x, y) for y in range(6, len(rows) - 6) for x in range(1, A.COLS - 1) if rows[y][x] in ".,"]
    rng.shuffle(spots)
    out = []
    for i in range(2):
        n = (route - 1) * 2 + i
        if n < len(pool) and i < len(spots):
            x, y = spots[i]
            out.append((f"dig{route}_{i}", x, y, pool[n]))
    return out


def corrupted_name(dex, key):
    from . import story as S
    return "Corrupted " + S.stone_name(dex, key)
