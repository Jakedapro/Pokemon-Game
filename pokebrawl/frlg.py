"""FireRed / LeafGreen graphics, loaded from the pret/pokefirered decompilation.

Nothing from the original games ships with PokeBrawl. The first time Adventure mode needs a sprite, tile set or
battle background, the file is downloaded from the public decompilation project on GitHub into
~/.pokebrawl/frlg/ (the same way Pokemon sprites and cries are fetched). If a file can't be downloaded, callers
fall back to the game's own drawn art.

Formats (as in the decomp):
  - sprites are indexed PNGs with their palette inside; colour 0 is transparent
  - tile sets are a grey-index tiles.png, 16-colour JASC .pal files and metatiles.bin, where each 16x16 metatile
    is 8 little-endian u16 entries (4 bottom-layer 8x8 tiles, then 4 top-layer ones, in TL TR BL BR order):
    bits 0-9 tile index, bit 10 h-flip, bit 11 v-flip, bits 12-15 palette
"""
import os
import struct
import threading
from concurrent.futures import ThreadPoolExecutor

import pygame

COMMIT = "037335f4c725d7c9aecdac87066f2002b4bd7e14"
BASE = f"https://raw.githubusercontent.com/pret/pokefirered/{COMMIT}/"
DIR = os.path.join(os.path.expanduser("~"), ".pokebrawl", "frlg")
PRIMARY_TILES = 640       # tiles and metatiles below this index live in the primary tile set
PRIMARY_PALS = 7          # palettes 0-6 come from the primary set, 7-12 from the secondary one

_lock = threading.Lock()
_ready = threading.Event()
_started = []
_failed = set()
_cache = {}
OFFLINE = False           # tests can switch the downloads off


def local(path):
    return os.path.join(DIR, *path.split("/"))


def fetch(path, timeout=8):
    """The local copy of a decomp file, downloading it once. None if it can't be had."""
    dest = local(path)
    if os.path.exists(dest):
        return dest
    if OFFLINE or path in _failed:
        return None
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        from .pokedex import fetch as download   # handles Mac certificate trouble (keychain, certifi, curl)
        data = download(BASE + path, timeout=max(timeout, 20))
        tmp = dest + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
        return dest
    except Exception:
        with _lock:
            _failed.add(path)
        return None


PROGRESS = [0, 0]   # files done, files to get (for the title screen's progress bar)
MARKER = os.path.join(DIR, "complete.json")
FILESET = 2         # bump when an update needs more files: everyone downloads just the new ones, once


def prefetch(paths, workers=8):
    """Downloads many files at once (used when Adventure starts). Returns how many are available."""
    todo = [p for p in paths if not os.path.exists(local(p)) and p not in _failed]
    if todo and not OFFLINE:
        PROGRESS[0], PROGRESS[1] = 0, len(todo)

        def one(p):
            fetch(p)
            PROGRESS[0] += 1
        with ThreadPoolExecutor(workers) as ex:
            list(ex.map(one, todo))
    return sum(os.path.exists(local(p)) for p in paths)


def complete():
    """True once everything has been downloaded (then the game never needs the internet for it again)."""
    try:
        import json
        with open(MARKER, encoding="utf-8") as f:
            m = json.load(f)
        return m.get("fileset") == FILESET and m.get("commit") == COMMIT
    except Exception:
        return False


def mark_complete():
    import json
    os.makedirs(DIR, exist_ok=True)
    with open(MARKER, "w", encoding="utf-8") as f:
        json.dump({"fileset": FILESET, "commit": COMMIT, "missing": sorted(_failed)}, f)


def _known_missing():
    """Files the decomp doesn't have (remembered, so they're never asked for again)."""
    try:
        import json
        with open(MARKER, encoding="utf-8") as f:
            return set(json.load(f).get("missing", []))
    except Exception:
        return set()


def start(job):
    """Runs job (which downloads files) once, in the background. is_ready() turns True when it's done.
    After one complete download the files are all on disk: it's ready at once and nothing is downloaded."""
    if _started:
        return
    _started.append(True)
    if complete():
        _failed.update(_known_missing())
        _ready.set()
        return

    def run():
        try:
            job()
        except Exception:
            pass
        _ready.set()
    threading.Thread(target=run, daemon=True).start()


