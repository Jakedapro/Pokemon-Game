"""A small sprite-editing kit for GBA-style 64x64 battle sprites - the operations a sprite artist uses to make a
"splice": cut parts out of sprites, recolour them onto a new palette, scale or turn them cleanly (Scale2x /
RotSprite), paste them over or under, erase, redraw outlines, and touch up single pixels.

Images are plain grids (rows of (r, g, b) or None for see-through), so this runs in the game with only pygame.
Our own Mega Evolutions are built with it on the player's machine from downloaded GBA-style sprites (see megas.py),
so no sprite files are ever stored in the repo.
"""
import colorsys
import math


class Img:
    def __init__(self, w, h, px=None):
        self.w, self.h = w, h
        self.px = px if px is not None else [[None] * w for _ in range(h)]

    # ------------------------------------------------------------------ basics
    def copy(self):
        return Img(self.w, self.h, [row[:] for row in self.px])

    def get(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.px[y][x]
        return None

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y][x] = c

    def points(self):
        return [(x, y) for y in range(self.h) for x in range(self.w) if self.px[y][x] is not None]

    def colors(self):
        return {c for row in self.px for c in row if c is not None}

    def bbox(self):
        pts = self.points()
        if not pts:
            return 0, 0, 0, 0
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1

    # ------------------------------------------------------------------ cutting
    def crop(self, rect):
        x0, y0, w, h = rect
        out = Img(w, h)
        for y in range(h):
            for x in range(w):
                out.px[y][x] = self.get(x0 + x, y0 + y)
        return out

    def cut(self, mask):
        """Keep only the pixels in mask (a set of (x, y)); same size."""
        out = Img(self.w, self.h)
        for x, y in mask:
            out.set(x, y, self.get(x, y))
        return out

    def trim(self):
        x, y, w, h = self.bbox()
        return self.crop((x, y, w, h)), (x, y)

    def flip(self):
        return Img(self.w, self.h, [row[::-1] for row in self.px])

    def vflip(self):
        return Img(self.w, self.h, [row[:] for row in self.px[::-1]])

    # ------------------------------------------------------------------ editing
    def erase(self, mask):
        for x, y in mask:
            self.set(x, y, None)
        return self

    def paste(self, part, x0, y0, under=False):
        for y in range(part.h):
            for x in range(part.w):
                c = part.px[y][x]
                if c is None:
                    continue
                if under and self.get(x0 + x, y0 + y) is not None:
                    continue
                self.set(x0 + x, y0 + y, c)
        return self

    def map_colors(self, fn, mask=None):
        for y in range(self.h):
            for x in range(self.w):
                c = self.px[y][x]
                if c is not None and (mask is None or (x, y) in mask):
                    self.px[y][x] = fn(c)
        return self

    def outline(self, color=None, mask=None):
        """Close the silhouette: every see-through pixel touching the sprite gets an outline pixel (the darkened
        neighbour colour, or `color`). Only outside the sprite; use after cutting things off."""
        add = {}
        for y in range(self.h):
            for x in range(self.w):
                if self.px[y][x] is not None:
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    c = self.get(x + dx, y + dy)
                    if c is not None and (mask is None or (x + dx, y + dy) in mask):
                        add[(x, y)] = color or darken(c)
                        break
        for (x, y), c in add.items():
            self.px[y][x] = c
        return self

    def edge_line(self, mask, color=None):
        """Turn the boundary pixels of `mask` (where they touch see-through) into outline - redraws the line
        along a fresh cut."""
        for x, y in mask:
            c = self.get(x, y)
            if c is None:
                continue
            if any(self.get(x + dx, y + dy) is None for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                if not is_dark(c):
                    self.set(x, y, color or darken(c))
        return self

    def to_surface(self):
        import pygame
        s = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        for y in range(self.h):
            for x in range(self.w):
                c = self.px[y][x]
                if c is not None:
                    s.set_at((x, y), (*c, 255))
        return s


# ---------------------------------------------------------------------------------------------- loading
def from_surface(surf, key=None):
    w, h = surf.get_size()
    img = Img(w, h)
    for y in range(h):
        for x in range(w):
            c = surf.get_at((x, y))
            if c.a >= 128 and (key is None or tuple(c)[:3] != key):
                img.px[y][x] = (c.r, c.g, c.b)
    return img


def read_pal(path):
    with open(path, encoding="ascii", errors="ignore") as f:
        lines = f.read().split("\n")
    out = []
    for line in lines[3:]:
        parts = line.split()
        if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
            out.append(tuple(int(v) for v in parts[:3]))
    return out


def load_gba(png, pal=None, frame=0):
    """A pokeemerald-style sprite: a 4-bit indexed PNG (64x64, or 64x128 with two animation frames) coloured by
    a JASC .pal file whose first colour is see-through."""
    import pygame
    surf = pygame.image.load(png)
    colors = read_pal(pal) if pal else None
    w = surf.get_width()
    img = Img(w, w)
    idx_mode = surf.get_bitsize() <= 8
    for y in range(w):
        for x in range(w):
            yy = y + frame * w
            if yy >= surf.get_height():
                continue
            if idx_mode:
                i = surf.get_at_mapped((x, yy))
                if i == 0:
                    continue
                c = colors[i] if colors and i < len(colors) else tuple(surf.get_palette_at(i))[:3]
            else:
                cc = surf.get_at((x, yy))
                if cc.a < 128:
                    continue
                c = (cc.r, cc.g, cc.b)
            img.px[y][x] = c
    return img


# ---------------------------------------------------------------------------------------------- masks
def rect(x, y, w, h):
    return {(xx, yy) for yy in range(y, y + h) for xx in range(x, x + w)}


def poly(points):
    """Pixels whose centres are inside the polygon."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    out = set()
    n = len(points)
    for y in range(int(min(ys)), int(max(ys)) + 1):
        for x in range(int(min(xs)), int(max(xs)) + 1):
            px, py = x + 0.5, y + 0.5
            inside = False
            for i in range(n):
                x1, y1 = points[i]
                x2, y2 = points[(i + 1) % n]
                if (y1 > py) != (y2 > py) and px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
                    inside = not inside
            if inside:
                out.add((x, y))
    return out


def solid(img, mask=None):
    """The opaque pixels of img (optionally within mask)."""
    return {(x, y) for x, y in img.points() if mask is None or (x, y) in mask}


def by_color(img, pred, mask=None):
    return {(x, y) for x, y in img.points() if (mask is None or (x, y) in mask) and pred(img.px[y][x])}


def flood(img, seeds, pred, diag=False):
    """Connected pixels from seeds that satisfy pred(colour)."""
    seen = set()
    todo = [s for s in seeds if img.get(*s) is not None and pred(img.get(*s))]
    nb = ((1, 0), (-1, 0), (0, 1), (0, -1)) + (((1, 1), (-1, 1), (1, -1), (-1, -1)) if diag else ())
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        for dx, dy in nb:
            q = (p[0] + dx, p[1] + dy)
            c = img.get(*q)
            if q not in seen and c is not None and pred(c):
                todo.append(q)
    return seen


def grow(mask, n=1):
    for _ in range(n):
        mask = mask | {(x + dx, y + dy) for x, y in mask for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))}
    return mask


# ---------------------------------------------------------------------------------------------- colour
def lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def hsv(c):
    h, s, v = colorsys.rgb_to_hsv(*(k / 255 for k in c))
    return h * 360, s, v


def from_hsv(h, s, v):
    return tuple(int(round(max(0.0, min(1.0, k)) * 255)) for k in colorsys.hsv_to_rgb((h % 360) / 360, s, v))


def is_dark(c, t=64):
    return lum(c) < t


def darken(c, k=0.3):
    h, s, v = hsv(c)
    return from_hsv(h + (8 if 60 < h < 240 else -8), min(1.0, s + 0.2), v * k)


def hue_in(lo, hi, min_s=0.12):
    """Predicate: colour hue between lo..hi degrees (wrapping) and saturated enough to have a hue."""
    def f(c):
        h, s, v = hsv(c)
        if s < min_s or v < 0.12:
            return False
        return lo <= h <= hi if lo <= hi else (h >= lo or h <= hi)
    return f


def ramp_map(colors, ramp):
    """A colour map sending `colors` (dark..light by luminance) onto `ramp` (dark..light): keeps the shading
    structure of the source while switching to the new palette. Very dark colours (the outline) go to ramp[0]."""
    cols = sorted(set(colors), key=lum)
    if not cols:
        return {}
    out = {}
    lo, hi = lum(cols[0]), lum(cols[-1])
    for c in cols:
        t = 0 if hi == lo else (lum(c) - lo) / (hi - lo)
        out[c] = ramp[min(len(ramp) - 1, int(round(t * (len(ramp) - 1))))]
    return out


def recolor(img, mask, ramp, keep_outline=True, outline=None):
    """Repaint the pixels in mask onto ramp (dark..light), keeping the original light/dark structure."""
    pts = [(x, y) for x, y in mask if img.get(x, y) is not None]
    src = [img.get(x, y) for x, y in pts if not (keep_outline and is_dark(img.get(x, y), 50))]
    m = ramp_map(src, ramp)
    for x, y in pts:
        c = img.get(x, y)
        if keep_outline and is_dark(c, 50):
            if outline:
                img.set(x, y, outline)
            continue
        img.set(x, y, m[c])
    return img


def hue_shift(img, mask, pred, to_hue, sat=1.0, val=1.0):
    """Turn colours matching pred (inside mask) to another hue, keeping their light/dark."""
    for x, y in (mask if mask is not None else img.points()):
        c = img.get(x, y)
        if c is None or not pred(c):
            continue
        h, s, v = hsv(c)
        img.set(x, y, from_hsv(to_hue, min(1.0, s * sat), min(1.0, v * val)))
    return img


def make_ramp(base, n=5, dark=0.42, light=0.7):
    """Hue-shifted ramp, darkest first (base colour in the middle): shadows turn toward blue-violet and get richer,
    lights toward yellow and paler - the usual pixel-art way."""
    h, s, v = hsv(base)

    def toward(h, target, amount):
        d = ((target - h + 180) % 360) - 180
        return h + max(-amount, min(amount, d))
    out = []
    mid = (n - 1) / 2
    for k in range(n):
        t = (k - mid) / mid                 # -1 .. 1
        if t < 0:
            out.append(from_hsv(toward(h, 250, 18 * -t), min(1.0, s + 0.15 * -t), v * (1 - dark * -t)))
        else:
            out.append(from_hsv(toward(h, 55, 12 * t), s * (1 - 0.45 * t), min(1.0, v + (1 - v) * light * t)))
    return out


# ---------------------------------------------------------------------------------------------- scaling / turning
def scale2x(img):
    """EPX / Scale2x: doubles a sprite while keeping its edges crisp (the start of RotSprite)."""
    out = Img(img.w * 2, img.h * 2)
    g = img.get
    for y in range(img.h):
        for x in range(img.w):
            P = g(x, y)
            A, B, C, D = g(x, y - 1), g(x + 1, y), g(x - 1, y), g(x, y + 1)
            e0 = e1 = e2 = e3 = P
            if C == A and C != D and A != B:
                e0 = A
            if A == B and A != C and B != D:
                e1 = B
            if D == C and D != B and C != A:
                e2 = C
            if B == D and B != A and D != C:
                e3 = D
            out.px[2 * y][2 * x] = e0
            out.px[2 * y][2 * x + 1] = e1
            out.px[2 * y + 1][2 * x] = e2
            out.px[2 * y + 1][2 * x + 1] = e3
    return out


def transform(img, scale=1.0, angle=0.0, pivot=None):
    """RotSprite-style scale + rotate: Scale2x three times, then sample back down - far cleaner than plain
    nearest-neighbour for pixel art. Returns a new image sized to fit, and the offset of the old (0, 0)."""
    big = scale2x(scale2x(scale2x(img)))
    k = 8
    px, py = pivot if pivot else (img.w / 2, img.h / 2)
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)
    corners = [(0, 0), (img.w, 0), (0, img.h), (img.w, img.h)]
    tc = [((x - px) * scale * ca - (y - py) * scale * sa + px, (x - px) * scale * sa + (y - py) * scale * ca + py)
          for x, y in corners]
    x0 = math.floor(min(c[0] for c in tc))
    y0 = math.floor(min(c[1] for c in tc))
    x1 = math.ceil(max(c[0] for c in tc))
    y1 = math.ceil(max(c[1] for c in tc))
    out = Img(x1 - x0, y1 - y0)
    for oy in range(out.h):
        for ox in range(out.w):
            X, Y = ox + x0 + 0.5 - px, oy + y0 + 0.5 - py
            sx = (X * ca + Y * sa) / scale + px
            sy = (-X * sa + Y * ca) / scale + py
            bx, by = int(sx * k), int(sy * k)
            if 0 <= bx < big.w and 0 <= by < big.h:
                out.px[oy][ox] = big.px[by][bx]
    return out, (x0, y0)


# ---------------------------------------------------------------------------------------------- drawn effects
def _spine(points, step=0.25):
    out = []
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        n = max(1, int(math.hypot(x2 - x1, y2 - y1) / step))
        for i in range(n):
            t = i / n
            out.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
    out.append(points[-1])
    return out


def flame(img, spine, width, colors, outline=None, under=False):
    """A tongue of fire drawn the pixel-art way: a tapered shape along `spine` (base -> tip, picture coords),
    filled in nested layers - colors = (outer, middle, inner, core) - with a dark outline round it."""
    pts = _spine(spine)
    n = len(pts)
    layers = [{} for _ in colors]
    frac = (1.0, 0.68, 0.42, 0.22)
    for i, (cx, cy) in enumerate(pts):
        t = i / max(1, n - 1)
        w = width * (1 - t) ** 0.8 + 0.3
        for li in range(len(colors)):
            r = w * frac[li] * (1 - 0.5 * t * li / 3)
            if li == len(colors) - 1 and t > 0.55:
                continue
            for y in range(int(cy - r) - 1, int(cy + r) + 2):
                for x in range(int(cx - r) - 1, int(cx + r) + 2):
                    if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r * r:
                        layers[li][(x, y)] = colors[li]
    shape = set(layers[0])
    if outline:
        ring = {(x + dx, y + dy) for x, y in shape for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))} - shape
        for p in ring:
            if not under or img.get(*p) is None:
                img.set(p[0], p[1], outline)
    for layer in layers:
        for (x, y), c in layer.items():
            if not under or img.get(x, y) is None:
                img.set(x, y, c)
    return img
