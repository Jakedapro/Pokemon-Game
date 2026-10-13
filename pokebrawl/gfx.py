"""Drawing helpers: window scaling, fonts, sprites, arena background, trainer and ball art."""
import colorsys
import math
import os
import random

import pygame

from . import pokedex
from .types import COLORS

W, H = 720, 1280
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/lilitaone/LilitaOne-Regular.ttf"
BACK_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/back/{}.png"

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
INK = (40, 30, 40)
TEAM_COLORS = [(235, 60, 60), (60, 130, 245), (60, 200, 90), (240, 190, 40)]


# ---------------------------------------------------------------------------- safe scaling
def rescale(img, size):
    """Nearest-neighbor scale of a contiguous 32-bit copy. Avoids smoothscale/subsurface edge cases that
    produced striped, alpha-less sprites on some Macs (and suits pixel art anyway)."""
    size = (max(1, int(size[0])), max(1, int(size[1])))
    src = img.copy() if img.get_parent() is not None else img
    if src.get_bitsize() != 32:
        src = _plain_rgba(src)
    return pygame.transform.scale(src, size)


def new_surface(size, alpha=False):
    """A plain 32-bit surface (never palette/24-bit, whatever the display uses)."""
    return pygame.Surface(size, pygame.SRCALPHA if alpha else 0, 32)


