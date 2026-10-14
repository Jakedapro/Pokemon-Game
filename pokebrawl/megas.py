"""Our own Mega Evolutions, made the way fan sprite artists make them: spliced and repainted from GBA-style
sprites (the pokeemerald-expansion community redraws - credited in the README). Each recipe takes a loader
L(folder, back=False) -> spritekit.Img and returns the front and back 64x64 sprites.

The sprites are downloaded and built on the player's machine and cached in ~/.pokebrawl/megas; nothing here is a
picture, only the editing steps.
"""
import os

from . import spritekit as K

# pinned so the cut coordinates always match the pictures
PEX_COMMIT = "73b3fbeb574327cd9420c89e56bef5aa3c08fead"
PEX_URL = "https://raw.githubusercontent.com/rh-hideout/pokeemerald-expansion/" + PEX_COMMIT + "/graphics/pokemon/"


PARTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "art", "megaparts")


def part(name):
    """One of our own drawn add-on layers (art/megaparts/NAME.png), as an Img."""
    import pygame
    return K.from_surface(pygame.image.load(os.path.join(PARTS, name + ".png")))


def stamp(img, x0, y0, rows, colors, only_on=False):
    """Hand-placed pixels: rows of characters, each mapped through `colors` ('.' = leave alone)."""
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            col = colors.get(ch)
            if col and (not only_on or img.get(x0 + c, y0 + r) is not None):
                img.set(x0 + c, y0 + r, col)


# ---------------------------------------------------------------------------------------------- Mega Snorlax
SN_OUT = (16, 16, 8)
SN_CREAM = (246, 230, 189)
SN_TEAL = [(16, 57, 65), (49, 90, 123), (82, 139, 172), (115, 164, 189)]
BAND = {"o": (96, 16, 32), "d": (184, 40, 48), "r": (232, 72, 64), "h": (248, 136, 112)}


def snorlax(L):
    """Mega Snorlax - Normal/Fighting, Iron Fist: up on its feet for once, boxing gloves on, a fighter's
    headband and a champion's belt. Snorlax's own sprite stood on new legs; the add-ons are drawn in its palette."""
    host = L("snorlax")
    host.erase(K.poly([(0, 43), (26, 43), (26, 64), (0, 64)]))     # the sitting feet
    host.erase(K.poly([(33, 45), (64, 45), (64, 64), (33, 64)]))
    body, (bx, by) = host.trim()
    out = K.Img(64, 64)
    out.paste(body, bx, by - 5)
    out.paste(part("snorlax_under"), 0, 0, under=True)
    out.paste(part("snorlax_over"), 0, 0)
    # eyes open - wide awake for once
    for x in range(20, 37):
        for y in range(11, 15):
            if out.get(x, y) in ((16, 16, 8), (112, 112, 112), (200, 200, 200), SN_TEAL[0], SN_TEAL[1]):
                out.set(x, y, SN_CREAM)
    eye = {"k": SN_OUT, "w": (248, 248, 248)}
    stamp(out, 20, 10, ["kk....",
                        "..kkk.",
                        ".wwkwk",
                        ".kwkwk",
                        "..kkk."], eye)
    stamp(out, 32, 10, ["....kk",
                        ".kkk..",
                        "kwkww.",
                        "kwkwk.",
                        ".kkk.."], eye)
    # back: the headband knotted behind the head, tails hanging
    back = L("snorlax", back=True)
    for x in range(19, 53):
        for y, ch in ((20, "o"), (21, "r"), (22, "d"), (23, "o")):
            if back.get(x, y) is not None:
                back.set(x, y, BAND[ch])
    stamp(back, 33, 19, [".ooo.",
                         "ohrro",
                         "orrdo",
                         "orddo",
                         ".ooo."], BAND)
    stamp(back, 31, 24, ["..oro....",
                         ".ordo....",
                         ".odo.....",
                         "odo......",
                         "oo......."], BAND)
    stamp(back, 36, 24, ["oro...",
                         "orrdo.",
                         ".odrdo",
                         "..oddo",
                         "...oo."], BAND)
    return out, back


