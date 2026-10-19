"""PokeBrawl's opening, the way the Game Boy Advance games open: a shooting star "presents" screen, a moonlit
Gengar-vs-Nidorino clash (FireRed's own intro sprites), then the title screen - Charizard in flames or Venusaur
in falling leaves, like FireRed and LeafGreen - with PRESS START. Plus the loading screen and the Poke Ball
wipe used between big screens.

Everything is drawn on a small 240x427 pixel screen and blown up 3x, so it all stays chunky pixel art. The
FireRed graphics download once into ~/.pokebrawl/frlg; without them the intro is skipped and the title screen
still works (just without the box-art Pokemon).
"""
import math
import os
import random
import threading

import pygame

from . import frlg, gfx
from . import pixelfont as F
from .app import Scene
from .audio import AUDIO

LW, LH = 240, 427      # the pixel screen; 3x is the 720x1280 canvas
SCALE = 3
I = "graphics/intro/"
T = "graphics/title_screen/"
FILES = [I + p for p in ("gengar.pal", "nidorino.pal", "scene_2/gengar.png", "scene_2/nidorino.png",
                         "scene_3/gengar_anim.png", "scene_3/gengar_anim.bin", "scene_3/nidorino.png",
                         "scene_3/recoil_dust.png", "game_freak/star.png", "game_freak/sparkles.pal",
                         "game_freak/sparkles_big.png", "game_freak/sparkles_small.png")] + \
        [T + v + p for v in ("firered/", "leafgreen/") for p in ("box_art_mon.png", "box_art_mon.bin",
                                                                 "box_art_mon.pal")] + \
        [T + "firered/flames.png", T + "leafgreen/leaves.png", T + "slash.png", T + "firered/slash.pal"]

YELLOW = (255, 214, 40)
BLUE = (40, 96, 200)
NAVY = (16, 36, 96)
_assets = {}
_state = {"started": False, "done": False}


def warm():
    """Downloads the intro's graphics in the background (once); ready() says when they're there."""
    if _state["started"]:
        return
    _state["started"] = True

    def run():
        try:
            frlg.prefetch(FILES)
        finally:
            _state["done"] = True
    threading.Thread(target=run, daemon=True).start()


def ready():
    return all(os.path.exists(frlg.local(p)) for p in FILES)


def settled():
    """True once the download either worked or gave up."""
    return ready() or _state["done"]


def _sheet(png, pal, w, h):
    """Frames of a sprite sheet in its palette (palette entry 0 is see-through)."""
    key = (png, pal, w, h)
    if key in _assets:
        return _assets[key]
    out = []
    f = frlg.fetch(png)
    if f:
        img = pygame.image.load(f)
        if img.get_bitsize() == 8:
            if pal:
                banks = frlg.pal_banks(pal)
                if banks:
                    img.set_palette(banks[0])
            img.set_colorkey(img.get_palette_at(0))
            from .gbaart import _rgba
            img = _rgba(img)
            out = [img.subsurface((x, y, w, h)).copy() for y in range(0, img.get_height() - h + 1, h)
                   for x in range(0, img.get_width() - w + 1, w)]
    _assets[key] = out
    return out


def _recolor(frames, light, dark):
    """Repaint sprites by brightness, from dark to light (for sheets whose palette lives elsewhere)."""
    out = []
    for f in frames:
        g = f.copy()
        w, h = g.get_size()
        lum = [(x, y, sum(g.get_at((x, y))[:3])) for y in range(h) for x in range(w) if g.get_at((x, y))[3]]
        if lum:
            lo, hi = min(v for *_, v in lum), max(v for *_, v in lum)
            for x, y, v in lum:
                k = (v - lo) / max(1, hi - lo)
                g.set_at((x, y), tuple(int(a + (b - a) * k) for a, b in zip(dark, light)) + (255,))
        out.append(g)
    return out


def gengar_back():
    """FireRed's big Gengar seen from behind: standing, crouching, and with its arm raised to swipe."""
    if "gengar_back" not in _assets:
        out = []
        banks = frlg.pal_banks(I + "gengar.pal")
        m = banks and frlg.tilemap(I + "scene_3/gengar_anim.png", I + "scene_3/gengar_anim.bin", banks, 0, 32)
        if m:
            for y in range(0, m.get_height() - 127, 128):
                part = m.subsurface((0, y, 128, 128))
                r = part.get_bounding_rect()
                if r.w and r.h:
                    out.append(part.subsurface(r).copy())
        _assets["gengar_back"] = out
    return _assets["gengar_back"]


