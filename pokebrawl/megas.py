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


# ---------------------------------------------------------------------------------------------- Mega Lapras
def _crab_crystals(L):
    crab = L("crabominable/mega")
    ice = lambda c: (K.hue_in(165, 215, 0.12)(c) or K.lum(c) > 215 or
                     (170 < K.hsv(c)[0] < 215 and K.lum(c) < 120))
    right = crab.cut(K.flood(crab, [(52, 10), (50, 14), (56, 12)], ice))
    left = crab.cut(K.flood(crab, [(20, 10), (22, 14), (18, 12)], ice))
    return left.trim()[0], right.trim()[0]


def _greys(img, mask):
    return {p for p in mask if img.get(*p) is not None and K.hsv(img.get(*p))[1] < 0.2 and
            not K.is_dark(img.get(*p), 50)}


def lapras(L):
    """Mega Lapras - Water/Ice, Snow Warning: its shell freezes into a glacier and grows spires of ice
    (Mega Crabominable's crystals), with an ice shard for a horn."""
    small_src, big_src = _crab_crystals(L)
    ice = sorted((c for c in big_src.colors() if not K.is_dark(c, 50)), key=K.lum)[1:]
    out = L("lapras")
    K.recolor(out, _greys(out, K.poly([(26, 24), (54, 30), (56, 48), (30, 48)])), ice)
    big, _ = K.transform(big_src, 1.1)
    small, _ = K.transform(small_src, 0.8)
    out.paste(small.flip(), 45, 20)
    out.paste(big, 32, 9)
    horn, _ = K.transform(small_src, 0.5)
    out.paste(horn, 10, -3)
    out.outline((24, 40, 64))
    back = L("lapras", back=True)
    K.recolor(back, _greys(back, K.poly([(4, 44), (64, 44), (64, 64), (4, 64)])), ice)
    bb, _ = K.transform(big_src.flip(), 1.3)
    back.paste(bb, 34, 22)
    return out, back


# ---------------------------------------------------------------------------------------------- Mega Machamp


def _skin(img):
    return {p for p in img.points() if K.hsv(img.get(*p))[1] < 0.3 and not K.is_dark(img.get(*p), 40)
            and K.hsv(img.get(*p))[2] < 0.97}


CHROME = [(40, 44, 64), (78, 86, 112), (122, 132, 160), (168, 178, 204), (212, 220, 238), (255, 255, 255)]


def machamp(L):
    """Mega Machamp - Fighting/Steel, Iron Fist: a living chrome titan - its whole body turns to polished
    steel (every muscle still there), with the gold crest and a bigger champion's belt."""
    out = L("machamp")
    skin = _skin(out)
    cmap = K.ramp_map([out.get(*p) for p in skin], CHROME)
    out.map_colors(lambda c: cmap.get(c, c), skin)
    out.paste(part("machamp_over"), 0, 0)
    back = L("machamp", back=True)
    back.map_colors(lambda c: cmap.get(c, c), _skin(back))
    return out, back


# ---------------------------------------------------------------------------------------------- Mega Arcanine
NAVY = [(20, 22, 60), (36, 46, 110), (52, 76, 164), (84, 122, 214), (140, 180, 240)]


BF = [(40, 72, 208), (72, 144, 248), (150, 214, 255), (240, 252, 255)]
BF_OUT = (16, 24, 88)
# blue fire off the mane and the tail: (spine base -> tip, width)
ARC_FIRE = [([(34, 12), (36, 6), (34, 2), (38, -2)], 4.2), ([(41, 11), (44, 5), (43, 0), (48, -3)], 4.8),
            ([(48, 12), (52, 7), (52, 2), (57, -1)], 4.8), ([(54, 16), (58, 11), (59, 6), (64, 3)], 4.2),
            ([(57, 22), (61, 18), (63, 13), (66, 11)], 3.4)]
ARC_BACK_FIRE = [([(18, 14), (17, 8), (20, 3), (19, -1)], 4.4), ([(28, 10), (30, 5), (28, 1), (31, -3)], 5.0),
                 ([(39, 10), (42, 5), (41, 0), (45, -3)], 5.0), ([(49, 14), (53, 9), (53, 4), (57, 1)], 4.4)]