RECIPES = {"snorlax": snorlax}
NEEDS = {"snorlax": ["snorlax"]}


# ---------------------------------------------------------------------------------------------- loading / building
def local_loader(root):
    """Loader reading a pokeemerald-expansion graphics/pokemon folder."""
    def L(name, back=False):
        d = os.path.join(root, name)
        if back:
            f = os.path.join(d, "back.png")
        else:
            f = os.path.join(d, "anim_front.png")
            if not os.path.exists(f):
                f = os.path.join(d, "front.png")
        return K.load_gba(f, os.path.join(d, "normal.pal"))
    return L


def _home():
    from .pokedex import HOME
    return HOME


def cache_dir():
    return os.path.join(_home(), "megas")


def src_dir():
    return os.path.join(_home(), "pex", PEX_COMMIT[:10])


def built_path(base_key, back=False):
    p = os.path.join(cache_dir(), f"{base_key}{'_back' if back else ''}.png")
    return p if os.path.exists(p) else None


def _download(names):
    """Fetch the source sprites a recipe needs (front, back, palette) into ~/.pokebrawl/pex."""
    from .pokedex import fetch
    for name in names:
        d = os.path.join(src_dir(), name)
        os.makedirs(d, exist_ok=True)
        for files in (("normal.pal",), ("back.png",), ("anim_front.png", "front.png")):
            if any(os.path.exists(os.path.join(d, f)) for f in files):
                continue
            last = None
            for f in files:
                try:
                    data = fetch(PEX_URL + name + "/" + f, timeout=30)
                except Exception as e:  # noqa: BLE001 - try the other name, then give up
                    last = e
                    continue
                with open(os.path.join(d, f) + ".part", "wb") as fh:
                    fh.write(data)
                os.replace(os.path.join(d, f) + ".part", os.path.join(d, f))
                break
            else:
                raise OSError(f"couldn't download {name}/{files[0]}: {last}")


def build(base_key):
    """Download what a recipe needs, build the Mega and save front + back into the cache. Returns True if built."""
    if base_key not in RECIPES:
        return False
    _download(NEEDS[base_key])
    front, back = RECIPES[base_key](local_loader(src_dir()))
    import pygame
    os.makedirs(cache_dir(), exist_ok=True)
    for img, suffix in ((front, ""), (back, "_back")):
        path = os.path.join(cache_dir(), f"{base_key}{suffix}.png")
        pygame.image.save(img.to_surface(), path + ".part.png")
        os.replace(path + ".part.png", path)
    with open(os.path.join(cache_dir(), "version.txt"), "w") as f:
        f.write(VERSION)
    return True


VERSION = "1"   # bump when a recipe changes so players' cached sprites get rebuilt
_busy = set()


def _stale():
    try:
        with open(os.path.join(cache_dir(), "version.txt")) as f:
            return f.read().strip() != VERSION
    except OSError:
        return True


def ensure(base_key, wait=False):
    """Path of the built front sprite, building it in the background if it isn't there yet (None meanwhile)."""
    if base_key not in RECIPES:
        return None
    if _stale() and not _busy:
        import shutil
        shutil.rmtree(cache_dir(), ignore_errors=True)
    path = built_path(base_key)
    if path:
        return path
    if wait:
        try:
            build(base_key)
        except Exception:  # noqa: BLE001 - offline: no sprite yet
            return None
        return built_path(base_key)
    if base_key not in _busy:
        _busy.add(base_key)
        import threading

        def run():
            try:
                build(base_key)
            except Exception:  # noqa: BLE001
                pass
            finally:
                _busy.discard(base_key)
        threading.Thread(target=run, daemon=True).start()
    return None


def build_all(log=print):
    for key in RECIPES:
        try:
            if not built_path(key) or _stale():
                build(key)
        except Exception as e:  # noqa: BLE001
            log(f"[pokebrawl] couldn't build Mega {key.title()} yet ({e})")
