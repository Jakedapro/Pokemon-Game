"""GBA-style interface pieces for Adventure mode (480x320 canvas): framed boxes, the typewriter text box,
cursor menus, HP/EXP bars and the controls (arrows + Z/Enter = A, X/Esc = B)."""
import pygame

from . import pixelfont as F
from .audio import AUDIO

W, H = 480, 320
TEXT = (72, 72, 80)
SHADOW = (208, 208, 200)
WHITE = (248, 248, 248)
NAVY = (40, 56, 96)

A_KEYS = (pygame.K_z, pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER)
B_KEYS = (pygame.K_x, pygame.K_ESCAPE, pygame.K_BACKSPACE)
DIR_KEYS = {pygame.K_UP: "up", pygame.K_w: "up", pygame.K_DOWN: "down", pygame.K_s: "down",
            pygame.K_LEFT: "left", pygame.K_a: "left", pygame.K_RIGHT: "right", pygame.K_d: "right"}


def is_a(ev):
    return (ev.type == pygame.KEYDOWN and ev.key in A_KEYS) or (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1)


def is_b(ev):
    return (ev.type == pygame.KEYDOWN and ev.key in B_KEYS) or (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3)


def direction(ev):
    return DIR_KEYS.get(ev.key) if ev.type == pygame.KEYDOWN else None


def _frame_tiles(name):
    """FireRed's window frame tiles (graphics/text_window/<name>.png) at 2x, or None."""
    from . import frlg
    if not frlg.is_ready():
        return None
    key = ("frame", name)
    if key not in _frames:
        fr = frlg.frames(f"graphics/text_window/{name}.png", 8, 8)
        _frames[key] = [pygame.transform.scale_by(t, 2) for t in fr] if fr else None
    return _frames[key]


_frames = {}


def _tile_row(surf, tile, x0, x1, y):
    x = x0
    while x < x1:
        w = min(16, x1 - x)
        surf.blit(tile, (x, y), (0, 0, w, 16))
        x += 16


def _tile_col(surf, tile, x, y0, y1):
    y = y0
    while y < y1:
        h = min(16, y1 - y)
        surf.blit(tile, (x, y), (0, 0, 16, h))
        y += 16


def std_frame(surf, r, fill=None):
    """FireRed's standard window (START menu, YES/NO, shop...) drawn over rect r. False if unavailable."""
    t = _frame_tiles("std")
    if not t or len(t) < 9:
        return False
    surf.fill(fill or t[4].get_at((8, 8)), r.inflate(-16, -16))
    _tile_row(surf, t[1], r.x + 16, r.right - 16, r.y)
    _tile_row(surf, t[7], r.x + 16, r.right - 16, r.bottom - 16)
    _tile_col(surf, t[3], r.x, r.y + 16, r.bottom - 16)
    _tile_col(surf, t[5], r.right - 16, r.y + 16, r.bottom - 16)
    surf.blit(t[0], (r.x, r.y))
    surf.blit(t[2], (r.right - 16, r.y))
    surf.blit(t[6], (r.x, r.bottom - 16))
    surf.blit(t[8], (r.right - 16, r.bottom - 16))
    return True


def dialogue_frame(surf, left, top, width, height=4):
    """FireRed's dialogue frame (WindowFunc_DrawDialogueFrame) around a window of width x height tiles whose
    top-left tile is (left, top) - in GBA tiles; drawn at 2x. False if unavailable."""
    t = _frame_tiles("menu_message")
    if not t or len(t) < 14:
        return False
    vf = {i: pygame.transform.flip(t[i], False, True) for i in (0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13)}

    def put(tile, tx, ty, w=1):
        for k in range(w):
            surf.blit(tile, ((tx + k) * 16, ty * 16))
    surf.fill(t[7].get_at((8, 8)), (left * 16, top * 16, width * 16, height * 16))
    put(t[0], left - 2, top - 1), put(t[1], left - 1, top - 1), put(t[2], left, top - 1, width)
    put(t[3], left + width, top - 1), put(t[4], left + width + 1, top - 1)
    for row, (a, b, c, d) in ((0, (5, 6, 8, 9)), (1, (10, 11, 12, 13))):
        put(t[a], left - 2, top + row), put(t[b], left - 1, top + row)
        put(t[c], left + width, top + row), put(t[d], left + width + 1, top + row)
    for row, (a, b, c, d) in ((2, (10, 11, 12, 13)), (3, (5, 6, 8, 9))):
        put(vf[a], left - 2, top + row), put(vf[b], left - 1, top + row)
        put(vf[c], left + width, top + row), put(vf[d], left + width + 1, top + row)
    put(vf[0], left - 2, top + 4), put(vf[1], left - 1, top + 4), put(vf[2], left, top + 4, width)
    put(vf[3], left + width, top + 4), put(vf[4], left + width + 1, top + 4)
    return True