def arcanine(L):
    """Mega Arcanine - Fire/Dragon, Tough Claws: its coat turns to dark dragon-blue, blue fire roars off its
    mane and tail, and it grows a pair of horns."""
    orange = {(255, 156, 106), (238, 115, 49), (197, 82, 90), (255, 98, 65), (197, 49, 32)}
    omap = K.ramp_map(list(orange), NAVY[1:])
    recol = lambda c: omap.get(c, c)
    out = L("arcanine")
    out.map_colors(recol)
    fire = K.Img(64, 64)
    for spine, w in ARC_FIRE:
        K.flame(fire, spine, w, BF, BF_OUT)
    out.paste(fire, 0, 0, under=True)
    out.paste(part("arcanine_over"), 0, 0)
    back = L("arcanine", back=True)
    back.map_colors(recol)
    bfire = K.Img(64, 64)
    for spine, w in ARC_BACK_FIRE:
        K.flame(bfire, spine, w, BF, BF_OUT)
    back.paste(bfire, 0, 0, under=True)
    return out, back


# ---------------------------------------------------------------------------------------------- Mega Typhlosion
TY_FUR = {(8, 32, 90): (14, 8, 30), (32, 65, 106): (34, 20, 60), (65, 90, 148): (58, 38, 100),
          (65, 131, 164): (96, 68, 150)}
TY_FIRE = {(222, 0, 0): (100, 20, 168), (255, 98, 0): (164, 56, 232), (255, 156, 0): (212, 120, 255),
           (255, 222, 0): (246, 214, 255)}
GHOSTFIRE = [(100, 20, 168), (164, 56, 232), (212, 120, 255), (246, 220, 255)]
GF_OUT = (40, 8, 72)
TY_BLAZE = [([(40, 12), (42, 6), (40, 1), (44, -3)], 4.6), ([(47, 14), (51, 8), (51, 3), (56, -1)], 4.8),
            ([(50, 20), (55, 15), (57, 10), (63, 7)], 4.6), ([(51, 27), (57, 24), (61, 20), (66, 19)], 3.8),
            ([(32, 9), (31, 4), (33, -1), (31, -4)], 4.0), ([(24, 11), (21, 6), (22, 2), (18, -2)], 3.6)]
TY_BACK_BLAZE = [([(14, 30), (10, 24), (11, 18), (6, 13)], 4.6), ([(22, 22), (21, 15), (24, 9), (21, 3)], 5.2),
                 ([(32, 22), (34, 15), (32, 9), (35, 3)], 5.0), ([(42, 28), (47, 22), (48, 16), (53, 12)], 4.4)]


def typhlosion(L):
    """Mega Typhlosion - Fire/Ghost, Drought: its fur goes shadow-dark, and its fire turns to a roaring corona of
    violet ghost-flame - even its eyes burn purple."""
    recol = lambda c: TY_FUR.get(c, TY_FIRE.get(c, c))
    out = L("typhlosion")
    out.map_colors(recol)
    fire = K.Img(64, 64)
    for spine, w in TY_BLAZE:
        K.flame(fire, spine, w, GHOSTFIRE, GF_OUT)
    out.paste(fire, 0, 0, under=True)
    back = L("typhlosion", back=True)
    back.map_colors(recol)
    bfire = K.Img(64, 64)
    for spine, w in TY_BACK_BLAZE:
        K.flame(bfire, spine, w, GHOSTFIRE, GF_OUT)
    back.paste(bfire, 0, 0, under=True)
    return out, back


# ---------------------------------------------------------------------------------------------- Mega Luxray
def _bolt_mane(L):
    """Mega Manectric's mane of lightning shards (yellow + its outline), cut free."""
    mn = L("manectric/mega")
    yellow = lambda c: K.hue_in(38, 62, 0.25)(c) or (K.lum(c) > 200 and K.hsv(c)[1] < 0.4)
    shards = K.flood(mn, [(30, 20), (20, 24), (44, 16), (40, 30)], yellow)
    piece = mn.cut(shards)
    piece.outline((48, 40, 16))
    return piece


