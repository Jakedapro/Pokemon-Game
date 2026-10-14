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
    "prof": "professor_oak", "leader": "cool_trainer_m", "camper": "camper", "cooltrainer_m": "cool_trainer_m",
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
    out += [f"graphics/trainers/front_pics/{n}_front_pic.png" for n in sorted(set(FRONT_PICS.values()))]
    out += ["graphics/trainers/back_pics/red_back_pic.png"]
    out += [f"graphics/interface/ball/{n}.png" for n in BALLS.values()]
    out += ["graphics/fonts/latin_normal.png", "src/text.c"]
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
    name = FRONT_PICS.get(look, look if isinstance(look, str) and look.islower() else None)
    if not name:
        return None

    def make():
        img = frlg.sprite(f"graphics/trainers/front_pics/{name}_front_pic.png")
        return pygame.transform.scale_by(img, S) if img else None
    return _cached(("tp", name), make)


def player_back(frame=0):
    """Red's back sprite (frame 0 standing, 1-4 the throw), 128x128 at 2x."""
    def make():
        fr = frlg.frames("graphics/trainers/back_pics/red_back_pic.png", 64, 64)
        return pygame.transform.scale_by(fr[min(frame, len(fr) - 1)], S) if fr else None
    return _cached(("back", frame), make)


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
        import urllib.request

        def get():
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with urllib.request.urlopen(MON_URL + sub + f"{pid}.png", timeout=10) as r:
                    data = r.read()
                with open(path + ".part", "wb") as f:
                    f.write(data)
                os.replace(path + ".part", path)
            except Exception:
                pass
        threading.Thread(target=get, daemon=True).start()
    return None