def box(surf, rect, fill=WHITE, border=(96, 160, 200), radius=6):
    """A framed window: dark outline, coloured border, light inner line, white fill."""
    r = pygame.Rect(rect)
    if std_frame(surf, r, None if fill == WHITE else fill):
        return r.inflate(-12, -12)
    pygame.draw.rect(surf, (48, 48, 56), r, border_radius=radius + 2)
    pygame.draw.rect(surf, border, r.inflate(-4, -4), border_radius=radius)
    pygame.draw.rect(surf, (232, 240, 248), r.inflate(-8, -8), border_radius=radius - 2)
    pygame.draw.rect(surf, fill, r.inflate(-12, -12), border_radius=max(1, radius - 3))
    return r.inflate(-12, -12)


def cursor(surf, pos, color=TEXT):
    F.draw(surf, "▶", pos, color, SHADOW)


class TextBox:
    """The bottom message box: two lines, types out, waits for A (with the little bouncing arrow)."""

    def __init__(self, lines=None, on_done=None, auto=None, speaker=""):
        self.pages = []
        self.on_done = on_done
        self.auto = auto          # seconds to wait before moving on by itself (battles); None = wait for A
        self.speaker = speaker
        self.page = 0
        self.shown = 0.0
        self.wait = 0.0
        for ln in (lines or []):
            self.add(ln)

    def add(self, text):
        rows = F.wrap(text, W - 100)
        for i in range(0, len(rows), 2):
            self.pages.append(rows[i:i + 2])

    @property
    def done(self):
        return self.page >= len(self.pages)

    def _len(self):
        return sum(len(r) for r in self.pages[self.page]) if not self.done else 0

    def update(self, dt):
        if self.done:
            return
        self.shown = min(self._len(), self.shown + dt * 60)
        if self.shown >= self._len():
            self.wait += dt
            if self.auto is not None and self.wait >= self.auto:
                self.next()

    def next(self):
        if self.done:
            return True
        if self.shown < self._len():
            self.shown = self._len()
            return False
        self.page += 1
        self.shown = 0
        self.wait = 0.0
        if self.done:
            if self.on_done:
                cb, self.on_done = self.on_done, None
                cb()
            return True
        return False

    def handle(self, ev):
        if is_a(ev) or is_b(ev):
            AUDIO.play("click", 0.3)
            return self.next()
        return False

    def draw(self, surf, t, rect=(24, 236, 432, 80), dark=False, bare=False, line_h=26):
        # FireRed: tiles (2,15) 26x4 + frame
        if self.done:
            return
        if bare:   # just the text: the box is already drawn (the real battle message box)
            inner = pygame.Rect(rect)
            col, sh = (WHITE, (104, 88, 112)) if dark else (TEXT, SHADOW)
        elif not dark and tuple(rect) == (24, 236, 432, 80) and dialogue_frame(surf, 2, 15, 26):
            inner = pygame.Rect(22, 234, 416, 64)    # FireRed: text window at tiles (2, 15), 26 x 4
            col, sh = TEXT, SHADOW
            line_h = 32
        elif dark:
            r = pygame.Rect(rect)
            pygame.draw.rect(surf, (48, 48, 56), r, border_radius=6)
            pygame.draw.rect(surf, (216, 176, 96), r.inflate(-4, -4), border_radius=5)
            inner = r.inflate(-10, -10)
            pygame.draw.rect(surf, NAVY, inner, border_radius=4)
            col, sh = WHITE, (96, 104, 128)
        else:
            inner = box(surf, rect)
            col, sh = TEXT, SHADOW
        left = self.shown
        for i, row in enumerate(self.pages[self.page]):
            part = row[:max(0, int(left))]
            left -= len(row)
            F.draw(surf, part, (inner.x + 10, inner.y + 6 + i * line_h), col, sh)
        if self.shown >= self._len() and self.auto is None and int(t * 3) % 2 == 0:
            F.draw(surf, "▼", (inner.right - 22, inner.bottom - 18), (224, 64, 64), None)