def box_art(version):
    """The title screen's Pokemon (FireRed's Charizard or LeafGreen's Venusaur), trimmed, or None."""
    key = ("box", version)
    if key not in _assets:
        banks = frlg.pal_banks(T + version + "/box_art_mon.pal")
        m = banks and frlg.tilemap(T + version + "/box_art_mon.png", T + version + "/box_art_mon.bin", banks, 0, 32)
        _assets[key] = m.subsurface(m.get_bounding_rect()).copy() if m else None
    return _assets[key]


def present(canvas, low, shake=(0, 0)):
    """Blow the pixel screen up onto the canvas."""
    canvas.fill((0, 0, 0))
    canvas.blit(pygame.transform.scale(low, (LW * SCALE, LH * SCALE)), (shake[0] * SCALE, shake[1] * SCALE))


def _ease_out(k):
    return 1 - (1 - max(0.0, min(1.0, k))) ** 3


def _back_out(k):
    k = max(0.0, min(1.0, k)) - 1
    return 1 + 2.7 * k ** 3 + 1.7 * k ** 2


def claw(surf, center, k):
    """Three claw slashes raking down across center: drawn in over the first third of k, then fading."""
    cx, cy = center
    grow = min(1.0, k / 0.3)
    a = 255 if k < 0.5 else int(255 * (1 - (k - 0.5) / 0.5))
    lay = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    for i in (-1, 0, 1):
        x0, y0 = cx - 36 + i * 14, cy - 42 + i * 5
        x1, y1 = x0 + 66 * grow, y0 + 86 * grow
        pygame.draw.line(lay, (150, 60, 200, a), (x0, y0), (x1, y1), 7)
        pygame.draw.line(lay, (255, 236, 255, a), (x0, y0), (x1, y1), 3)
    surf.blit(lay, (0, 0))


def flash(surf, a, color=(255, 255, 255)):
    if a <= 0:
        return
    s = pygame.Surface(surf.get_size())
    s.fill(color)
    s.set_alpha(int(max(0, min(255, a))))
    surf.blit(s, (0, 0))