def retry(job):
    """After a failed download: forget what failed and try again."""
    _started.clear()
    _ready.clear()
    _failed.clear()
    _cache.clear()
    _sets.clear()
    start(job)


def is_ready():
    return _ready.is_set()


def set_ready():
    _ready.set()


# ====================================================================== sprites
def recolor_palette(colors, rules):
    """Palette swap, the way the games make new characters from old ones. rules: list of
    (hue_from, hue_to, new_hue, sat_mult, val_mult[, min_saturation]); hues in degrees, only fairly saturated colours (not skin,
    not greys) are touched. new_hue None keeps the hue. Returns the new colour list."""
    import colorsys
    out = []
    for c in colors:
        r, g, b = (v / 255 for v in c[:3])
        h, sat, val = colorsys.rgb_to_hsv(r, g, b)
        hd = h * 360
        for rule in rules:
            lo, hi, new, sm, vm = rule[:5]
            min_sat = rule[5] if len(rule) > 5 else 0.22
            inside = lo <= hd <= hi if lo <= hi else (hd >= lo or hd <= hi)
            skin = 10 <= hd <= 40 and sat < 0.45 and val > 0.6
            if inside and sat > min_sat and not skin:
                if new is not None:
                    h = (new % 360) / 360
                sat, val = min(1.0, sat * sm), min(1.0, val * vm)
                break
        r, g, b = colorsys.hsv_to_rgb(h, sat, val)
        out.append((int(r * 255), int(g * 255), int(b * 255)))
    return out


def sprite(path, recolor=None):
    """An indexed sprite sheet with colour 0 made transparent (palette-swapped by `recolor` rules). None if
    missing."""
    key = ("spr", path, recolor)
    if key in _cache:
        return _cache[key]
    f = fetch(path)
    img = None
    if f:
        try:
            raw = pygame.image.load(f)
            if raw.get_bitsize() == 8:
                if recolor:
                    pal = [tuple(c)[:3] for c in raw.get_palette()]
                    raw.set_palette([pal[0]] + recolor_palette(pal[1:], recolor))
                raw.set_colorkey(raw.get_palette_at(0))
            img = raw.convert_alpha() if pygame.display.get_surface() else _to_rgba(raw)
        except Exception:
            img = None
    _cache[key] = img
    return img


def _to_rgba(raw):
    out = pygame.Surface(raw.get_size(), pygame.SRCALPHA)
    out.blit(raw, (0, 0))
    return out


def frames(path, w, h, recolor=None):
    """A sprite sheet cut into w x h frames (left to right, then top to bottom)."""
    key = ("frames", path, w, h, recolor)
    if key in _cache:
        return _cache[key]
    sheet = sprite(path, recolor)
    out = None
    if sheet:
        sw, sh = sheet.get_size()
        out = [sheet.subsurface((x, y, w, h)).copy() for y in range(0, sh - h + 1, h) for x in range(0, sw - w + 1, w)]
    _cache[key] = out
    return out


# ====================================================================== tile sets
def read_pal(path):
    f = fetch(path)
    if not f:
        return None
    with open(f, encoding="utf-8") as fh:
        lines = fh.read().split()
    # JASC-PAL, 0100, count, then r g b triples
    n = int(lines[2])
    vals = list(map(int, lines[3:3 + n * 3]))
    return [tuple(vals[i:i + 3]) for i in range(0, n * 3, 3)]