class Menu:
    """A list or grid of options with the ▶ cursor. Returns the chosen key from handle(), or 'back'."""

    def __init__(self, options, cols=1, index=0):
        self.options = list(options)    # (key, label) or (key, label, enabled)
        self.cols = cols
        self.index = index
        self.rects = []

    def _enabled(self, i):
        o = self.options[i]
        return len(o) < 3 or o[2]

    def handle(self, ev, pos=None):
        d = direction(ev)
        n = len(self.options)
        if d and n:
            step = {"up": -self.cols, "down": self.cols, "left": -1, "right": 1}[d]
            if self.cols == 1 and d in ("left", "right"):
                return None
            j = self.index + step
            if 0 <= j < n:
                self.index = j
                AUDIO.play("click", 0.25)
            return None
        if ev.type == pygame.MOUSEMOTION and self.rects and pos:
            for i, r in enumerate(self.rects):
                if r.collidepoint(pos):
                    self.index = i
            return None
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if not (self.rects and pos):
                return None
            for i, r in enumerate(self.rects):
                if r.collidepoint(pos):
                    self.index = i
                    break
            else:
                return None
        if is_a(ev) and n:
            if self._enabled(self.index):
                AUDIO.play("select", 0.5)
                return self.options[self.index][0]
            AUDIO.play("miss", 0.4)
            return None
        if is_b(ev):
            AUDIO.play("click", 0.3)
            return "back"
        return None

    def draw(self, surf, rect, row_h=26, col_w=None, border=(96, 160, 200), fill=WHITE, bare=False):
        inner = pygame.Rect(rect) if bare else box(surf, rect, fill, border)
        cw = col_w or (inner.w - 8) // self.cols
        self.rects = []
        for i, o in enumerate(self.options):
            c, r = i % self.cols, i // self.cols
            x, y = inner.x + 22 + c * cw, inner.y + 6 + r * row_h
            self.rects.append(pygame.Rect(x - 20, y - 2, cw, row_h))
            col = TEXT if self._enabled(i) else (168, 168, 168)
            F.draw(surf, o[1], (x, y), col, SHADOW)
            if i == self.index:
                cursor(surf, (x - 16, y))
        return inner


def hp_color(frac):
    return (88, 208, 128) if frac > 0.5 else (248, 192, 56) if frac > 0.2 else (232, 72, 64)


def hp_bar(surf, x, y, w, frac, label=True):
    """'HP' tag + the bar, like the handhelds."""
    if label:
        pygame.draw.rect(surf, (72, 64, 64), (x, y, 26, 10), border_radius=3)
        F.draw(surf, "HP", (x + 4, y - 2), (248, 200, 64), None, scale=1)
        x += 24
    pygame.draw.rect(surf, (72, 64, 64), (x, y, w, 10), border_radius=3)
    pygame.draw.rect(surf, (248, 248, 248), (x + 2, y + 2, w - 4, 6))
    fw = int((w - 4) * max(0.0, min(1.0, frac)))
    if fw > 0:
        pygame.draw.rect(surf, hp_color(frac), (x + 2, y + 2, fw, 6))
        pygame.draw.line(surf, tuple(min(255, c + 40) for c in hp_color(frac)), (x + 2, y + 2), (x + 1 + fw, y + 2))


def exp_bar(surf, x, y, w, frac):
    pygame.draw.rect(surf, (72, 64, 64), (x, y, w, 6))
    fw = int((w - 2) * max(0.0, min(1.0, frac)))
    if fw:
        pygame.draw.rect(surf, (64, 168, 248), (x + 1, y + 1, fw, 4))


def ball(surf, center, r=7, open_k=0.0):
    x, y = center
    pygame.draw.circle(surf, (40, 40, 48), (x, y), r + 1)
    pygame.draw.circle(surf, (248, 248, 248), (x, y), r)
    pygame.draw.rect(surf, (232, 64, 56), (x - r, y - r - int(open_k * 6), 2 * r + 1, r))
    pygame.draw.line(surf, (40, 40, 48), (x - r, y), (x + r, y), 2)
    pygame.draw.circle(surf, (40, 40, 48), (x, y), 3)
    pygame.draw.circle(surf, (248, 248, 248), (x, y), 2)


def fade(surf, k, color=(0, 0, 0)):
    if k <= 0:
        return
    s = pygame.Surface((W, H))
    s.fill(color)
    s.set_alpha(int(255 * min(1.0, k)))
    surf.blit(s, (0, 0))