def pixel_ball(r, open_k=0.0, glow=0.0):
    """A chunky Poke Ball of radius r (drawn small, so it stays pixel art). glow lights its button."""
    size = r * 2 + 4
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    ink = (24, 24, 32)
    pygame.draw.circle(s, ink, (c, c), r + 1)
    pygame.draw.circle(s, (240, 240, 248), (c, c), r - 1)
    top = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(top, (224, 48, 48), (c, c), r - 1)
    pygame.draw.circle(top, (255, 120, 104), (c - r // 3, c - r // 3), max(1, r // 4))
    s.blit(top, (0, -int(open_k * r)), (0, 0, size, c))
    pygame.draw.circle(s, (200, 200, 212), (c + r // 3, c + r // 2), max(1, r // 5))
    band = max(2, r // 6)
    pygame.draw.rect(s, ink, (1, c - band // 2, size - 2, band))
    br = max(3, r // 3)
    pygame.draw.circle(s, ink, (c, c), br + 1)
    btn = tuple(int(a + (b - a) * glow) for a, b in zip((240, 240, 248), (255, 90, 80)))
    pygame.draw.circle(s, btn, (c, c), br - 1)
    return s


def logo(scale=1.0):
    """'PokeBrawl' in the Pokemon logo's colours: yellow letters, thick blue outline, a navy drop shadow."""
    key = ("logo", round(scale, 2))
    if key in _assets:
        return _assets[key]
    size = max(8, int(40 * scale))
    f = gfx.font(size)
    word = f.render("PokeBrawl", False, YELLOW)
    ow = max(2, size // 9)
    w, h = word.get_width() + ow * 2 + 4, word.get_height() + ow * 2 + 6
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    for col, dy in ((NAVY, 4), (BLUE, 0)):
        o = f.render("PokeBrawl", False, col)
        for dx in range(-ow, ow + 1):
            for ddy in range(-ow, ow + 1):
                if dx * dx + ddy * ddy <= ow * ow + 1:
                    out.blit(o, (ow + dx + 2, ow + ddy + dy))
    # letters: yellow, a lighter top half and a deeper orange underside, like the real logo's bevel
    shade = pygame.Surface(word.get_size(), pygame.SRCALPHA)
    wh = word.get_height()
    for y in range(wh):
        k = y / max(1, wh - 1)
        col = (255, 240, 120) if k < 0.38 else YELLOW if k < 0.7 else (246, 168, 24)
        pygame.draw.line(shade, col + (255,), (0, y), (word.get_width(), y))
    letters = word.copy()
    letters.blit(shade, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    letters.blit(word, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    tint = word.copy()
    tint.fill((0, 0, 0, 0))
    tint.blit(shade, (0, 0))
    tint.blit(word, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    out.blit(tint, (ow + 2, ow))
    _assets[key] = out
    return out


def _sparkle(surf, x, y, n, color=(255, 255, 255)):
    """A four-pointed twinkle."""
    x, y = int(x), int(y)
    if n <= 0:
        return
    surf.set_at((x, y), color)
    for i in range(1, n + 1):
        for dx, dy in ((i, 0), (-i, 0), (0, i), (0, -i)):
            if 0 <= x + dx < surf.get_width() and 0 <= y + dy < surf.get_height():
                surf.set_at((x + dx, y + dy), color)


# ---------------------------------------------------------------------- the opening
class IntroScene(Scene):
    """Presents screen, then the clash. Any key or click jumps to the title screen."""
    no_transition = True
    PRESENTS_END = 3.8
    CLASH_END = 11.2

    def __init__(self, app):
        super().__init__(app)
        self.t = 0.0
        self.low = pygame.Surface((LW, LH))
        self.rng = random.Random(4)
        self.bits = []          # falling sparkles: [x, y, vx, vy, life]
        self.stars = [(self.rng.randrange(LW), self.rng.randrange(230), self.rng.random() * 6) for _ in range(60)]
        self.cues = set()
        self.shake = 0.0
        gen = _sheet(I + "scene_2/gengar.png", I + "gengar.pal", 64, 64)
        self.gengar = gen[0] if gen else None
        self.gengar_back = gengar_back()
        self.nido = _sheet(I + "scene_3/nidorino.png", I + "nidorino.pal", 64, 64)
        self.dust = _recolor(_sheet(I + "scene_3/recoil_dust.png", I + "nidorino.pal", 16, 16), (240, 236, 220),
                             (150, 140, 120))
        self.star = (_sheet(I + "game_freak/star.png", I + "game_freak/sparkles.pal", 16, 16) or [None])[0]
        self.big_sparks = _sheet(I + "game_freak/sparkles_big.png", I + "game_freak/sparkles.pal", 32, 32)
        self.small_spark = (_sheet(I + "game_freak/sparkles_small.png", I + "game_freak/sparkles.pal", 16, 16)
                            or [None])[0]

    def _cue(self, name, at, fn):
        if self.t >= at and name not in self.cues:
            self.cues.add(name)
            fn()

    def handle(self, ev, pos):
        if ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            self._done()

    def _done(self):
        self.app.replace(TitleScene(self.app, from_white=True))

    def update(self, dt):
        self.t += dt
        t = self.t
        self.shake = max(0.0, self.shake - dt * 3)
        self._cue("chime", 1.35, lambda: AUDIO.play("catch", 0.7))
        self._cue("music", self.PRESENTS_END, lambda: AUDIO.music("title"))
        self._cue("gengar", 4.3, lambda: AUDIO.cry(94, 0.9))
        self._cue("nido", 5.9, lambda: AUDIO.cry(33, 0.9))
        self._cue("roar", 9.1, lambda: AUDIO.cry(33, 1.0))
        self._cue("leap", 10.5, lambda: AUDIO.play("boom", 0.8))
        # the shooting star's trail of sparkles
        if 0.2 < t < 1.4:
            x, y = self._star_pos(t)
            for _ in range(2):
                self.bits.append([x, y, self.rng.uniform(-14, 14), self.rng.uniform(-10, 8), 1.6])
        if 1.4 <= t < 1.5 and "burst" not in self.cues:
            self.cues.add("burst")
            for _ in range(40):
                a = self.rng.uniform(0, math.tau)
                v = self.rng.uniform(20, 70)
                self.bits.append([LW / 2, 150, math.cos(a) * v, math.sin(a) * v - 10, self.rng.uniform(1.2, 2.4)])
        for b in self.bits:
            b[0] += b[2] * dt
            b[1] += b[3] * dt
            b[3] += 26 * dt
            b[2] *= 0.98
            b[4] -= dt
        self.bits = [b for b in self.bits if b[4] > 0]
        if t >= self.CLASH_END:
            self._done()

    @staticmethod
    def _star_pos(t):
        k = _ease_out((t - 0.2) / 1.2)
        return LW + 10 - (LW + 10 - LW / 2) * k, -10 + 160 * k - math.sin(k * math.pi) * 40

    # -- drawing
    def draw(self, surf):
        low = self.low
        if self.t < self.PRESENTS_END:
            self._presents(low)
        else:
            self._clash(low)
        sh = (0, 0)
        if self.shake > 0:
            sh = (self.rng.randint(-3, 3) * self.shake, self.rng.randint(-2, 2) * self.shake)
        present(surf, low, sh)
        F.draw(surf, "Press any key to skip", (gfx.W - 16, gfx.H - 30), (120, 120, 140), None, 2,
               anchor="topright") if self.t > 1.0 else None

    def _presents(self, low):
        t = self.t
        low.fill((0, 0, 0))
        for b in self.bits:
            n = 1 if b[4] < 0.6 else 2
            if self.small_spark is not None and b[4] > 1.2:
                low.blit(self.small_spark, (b[0] - 8, b[1] - 8))
            else:
                _sparkle(low, b[0], b[1], n if int(b[4] * 12) % 3 else 0, (255, 250, 200))
        if 0.2 < t < 1.4:
            x, y = self._star_pos(t)
            if self.star is not None:
                low.blit(self.star, (x - 8, y - 8))
            else:
                _sparkle(low, x, y, 3)
        if t >= 1.4:
            k = _back_out((t - 1.4) / 0.5)
            ball = pixel_ball(max(2, int(22 * k)), glow=max(0.0, 1 - (t - 1.4) * 1.5))
            low.blit(ball, ball.get_rect(center=(LW // 2, 150)))
            if self.big_sparks and t < 2.2:
                fr = self.big_sparks[int((t - 1.4) * 10) % len(self.big_sparks)]
                low.blit(fr, (LW // 2 + 14, 122))
            a = int(255 * max(0.0, min(1.0, (t - 1.9) / 0.4)))
            if a:
                name = gfx.text_image("JAKEDAPRO", 22, (255, 255, 255), (40, 80, 180), 2)
                name = name.copy()
                name.set_alpha(a)
                low.blit(name, name.get_rect(center=(LW // 2, 200)))
                F.draw(low, "presents", (LW // 2, 226), (200, 200, 220), (60, 60, 90), 1, anchor="center")
                if t > 2.3:
                    F.draw(low, "a fan-made Pokemon game", (LW // 2, 400), (110, 110, 130), None, 1,
                           anchor="center")
        fade = max(0.0, (t - (self.PRESENTS_END - 0.45)) / 0.45)
        flash(low, fade * 255, (0, 0, 0))

    def _night(self, low, t, pan=0.0):
        """Moonlit sky over a field."""
        for y in range(0, 300, 3):
            k = y / 300
            pygame.draw.rect(low, (int(10 + 34 * k), int(10 + 14 * k), int(34 + 40 * k)), (0, y, LW, 3))
        for x, y, ph in self.stars:
            if math.sin(t * 3 + ph) > -0.3:
                low.set_at(((int(x - pan * 0.2)) % LW, y), (200, 200, 230))
        mx = 178 - pan * 0.3
        glow = pygame.Surface((90, 90), pygame.SRCALPHA)
        for r in range(44, 27, -3):
            pygame.draw.circle(glow, (200, 200, 255, 10), (45, 45), r)
        low.blit(glow, (int(mx) - 45, 25))
        pygame.draw.circle(low, (250, 246, 210), (int(mx), 70), 27)
        for cx, cy, r in ((-8, -6, 5), (7, 8, 4), (9, -10, 3)):
            pygame.draw.circle(low, (226, 222, 186), (int(mx + cx), 70 + cy), r)
        # hills and the tree line, darker the nearer
        for base, col, amp, sp in ((210, (26, 26, 56), 18, 0.5), (240, (16, 30, 40), 12, 0.8)):
            pts = [(0, LH)]
            for x in range(0, LW + 9, 8):
                xx = x + pan * sp
                pts.append((x, base - amp * math.sin(xx * 0.02) - 6 * math.sin(xx * 0.07)))
            pts.append((LW, LH))
            pygame.draw.polygon(low, col, pts)
        for i in range(-1, 14):
            x = i * 20 - (pan * 0.8) % 20
            h = 28 + (i * 37) % 17
            pygame.draw.polygon(low, (10, 22, 26), [(x - 9, 262), (x, 262 - h), (x + 9, 262)])
        for y in range(258, LH, 3):           # the field, lit by the moon further back
            k = (y - 258) / (LH - 258)
            low.fill((int(22 - 10 * k), int(52 - 22 * k), int(42 - 16 * k)), (0, y, LW, 3))
        rng = random.Random(11)
        for _ in range(90):                   # grass tufts, bigger the nearer they are
            x0, y = rng.uniform(-20, LW + 20), rng.uniform(262, LH)
            k = (y - 258) / (LH - 258)
            x = (x0 - pan * (0.8 + k)) % (LW + 40) - 20
            h = int(3 + 9 * k)
            sway = math.sin(t * 2 + x0) * (1 + k)
            col = (int(40 + 30 * (1 - k)), int(96 + 40 * (1 - k)), int(60 + 20 * (1 - k)))
            for dx in (-2 - int(2 * k), 0, 2 + int(2 * k)):
                pygame.draw.line(low, col, (x + dx, y), (x + dx * 1.6 + sway, y - h + abs(dx)))

    def _clash(self, low):
        t = self.t - self.PRESENTS_END       # 0 .. 6.6
        if t < 2.0:                           # Gengar grins out of the dark
            self._night(low, self.t, pan=0)
            if self.gengar is not None:
                k = max(0.0, min(1.0, (t - 0.4) / 0.9))
                g = pygame.transform.scale_by(self.gengar, 2)
                if k < 1:
                    dark = g.copy()
                    dark.fill((0, 0, 0, 255 - int(255 * k)), special_flags=pygame.BLEND_RGBA_MULT)
                    sil = g.copy()
                    sil.fill((8, 6, 20, 255), special_flags=pygame.BLEND_RGBA_MIN)
                    low.blit(sil, sil.get_rect(midbottom=(LW // 2, 330)))
                    g.set_alpha(int(255 * k))
                low.blit(g, g.get_rect(midbottom=(LW // 2, 330 + int(math.sin(self.t * 3) * 2))))
            if t < 0.4:   # just its eyes at first
                for ex in (106, 128):
                    pygame.draw.rect(low, (255, 40, 40), (ex, 236, 6, 3))
            flash(low, 255 * max(0.0, 1 - t / 0.5), (0, 0, 0))
            if t > 1.75:   # whip pan
                self._speed_lines(low, (t - 1.75) / 0.25)
        elif t < 3.4:                         # Nidorino answers from the hill
            tt = t - 2.0
            self._night(low, self.t, pan=120)
            if self.nido:
                drop = max(0.0, 1 - tt / 0.3)
                fr = self.nido[1] if 0.15 < tt < 1.2 else self.nido[0]
                n = pygame.transform.scale_by(fr, 2)
                low.blit(n, n.get_rect(midbottom=(LW // 2 + 10, 320 - int(drop * 120))))
                if tt > 0.3 and self.dust:
                    d = self.dust[min(len(self.dust) - 1, int((tt - 0.3) * 12))]
                    for dx in (-40, 40):
                        low.blit(pygame.transform.scale_by(d, 2), (LW // 2 + 10 + dx - 16, 296))
            if tt < 0.25:
                self._speed_lines(low, 1 - tt / 0.25)
        else:                                 # the face-off
            tt = t - 3.4
            self._night(low, self.t, pan=60)
            self._faceoff(low, tt)

    def _faceoff(self, low, tt):
        nx, ny = 168, 300
        sw0 = 1.05                            # Gengar's swipe; Nidorino is knocked back by it
        if sw0 + 0.15 < tt < sw0 + 0.75:
            nx += int(18 * math.sin((tt - sw0 - 0.15) / 0.6 * math.pi))
        if self.nido:
            if tt < 0.5:
                fr = self.nido[0]
            elif tt < 1.4:
                fr = self.nido[2]              # crouch, waiting
            elif tt < 1.9:
                fr = self.nido[0]
            elif tt < 2.4:
                fr = self.nido[4]              # roar
            elif tt < 3.3:
                fr = self.nido[2]
            else:
                fr = self.nido[3]
            k = 0.0 if tt < 3.3 else min(1.0, (tt - 3.3) / 0.45)
            if k > 0:   # leaps at the camera
                s = 1.5 + k * 7
                img = pygame.transform.scale_by(self.nido[4], s)
                low.blit(img, img.get_rect(center=(nx - 40 * k, ny - 30 - 90 * k)))
            else:
                img = pygame.transform.scale_by(fr, 1.5)
                low.blit(img, img.get_rect(midbottom=(nx, ny)))
        # Gengar, from behind, in the foreground
        if self.gengar_back:
            lunge = 14 * math.sin(min(1.0, max(0.0, (tt - 0.85) / 0.5)) * math.pi)   # lunges into the swipe
            frames = self.gengar_back
            gi = (len(frames) - 1 if 0.8 < tt < 1.5 else 1 if 0.5 < tt <= 0.8 else 0) if len(frames) > 2 else 0
            gb = pygame.transform.scale_by(frames[gi], 1.6)
            low.blit(gb, gb.get_rect(midbottom=(78 + lunge, LH + 8 - lunge - int(math.sin(tt * 2.5) * 2))))
        # the swipe
        if sw0 <= tt < sw0 + 0.5:
            claw(low, (nx, ny - 40), (tt - sw0) / 0.5)
        if sw0 + 0.15 <= tt < sw0 + 0.3:
            flash(low, 160)
        if sw0 + 0.15 <= tt and "shook" not in self.cues:
            self.cues.add("shook")
            self.shake = 1.0
            AUDIO.play("hit_super")
        if tt >= 3.3:
            k = min(1.0, (tt - 3.3) / 0.6)
            flash(low, 255 * k ** 2)

    @staticmethod
    def _speed_lines(low, k):
        rng = random.Random(int(k * 20))
        for _ in range(40):
            y = rng.randrange(LH)
            w = rng.randrange(30, 120)
            x = rng.randrange(-60, LW)
            pygame.draw.line(low, (230, 230, 255), (x, y), (x + w, y))
        flash(low, 90 * (1 - abs(k - 0.5) * 2))


# ---------------------------------------------------------------------- the title screen
class TitleScene(Scene):
    """PokeBrawl's title screen. A key or click (PRESS START) goes on to the main menu."""
    no_transition = True

    def __init__(self, app, from_white=False):
        super().__init__(app)
        self.t = 0.0
        self.white = 1.0 if from_white else 0.0
        self.low = pygame.Surface((LW, LH))
        self.rng = random.Random()
        self.version = self.rng.choice(("firered", "leafgreen"))
        self.mon = box_art(self.version)
        self.fx = []               # rising flames / falling leaves: [x, y, vx, vy, age, frame0]
        if self.version == "firered":
            self.fx_frames = _sheet(T + "firered/flames.png", None, 16, 16)[:6]   # (the rest is grey smoke)
        else:
            self.fx_frames = _sheet(T + "leafgreen/leaves.png", None, 16, 16)
        self.slash = (_sheet(T + "slash.png", T + "firered/slash.pal", 64, 64) or [None])[0]
        self.leaving = None
        self.embers = []
        self.slammed = False

    def handle(self, ev, pos):
        if self.leaving is None and self.t > 0.4 and (ev.type == pygame.KEYDOWN or
                                                     (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1)):
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self.app.running = False
                return
            self.leaving = 0.0
            AUDIO.play("select")

    def update(self, dt):
        self.t += dt
        AUDIO.music("title")
        self.white = max(0.0, self.white - dt * 1.6)
        if self.t > 0.35 and not self.slammed:
            self.slammed = True
            AUDIO.play("impact")
        fire = self.version == "firered"
        if self.rng.random() < dt * (18 if fire else 7):
            if fire:
                self.fx.append([self.rng.uniform(0, LW), LH + 8, self.rng.uniform(-6, 6),
                                -self.rng.uniform(40, 80), 0.0, 0])
            else:
                self.fx.append([self.rng.uniform(-20, LW), -10, self.rng.uniform(10, 30),
                                self.rng.uniform(20, 40), 0.0, self.rng.randrange(11)])
        for p in self.fx:
            p[4] += dt
            p[0] += (p[2] + (0 if fire else math.sin(p[4] * 3 + p[5]) * 18)) * dt
            p[1] += p[3] * dt
        life = 1.6 if fire else 12
        self.fx = [p for p in self.fx if p[4] < life and -30 < p[1] < LH + 20]
        if self.leaving is not None:
            self.leaving += dt
            if self.leaving > 0.45:
                from .app import MainMenu
                self.app.next_transition = "ball"
                self.app.replace(MainMenu(self.app))

    def draw(self, surf):
        low = self.low
        t = self.t
        fire = self.version == "firered"
        top, bot = ((6, 4, 10), (120, 24, 12)) if fire else ((4, 12, 10), (16, 96, 48))
        for y in range(0, LH, 3):
            k = (y / LH) ** 1.6
            low.fill(tuple(int(a + (b - a) * k) for a, b in zip(top, bot)), (0, y, LW, 3))
        # light rays turning slowly behind the Pokemon
        cx, cy = LW // 2, 250
        rays = pygame.Surface((LW, LH), pygame.SRCALPHA)
        for i in range(12):
            a = t * 0.15 + i * math.tau / 12
            pts = [(cx, cy), (cx + math.cos(a) * 400, cy + math.sin(a) * 400),
                   (cx + math.cos(a + 0.18) * 400, cy + math.sin(a + 0.18) * 400)]
            pygame.draw.polygon(rays, (255, 200, 120, 14) if fire else (180, 255, 180, 12), pts)
        low.blit(rays, (0, 0))
        # the box-art Pokemon rises into place
        if self.mon is not None:
            k = _ease_out((t - 0.2) / 1.0)
            mon = pygame.transform.scale_by(self.mon, 2)
            bob = int(math.sin(t * 1.6) * 2)
            r = mon.get_rect(center=(LW // 2 + 6, 255 + int((1 - k) * 180) + bob))
            low.blit(mon, r)
        # flames / leaves
        for x, y, _vx, _vy, age, f0 in self.fx:
            if not self.fx_frames:
                break
            if fire:
                fr = self.fx_frames[min(len(self.fx_frames) - 1, int(age / 1.6 * len(self.fx_frames)))]
            else:
                fr = self.fx_frames[(f0 + int(age * 8)) % len(self.fx_frames)]
            low.blit(fr, (int(x) - 8, int(y) - 8))
        if fire:   # a wall of fire along the bottom
            for i in range(0, LW + 16, 12):
                if self.fx_frames:
                    fr = self.fx_frames[int(t * 10 + i) % 4]
                    low.blit(fr, (i - 8, LH - 12 - int(abs(math.sin(t * 5 + i)) * 4)))
        # the logo slams down, then a shine sweeps across it now and then
        lk = _back_out((t - 0.05) / 0.35)
        lg = logo(1.0)
        if lk < 1:
            lg = pygame.transform.scale_by(lg, 1 + (1 - lk) * 1.5)
        lr = lg.get_rect(center=(LW // 2, 92 + int(math.sin(t * 1.2) * 2)))
        low.blit(lg, lr)
        cyc = (t - 1.2) % 4.0
        if t > 1.2 and cyc < 0.6 and self.slash is not None:
            shine = logo(1.0).copy()
            band = pygame.Surface(shine.get_size(), pygame.SRCALPHA)
            sx = int(-60 + cyc / 0.6 * (shine.get_width() + 120))
            pygame.draw.polygon(band, (255, 255, 255, 200), [(sx, 0), (sx + 14, 0), (sx - 10, shine.get_height()),
                                                            (sx - 24, shine.get_height())])
            band.blit(shine, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            low.blit(band, lr.topleft, special_flags=pygame.BLEND_RGBA_ADD)
        sub = "FIRE VERSION" if fire else "LEAF VERSION"
        if t > 0.5:
            col = (255, 140, 60) if fire else (120, 230, 110)
            F.draw(low, sub, (LW // 2, lr.bottom + 8), col, (40, 16, 16) if fire else (8, 40, 16), 1, anchor="center")
        if t > 1.4 and self.leaving is None and int(t * 1.6) % 2 == 0:
            F.draw(low, "PRESS START", (LW // 2, 381), (255, 255, 255), (60, 60, 80), 1, anchor="center")
        if self.leaving is not None and int(self.leaving * 16) % 2 == 0:
            F.draw(low, "PRESS START", (LW // 2, 381), (255, 255, 120), (60, 60, 80), 1, anchor="center")
        F.draw(low, "Fan-made. Pokemon (c) Nintendo / Game Freak", (LW // 2, 400), (230, 220, 220), (20, 10, 10),
               1, anchor="center", small=True)
        present(surf, low)
        flash(surf, 255 * self.white)
        if self.leaving is not None:
            flash(surf, 200 * max(0.0, 1 - self.leaving / 0.3))


# ---------------------------------------------------------------------- loading
class Loading:
    """A Poke Ball wobbling like it's catching something, a bar with a ball rolling along it, and tips."""
    TIPS = ["Hold X to run in Adventure.",
            "Shiny Pokemon are 1 in 512!",
            "Talk to the nurse in a Pokemon Center to heal.",
            "Press G in a 1v1 to Gigantamax.",
            "Win battles for a chance to meet a legendary.",
            "Your rival always picks the starter strong against yours."]

    def __init__(self):
        self.low = pygame.Surface((LW, LH))
        self.rng = random.Random(9)
        self.dots = [(self.rng.uniform(0, LW), self.rng.uniform(0, LH), self.rng.uniform(4, 14),
                      self.rng.random() * 6) for _ in range(50)]
        self.tip = random.randrange(len(self.TIPS))

    def draw(self, surf, t, frac=None, msg="Loading...", error=None):
        low = self.low
        for y in range(0, LH, 3):
            k = y / LH
            low.fill((int(16 + 10 * k), int(22 + 12 * k), int(44 + 20 * k)), (0, y, LW, 3))
        for x, y, sp, ph in self.dots:
            yy = (y - t * sp) % LH
            if math.sin(t * 2 + ph) > 0.2:
                _sparkle(low, x, yy, 1, (120, 140, 200))
        # the ball: three wobbles, then a pause and a glint, like a catch
        cyc = t % 2.2
        ang = math.sin(cyc / 1.2 * math.pi * 3) * 20 if cyc < 1.2 else 0.0
        glow = max(0.0, 1 - abs(cyc - 1.6) * 4)
        ball = pixel_ball(30, glow=glow)
        ball = pygame.transform.rotate(ball, ang)
        hop = abs(math.sin(cyc / 1.2 * math.pi * 3)) * 6 if cyc < 1.2 else 0
        low.blit(ball, ball.get_rect(center=(LW // 2, 160 - hop)))
        pygame.draw.ellipse(low, (8, 12, 26), (LW // 2 - 24, 194, 48, 8))
        if glow > 0.5:
            _sparkle(low, LW // 2 + 22, 140, 3)
        dots = "." * (int(t * 3) % 4)
        F.draw(low, error or (msg + dots if not msg.endswith("...") else msg[:-3] + dots), (LW // 2, 232),
               (255, 255, 255), (40, 50, 90), 1, anchor="center")
        if frac is not None and not error:
            x0, y0, w = 40, 254, LW - 80
            pygame.draw.rect(low, (12, 12, 20), (x0 - 2, y0 - 2, w + 4, 10))
            pygame.draw.rect(low, (60, 70, 100), (x0, y0, w, 6))
            fw = int(w * max(0.0, min(1.0, frac)))
            if fw:
                pygame.draw.rect(low, (88, 208, 120), (x0, y0, fw, 6))
                pygame.draw.rect(low, (160, 248, 168), (x0, y0, fw, 2))
            rb = pygame.transform.rotate(pixel_ball(5), -t * 360)
            low.blit(rb, rb.get_rect(center=(x0 + fw, y0 + 3)))
        # a tip, in a FireRed-ish text box
        tip = self.TIPS[(self.tip + int(t / 5)) % len(self.TIPS)]
        pygame.draw.rect(low, (40, 56, 96), (10, 340, LW - 20, 46), border_radius=4)
        pygame.draw.rect(low, (248, 248, 248), (12, 342, LW - 24, 42), border_radius=3)
        pygame.draw.rect(low, (112, 160, 208), (14, 344, LW - 28, 38), 1, border_radius=3)
        F.draw(low, "TIP", (22, 350), (232, 64, 56), (248, 200, 192), 1)
        lines = F.wrap(tip, LW - 74, 1)
        for i, line in enumerate(lines[:2]):
            F.draw(low, line, (48, 350 + i * 14), (72, 72, 80), (208, 208, 200), 1)
        present(surf, low)


def ball_wipe(canvas, old, k):
    """The Poke Ball wipe between big screens. k 0..1: the ball's halves close over the old screen (old is that
    picture, the live screen is already on canvas once k passes 0.5) and open again on the new one."""
    w, h = canvas.get_size()
    if k < 0.5:
        canvas.blit(old, (0, 0))
        c = _ease_out(k / 0.5)
    else:
        c = 1 - _ease_out((k - 0.5) / 0.5) if k < 1 else 0
    if c <= 0:
        return
    half = int(h / 2 * c)
    band = max(8, h // 48)
    pygame.draw.rect(canvas, (224, 48, 48), (0, 0, w, half))
    pygame.draw.rect(canvas, (255, 112, 100), (0, max(0, half - h // 2), w, max(4, h // 90)))
    pygame.draw.rect(canvas, (240, 240, 248), (0, h - half, w, half))
    pygame.draw.rect(canvas, (24, 24, 32), (0, half - band // 2, w, band // 2 + 2))
    pygame.draw.rect(canvas, (24, 24, 32), (0, h - half - 2, w, band // 2 + 2))
    if c > 0.75:
        cy = h // 2
        r = int(min(w, h) * 0.11 * min(1.0, (c - 0.75) / 0.25))
        edge = max(3, r // 6)
        pygame.draw.circle(canvas, (24, 24, 32), (w // 2, cy), r + edge)
        pygame.draw.circle(canvas, (240, 240, 248), (w // 2, cy), r)
        pygame.draw.circle(canvas, (24, 24, 32), (w // 2, cy), max(1, r // 2), max(1, edge // 2))
