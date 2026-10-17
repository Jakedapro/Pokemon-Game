"""FireRed battle graphics for Adventure battles (from the pret/pokefirered files, see frlg.py): the battle
backgrounds, the message / action / move boxes, the healthboxes, trainer pictures, Red's back sprite and Poke Balls.
Every function returns None when the files aren't there, and the battle screen draws its own art instead."""
import pygame

from . import frlg

S = 2
TERRAIN_DIR = "graphics/battle_terrain/"
TERRAINS = {   # kind -> (tile set folder, palette file)
    "grass": ("grass", "grass/terrain.pal"), "longgrass": ("longgrass", "longgrass/terrain.pal"),
    "cave": ("cave", "cave/terrain.pal"), "mountain": ("mountain", "mountain/terrain.pal"),
    "pond": ("pond", "pond/terrain.pal"), "sand": ("sand", "sand/terrain.pal"),
    "building": ("building", "building/terrain.pal"), "plain": ("indoor", "indoor/plain.pal"),
    "gym": ("indoor", "indoor/gym.pal"), "leader": ("indoor", "indoor/leader.pal"),
    "lorelei": ("indoor", "indoor/lorelei.pal"), "bruno": ("indoor", "indoor/bruno.pal"),
    "agatha": ("indoor", "indoor/agatha.pal"), "lance": ("indoor", "indoor/lance.pal"),
    "champion": ("indoor", "indoor/champion.pal"),
}
BOX_ROWS = {"message": 14, "action": 34, "move": 54}   # where each bottom box sits in the textbox tile map
UI = "graphics/battle_interface/"

# trainer pictures (graphics/trainers/front_pics/<name>_front_pic.png) for each look
FRONT_PICS = {
    "rival": "rival_early", "Youngster": "youngster", "Lass": "lass", "Bug Catcher": "bug_catcher",
    "Hiker": "hiker", "Swimmer": "swimmer_m", "Ace Trainer": "cool_trainer_m", "Psychic": "psychic_m",
    "Black Belt": "black_belt", "Picnicker": "picnicker", "Fisher": "fisherman", "Biker": "biker",
    "Beauty": "beauty", "grunt": "rocket_grunt_m", "admin": "rocket_grunt_f", "boss": "leader_giovanni",
    "ace": "cool_trainer_m", "champ": "leaf", "creator": "red", "frost": "elite_four_lorelei",
    "brutus": "elite_four_bruno", "morrow": "elite_four_agatha", "drakon": "elite_four_lance",
    "prof": "professor_oak", "elias": "scientist", "leader": "cool_trainer_m", "camper": "camper",
    "cooltrainer_m": "cool_trainer_m",
    "cooltrainer_f": "cool_trainer_f", "brock": "leader_brock", "misty": "leader_misty",
    "lt_surge": "leader_lt_surge", "erika": "leader_erika", "koga": "leader_koga", "sabrina": "leader_sabrina",
    "blaine": "leader_blaine", "giovanni": "leader_giovanni", "lass": "lass", "youngster": "youngster",
    "picnicker": "picnicker", "hiker": "hiker", "black_belt": "black_belt", "beauty": "beauty",
    "channeler": "channeler", "rocker": "rocker", "gentleman": "gentleman", "super_nerd": "super_nerd",
    "juggler": "juggler", "tamer": "tamer", "bird_keeper": "bird_keeper", "burglar": "burglar",
    "scientist": "scientist", "sailor": "sailor", "fisher": "fisherman", "biker": "biker",
    "bug_catcher": "bug_catcher", "swimmer_m_land": "swimmer_m", "rocket_m": "rocket_grunt_m",
    "rocket_f": "rocket_grunt_f", "gym_guy": "cool_trainer_m", "worker_m": "engineer",
}
BALLS = {"poke-ball": "poke", "great-ball": "great", "ultra-ball": "ultra", "master-ball": "master"}