def luxray(L):
    """Mega Luxray - Electric/Dark, Strong Jaw: a crown of lightning shards bursts from its black mane
    (Mega Manectric's), crackling against the dark."""
    out = L("luxray")
    mane = _bolt_mane(L)
    big, _ = K.transform(mane, 0.95)
    out.paste(big, -10, -3, under=True)
    back = L("luxray", back=True)
    bm, _ = K.transform(mane.flip(), 0.95)
    back.paste(bm, 8, 0, under=True)
    return out, back


# ---------------------------------------------------------------------------------------------- Mega Ninetales
NT_FUR = {(131, 98, 24): (122, 66, 104), (205, 156, 74): (204, 156, 170), (205, 156, 98): (210, 164, 176),
          (230, 197, 82): (238, 218, 204), (238, 222, 115): (246, 234, 220), (246, 230, 123): (250, 242, 232),
          (255, 238, 180): (255, 254, 250), (255, 106, 41): (240, 80, 168), (248, 160, 56): (250, 150, 210),
          (232, 128, 40): (232, 96, 184), (222, 32, 16): (216, 32, 128), (180, 16, 0): (150, 16, 96)}
FAIRYFIRE = [(228, 72, 168), (248, 132, 210), (255, 196, 236), (255, 248, 252)]
FF_OUT = (112, 24, 88)
# (base, direction) of a flame at each tail tip
NT_TIPS = [((30, 6), (0, -1)), ((42, 9), (0.4, -1)), ((52, 15), (0.8, -0.8)), ((59, 25), (1, -0.4)),
           ((62, 36), (1, 0)), ((60, 47), (1, 0.5)), ((52, 55), (0.6, 1)), ((40, 58), (0, 1)), ((27, 57), (-0.4, 1))]
NT_BACK_TIPS = [((6, 44), (-1, -0.6)), ((14, 41), (-0.6, -1)), ((24, 40), (-0.2, -1)), ((4, 54), (-1, 0))]


def _tip_flames(tips, length=7.0, width=4.4):
    """Fox-fire: a fat teardrop of pink flame on each tail tip, curling a little at the point."""
    img = K.Img(64, 64)
    for (x, y), (dx, dy) in tips:
        n = (dx * dx + dy * dy) ** 0.5
        dx, dy = dx / n, dy / n
        spine = [(x - dx * 2.5, y - dy * 2.5), (x + dx * length * 0.45, y + dy * length * 0.45),
                 (x + dx * length - dy * 1.6, y + dy * length + dx * 1.6)]
        K.flame(img, spine, width, FAIRYFIRE, FF_OUT)
    return img


def ninetales(L):
    """Mega Ninetales - Fire/Fairy, Drought: its coat turns pearl-white with a blush of pink, and every one of
    its nine tails ends in a flickering pink fairy-flame."""
    recol = lambda c: NT_FUR.get(c, c)
    out = L("ninetales")
    out.map_colors(recol)
    out.paste(_tip_flames(NT_TIPS, 6.0, 3.6), 0, 0)
    back = L("ninetales", back=True)
    back.map_colors(recol)
    back.paste(_tip_flames(NT_BACK_TIPS, 7.0, 4.2), 0, 0)
    return out, back


# ---------------------------------------------------------------------------------------------- Mega Milotic
def _diancie(L):
    di = L("diancie/mega")
    light = lambda c: K.lum(c) > 165 and K.hsv(c)[1] < 0.3
    veil = di.cut(K.flood(di, [(4, 40), (6, 34), (58, 40), (56, 34)], light) |
                  K.flood(di, [(3, 44), (59, 44)], light))
    veil.outline((120, 96, 140))
    crown = di.cut(K.poly([(16, 0), (48, 0), (48, 12), (16, 12)]) &
                   K.by_color(di, lambda c: K.hue_in(290, 359, 0.15)(c) or K.lum(c) > 200 or K.is_dark(c, 50)))
    return veil.trim()[0], crown.trim()[0]


TIARA = {"o": (104, 24, 76), "w": (255, 255, 255), "l": (252, 196, 228), "p": (236, 104, 176)}
MI_FIN = {(8, 120, 160): (96, 64, 176), (56, 168, 216): (160, 120, 236)}
SPARKLE = {"w": (255, 255, 255), "p": (248, 168, 224), "k": (176, 72, 160)}


