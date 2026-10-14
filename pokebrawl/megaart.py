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

    def finish(self):
        self._outline(self.under, keep_clear=self.body)
        self._outline(self.over)
        out = pygame.Surface(self.body.get_size(), pygame.SRCALPHA)
        out.blit(self.under, (0, 0))
        out.blit(self.body, (0, 0))
        out.blit(self.over, (0, 0))
        return out


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
    """Mega Snorlax (Normal/Fighting): a sparring champion - headband, spiky tuft, wrapped fists and a title belt."""
    c.recolor(((140, 200, 214, 0.9, 0.75),))
    band, band_hi = (216, 48, 48), (248, 120, 104)
    # headband with streaming tails
    c.poly([(43, 10), (58, 12), (58, 14), (43, 12)], band, band_hi)
    c.poly([(58, 12), (64, 6), (63, 10), (59, 15)], band, band_hi, layer="under")
    # spiky tuft
    for a, b, tip in (((46, 10), (50, 9), (47, 2)), ((51, 9), (55, 10), (55, 3))):
        c.spike(a, b, tip, (40, 72, 88), (72, 112, 128), layer="under")
    # wrapped fists
    for y in (37, 42):
        c.line((3, y), (12, y + 2), (240, 240, 232), 2)
    # the championship belt
    c.poly([(14, 37), (52, 37), (52, 41), (14, 41)], (216, 168, 48), (248, 224, 120))
    c.poly([(28, 35), (38, 35), (38, 43), (28, 43)], (248, 216, 72), (255, 248, 176))
    c.circle((33, 39), 2, (216, 48, 48))


def lapras(c):
    """Mega Lapras (Water/Ice): a shell of ice crystals, a frozen horn and a frosty collar."""
    c.recolor(((180, 240, 196, 0.55, 1.12), (40, 60, 200, 0.12, 1.1, 0.1)))
    ice, ice_hi, ice_lo = (136, 216, 240), (232, 252, 255), (88, 160, 208)
    for a, b, tip in (((34, 34), (40, 32), (36, 18)), ((40, 32), (46, 31), (44, 14)), ((46, 32), (52, 33), (52, 18)),
                      ((52, 34), (56, 36), (60, 24)), ((30, 36), (34, 34), (28, 26))):
        c.spike(a, b, tip, ice_lo, ice)
        c.line(a, tip, ice_hi)
    # the horn freezes into a long crystal
    c.spike((22, 8), (26, 8), (25, 0), ice, ice_hi)
    # frosty collar
    for x in range(20, 34, 3):
        c.spike((x, 24), (x + 3, 24), (x + 1, 29), ice, ice_hi)


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
    """Mega Machamp (Fighting/Steel): steel gauntlets on all four fists, steel shoulder spikes and a golden belt."""
    c.recolor(((60, 170, 214, 0.35, 0.95, 0.1),))
    steel, steel_hi, steel_lo = (152, 160, 184), (224, 232, 248), (96, 104, 128)
    for x0, y0, x1, y1 in ((4, 14, 16, 20), (48, 14, 60, 20), (13, 36, 22, 41), (44, 36, 53, 41)):
        # a steel cuff round the wrist, studs on the knuckles above it
        c.poly([(x0, y0 + 1), (x0 + 1, y0), (x1 - 1, y0), (x1, y0 + 1), (x1, y1 - 1), (x1 - 1, y1), (x0 + 1, y1),
                (x0, y1 - 1)], steel_lo, steel)
        c.line((x0 + 1, y0 + 1), (x1 - 1, y0 + 1), steel_hi)
        for x in range(x0 + 2, x1 - 1, 3):
            c.px(x, y0 - 2, steel_hi)
            c.px(x, y0 - 3, steel)
    for a, b, tip in (((16, 20), (22, 18), (14, 12)), ((44, 18), (50, 20), (52, 12))):
        c.spike(a, b, tip, steel, steel_hi)
    c.poly([(24, 43), (42, 43), (42, 47), (24, 47)], (216, 168, 48), (248, 224, 120))
    c.circle((33, 45), 2, (232, 64, 64))


def togekiss(c):
    """Mega Togekiss (Fairy/Flying): a second pair of great wings raised high, golden markings and a halo."""
    c.swap(lambda r, g, b: r > 150 and g < 100 and b < 100, (248, 192, 48))   # red marks -> gold
    c.swap(lambda r, g, b: b > 180 and r < 120, (240, 120, 200))              # blue marks -> pink
    wing, wing_hi, tip = (224, 228, 248), (255, 255, 255), (248, 200, 72)
    for side in (-1, 1):
        x = 32 + side * 6
        pts = [(x, 36), (x + side * 10, 18), (x + side * 22, 8), (x + side * 26, 14), (x + side * 18, 30),
               (x + side * 6, 40)]
        c.poly(pts, wing, wing_hi, layer="under")
        c.spike((x + side * 20, 10), (x + side * 26, 14), (x + side * 30, 4), tip, (255, 240, 160), layer="under")
    c.ring((24, 24, 16, 6), (248, 208, 72), 2)


DESIGNS = {"flygon": flygon, "luxray": luxray, "arcanine": arcanine, "milotic": milotic, "typhlosion": typhlosion,
           "snorlax": snorlax, "lapras": lapras, "ninetales": ninetales, "machamp": machamp, "togekiss": togekiss}


def draw(base_key, body):
    """The Mega's 64x64 front sprite, drawn over its base Pokemon's front sprite."""
    c = Canvas(body)
    DESIGNS[base_key](c)
    return c.finish()