class Tileset:
    """One primary + secondary tile set pair, drawn as 16x16 metatiles."""

    def __init__(self, primary, secondary, recolor=None):
        self.ok = False
        self.parts = []
        for name in (primary, secondary):
            d = f"data/tilesets/{name}/"
            tiles_f = fetch(d + "tiles.png")
            meta_f = fetch(d + "metatiles.bin")
            if not tiles_f or not meta_f:
                return
            pals = [read_pal(d + f"palettes/{i:02d}.pal") for i in range(16)]
            if recolor and name == secondary:   # a palette swap of the room's own tiles (gyms in type colours)
                pals = [[p[0]] + recolor_palette(p[1:], recolor) if p else p for p in pals]
            img = pygame.image.load(tiles_f)
            w, h = img.get_size()
            idx = pygame.image.tobytes(img, "P") if img.get_bitsize() == 8 else None
            if idx is None:
                return
            with open(meta_f, "rb") as fh:
                meta = fh.read()
            attr_f = fetch(d + "metatile_attributes.bin")
            attrs = ()
            if attr_f:
                with open(attr_f, "rb") as fh:
                    a = fh.read()
                attrs = struct.unpack(f"<{len(a) // 4}I", a)
            self.parts.append({"w": w, "h": h, "idx": idx, "pals": pals, "attrs": attrs,
                               "meta": struct.unpack(f"<{len(meta) // 2}H", meta)})
        self.cache = {}
        self.ok = True

    def _pal(self, n):
        part = self.parts[0] if n < PRIMARY_PALS else self.parts[1]
        return part["pals"][n] or [(0, 0, 0)] * 16

    def attr(self, mid):
        part = self.parts[0] if mid < PRIMARY_TILES else self.parts[1]
        m = mid if mid < PRIMARY_TILES else mid - PRIMARY_TILES
        return part["attrs"][m] if m < len(part["attrs"]) else 0

    def layer_type(self, mid):
        """0 normal (second half drawn over people), 1 covered (all under), 2 split (second half over)."""
        return (self.attr(mid) >> 29) & 3

    def behavior(self, mid):
        return self.attr(mid) & 0x1FF

    def _tile(self, entry, surf, ox, oy, layer_top):
        t = entry & 0x3FF
        hf, vf = entry & 0x400, entry & 0x800
        pal = self._pal(entry >> 12)
        part = self.parts[0] if t < PRIMARY_TILES else self.parts[1]
        t = t if t < PRIMARY_TILES else t - PRIMARY_TILES
        per_row = part["w"] // 8
        tx, ty = (t % per_row) * 8, (t // per_row) * 8
        if ty >= part["h"]:
            return
        idx, w = part["idx"], part["w"]
        for y in range(8):
            sy = 7 - y if vf else y
            row = (ty + sy) * w + tx
            for x in range(8):
                sx = 7 - x if hf else x
                c = idx[row + sx] & 15
                if c == 0:
                    if layer_top:
                        continue
                    surf.set_at((ox + x, oy + y), self._pal(0)[0])   # the backdrop shows through
                    continue
                surf.set_at((ox + x, oy + y), pal[c])

    def metatile(self, mid, layers="both"):
        """A 16x16 metatile. layers: 'both', 'bottom', 'top' (transparent where empty), or as the field engine
        draws it: 'under' (beneath people) and 'over' (above people, e.g. tree tops and roofs)."""
        if layers in ("under", "over"):
            lt = self.layer_type(mid)
            if layers == "under":
                return self.metatile(mid, "both" if lt == 1 else "bottom")
            key = (mid, "over")
            if key not in self.cache:
                self.cache[key] = self.metatile(mid, "top") if lt in (0, 2) else None
            return self.cache[key]
        key = (mid, layers)
        if key in self.cache:
            return self.cache[key]
        part = self.parts[0] if mid < PRIMARY_TILES else self.parts[1]
        m = mid if mid < PRIMARY_TILES else mid - PRIMARY_TILES
        ents = part["meta"][m * 8:m * 8 + 8]
        surf = pygame.Surface((16, 16), pygame.SRCALPHA)
        if len(ents) == 8:
            if layers in ("both", "bottom"):
                for k in range(4):
                    self._tile(ents[k], surf, (k % 2) * 8, (k // 2) * 8, False)
            if layers in ("both", "top"):
                for k in range(4):
                    self._tile(ents[4 + k], surf, (k % 2) * 8, (k // 2) * 8, True)
        self.cache[key] = surf
        return surf

    def count(self, which=0):
        return len(self.parts[which]["meta"]) // 8


_sets = {}


def tileset(primary, secondary, recolor=None):
    key = (primary, secondary, recolor)
    if key not in _sets:
        ts = Tileset(primary, secondary, recolor)
        _sets[key] = ts if ts.ok else None
    return _sets[key]


def _tileset_name(sym):
    import re
    name = re.sub(r"(?<!^)(?=[A-Z])", "_", sym.replace("gTileset_", ""))
    return re.sub(r"(?<=[A-Za-z])(?=[0-9])", "_", name).lower()   # GenericBuilding1 -> generic_building_1


def layouts():
    if "layouts" not in _cache:
        import json
        f = fetch("data/layouts/layouts.json")
        out = {}
        if f:
            with open(f, encoding="utf-8") as fh:
                for l in json.load(fh)["layouts"]:
                    if l.get("name"):
                        out[l["name"]] = l
        _cache["layouts"] = out
    return _cache["layouts"]


def layout(name, recolor=None):
    """A map layout: {'w', 'h', 'blocks' (u16 per cell), 'tiles' (Tileset)} or None."""
    key = ("layout", name, recolor)
    if key in _cache:
        return _cache[key]
    out = None
    l = layouts().get(name)
    if l:
        f = fetch(l["blockdata_filepath"])
        ts = tileset("primary/" + _tileset_name(l["primary_tileset"]),
                     "secondary/" + _tileset_name(l["secondary_tileset"]), recolor)
        if f and ts:
            with open(f, "rb") as fh:
                data = fh.read()
            w, h = l["width"], l["height"]
            out = {"w": w, "h": h, "blocks": struct.unpack(f"<{w * h}H", data[:w * h * 2]), "tiles": ts}
    _cache[key] = out
    return out


def map_json(name):
    """data/maps/<name>/map.json: object_events, warp_events, bg_events."""
    key = ("mapjson", name)
    if key not in _cache:
        import json
        f = fetch(f"data/maps/{name}/map.json")
        try:
            with open(f, encoding="utf-8") as fh:
                _cache[key] = json.load(fh)
        except Exception:
            _cache[key] = None
    return _cache[key]


def render(name, x=0, y=0, w=None, h=None, scale=2, recolor=None):
    """Part of a real map, as the field engine draws it: (under, over, blocked) where blocked[y][x] says whether
    a cell has collision. None if the files can't be had."""
    key = ("render", name, x, y, w, h, scale, recolor)
    if key in _cache:
        return _cache[key]
    lay = layout(name, recolor)
    out = None
    if lay:
        w = w or lay["w"] - x
        h = h or lay["h"] - y
        ts = lay["tiles"]
        under = pygame.Surface((w * 16, h * 16), pygame.SRCALPHA)
        over = pygame.Surface((w * 16, h * 16), pygame.SRCALPHA)
        blocked = []
        for yy in range(h):
            row = []
            for xx in range(w):
                b = lay["blocks"][(y + yy) * lay["w"] + x + xx]
                mid = b & 0x3FF
                under.blit(ts.metatile(mid, "under"), (xx * 16, yy * 16))
                top = ts.metatile(mid, "over")
                if top is not None:
                    over.blit(top, (xx * 16, yy * 16))
                row.append(bool(b & 0xC00))
            blocked.append(row)
        if scale != 1:
            under = pygame.transform.scale_by(under, scale)
            over = pygame.transform.scale_by(over, scale)
        out = (under, over, blocked)
    _cache[key] = out
    return out


# ====================================================================== tile maps (battle backgrounds, windows)
def tilemap(tiles_path, map_path, pals, base_bank=0, width=32, rows=None):
    """Draws a GBA tile map: tiles_path (indexed PNG of 8x8 tiles), map_path (u16 entries: tile, flips, palette
    bank), pals (list of 16-colour palettes, the first one being bank `base_bank`). None if anything's missing."""
    key = ("tilemap", tiles_path, map_path, tuple(map(tuple, pals[0])) if pals and pals[0] else None, base_bank,
           width, rows)
    if key in _cache:
        return _cache[key]
    tf, mf = fetch(tiles_path), fetch(map_path)
    out = None
    if tf and mf and pals and all(pals):
        img = pygame.image.load(tf)
        if img.get_bitsize() == 8:
            idx = pygame.image.tobytes(img, "P")
            tw = img.get_width()
            per_row = tw // 8
            ntiles = per_row * (img.get_height() // 8)
            with open(mf, "rb") as fh:
                data = fh.read()
            ents = struct.unpack(f"<{len(data) // 2}H", data)
            h = rows or len(ents) // width
            out = pygame.Surface((width * 8, h * 8), pygame.SRCALPHA)
            out.fill((0, 0, 0, 0))
            for n in range(min(len(ents), width * h)):
                e = ents[n]
                t, hf, vf, bank = e & 0x3FF, e & 0x400, e & 0x800, e >> 12
                if t >= ntiles:
                    continue
                k = bank - base_bank
                pal = pals[k] if 0 <= k < len(pals) else pals[0]
                tx, ty = (t % per_row) * 8, (t // per_row) * 8
                ox, oy = (n % width) * 8, (n // width) * 8
                for y in range(8):
                    sy = 7 - y if vf else y
                    row = (ty + sy) * tw + tx
                    for x in range(8):
                        sx = 7 - x if hf else x
                        c = idx[row + sx] & 15
                        if c:
                            out.set_at((ox + x, oy + y), pal[c])
    _cache[key] = out
    return out


def pal_banks(path):
    """A .pal file split into 16-colour banks."""
    p = read_pal(path)
    if not p:
        return None
    return [p[i:i + 16] + [(0, 0, 0)] * (16 - len(p[i:i + 16])) for i in range(0, len(p), 16)]


# ====================================================================== the text font
# Gen 3 character codes for what Adventure mode writes
_CHARS = {" ": 0x00, "!": 0xAB, "?": 0xAC, ".": 0xAD, "-": 0xAE, "…": 0xB0, '"': 0xB1, "'": 0xB4, "♂": 0xB5,
          "♀": 0xB6, ",": 0xB8, "×": 0xB9, "/": 0xBA, ":": 0xF0, "é": 0x1B, "(": 0x5C, ")": 0x5D, "&": 0x2D,
          "+": 0x2E, "=": 0x35, ";": 0x36, "%": 0x5B}
_CHARS.update({str(d): 0xA1 + d for d in range(10)})
_CHARS.update({chr(65 + i): 0xBB + i for i in range(26)})
_CHARS.update({chr(97 + i): 0xD5 + i for i in range(26)})


class Font:
    """FireRed's normal text font (graphics/fonts/latin_normal.png, widths from src/text.c)."""

    def __init__(self, kind="normal"):
        self.ok = False
        img_f = fetch(f"graphics/fonts/latin_{kind}.png")
        src_f = fetch("src/text.c")
        if not img_f or not src_f:
            return
        import re
        with open(src_f, encoding="utf-8", errors="replace") as fh:
            src = fh.read()
        table = {"normal": "sFontNormalLatinGlyphWidths", "small": "sFontSmallLatinGlyphWidths"}[kind]
        m = re.search(table + r"\[\]\s*=\s*\{([^}]*)\}", src)
        if not m:
            return
        self.widths = [int(v) for v in re.findall(r"\d+", m.group(1))]
        img = pygame.image.load(img_f)
        if img.get_bitsize() != 8:
            return
        self.idx = pygame.image.tobytes(img, "P")
        self.iw = img.get_width()
        self.cw = 8 if kind == "small" else 16      # glyph cell width in the sheet (cells are 16 tall)
        self.per_row = self.iw // self.cw
        self.cache = {}
        # where capitals start and end inside the 16x16 cell, to line text up with the old font
        rows = [y for y in range(16) for x in range(min(8, self.cw)) if self._px(_CHARS["A"], x, y) == 1]
        self.top = min(rows) if rows else 2
        self.cap = (max(rows) - self.top + 1) if rows else 10
        self.ok = True

    def _px(self, code, x, y):
        cx, cy = (code % self.per_row) * self.cw, (code // self.per_row) * 16
        return self.idx[(cy + y) * self.iw + cx + x]

    def has(self, ch):
        return ch in _CHARS

    def width(self, ch):
        code = _CHARS.get(ch)
        return self.widths[code] if code is not None and code < len(self.widths) else 6

    def glyph(self, ch, color, shadow, scale=1):
        key = (ch, color, shadow, scale)
        if key in self.cache:
            return self.cache[key]
        if scale != 1:
            self.cache[key] = pygame.transform.scale_by(self.glyph(ch, color, shadow), scale)
            return self.cache[key]
        if key in self.cache:
            return self.cache[key]
        code = _CHARS[ch]
        w = self.width(ch)
        s = pygame.Surface((w, 16), pygame.SRCALPHA)
        for y in range(16):
            for x in range(min(w, self.cw)):
                c = self._px(code, x, y)
                if c == 1:
                    s.set_at((x, y), color)
                elif c == 2 and shadow:
                    s.set_at((x, y), shadow)
        self.cache[key] = s
        return s


def font(kind="normal"):
    key = ("font", kind)
    if key not in _cache:
        f = Font(kind)
        _cache[key] = f if f.ok else None
    return _cache[key]