def sparkle(img, x, y, big=False):
    rows = (["..k..", ".kpk.", "kpwpk", ".kpk.", "..k.."] if big else [".p.", "pwp", ".p."])
    K_ = len(rows) // 2
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch in SPARKLE and img.get(x + c - K_, y + r - K_) is None:
                img.set(x + c - K_, y + r - K_, SPARKLE[ch])


def milotic(L):
    """Mega Milotic - Water/Fairy, Multiscale: its tail fan grows into a vast iridescent fin, a pink diamond
    tiara crowns it and veils of fairy light (Mega Diancie's) trail behind."""
    veil, _ = _diancie(L)
    out = L("milotic")
    fin = out.cut(K.poly([(40, 10), (64, 10), (64, 40), (44, 40), (40, 26)]))
    fin, (fx, fy) = fin.trim()
    big, _ = K.transform(fin, 1.45)
    recol = lambda c: MI_FIN.get(c, c)
    big.map_colors(recol)
    out.map_colors(recol)
    out.paste(big, fx - 6, fy - 12, under=True)
    v, _ = K.transform(veil, 1.15)
    out.paste(v, -3, 10, under=True)
    stamp(out, 11, 4, ["o.......o",
                        "ol..o..lo",
                        "olpowoplo",
                        "oplpwplpo",
                        "oppppppo.",
                        ".oooooo.."], TIARA)
    for x, y, b in ((4, 6, True), (60, 50, True), (30, 6, False), (56, 2, False), (2, 30, False)):
        sparkle(out, x, y, b)
    back = L("milotic", back=True)
    back.map_colors(recol)
    bv, _ = K.transform(veil, 1.2)
    back.paste(bv, -4, 16, under=True)
    return out, back


# ---------------------------------------------------------------------------------------------- Mega Flygon
FL_MEMBRANE = {(136, 160, 80): (184, 120, 40), (176, 216, 112): (232, 176, 64), (216, 248, 136): (252, 224, 128),
               (80, 96, 32): (120, 64, 24)}
FL_WING_COLS = set(FL_MEMBRANE) | {(200, 56, 72), (216, 96, 112), (248, 160, 176), (128, 40, 56), (16, 16, 16)}


FL_RIM = {(200, 56, 72), (216, 96, 112), (248, 160, 176), (128, 40, 56)}


def flygon(L):
    """Mega Flygon - Ground/Dragon, Tough Claws: a second, greater pair of wings unfolds behind the first - four
    diamond wings with sand-gold membranes and crimson rims, the spirit of the desert."""
    out = L("flygon")
    wing_area = (K.poly([(1, 8), (15, 8), (15, 18), (25, 31), (4, 26)]) |
                 K.poly([(31, 6), (63, 6), (57, 36), (33, 36)])) - K.rect(14, 8, 18, 14)
    membrane = K.flood(out, [(8, 16), (6, 12), (20, 26), (40, 16), (50, 12), (44, 26), (36, 30)],
                       lambda c: c in FL_MEMBRANE) & wing_area
    rims = K.by_color(out, lambda c: c in FL_RIM, wing_area)
    wmask = K.grow(membrane | rims, 1) & (wing_area | membrane)
    recol = lambda c: FL_MEMBRANE.get(c, c)
    out.map_colors(recol, membrane)
    w = out.cut(wmask)
    for half, piv, ang, dx in (([(0, 0), (31, 0), (31, 40), (0, 40)], (28, 30), -12, -2),
                               ([(31, 0), (64, 0), (64, 40), (31, 40)], (33, 31), 12, 2)):
        part_, (px, py) = K.transform(w.cut(K.poly(half)), 1.32, ang, pivot=piv)
        out.paste(part_, px + dx, py + 4, under=True)
    back = L("flygon", back=True)
    bmem = K.by_color(back, lambda c: c in FL_MEMBRANE, K.poly([(0, 0), (64, 0), (64, 26), (44, 36), (0, 40)]))
    back.map_colors(recol, bmem)
    return out, back


# ---------------------------------------------------------------------------------------------- Mega Togekiss
HALO = [(176, 120, 24), (232, 184, 48), (252, 232, 120), (255, 252, 220)]
HALO_OUT = (104, 64, 16)
TG_STREAM = [(160, 104, 24), (216, 160, 40), (244, 204, 88), (252, 236, 168)]