def files():
    """Every file the battle screen uses (downloaded in the background with the rest)."""
    out = [UI + n for n in ("textbox.png", "textbox.bin", "textbox1.pal", "healthbox_singles_player.png",
                            "healthbox_singles_opponent.png", "healthbox_elements.png", "healthbox.pal",
                            "healthbar.pal")]
    for folder, pal in set(TERRAINS.values()):
        out += [TERRAIN_DIR + folder + "/terrain.png", TERRAIN_DIR + folder + "/terrain.bin", TERRAIN_DIR + pal]
    from . import cast
    pics = set(FRONT_PICS.values()) | {c[1] for c in cast.CAST.values()}
    out += [f"graphics/trainers/front_pics/{n}_front_pic.png" for n in sorted(pics)]
    out += [f"graphics/object_events/pics/people/{c[0]}.png" for c in cast.CAST.values()]
    out += ["graphics/trainers/back_pics/red_back_pic.png", "graphics/trainers/back_pics/leaf_back_pic.png"]
    out += [f"graphics/interface/ball/{n}.png" for n in BALLS.values()]
    out += ["graphics/fonts/latin_normal.png", "graphics/fonts/latin_small.png", "src/text.c"]
    out += [PARTY + n for n in ("bg.png", "bg.bin", "slot_main.bin", "slot_wide.bin", "slot_wide_empty.bin")]
    out += [f"graphics/text_window/{n}.png" for n in ("std", "menu_message")]
    out += INTRO_FILES
    return out


_cache = {}


def _cached(key, make):
    if key not in _cache:
        try:
            _cache[key] = make() if frlg.is_ready() else None
        except Exception:
            _cache[key] = None
        if _cache[key] is None and not frlg.is_ready():
            return _cache.pop(key)
    return _cache[key]


def terrain(kind):
    """The battle background: 480x224 (the GBA's 240x112 above the text box, at 2x)."""
    def make():
        folder, pal = TERRAINS.get(kind, TERRAINS["grass"])
        banks = frlg.pal_banks(TERRAIN_DIR + pal)
        img = frlg.tilemap(TERRAIN_DIR + folder + "/terrain.png", TERRAIN_DIR + folder + "/terrain.bin", banks,
                           base_bank=2)
        if img is None:
            return None
        base = pygame.Surface((240, 112))
        base.fill(banks[0][0])
        base.blit(img, (0, 0), (0, 0, 240, 112))
        return pygame.transform.scale_by(base, S)
    return _cached(("terrain", kind), make)


def box(which):
    """A bottom box (480x96): 'message', 'action' (with the menu) or 'move' (moves + PP/TYPE)."""
    def make():
        banks = frlg.pal_banks(UI + "textbox1.pal")
        img = frlg.tilemap(UI + "textbox.png", UI + "textbox.bin", banks, base_bank=0)
        if img is None:
            return None
        r = BOX_ROWS[which] * 8
        out = pygame.Surface((240, 48))
        out.fill(banks[0][0])
        out.blit(img, (0, 0), (0, r, 240, 48))
        return pygame.transform.scale_by(out, S)
    return _cached(("box", which), make)


