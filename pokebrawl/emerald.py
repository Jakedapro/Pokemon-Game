"""Maps from Pokemon Emerald (the pret/pokeemerald decomp), drawn like frlg.py draws FireRed's.

Emerald keeps its maps the same way FireRed does, with a few differences: 512 metatiles and 6 palettes in a
primary tile set (FireRed: 640 and 7), and 16-bit metatile attributes with the layer type in the top bits.
Files download once into ~/.pokebrawl/emerald, and everything returns None when they can't be had.
"""
import os
import struct
import threading

import pygame

from . import frlg

COMMIT = "731ad5bfd6e6f265508d0efcca0ba42f9dcf5881"
BASE = f"https://raw.githubusercontent.com/pret/pokeemerald/{COMMIT}/"
DIR = os.path.join(os.path.dirname(frlg.DIR), "emerald")
PRIMARY_TILES = 512
PRIMARY_PALS = 6
_cache = {}
_failed = set()
_lock = threading.Lock()


def fetch(path, timeout=20):
    dest = os.path.join(DIR, *path.split("/"))
    if os.path.exists(dest):
        return dest
    if frlg.OFFLINE or path in _failed:
        return None
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        from .pokedex import fetch as download
        data = download(BASE + path, timeout=timeout)
        tmp = dest + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
        return dest
    except Exception:  # noqa: BLE001
        with _lock:
            _failed.add(path)
        return None


def _read_pal(f):
    with open(f, encoding="utf-8") as fh:
        vals = fh.read().split()
    n = int(vals[2])   # JASC-PAL, 0100, count, then r g b triples
    nums = list(map(int, vals[3:3 + n * 3]))
    return [tuple(nums[i:i + 3]) for i in range(0, n * 3, 3)]


class Tileset(frlg.Tileset):
    """An Emerald primary + secondary tile set pair."""

    def __init__(self, primary, secondary):   # noqa: D107 - same as frlg.Tileset, Emerald's files
        self.ok = False
        self.parts = []
        for name in (primary, secondary):
            d = f"data/tilesets/{name}/"
            tiles_f, meta_f = fetch(d + "tiles.png"), fetch(d + "metatiles.bin")
            if not tiles_f or not meta_f:
                return
            pals = []
            for i in range(16):
                f = fetch(d + f"palettes/{i:02d}.pal")
                pals.append(_read_pal(f) if f else None)
            img = pygame.image.load(tiles_f)
            if img.get_bitsize() != 8:
                return
            with open(meta_f, "rb") as fh:
                meta = fh.read()
            attr_f = fetch(d + "metatile_attributes.bin")
            attrs = ()
            if attr_f:
                with open(attr_f, "rb") as fh:
                    a = fh.read()
                attrs = struct.unpack(f"<{len(a) // 2}H", a)
            w, h = img.get_size()
            self.parts.append({"w": w, "h": h, "idx": pygame.image.tobytes(img, "P"), "pals": pals,
                               "attrs": attrs, "meta": struct.unpack(f"<{len(meta) // 2}H", meta)})
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
        return (self.attr(mid) >> 12) & 0xF

    def behavior(self, mid):
        return self.attr(mid) & 0xFF

    def _part(self, t):
        return (self.parts[0], t) if t < PRIMARY_TILES else (self.parts[1], t - PRIMARY_TILES)

    def _tile(self, entry, surf, ox, oy, layer_top):
        t = entry & 0x3FF
        hf, vf = entry & 0x400, entry & 0x800
        pal = self._pal(entry >> 12)
        part, t = self._part(t)
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
                    if not layer_top:
                        surf.set_at((ox + x, oy + y), self._pal(0)[0])
                    continue
                surf.set_at((ox + x, oy + y), pal[c])

    def metatile(self, mid, layers="both"):
        if layers in ("under", "over"):
            return super().metatile(mid, layers)
        key = (mid, layers)
        if key in self.cache:
            return self.cache[key]
        part, m = self._part(mid)
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


def layout(name):
    key = ("layout", name)
    if key in _cache:
        return _cache[key]
    out = None
    l = layouts().get(name)
    if l:
        f = fetch(l["blockdata_filepath"])
        ts_key = (l["primary_tileset"], l["secondary_tileset"])
        if ts_key not in _cache:
            ts = Tileset("primary/" + frlg._tileset_name(ts_key[0]), "secondary/" + frlg._tileset_name(ts_key[1]))
            _cache[ts_key] = ts if ts.ok else None
        ts = _cache[ts_key]
        if f and ts:
            with open(f, "rb") as fh:
                data = fh.read()
            w, h = l["width"], l["height"]
            out = {"w": w, "h": h, "blocks": struct.unpack(f"<{w * h}H", data[:w * h * 2]), "tiles": ts}
    _cache[key] = out
    return out


def render(name, x=0, y=0, w=None, h=None, scale=1, swap=None, cells=None):
    """Part of a real Emerald map: (under, over, blocked), like frlg.render. swap: {metatile: metatile} to
    change pieces of the map (say, gravestones into grass); cells: {(x, y): metatile} to repaint single cells
    (blocked is then left as the original map has it)."""
    swap = swap or {}
    cells = cells or {}
    key = ("render", name, x, y, w, h, scale, tuple(sorted(swap.items())), tuple(sorted(cells.items())))
    if key in _cache:
        return _cache[key]
    lay = layout(name)
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
                mid = cells.get((x + xx, y + yy), swap.get(b & 0x3FF, b & 0x3FF))
                under.blit(ts.metatile(mid, "under"), (xx * 16, yy * 16))
                top = ts.metatile(mid, "over")
                if top is not None:
                    over.blit(top, (xx * 16, yy * 16))
                row.append(bool(b & 0xC00) and (b & 0x3FF) not in swap)
            blocked.append(row)
        if scale != 1:
            under = pygame.transform.scale_by(under, scale)
            over = pygame.transform.scale_by(over, scale)
        out = (under, over, blocked)
    _cache[key] = out
    return out