def ring(img, cx, cy, rx, ry, colors, outline):
    """A glowing ring (halo), lit from the top: outline, then the band in 3 tones."""
    band = set()
    for y in range(int(cy - ry - 3), int(cy + ry + 4)):
        for x in range(int(cx - rx - 3), int(cx + rx + 4)):
            d = ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2
            if 0.55 <= d <= 1.25:
                band.add((x, y))
    edge = {(x + dx, y + dy) for x, y in band for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))} - band
    for x, y in edge:
        img.set(x, y, outline)
    for x, y in band:
        top = y + 0.5 < cy
        img.set(x, y, colors[2] if top else colors[1])
    for x, y in band:
        if y + 0.5 < cy - ry * 0.6:
            img.set(x, y, colors[3])


def tri(img, pts, fill, light, outline):
    m = K.poly(pts)
    edge = {(x + dx, y + dy) for x, y in m for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))} - m
    for x, y in edge:
        img.set(x, y, outline)
    for x, y in m:
        img.set(x, y, fill)
    xs = [p[0] for p in pts]
    for x, y in m:
        if x < min(xs) + (max(xs) - min(xs)) * 0.4:
            img.set(x, y, light)


TG_CREST = [([(15, 30), (12, 22), (13, 14), (9, 7)], 3.4, [(184, 40, 32), (224, 72, 48), (248, 128, 96), (252, 192, 168)],
             (96, 24, 24)),
            ([(21, 27), (21, 18), (25, 10), (24, 3)], 3.6, [(48, 80, 200), (72, 120, 232), (144, 184, 248),
                                                           (216, 232, 255)], (24, 40, 112)),
            ([(28, 26), (31, 18), (36, 12), (37, 5)], 3.2, [(200, 144, 32), (232, 184, 48), (252, 232, 120),
                                                           (255, 252, 220)], (104, 64, 16))]
TG_STREAMERS = [([(46, 46), (52, 52), (56, 58), (63, 60)], 2.4), ([(40, 48), (43, 55), (48, 60), (54, 64)], 2.2)]


def togekiss(L):
    """Mega Togekiss - Fairy/Flying, Serene Grace: a radiant halo, a crest of long red, blue and gold plumes
    swept back from its head, and golden streamers trailing behind - a messenger of blessings."""
    out = L("togekiss")
    layer = K.Img(64, 64)
    for spine, w, cols, o in TG_CREST:
        K.flame(layer, spine, w, cols, o)
    for spine, w in TG_STREAMERS:
        K.flame(layer, spine, w, TG_STREAM, (96, 56, 16))
    ring(layer, 17, 3.5, 9, 2.6, HALO, HALO_OUT)
    out.paste(layer, 0, 0, under=True)
    back = L("togekiss", back=True)
    bl = K.Img(64, 64)
    for spine, w, cols, o in TG_CREST:
        K.flame(bl, [(64 - x + 6, y + 6) for x, y in spine], w * 1.15, cols, o)
    ring(bl, 40, 6, 10, 3, HALO, HALO_OUT)
    back.paste(bl, 0, 0, under=True)
    return out, back


RECIPES = {"snorlax": snorlax, "lapras": lapras, "machamp": machamp, "arcanine": arcanine, "typhlosion": typhlosion, "luxray": luxray, "ninetales": ninetales, "milotic": milotic, "flygon": flygon, "togekiss": togekiss}
NEEDS = {"snorlax": ["snorlax"], "lapras": ["lapras", "crabominable/mega"], "machamp": ["machamp"],
         "arcanine": ["arcanine"], "typhlosion": ["typhlosion"],
         "luxray": ["luxray", "manectric/mega"], "ninetales": ["ninetales"],
         "milotic": ["milotic", "diancie/mega"], "flygon": ["flygon"],
         "togekiss": ["togekiss"]}


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
    with open(os.path.join(cache_dir(), "version.txt"), "w", encoding="utf-8") as f:
        f.write(VERSION)
    return True


VERSION = "3"   # bump when a recipe changes so players' cached sprites get rebuilt
_busy = set()


def _stale():
    try:
        with open(os.path.join(cache_dir(), "version.txt"), encoding="utf-8") as f:
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