def _sprite_tiles(img):
    w, h = img.get_size()
    return [img.subsurface((tx * 8, ty * 8, 8, 8)) for ty in range(h // 8) for tx in range(w // 8)]


def _assemble(tiles, w, h):
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    per = w // 8
    for i, t in enumerate(tiles[:per * (h // 8)]):
        out.blit(t, ((i % per) * 8, (i // per) * 8))
    return out


def healthbox(side):
    """The healthbox frame (2x): side 1 = the foe's (256x64), side 0 = yours, with the EXP bar (256x128)."""
    def make():
        name = "healthbox_singles_opponent" if side == 1 else "healthbox_singles_player"
        f = frlg.fetch(UI + name + ".png")
        pal = frlg.read_pal(UI + "healthbox.pal")
        if not f or not pal:
            return None
        img = pygame.image.load(f)
        img.set_palette((pal + [(0, 0, 0)] * 256)[:256])
        img.set_colorkey(pal[0])
        img = img.convert_alpha() if pygame.display.get_surface() else img
        t = _sprite_tiles(img)
        if side == 1:
            parts = [_assemble(t[0:32], 64, 32), _assemble(t[32:64], 64, 32)]
            out = pygame.Surface((128, 32), pygame.SRCALPHA)
        else:
            parts = [_assemble(t[0:64], 64, 64), _assemble(t[64:128], 64, 64)]
            out = pygame.Surface((128, 64), pygame.SRCALPHA)
        out.blit(parts[0], (0, 0))
        out.blit(parts[1], (64, 0))
        return pygame.transform.scale_by(out, S)
    return _cached(("hb", side), make)


def trainer_pic(look):
    """A trainer's battle picture (128x128 at 2x), or None."""
    from . import cast
    mine = cast.picture(look)
    rules = None
    if mine:
        name, rules = mine
    else:
        name = FRONT_PICS.get(look, look if isinstance(look, str) and look.islower() else None)
    if not name:
        return None

    def make():
        img = frlg.sprite(f"graphics/trainers/front_pics/{name}_front_pic.png", rules)
        return pygame.transform.scale_by(img, S) if img else None
    return _cached(("tp", name, rules), make)


def player_back(frame=0):
    """The player's back sprite (frame 0 standing, 1-4 the throw), 128x128 at 2x - in our colours."""
    from . import cast
    look = cast.player_look()

    def make():
        fr = frlg.frames(f"graphics/trainers/back_pics/{cast.BACK_PICS[look]}_back_pic.png", 64, 64,
                         cast.CAST[look][2])
        return pygame.transform.scale_by(fr[min(frame, len(fr) - 1)], S) if fr else None
    return _cached(("back", look, frame), make)


def ball(kind="poke-ball", frame=0):
    """A Poke Ball sprite (32x32 at 2x); frames: 0 closed, 1-2 opening."""
    def make():
        fr = frlg.frames(f"graphics/interface/ball/{BALLS.get(kind, 'poke')}.png", 16, 16)
        return pygame.transform.scale_by(fr[min(frame, len(fr) - 1)], S) if fr else None
    return _cached(("ball", kind, frame), make)


# ====================================================================== FireRed Pokemon sprites (#1-386)
MON_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/generation-iii/firered-leafgreen/"
_mon_wait = set()


def mon(pid, back=False, shiny=False):
    """The FireRed / LeafGreen battle sprite (128x128 at 2x) for the first 386, fetched in the background.
    None until it's there (or for later Pokemon)."""
    if not (1 <= pid <= 386):
        return None
    import os
    sub = ("back/" if back else "") + ("shiny/" if shiny else "")
    path = os.path.join(frlg.DIR, "mons", sub.replace("/", "_") + f"{pid}.png")
    key = ("mon", pid, back, shiny)
    if key in _cache:
        return _cache[key]
    if os.path.exists(path):
        try:
            img = pygame.image.load(path)
            img = img.convert_alpha() if pygame.display.get_surface() else img
            _cache[key] = pygame.transform.scale_by(img, S)
        except Exception:
            _cache[key] = None
        return _cache[key]
    if key not in _mon_wait:
        _mon_wait.add(key)
        import threading
        threading.Thread(target=_download_mon, args=(pid, back, shiny), daemon=True).start()
    return None


def _mon_path(pid, back, shiny):
    import os
    sub = ("back/" if back else "") + ("shiny/" if shiny else "")
    return os.path.join(frlg.DIR, "mons", sub.replace("/", "_") + f"{pid}.png"), sub


def _download_mon(pid, back=False, shiny=False):
    import os
    path, sub = _mon_path(pid, back, shiny)
    if os.path.exists(path):
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        from .pokedex import fetch as download
        data = download(MON_URL + sub + f"{pid}.png", timeout=20)
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
    except Exception:
        pass


_prefetched = []


def prefetch_mons(first=(1, 2, 3, 4, 5, 6, 7, 8, 9, 16, 19, 10, 13)):
    """Gets the FireRed sprites ahead of time so a battle never shows a stand-in while one downloads: the starters
    and early Pokemon right away, then all 386 in the background."""
    if _prefetched:
        return
    _prefetched.append(True)
    from concurrent.futures import ThreadPoolExecutor
    jobs = [(p, b) for p in first for b in (False, True)]
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda j: _download_mon(*j), jobs))

    def rest():
        with ThreadPoolExecutor(6) as ex:
            list(ex.map(lambda j: _download_mon(*j), [(p, b) for p in range(1, 387) for b in (False, True)]))
    import threading
    threading.Thread(target=rest, daemon=True).start()


# ====================================================================== the party menu (graphics/party_menu)
PARTY = "graphics/party_menu/"
# FireRed's party windows (src/data/party_menu.h): tile position, size and palette bank
PARTY_SLOTS = [((1, 3), (10, 7), 3)] + [((12, 1 + 3 * i), (18, 3), 4 + i) for i in range(5)]
# colours swapped into slots 4,5,6 and 1,7,8 of a slot's palette, by state (party_menu.c LoadPartyBoxPalette)
SLOT_PALS = {"normal": ((52, 53, 54), (49, 55, 56)), "selected": ((116, 117, 118), (97, 103, 104)),
             "fainted": ((84, 85, 86), (81, 87, 88)), "fainted_sel": ((148, 149, 150), (97, 103, 104)),
             "switch": ((100, 101, 102), (161, 167, 168))}
HP_PALS = {"green": (57, 58), "yellow": (73, 74), "red": (89, 90)}


def _party_pal():
    f = frlg.fetch(PARTY + "bg.png")
    if not f:
        return None
    img = pygame.image.load(f)
    return [tuple(c)[:3] for c in img.get_palette()]


def party_bg():
    def make():
        pal = _party_pal()
        if not pal:
            return None
        banks = [pal[i:i + 16] for i in range(0, len(pal), 16)]
        img = frlg.tilemap(PARTY + "bg.png", PARTY + "bg.bin", banks, 0)
        if img is None:
            return None
        out = pygame.Surface((240, 160))
        out.fill(pal[0])
        out.blit(img, (0, 0), (0, 0, 240, 160))
        return pygame.transform.scale_by(out, S)
    return _cached(("partybg",), make)


def party_hp_colors(level):
    pal = _cached(("partypal",), _party_pal)
    if not pal:
        return None
    a, b = HP_PALS[level]
    return pal[a], pal[b]


def party_slot(i, state="normal", empty=False):
    """Party slot i's box (2x) in this state, or None."""
    def make():
        pal = _party_pal()
        f = frlg.fetch(PARTY + "bg.png")
        (tx, ty), (w, h), bank = PARTY_SLOTS[i]
        name = "slot_main.bin" if i == 0 else ("slot_wide_empty.bin" if empty else "slot_wide.bin")
        mf = frlg.fetch(PARTY + name)
        if not pal or not f or not mf:
            return None
        colors = list(pal[bank * 16:bank * 16 + 16])
        if empty:   # empty slots: placeholder colours in the file; FireRed shows a dark outline
            dark = pal[1] if pal[1] != (255, 0, 255) else (41, 98, 90)
            colors = [dark if c[0] > 200 and c[1] < 60 and c[2] > 200 else c for c in colors]
        else:
            ids1, ids2 = SLOT_PALS[state]
            for off, pid in zip((4, 5, 6), ids1):
                colors[off] = pal[pid]
            for off, pid in zip((1, 7, 8), ids2):
                colors[off] = pal[pid]
        img = pygame.image.load(f)
        idx = pygame.image.tobytes(img, "P")
        iw = img.get_width()
        per_row = iw // 8
        with open(mf, "rb") as fh:
            nums = fh.read()
        out = pygame.Surface((w * 8, h * 8), pygame.SRCALPHA)
        for n in range(min(len(nums), w * h)):
            t = nums[n]
            sx, sy = (t % per_row) * 8, (t // per_row) * 8
            ox, oy = (n % w) * 8, (n // w) * 8
            for y in range(8):
                for x in range(8):
                    c = idx[(sy + y) * iw + sx + x] & 15
                    if c:
                        out.set_at((ox + x, oy + y), colors[c])
        return pygame.transform.scale_by(out, S)
    return _cached(("slot", i, state, empty), make)


# ====================================================================== "demake": newer sprites in the GBA style
def demake(src, size=64, colors=14):
    """Redraws a sprite the way a GBA one is made: fit into size x size, at most `colors` colours (+ outline),
    hard transparency and a dark outline. Returns a size x size surface (1x)."""
    w, h = src.get_size()
    box = src.get_bounding_rect(min_alpha=40)
    if box.w == 0 or box.h == 0:
        return pygame.Surface((size, size), pygame.SRCALPHA)
    part = src.subsurface(box).copy()
    k = min((size - 4) / box.w, (size - 4) / box.h, 1.0)
    tw, th = max(1, int(box.w * k)), max(1, int(box.h * k))
    small = pygame.transform.smoothscale(part.convert_alpha() if pygame.display.get_surface() else part, (tw, th))
    px = [[small.get_at((x, y)) for x in range(tw)] for y in range(th)]
    solid = [(x, y) for y in range(th) for x in range(tw) if px[y][x].a >= 128]
    if not solid:
        return pygame.Surface((size, size), pygame.SRCALPHA)
    pts = [tuple(px[y][x])[:3] for x, y in solid]
    # k-means down to a GBA-sized palette
    uniq = sorted(set(pts), key=lambda c: c[0] * 0.3 + c[1] * 0.59 + c[2] * 0.11)
    cent = [uniq[int(i * (len(uniq) - 1) / max(1, colors - 1))] for i in range(min(colors, len(uniq)))]
    assign = [0] * len(pts)
    for _ in range(6):
        sums = [[0, 0, 0, 0] for _ in cent]
        for n, c in enumerate(pts):
            best = min(range(len(cent)), key=lambda j: (c[0] - cent[j][0]) ** 2 + (c[1] - cent[j][1]) ** 2 +
                       (c[2] - cent[j][2]) ** 2)
            assign[n] = best
            sm = sums[best]
            sm[0] += c[0]
            sm[1] += c[1]
            sm[2] += c[2]
            sm[3] += 1
        cent = [(sm[0] // sm[3], sm[1] // sm[3], sm[2] // sm[3]) if sm[3] else cent[j] for j, sm in enumerate(sums)]
    out = pygame.Surface((size, size), pygame.SRCALPHA)
    ox, oy = (size - tw) // 2, size - th - 1
    filled = set()
    for n, (x, y) in enumerate(solid):
        out.set_at((ox + x, oy + y), cent[assign[n]])
        filled.add((ox + x, oy + y))
    for x, y in list(filled):   # the outline: darker versions of what's inside
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (x + dx, y + dy)
            if q not in filled and 0 <= q[0] < size and 0 <= q[1] < size and out.get_at(q).a == 0:
                c = out.get_at((x, y))
                out.set_at(q, (c.r // 4 + 16, c.g // 4 + 16, c.b // 4 + 24))
    return out


# ====================================================================== the professor's speech (graphics/oak_speech)
INTRO = "graphics/oak_speech/"
INTRO_FILES = [INTRO + n for n in ("bg_tiles.png", "oak_speech_bg.png", "oak_speech_bg.bin", "platform.png",
                                   "platform.pal", "oak/pic.png", "oak/pal.pal", "red/pic.png", "red/pal.pal",
                                   "leaf/pic.png", "leaf/pal.pal", "rival/pic.png", "rival/pal.pal")]


def intro_bg():
    """The backdrop of FireRed's professor speech (480x320)."""
    def make():
        f = frlg.fetch(INTRO + "bg_tiles.png")
        if not f:
            return None
        pal = [tuple(c)[:3] for c in pygame.image.load(f).get_palette()]
        img = frlg.tilemap(INTRO + "oak_speech_bg.png", INTRO + "oak_speech_bg.bin",
                           [pal[i:i + 16] for i in range(0, len(pal), 16)], 0)
        if img is None:
            return None
        out = pygame.Surface((240, 160))
        out.fill(pal[1])
        out.blit(img, (0, 0), (0, 0, 240, 160))
        return pygame.transform.scale_by(out, S)
    return _cached(("introbg",), make)


def intro_pic(who):
    """The big speech portraits (128x192): 'prof', 'player', 'player_f', 'rival' - in our cast's colours."""
    from . import cast
    folder = {"prof": "oak", "player": "red", "player_f": "leaf", "rival": "rival"}[who]
    rules = cast.CAST[who][2] if who in cast.CAST else ()
    if who == "rival":   # his intro picture has one trouser leg in a second (lilac) palette: match the other
        rules = tuple(rules) + ((285, 315, 20, 1.45, 0.8, 0.1),)

    def make():
        f = frlg.fetch(INTRO + folder + "/pic.png")
        if not f:
            return None
        img = pygame.image.load(f)
        idx = pygame.image.tobytes(img, "P")
        w, h = img.get_size()
        pal = [tuple(c)[:3] for c in img.get_palette()]   # some pics use two 16-colour banks
        while len(pal) > 16 and pal[-1] == (0, 0, 0):
            pal.pop()
        cols = frlg.recolor_palette(pal, rules) if rules else pal
        out = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            for x in range(w):
                c = idx[y * w + x]
                if c % 16:
                    out.set_at((x, y), cols[c % len(cols)])
        return pygame.transform.scale_by(out, S)
    return _cached(("intropic", who), make)


def intro_platform():
    """The little platform a Pokemon stands on during the speech (192x64)."""
    def make():
        f = frlg.fetch(INTRO + "platform.png")
        pal = frlg.read_pal(INTRO + "platform.pal")
        if not f or not pal:
            return None
        img = pygame.image.load(f)
        idx = pygame.image.tobytes(img, "P")
        w, h = img.get_size()
        out = pygame.Surface((96, 32), pygame.SRCALPHA)
        for part in range(3):   # three 32x32 pieces, stacked in the file, side by side on screen
            for y in range(32):
                for x in range(32):
                    c = idx[(part * 32 + y) * w + x] & 15
                    if c:
                        out.set_at((part * 32 + x, y), pal[c])
        return pygame.transform.scale_by(out, S)
    return _cached(("platform",), make)
