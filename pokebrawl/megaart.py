"""Hand-drawn Mega Evolutions for the Megas the official games never made.

Each design starts from the Pokemon's own (downloaded) 64x64 front sprite, recolours it, then draws new parts on
two layers - behind the body and in front of it - pixel by pixel: horns, crystals, extra wings, flames, armour.
New parts get a GBA-style dark outline and two-tone shading. Nothing here is a copied image: it's the drawing,
as code, so it can be painted over each player's own download."""
import math

import pygame

OUTLINE = (32, 24, 40)


class Canvas:
    """A 64x64 sprite being drawn on: the body, and the new parts behind (under) and in front (over) of it."""

    def __init__(self, body):
        self.body = body.copy()
        self.under = pygame.Surface(body.get_size(), pygame.SRCALPHA)
        self.over = pygame.Surface(body.get_size(), pygame.SRCALPHA)
        self.s_under = pygame.Surface(body.get_size(), pygame.SRCALPHA)   # sculpted parts (own outlines)
        self.s_over = pygame.Surface(body.get_size(), pygame.SRCALPHA)

    # -- recolouring the body ------------------------------------------------------------------
    def recolor(self, rules):
        from . import frlg
        w, h = self.body.get_size()
        cols = {}
        for y in range(h):
            for x in range(w):
                c = self.body.get_at((x, y))
                if c.a:
                    cols[(c.r, c.g, c.b)] = None
        keys = list(cols)
        new = dict(zip(keys, frlg.recolor_palette(keys, rules)))
        for y in range(h):
            for x in range(w):
                c = self.body.get_at((x, y))
                if c.a:
                    self.body.set_at((x, y), (*new[(c.r, c.g, c.b)], 255))

    def swap(self, test, col):
        """Paint every body pixel whose colour passes test(r, g, b) with col (eyes, gems...)."""
        w, h = self.body.get_size()
        for y in range(h):
            for x in range(w):
                c = self.body.get_at((x, y))
                if c.a and test(c.r, c.g, c.b):
                    self.body.set_at((x, y), (*col, 255))

    def paint(self, pts, col, layer="over"):
        """Recolour the body inside a polygon (markings, stripes) - no new outline."""
        mask = pygame.Surface(self.body.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(mask, (255, 255, 255, 255), pts)
        w, h = self.body.get_size()
        for y in range(h):
            for x in range(w):
                if mask.get_at((x, y)).a and self.body.get_at((x, y)).a:
                    self.body.set_at((x, y), (*col, 255))

    # -- new parts --------------------------------------------------------------------------------
    def _layer(self, layer):
        return self.under if layer == "under" else self.over

    def poly(self, pts, col, hi=None, layer="over"):
        """A filled shape; hi = a lighter tone on its upper-left half."""
        s = self._layer(layer)
        pygame.draw.polygon(s, col, pts)
        if hi:
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            lit = [p for p in pts if p[0] + p[1] <= cx + cy] or pts[:2]
            pygame.draw.polygon(s, hi, lit + [(cx, cy)]) if len(lit) >= 2 else None

    def spike(self, a, b, tip, col, hi=None, layer="over"):
        s = self._layer(layer)
        pygame.draw.polygon(s, col, [a, b, tip])
        if hi:
            m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            pygame.draw.polygon(s, hi, [a, m, tip])

    def circle(self, c, r, col, hi=None, layer="over"):
        s = self._layer(layer)
        pygame.draw.circle(s, col, c, r)
        if hi and r >= 2:
            pygame.draw.circle(s, hi, (c[0] - r // 3, c[1] - r // 3), max(1, r // 2))

    def line(self, a, b, col, w=1, layer="over"):
        pygame.draw.line(self._layer(layer), col, a, b, w)

    def px(self, x, y, col, layer="over"):
        s = self._layer(layer)
        if 0 <= x < s.get_width() and 0 <= y < s.get_height():
            s.set_at((x, y), (*col, 255))

    def ring(self, rect, col, w=1, layer="over"):
        pygame.draw.ellipse(self._layer(layer), col, rect, w)

    # -- finishing -------------------------------------------------------------------------------------
    @staticmethod
    def _outline(layer, keep_clear=None):
        w, h = layer.get_size()
        out = []
        for y in range(h):
            for x in range(w):
                if layer.get_at((x, y)).a:
                    continue
                if keep_clear is not None and keep_clear.get_at((x, y)).a:
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < w and 0 <= yy < h and layer.get_at((xx, yy)).a:
                        out.append((x, y))
                        break
        for p in out:
            layer.set_at(p, (*OUTLINE, 255))

    # -- sculpting: curved, shaded parts that sit in the sprite like they were always there ------------------
    def opaque(self, x, y):
        return 0 <= x < 64 and 0 <= y < 64 and self.body.get_at((x, y)).a > 0

    def sculpt(self, pix, ramp, layer="over", clip_body=False, alt=None):
        """Shade a set of pixels as a rounded form lit from the top-left, with an outline in its own darkest
        tone. ramp = (outline, shadow, base, light, highlight). alt = (ramp2, test(x, y)) paints some pixels with
        a second ramp (e.g. gold feather tips) using the same light."""
        pix = {(x, y) for x, y in pix if 0 <= x < 64 and 0 <= y < 64}
        if clip_body:
            pix = {p for p in pix if self.opaque(*p)}
        if not pix:
            return
        surf = self.s_under if layer == "under" else self.s_over

        def run(x, y, dx, dy):
            n = 0
            while (x + dx * (n + 1), y + dy * (n + 1)) in pix and n < 4:
                n += 1
            return n
        for x, y in pix:
            up, left = (x, y - 1) not in pix, (x - 1, y) not in pix
            down, right = (x, y + 1) not in pix, (x + 1, y) not in pix
            tl, br = run(x, y, -1, -1), run(x, y, 1, 1)
            if down or right or br == 0:
                tier = 1
            elif (up or left) and br >= 2:
                tier = 4 if tl == 0 and br >= 3 else 3
            elif tl <= 1 and br >= 3:
                tier = 3
            elif br <= 1:
                tier = 1
            else:
                tier = 2
            r = ramp
            if alt and alt[1](x, y):
                r = alt[0]
            surf.set_at((x, y), (*r[tier], 255))
        for x, y in pix:   # the outline, in the part's own darkest tone
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                q = (x + dx, y + dy)
                if q in pix or not (0 <= q[0] < 64 and 0 <= q[1] < 64):
                    continue
                if clip_body and not self.opaque(*q):
                    continue
                if layer == "under" and self.opaque(*q):
                    continue
                r = alt[0] if alt and alt[1](*q) else ramp
                surf.set_at(q, (*r[0], 255))

    def material(self, region, ramp, test=None):
        """Turn part of the body into another material, keeping its own shading (so muscles stay muscles, bumps
        stay bumps): pixels by brightness onto ramp (darkest = outline)."""
        mask = pygame.Surface((64, 64), pygame.SRCALPHA)
        pygame.draw.polygon(mask, (255, 255, 255), region)
        pts = []
        for y in range(64):
            for x in range(64):
                if mask.get_at((x, y)).a and self.opaque(x, y):
                    c = self.body.get_at((x, y))
                    if test is None or test(c.r, c.g, c.b):
                        pts.append((x, y, 0.3 * c.r + 0.59 * c.g + 0.11 * c.b))
        if not pts:
            return
        lums = sorted(p[2] for p in pts if p[2] > 60)
        for x, y, lum in pts:
            if lum <= 60:
                col = ramp[0]
            else:
                k = sum(1 for v in lums if v < lum) / max(1, len(lums))
                col = ramp[1 + min(len(ramp) - 2, int(k * (len(ramp) - 1)))]
            self.body.set_at((x, y), (*col, 255))

    @staticmethod
    def spline(pts, closed=True, steps=8):
        """A smooth Catmull-Rom curve through the points."""
        out = []
        n = len(pts)
        rng = range(n) if closed else range(n - 1)
        for i in rng:
            p0 = pts[(i - 1) % n] if closed or i > 0 else pts[0]
            p1, p2 = pts[i], pts[(i + 1) % n]
            p3 = pts[(i + 2) % n] if closed or i + 2 < n else pts[-1]
            for k in range(steps):
                t = k / steps
                t2, t3 = t * t, t * t * t
                out.append(tuple(0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                        + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
        if not closed:
            out.append(pts[-1])
        return out

    @staticmethod
    def fill(poly):
        m = pygame.Surface((64, 64), pygame.SRCALPHA)
        pygame.draw.polygon(m, (255, 255, 255), [(round(x), round(y)) for x, y in poly])
        return {(x, y) for y in range(64) for x in range(64) if m.get_at((x, y)).a}

    def shape(self, pts, ramp, smooth=True, **kw):
        poly = self.spline(pts) if smooth else pts
        pix = self.fill(poly)
        self.sculpt(pix, ramp, **kw)
        return pix

    def tube(self, pts, w0, w1, ramp, **kw):
        """A tapering curved tube along the points (horns, ropes, tails)."""
        path = self.spline(pts, closed=False, steps=10)
        pix = set()
        for i, (x, y) in enumerate(path):
            r = (w0 + (w1 - w0) * i / max(1, len(path) - 1)) / 2
            for yy in range(int(y - r) - 1, int(y + r) + 2):
                for xx in range(int(x - r) - 1, int(x + r) + 2):
                    if (xx + 0.5 - x - 0.5) ** 2 + (yy + 0.5 - y - 0.5) ** 2 <= r * r + 0.25:
                        pix.add((xx, yy))
        self.sculpt(pix, ramp, **kw)
        return pix

    def finish(self):
        self._outline(self.under, keep_clear=self.body)
        self._outline(self.over)
        out = pygame.Surface(self.body.get_size(), pygame.SRCALPHA)
        out.blit(self.under, (0, 0))
        out.blit(self.s_under, (0, 0))
        out.blit(self.body, (0, 0))
        out.blit(self.over, (0, 0))
        out.blit(self.s_over, (0, 0))
        return out


# material ramps: (outline, shadow, base, light, highlight)
STEEL = ((40, 44, 64), (96, 104, 128), (152, 160, 184), (208, 216, 232), (255, 255, 255))
GOLD = ((112, 72, 24), (192, 136, 40), (236, 184, 56), (255, 222, 112), (255, 248, 208))
ICE = ((40, 88, 152), (96, 160, 216), (152, 212, 244), (212, 242, 255), (255, 255, 255))
WHITE = ((128, 136, 176), (192, 200, 228), (232, 236, 250), (246, 248, 255), (255, 255, 255))
ROPE = ((112, 112, 120), (176, 176, 184), (224, 224, 228), (244, 244, 246), (255, 255, 255))
HAIR = ((24, 24, 40), (48, 48, 72), (72, 72, 104), (104, 104, 144), (152, 152, 192))
RED = ((96, 16, 24), (168, 32, 40), (216, 56, 56), (248, 112, 104), (255, 184, 176))


DARKSTEEL = ((16, 16, 28), (52, 56, 76), (92, 98, 122), (150, 158, 184), (228, 236, 255))
BLACKGOLD = ((16, 12, 8), (40, 32, 24), (72, 56, 32), (200, 152, 48), (255, 224, 112))
HORN = ((16, 12, 20), (44, 36, 52), (80, 68, 92), (132, 120, 148), (200, 192, 216))
DEEPICE = ((8, 32, 72), (32, 80, 152), (72, 152, 224), (160, 224, 255), (255, 255, 255))


def glow_eye(c, pts, core, halo):
    """Eyes that burn: the eye pixels in a hot colour, the face around them catching the light."""
    for x, y in pts:
        c.body.set_at((x, y), (*core, 255))
    for x, y in pts:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (x + dx, y + dy)
            if q not in pts and c.opaque(*q):
                col = c.body.get_at(q)
                if col.r + col.g + col.b > 120:
                    c.body.set_at(q, (*halo, 255))


def scar(c, a, b):
    """A healed battle scar cut into the body itself: a pale line with a dark edge under it."""
    n = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
    for i in range(n + 1):
        x = round(a[0] + (b[0] - a[0]) * i / n)
        y = round(a[1] + (b[1] - a[1]) * i / n)
        if c.opaque(x, y + 1):
            c.body.set_at((x, y + 1), (72, 40, 48, 255))
        if c.opaque(x, y):
            c.body.set_at((x, y), (240, 208, 192, 255))


def _bright(r, g, b):
    return r + g + b > 600


# ====================================================================== the designs (64x64 front sprites)
def flygon(c):
    """Mega Flygon (Ground/Dragon): a desert dragon - crimson sail-wings, a second pair of wings, a horned crest,
    spines down its neck and a bigger tail fin."""
    c.recolor(((60, 100, 128, 1.1, 0.85), (100, 170, 150, 1.0, 0.75), (330, 30, 352, 1.2, 0.8, 0.3)))
    wing, wing_hi = (176, 32, 48), (232, 88, 88)
    # the second, lower pair of wings (behind the body)
    c.poly([(30, 30), (6, 36), (2, 44), (14, 42), (26, 40)], wing, wing_hi, layer="under")
    c.poly([(42, 34), (60, 38), (63, 46), (52, 44), (44, 40)], wing, wing_hi, layer="under")
    # horned crest on the head
    c.spike((36, 9), (40, 8), (31, 0), (232, 200, 104), (255, 240, 176))
    c.spike((41, 7), (45, 8), (44, 0), (232, 200, 104), (255, 240, 176))
    # spines down the neck
    for y in (15, 20, 25):
        c.spike((38, y), (38, y + 4), (43, y + 1), wing, wing_hi, layer="under")
    # the tail fin grows a third blade
    c.spike((50, 47), (56, 47), (58, 38), wing, wing_hi)
    # gold eye lenses
    c.swap(lambda r, g, b: r > 200 and g < 120 and b < 120, (248, 200, 64))


def luxray(c):
    """Mega Luxray (Electric/Dark): a storm-mane of jagged spikes, lightning stripes and a huge star tail."""
    c.recolor(((200, 260, 186, 1.2, 1.2, 0.4),))
    mane, mane_hi = (48, 40, 72), (88, 76, 120)
    for a, b, tip in (((10, 12), (16, 10), (4, 2)), ((5, 18), (7, 24), (0, 12)), ((4, 28), (5, 34), (0, 30)),
                      ((20, 9), (25, 9), (21, 0)), ((27, 11), (31, 13), (34, 3))):
        c.spike(a, b, tip, mane, mane_hi, layer="under")
    # lightning bolts down the body
    bolt = (255, 224, 64)
    for pts in ([(24, 36), (28, 36), (26, 39), (30, 39), (25, 44), (26, 40), (23, 40)],
                [(38, 38), (42, 38), (40, 41), (44, 41), (39, 46), (40, 42), (37, 42)]):
        c.poly(pts, bolt, (255, 248, 176))
    # the tail star, bigger and crackling
    cx, cy = 56, 46
    star = [(cx, cy - 10), (cx + 3, cy - 3), (cx + 9, cy), (cx + 3, cy + 3), (cx, cy + 10), (cx - 3, cy + 3),
            (cx - 8, cy), (cx - 3, cy - 3)]
    c.poly(star, (248, 208, 48), (255, 248, 160))
    c.swap(lambda r, g, b: r > 200 and g > 150 and b < 100, (255, 64, 64))   # red-gold eyes


def arcanine(c):
    """Mega Arcanine (Fire/Dragon): dragon horns, a flame-crest mane and dark dragon stripes."""
    c.recolor(((0, 25, 352, 1.1, 0.9, 0.3), (25, 40, 18, 1.2, 1.0, 0.35), (40, 60, 44, 0.8, 1.05, 0.2)))
    # flame crest on the mane
    for a, b, tip, col in (((14, 8), (20, 6), (12, -1), (248, 96, 48)), ((22, 6), (28, 8), (27, 0), (248, 136, 48)),
                           ((38, 6), (44, 5), (40, -1), (248, 96, 48)), ((46, 7), (52, 10), (54, 2), (248, 136, 48))):
        c.spike(a, b, tip, col, (255, 216, 120), layer="under")
    # dragon horns
    c.spike((9, 13), (13, 12), (4, 3), (72, 56, 120), (136, 112, 200))
    c.spike((17, 11), (21, 11), (20, 2), (72, 56, 120), (136, 112, 200))
    # glowing dragon marks on the legs
    for x, y in ((12, 50), (36, 52), (52, 50)):
        c.poly([(x, y), (x + 3, y - 2), (x + 6, y), (x + 3, y + 2)], (152, 120, 232), (200, 184, 255))


def milotic(c):
    """Mega Milotic (Water/Fairy): flowing ribbon tendrils, a jewel crown and pastel fairy fins."""
    c.recolor(((180, 260, 330, 0.9, 1.05), (330, 20, 176, 0.9, 1.0, 0.3)))
    ribbon, ribbon_hi = (248, 160, 200), (255, 216, 232)
    # long ribbons streaming from the head (behind)
    for side in (-1, 1):
        x0 = 31 + side * 4
        pts = []
        for i in range(12):
            t = i / 11
            pts.append((x0 + side * (6 + 14 * t) + math.sin(t * 5) * 2, 12 + 30 * t))
        for a, b in zip(pts, pts[1:]):
            c.line(a, b, ribbon, 3, layer="under")
            c.line(a, (b[0], b[1] - 1), ribbon_hi, 1, layer="under")
    # a jewel crown
    c.poly([(30, 8), (33, 3), (36, 8), (33, 11)], (96, 224, 232), (216, 255, 255))
    c.px(33, 6, (255, 255, 255))
    for x in (28, 38):
        c.spike((x - 1, 10), (x + 2, 10), (x, 5), (248, 216, 96), (255, 248, 200))
    # a third tail fan
    c.poly([(48, 44), (62, 36), (60, 44), (63, 50), (52, 48)], ribbon, ribbon_hi, layer="under")


def typhlosion(c):
    """Mega Typhlosion (Fire/Ghost): violet spirit-flames, a burning mane down its back and a pale ghostly body."""
    c.recolor(((0, 60, 282, 1.0, 1.0, 0.45), (190, 250, 268, 0.7, 0.45), (40, 70, 255, 0.3, 0.82, 0.15)))
    flame, mid, core = (136, 48, 200), (200, 112, 248), (248, 208, 255)
    # a bigger crown of flame, and flames down the back
    for a, b, tip in (((40, 6), (44, 10), (58, 2)), ((44, 12), (46, 16), (62, 12)), ((46, 18), (46, 22), (60, 24)),
                      ((46, 26), (47, 31), (58, 32)), ((48, 34), (49, 40), (58, 42))):
        c.spike(a, b, tip, flame, mid, layer="under")
        c.spike(a, b, ((a[0] + tip[0]) // 2 + 2, (a[1] + tip[1]) // 2), core, layer="under")
    # will-o-wisps floating around it
    for x, y in ((6, 6), (2, 26), (10, 50)):
        c.circle((x, y), 3, flame, core)
    c.swap(lambda r, g, b: r > 200 and 40 < g < 140 and b < 80, (255, 96, 200))   # glowing eyes


def snorlax(c):
    """Mega Snorlax (Normal/Fighting): the Juggernaut - a black-armoured hide, curved horns, burning red eyes
    under angry brows, battle scars, and the champion's black-and-gold rope bent round its belly."""
    c.recolor(((140, 200, 228, 0.55, 0.42), (40, 70, 34, 0.6, 0.88, 0.1)))
    # horns
    for pts in ([(48, 9), (45, 4), (41, 1)], [(56, 9), (59, 4), (63, 2)]):
        c.tube(pts, 4, 1, HORN, layer="under")
    # burning eyes and angry brows
    glow_eye(c, [(44, 13), (45, 13), (53, 11), (54, 11)], (255, 64, 32), (255, 160, 64))
    c.line((42, 11), (46, 12), (16, 12, 20), 2)
    c.line((57, 9), (53, 10), (16, 12, 20), 2)
    # battle scars across the belly
    scar(c, (17, 15), (25, 21))
    scar(c, (21, 13), (27, 18))
    # the champion's rope: black and gold, sagging round the curve of the belly
    rope = [(8, 25), (19, 30), (32, 32), (45, 30), (55, 24)]
    pix = c.tube(rope, 6, 5, BLACKGOLD, clip_body=True)
    path = c.spline(rope, closed=False, steps=12)
    for i in range(2, len(path) - 2, 4):   # gold strands twisting round it
        x, y = path[i]
        for k in (-2, -1, 1, 2):
            q = (round(x + k * 0.6 - 1), round(y + k))
            if q in pix:
                c.s_over.set_at(q, (*BLACKGOLD[3], 255))
    for t in (0.32, 0.5, 0.68):   # red tassels
        x, y = path[int(t * (len(path) - 1))]
        c.tube([(round(x), round(y) + 3), (round(x) + 1, round(y) + 6), (round(x), round(y) + 8)], 2, 1, RED)


def lapras(c):
    """Mega Lapras (Water/Ice): the Glacier Leviathan - a black-blue hide, a shell that has become a jagged
    glacier of glowing ice blades, a great ice horn and cold, burning eyes."""
    import colorsys
    c.recolor(((180, 245, 226, 1.0, 0.5), (40, 64, 205, 0.18, 0.92, 0.1)))

    def shell(r, g, b):
        h, sat, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        return sat < 0.4 and v < 0.85
    c.material([(32, 27), (61, 30), (61, 53), (34, 53)], DEEPICE, shell)
    lit = ((8, 32, 72), (104, 188, 240), (176, 232, 255), (224, 248, 255), (255, 255, 255))
    dark = ((8, 32, 72), (24, 64, 136), (48, 112, 196), (96, 168, 232), (176, 232, 255))

    def blade(x, y, w, h, lean):
        t = (x + lean, y - h)
        m = (x + lean * 0.4, y)
        c.shape([(x - w / 2, y + 2), (x - w / 2 + 1, y - h * 0.4), t, m], lit, smooth=False)
        c.shape([m, t, (x + w / 2 - 1, y - h * 0.35), (x + w / 2, y + 2)], dark, smooth=False)
    for x, y, w, h, lean in ((60, 42, 6, 12, 5), (34, 40, 6, 14, -5), (55, 37, 7, 21, 4), (39, 36, 7, 22, -3),
                             (47, 34, 9, 29, 0)):
        blade(x, y, w, h, lean)
    # the great ice horn, sweeping back
    c.tube([(25, 9), (27, 4), (32, 0), (38, -1)], 5, 1, DEEPICE, layer="under")
    c.tube([(21, 10), (18, 6), (14, 4)], 3, 1, DEEPICE, layer="under")
    glow_eye(c, [(24, 10), (23, 11), (24, 11), (25, 11), (25, 12), (26, 12)], (96, 255, 255), (64, 160, 220))
    c.line((27, 8), (22, 10), (8, 16, 32), 2)


def ninetales(c):
    """Mega Ninetales (Fire/Fairy): moon-white fur, a crown of pink fox-fire and starry eyes."""
    c.recolor(((35, 65, 280, 0.12, 1.1, 0.12), (20, 35, 300, 0.25, 1.0, 0.2)))
    fire, fire_hi = (240, 104, 184), (255, 208, 240)
    for i in range(5):   # floating fox-fire over its head
        a = math.pi * (0.15 + 0.7 * i / 4)
        x, y = 46 - math.cos(a) * 16, 12 - math.sin(a) * 10
        c.spike((x - 3, y + 2), (x + 3, y + 2), (x, y - 5), fire, fire_hi)
        c.circle((int(x), int(y + 2)), 2, fire, fire_hi)
    c.swap(lambda r, g, b: r > 180 and g < 110, (96, 160, 255))   # eyes go starry blue
    for x, y in ((8, 20), (2, 40), (58, 40)):
        c.px(x, y, (255, 255, 255))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c.px(x + dx, y + dy, fire_hi)


def machamp(c):
    """Mega Machamp (Fighting/Steel): a gunmetal war-machine - black-steel fists and forearms with red-hot
    knuckles and spikes, spiked shoulder plates, a crimson crest, burning eyes and a scarred chest."""
    c.recolor(((75, 170, 214, 0.35, 0.6, 0.1),))
    c.material([(18, 4), (46, 4), (46, 13), (18, 13)], RED, lambda r, g, b: r > 120 and g > 100 and b < 110)
    for region in ([(0, 0), (21, 0), (21, 17), (0, 17)], [(43, 0), (64, 0), (64, 19), (43, 19)],
                   [(9, 31), (25, 31), (25, 45), (9, 45)], [(40, 31), (57, 31), (57, 45), (40, 45)]):
        c.material(region, DARKSTEEL)
    for x0, x1 in ((4, 15), (47, 59)):   # spikes, glowing red-hot at the base
        for k in range(3):
            x = x0 + k * (x1 - x0) // 2
            c.tube([(x, 5), (x - 1 if x < 32 else x + 1, -1)], 4, 1, DARKSTEEL, layer="under")
            c.px(x, 4, (255, 96, 48))
    for side in (1, -1):   # spiked shoulder plates
        pts = [(14, 22), (16, 18), (21, 16), (26, 18), (25, 21), (19, 22)]
        spike = [(19, 18), (15, 11), (11, 7)]
        if side < 0:
            pts = [(65 - x, y) for x, y in pts]
            spike = [(65 - x, y) for x, y in spike]
        c.tube(spike, 4, 1, DARKSTEEL, layer="under")
        c.shape(pts, DARKSTEEL)
    glow_eye(c, [(22, 17), (30, 17), (22, 16), (30, 16)], (255, 240, 96), (255, 128, 48))
    scar(c, (27, 30), (37, 37))
    c.tube([(22, 44), (33, 47), (44, 44)], 5, 5, BLACKGOLD, clip_body=True)
    c.shape([(30, 43), (36, 43), (37, 46), (33, 50), (29, 46)], GOLD)
    c.shape([(32, 45), (34, 45), (34, 47), (32, 47)], RED, smooth=False)


def togekiss(c):
    """Mega Togekiss (Fairy/Flying): the Seraph - two great blade-wings raised high, every feather a sharp
    gold-edged blade with a dark underside, and a golden war-crown."""
    c.swap(lambda r, g, b: r > 150 and g < 100 and b < 100, (248, 192, 48))   # red marks -> gold
    c.swap(lambda r, g, b: b > 180 and r < 120, (176, 40, 72))                # blue marks -> crimson
    blade = ((48, 40, 88), (120, 120, 176), (220, 224, 244), (244, 246, 255), (255, 255, 255))
    for side in (-1, 1):
        bx, by = 32 + side * 4, 38
        angles = [100, 114, 128, 142, 156, 170]
        lengths = [34, 35, 33, 29, 24, 18]
        for i in reversed(range(6)):   # back feathers first, so the front ones overlap them
            a = math.radians(angles[i] if side < 0 else 180 - angles[i])
            dx, dy = math.cos(a), -math.sin(a)
            nx, ny = -dy * side, dx * side
            L = lengths[i]
            tip = (bx + dx * L, by + dy * L)
            mid = (bx + dx * L * 0.6 + nx * 1.0, by + dy * L * 0.6 + ny * 1.0)
            w = 2.6
            pts = [(bx + nx * 1.2, by + ny * 1.2), (mid[0] + nx * w, mid[1] + ny * w), tip,
                   (mid[0] - nx * w * 0.5, mid[1] - ny * w * 0.5), (bx - nx * 1.2, by - ny * 1.2)]

            def gold_tip(x, y, bx=bx, by=by, dx=dx, dy=dy, L=L):
                return ((x - bx) * dx + (y - by) * dy) / L > 0.82
            c.shape(pts, blade, smooth=False, layer="under", alt=(GOLD, gold_tip))
        cov = [(bx, by + 1), (bx + side * 3, by - 9), (bx + side * 9, by - 13), (bx + side * 14, by - 9),
               (bx + side * 11, by - 2)]
        c.shape(cov, blade, layer="under")
    # golden war-crown
    c.shape([(15, 32), (16, 28), (17, 30), (19, 25), (21, 30), (22, 28), (23, 32)], GOLD, smooth=False)
    c.px(19, 28, (176, 40, 72))


DESIGNS = {"flygon": flygon, "luxray": luxray, "arcanine": arcanine, "milotic": milotic, "typhlosion": typhlosion,
           "snorlax": snorlax, "lapras": lapras, "ninetales": ninetales, "machamp": machamp, "togekiss": togekiss}


def draw(base_key, body):
    """The Mega's 64x64 front sprite, drawn over its base Pokemon's front sprite."""
    c = Canvas(body)
    DESIGNS[base_key](c)
    return c.finish()