# ---------------------------------------------------------------------------- display
class Display:
    """Renders to a fixed 720x1280 canvas and scales it into the window or full screen. The game keeps its
    9:16 shape in the middle; the space around it shows a blurred, dimmed copy of the game."""

    def __init__(self, headless=False, title="PokeBrawl", fullscreen=False):
        self.headless = headless
        self.fullscreen = False
        self._backdrop = None
        self._frame = 0
        if headless:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        pygame.init()
        pygame.display.set_caption(title)
        if headless:
            self.window = pygame.display.set_mode((W, H))
        else:
            self.set_fullscreen(fullscreen)
        self.canvas = new_surface((W, H))
        self._rect = pygame.Rect(0, 0, W, H)

    def set_fullscreen(self, on):
        if self.headless:
            return
        self._backdrop = None
        if on:
            try:
                self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                self.fullscreen = True
                return
            except pygame.error:
                pass
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
        except Exception:
            dw, dh = 1280, 800
        scale = min((dh - 90) / H, (dw - 40) / W, 1.0)
        self.window = pygame.display.set_mode((int(W * scale), int(H * scale)), pygame.RESIZABLE)
        self.fullscreen = False

    def toggle_fullscreen(self):
        self.set_fullscreen(not self.fullscreen)
        return self.fullscreen

    def present(self):
        if self.headless:
            return
        ww, wh = self.window.get_size()
        s = min(ww / W, wh / H)
        size = (max(1, int(W * s)), max(1, int(H * s)))
        self._rect = pygame.Rect((ww - size[0]) // 2, (wh - size[1]) // 2, *size)
        if size[0] < ww - 4 or size[1] < wh - 4:
            # side space: a blurred, darkened copy of the game (refreshed a few times a second - cheap)
            self._frame += 1
            if self._backdrop is None or self._backdrop.get_size() != (ww, wh) or self._frame % 8 == 0:
                tiny = pygame.transform.smoothscale(self.canvas, (9, 16))
                cover = max(ww / 9, wh / 16)
                bd = pygame.transform.smoothscale(tiny, (int(9 * cover) + 1, int(16 * cover) + 1))
                dim = pygame.Surface(bd.get_size())
                dim.fill((95, 95, 110))
                bd.blit(dim, (0, 0), special_flags=pygame.BLEND_MULT)
                self._backdrop = pygame.Surface((ww, wh))
                self._backdrop.blit(bd, bd.get_rect(center=(ww // 2, wh // 2)))
            self.window.blit(self._backdrop, (0, 0))
            shadow = self._rect.inflate(24, 24)
            pygame.draw.rect(self.window, (0, 0, 0), shadow, border_radius=14)
        else:
            self.window.fill((12, 12, 16))
        self.window.blit(pygame.transform.smoothscale(self.canvas, size), self._rect)
        pygame.display.flip()

    def to_canvas(self, pos):
        if self.headless:
            return pos
        r = self._rect
        return ((pos[0] - r.x) * W / max(1, r.w), (pos[1] - r.y) * H / max(1, r.h))


# ---------------------------------------------------------------------------- fonts
_fonts = {}


def _font_path():
    path = os.path.join(pokedex.HOME, "fonts", "LilitaOne-Regular.ttf")
    if not os.path.exists(path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = pokedex.fetch(FONT_URL, timeout=10)
            with open(path, "wb") as f:
                f.write(data)
        except Exception:
            return None
    return path


def font(size, chunky=True):
    key = (size, chunky)
    if key not in _fonts:
        path = _font_path() if chunky else None
        try:
            _fonts[key] = pygame.font.Font(path, size)
        except Exception:
            _fonts[key] = pygame.font.Font(None, size)
    return _fonts[key]


_text_cache = {}


def text(surf, s, pos, size=24, color=WHITE, outline=INK, ow=2, anchor="center", chunky=True, alpha=255):
    """Draw outlined text. anchor: center | topleft | midleft | midright | midtop."""
    key = (str(s), size, color, outline, ow, chunky)
    img = _text_cache.get(key)
    if img is None:
        f = font(size, chunky)
        img = f.render(str(s), True, color)
        if outline is not None and ow > 0:
            o = f.render(str(s), True, outline)
            full = pygame.Surface((img.get_width() + ow * 2, img.get_height() + ow * 2), pygame.SRCALPHA)
            for dx in range(-ow, ow + 1):
                for dy in range(-ow, ow + 1):
                    if dx * dx + dy * dy <= ow * ow + 1:
                        full.blit(o, (dx + ow, dy + ow))
            full.blit(img, (ow, ow))
            img = full
        if len(_text_cache) > 400:  # big outlined titles are slow to build: keep recent ones
            _text_cache.clear()
        _text_cache[key] = img
    if alpha < 255:
        img = img.copy()
        img.set_alpha(alpha)
    r = img.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
    surf.blit(img, r)
    return r


def title_text(surf, s, pos, size=60, alpha=255, scale=1.0, color=WHITE):
    """Big bold white title text with a thick dark outline."""
    sz = int(size * scale)
    text(surf, s, pos, sz, color, INK, max(2, sz // 14), alpha=alpha)


def pill(surf, s, pos, bg, size=13, fg=WHITE, alpha=255):
    f = font(size, False)
    img = f.render(s, True, fg)
    w, h = img.get_width() + 10, img.get_height() + 2
    p = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
    pygame.draw.rect(p, INK, (0, 0, w + 2, h + 2), border_radius=4)
    pygame.draw.rect(p, bg, (1, 1, w, h), border_radius=4)
    p.blit(img, (6, 2))
    if alpha < 255:
        p.set_alpha(alpha)
    r = p.get_rect(center=(int(pos[0]), int(pos[1])))
    surf.blit(p, r)
    return r


def type_color(t, shade=0):
    return COLORS.get(t, COLORS["normal"])[shade]


def hsv(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


# ---------------------------------------------------------------------------- sprites
class Sprites:
    """Loads and caches Pokemon sprites (cropped, scaled, flipped, outlined)."""

    def __init__(self):
        self.raw = {}
        self.cache = {}
        self.missing = None

    def _missing(self):
        if self.missing is None:
            s = pygame.Surface((40, 40), pygame.SRCALPHA)
            pygame.draw.circle(s, (120, 120, 140), (20, 20), 16)
            text(s, "?", (20, 20), 26)
            self.missing = s
        return self.missing

    def base(self, pid, back=False):
        key = (pid, back)
        if key not in self.raw:
            img = None
            if back:
                path = os.path.join(pokedex.SPRITE_DIR, f"back-{pid}.png")
                if not os.path.exists(path):
                    try:
                        data = pokedex.fetch(BACK_URL.format(pid), timeout=10)
                        os.makedirs(pokedex.SPRITE_DIR, exist_ok=True)
                        with open(path, "wb") as f:
                            f.write(data)
                    except Exception:
                        path = None
            else:
                path = pokedex.ensure_sprite(pid)
            if path:
                try:
                    img = _plain_rgba(pygame.image.load(path))
                    r = img.get_bounding_rect()
                    if r.w > 0:
                        img = _plain_rgba(img.subsurface(r))
                except Exception:
                    img = None
            if img is None and back:
                return self.base(pid, False)
            self.raw[key] = img or self._missing()
        return self.raw[key]

    def get(self, pid, height, flip=False, outline=None, back=False, white=0.0, ow=2):
        key = (pid, int(height), flip, outline, back, round(white, 1), ow)
        if key in self.cache:
            return self.cache[key]
        img = self.base(pid, back)
        s = height / max(1, img.get_height())
        size = (max(1, int(img.get_width() * s)), max(1, int(height)))
        img = rescale(img, size)
        if flip:
            img = pygame.transform.flip(img, True, False)
        if white > 0:  # hit flash: brighten toward white, keep the sprite's own transparency
            img = img.copy()
            v = int(255 * white)
            img.fill((v, v, v, 0), special_flags=pygame.BLEND_RGBA_ADD)
        if outline:
            sil = silhouette(img, outline)
            out = pygame.Surface((img.get_width() + ow * 2, img.get_height() + ow * 2), pygame.SRCALPHA)
            for dx, dy in ((-ow, 0), (ow, 0), (0, -ow), (0, ow), (-1, -1), (1, 1), (-1, 1), (1, -1)):
                out.blit(sil, (dx + ow, dy + ow))
            out.blit(img, (ow, ow))
            img = out
        if len(self.cache) > 4000:
            self.cache.clear()
        self.cache[key] = img
        return img


SPRITES = Sprites()


def silhouette(img, color):
    """A flat-colored copy of a sprite with the same transparency (no pygame.mask: it misbehaves on some Macs)."""
    sil = img.copy()
    sil.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)        # black, alpha untouched
    sil.fill((*color, 0), special_flags=pygame.BLEND_RGBA_ADD)            # -> flat color, alpha untouched
    return sil


def _plain_rgba(img):
    """Rebuild a surface as plain 32-bit RGBA (sprites are palette PNGs; avoid palette/pitch edge cases)."""
    w, h = img.get_size()
    return pygame.image.frombytes(pygame.image.tobytes(img, "RGBA"), (w, h), "RGBA")


# ---------------------------------------------------------------------------- arena
def arena_background(seed=7):
    """Grass border, dirt floor with pebble pattern and a stepped rock wall, like the videos."""
    rng = random.Random(seed)
    bg = new_surface((W, H))
    bg.fill((92, 180, 70))
    for _ in range(5000):  # grass texture
        x, y = rng.randrange(W), rng.randrange(H)
        c = rng.choice([(80, 165, 60), (108, 196, 82), (70, 150, 55)])
        pygame.draw.rect(bg, c, (x, y, 3, 2))
    floor = pygame.Rect(36, 52, W - 72, H - 96)
    pygame.draw.rect(bg, (98, 72, 52), floor.inflate(10, 10), border_radius=26)
    pygame.draw.rect(bg, (166, 124, 92), floor, border_radius=22)
    for gy in range(floor.top + 18, floor.bottom - 10, 34):  # pebble rows
        for gx in range(floor.left + 16 + (gy // 34 % 2) * 17, floor.right - 10, 34):
            for _ in range(3):
                ox, oy = rng.randint(-6, 6), rng.randint(-5, 5)
                pygame.draw.ellipse(bg, (148, 108, 80), (gx + ox, gy + oy, rng.randint(4, 8), rng.randint(3, 6)))
    for _ in range(600):
        x, y = rng.randint(floor.left + 6, floor.right - 8), rng.randint(floor.top + 6, floor.bottom - 8)
        pygame.draw.rect(bg, (176, 134, 100), (x, y, 2, 2))
    # stepped wall on the top corners
    wall = (110, 76, 56)
    pygame.draw.rect(bg, wall, (floor.left - 4, floor.top - 6, floor.w + 8, 8), border_radius=3)
    for side in (0, 1):
        x = floor.left - 4 if side == 0 else floor.right - 4
        pygame.draw.rect(bg, wall, (x, floor.top - 6, 8, 160), border_radius=3)
    # grass bushes rim
    for x in range(floor.left, floor.right, 14):
        pygame.draw.circle(bg, (84, 170, 64), (x, floor.bottom + 4), 9)
    return bg


def turn_background(weather=None):
    bg = new_surface((W, H))
    for y in range(H):
        t = y / H
        c = (int(150 + 60 * t), int(205 + 20 * t), int(240 - 40 * t)) if y < 640 else (98, 172, 78)
        pygame.draw.line(bg, c, (0, y), (W, y))
    for _ in range(1200):
        x, y = random.randrange(W), random.randrange(640, H)
        pygame.draw.rect(bg, random.choice([(84, 160, 66), (110, 190, 88)]), (x, y, 3, 2))
    pygame.draw.ellipse(bg, (176, 150, 100), (360, 380, 300, 80))   # foe platform
    pygame.draw.ellipse(bg, (150, 126, 84), (360, 380, 300, 80), 4)
    pygame.draw.ellipse(bg, (176, 150, 100), (40, 690, 360, 100))   # our platform
    pygame.draw.ellipse(bg, (150, 126, 84), (40, 690, 360, 100), 4)
    return bg


# ---------------------------------------------------------------------------- trainer + ball
TRAINER = [
    "....RRRRRR......",
    "...RRRRRRRR.....",
    "..RRWWRRRRRR....",
    "..KKKKKKKKKK....",
    "..KKSSSSSSKK....",
    "..KSSKSSKSSK....",
    "...SSSSSSSS.....",
    "....SSSSSS......",
    "..BBBBWWBBBB....",
    ".BBBBBWWBBBBB...",
    ".SBBBBWWBBBBS...",
    ".SBBBBWWBBBBS...",
    "..BBBBBBBBBB....",
    "..LLLL..LLLL....",
    "..LLLL..LLLL....",
    "..LLL....LLL....",
    ".KKKK....KKKK...",
]
TRAINER_PAL = {"R": (220, 40, 40), "W": (250, 250, 250), "K": (30, 28, 34), "S": (245, 200, 160),
               "B": (50, 90, 200), "L": (40, 50, 90)}
TRAINER_BACK = [row.replace("S", "K") if i < 7 else row for i, row in enumerate(TRAINER)]


def trainer_sprite(scale=4, frame=0, back=False):
    rows = TRAINER_BACK if back else TRAINER
    if frame == 1:
        rows = rows[:13] + ["..LLLL..LLLL....", "...LLL..LLLL....", "...LLL...LLL....", "..KKKK...KKKK..."]
    surf = pygame.Surface((16 * scale, len(rows) * scale), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in TRAINER_PAL:
                pygame.draw.rect(surf, TRAINER_PAL[ch], (x * scale, y * scale, scale, scale))
    return surf


_ball = {}


def ball_sprite(size=24):
    if size not in _ball:
        path = pokedex.ensure_item("poke-ball")
        img = None
        if path:
            try:
                img = pygame.image.load(path).convert_alpha()
                img = _plain_rgba(img.subsurface(img.get_bounding_rect()))
                img = rescale(img, (size, size))
            except Exception:
                img = None
        if img is None:
            img = pygame.Surface((size, size), pygame.SRCALPHA)
            r = size // 2
            pygame.draw.circle(img, (230, 40, 40), (r, r), r - 1)
            pygame.draw.rect(img, (250, 250, 250), (0, r, size, r))
            pygame.draw.circle(img, INK, (r, r), r - 1, 2)
            pygame.draw.line(img, INK, (0, r), (size, r), 2)
            pygame.draw.circle(img, (250, 250, 250), (r, r), max(2, size // 6))
            pygame.draw.circle(img, INK, (r, r), max(2, size // 6), 2)
        _ball[size] = img
    return _ball[size]


def rainbow_ring(surf, center, radius, t, width=6, alpha=255):
    segs = 36
    for i in range(segs):
        a0 = i / segs * math.tau + t * 3
        a1 = (i + 1.2) / segs * math.tau + t * 3
        col = hsv(i / segs + t)
        pts = [(center[0] + math.cos(a) * radius, center[1] + math.sin(a) * radius) for a in (a0, a1)]
        pygame.draw.line(surf, col, pts[0], pts[1], width)


def hp_color(frac):
    if frac > 0.5:
        return (80, 220, 100)
    if frac > 0.2:
        return (245, 200, 50)
    return (235, 70, 60)


def hp_bar(surf, rect, frac, back=(40, 40, 48)):
    x, y, w, h = rect
    pygame.draw.rect(surf, INK, (x - 1, y - 1, w + 2, h + 2), border_radius=3)
    pygame.draw.rect(surf, back, (x, y, w, h), border_radius=3)
    if frac > 0:
        pygame.draw.rect(surf, hp_color(frac), (x, y, max(2, int(w * frac)), h), border_radius=3)
