"""Small immediate-mode-ish widget kit for the menus (all coordinates are canvas pixels, 720x1280)."""
import pygame

from . import gfx
from .gfx import WHITE  # noqa: F401 - re-exported for screens

# Pokedex palette: a red device shell around slate "screens", the big blue lens for focus/selection
SHELL = (200, 40, 58)
SHELL_DARK = (128, 22, 34)
SCREEN = (24, 33, 46)
SCREEN2 = (36, 49, 66)
LCD_LINE = (46, 61, 82)
LENS = (64, 170, 235)
SIGNAL = (246, 201, 69)
TEXT = (238, 242, 246)
MUTED = (140, 156, 176)
PANEL = SCREEN
PANEL2 = SCREEN2
ACCENT = SHELL
ACCENT2 = LENS


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def panel(surf, rect, color=PANEL, radius=14, border=None):
    """A flat screen panel: thin dark rim and a faint highlight along the top edge."""
    r = pygame.Rect(rect)
    pygame.draw.rect(surf, border or _shade(color, 0.55), r.inflate(4, 4), border_radius=radius + 2)
    pygame.draw.rect(surf, color, r, border_radius=radius)
    pygame.draw.line(surf, _shade(color, 1.35), (r.x + radius, r.y + 1), (r.right - radius, r.y + 1), 2)


class Button:
    """A physical key: colored face on a darker lip. Hover lifts the face color; holding the mouse presses it."""

    LIP = 6

    def __init__(self, rect, label, color=PANEL2, size=26, sub=None, enabled=True, tag=None, icon=None):
        self.rect = pygame.Rect(rect)
        self.icon = icon        # a Pokemon id: drawn on the left, text then sits left-aligned beside it
        self.label = label
        self.color = color
        self.size = size
        self.sub = sub
        self.enabled = enabled
        self.tag = tag
        self.hover = False

    def draw(self, surf):
        c = self.color if self.enabled else (48, 56, 68)
        pressed = self.enabled and self.hover and pygame.mouse.get_pressed()[0]
        if self.hover and self.enabled and not pressed:
            c = tuple(min(255, int(v * 1.12) + 8) for v in c)
        face = self.rect.move(0, -self.LIP + (self.LIP - 1 if pressed else 0))
        lip = self.rect.copy()
        pygame.draw.rect(surf, (10, 14, 20), lip.inflate(4, 4), border_radius=14)
        pygame.draw.rect(surf, _shade(c, 0.55), lip, border_radius=12)
        pygame.draw.rect(surf, c, face, border_radius=12)
        pygame.draw.line(surf, _shade(c, 1.3), (face.x + 12, face.y + 2), (face.right - 12, face.y + 2), 2)
        cy = face.centery - (10 if self.sub else 0)
        if self.icon:
            clip = surf.get_clip()
            surf.set_clip(face.inflate(-4, -4))
            img = gfx.SPRITES.get(self.icon, int(face.h * 1.15), flip=True)
            surf.blit(img, img.get_rect(midbottom=(face.x + face.h * 0.62, face.bottom + face.h * 0.12)))
            surf.set_clip(clip)
            x = face.x + face.h * 1.25
            gfx.text(surf, self.label, (x, cy), self.size, TEXT, _shade(c, 0.45), 2, anchor="midleft")
            if self.sub:
                gfx.text(surf, self.sub, (x + 2, cy + self.size * 0.8), 16, _shade(TEXT, 0.92), None, 0,
                         anchor="midleft", chunky=False)
            return
        gfx.text(surf, self.label, (face.centerx, cy), self.size, TEXT if self.enabled else MUTED,
                 _shade(c, 0.45), 2)
        if self.sub:
            gfx.text(surf, self.sub, (face.centerx, cy + self.size * 0.8), 15,
                     _shade(TEXT, 0.92) if self.enabled else MUTED, None, 0, chunky=False)

    def hit(self, pos):
        return self.enabled and self.rect.collidepoint(pos)


class Cycle:
    """A '< value >' selector."""

    def __init__(self, rect, label, options, index=0, fmt=str):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.options = list(options)
        self.index = index
        self.fmt = fmt

    @property
    def value(self):
        return self.options[self.index] if self.options else None

    def set(self, value):
        if value in self.options:
            self.index = self.options.index(value)

    def _left(self):
        if not self.label:
            return self.rect.x + 16
        room = 0.36 if self.rect.w > 300 else 0.5   # narrow selectors give the label a bigger share
        return self.rect.x + min(self.rect.w * room, gfx.font(16).size(self.label)[0] + 40)

    def draw(self, surf):
        panel(surf, self.rect, SCREEN2, 10)
        if self.label:
            gfx.text(surf, self.label, (self.rect.x + 14, self.rect.centery), 16, MUTED, None, 0,
                     anchor="midleft")
        left, right = self._left(), self.rect.right - 20
        box = pygame.Rect(left - 14, self.rect.y + 8, right - left + 28, self.rect.h - 16)
        pygame.draw.rect(surf, SCREEN, box, border_radius=8)
        cy = self.rect.centery
        for x, d in ((left, -1), (right, 1)):  # lens-blue chevrons
            pygame.draw.polygon(surf, LENS, [(x + d * 7, cy), (x - d * 5, cy - 8), (x - d * 5, cy + 8)])
        size = 20
        while size > 12 and gfx.font(size).size(self.fmt(self.value))[0] > right - left - 36:
            size -= 1
        gfx.text(surf, self.fmt(self.value), ((left + right) / 2, cy), size, TEXT, None, 0)

    def click(self, pos):
        if not self.rect.collidepoint(pos) or not self.options:
            return False
        step = -1 if pos[0] < (self._left() + self.rect.right - 20) / 2 else 1
        self.index = (self.index + step) % len(self.options)
        return True


class TextInput:
    def __init__(self, rect, label="", value="", placeholder=""):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.value = value
        self.placeholder = placeholder
        self.focus = False

    def draw(self, surf):
        panel(surf, self.rect, SCREEN if not self.focus else (30, 42, 58), 10,
              border=LENS if self.focus else None)
        if self.label:
            gfx.text(surf, self.label, (self.rect.x, self.rect.y - 16), 16, MUTED, None, 0, anchor="midleft")
        shown = self.value or self.placeholder
        col = WHITE if self.value else (110, 110, 125)
        caret = "|" if self.focus and pygame.time.get_ticks() // 500 % 2 else ""
        gfx.text(surf, shown + (caret if self.value or self.focus else ""), (self.rect.x + 14, self.rect.centery),
                 20, col, anchor="midleft", ow=1, chunky=False)

    def handle(self, ev, pos=None):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and pos:
            self.focus = self.rect.collidepoint(pos)
            return self.focus
        if self.focus and ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
            elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB):
                self.focus = False
            elif ev.key == pygame.K_v and (ev.mod & (pygame.KMOD_META | pygame.KMOD_CTRL)):
                from .clip import paste
                self.value += paste().strip().splitlines()[0] if paste().strip() else ""
            return True
        if self.focus and ev.type == pygame.TEXTINPUT:
            self.value += ev.text
            return True
        return False


class ListView:
    """Scrollable list of rows. rows: list of (key, draw_fn(surf, rect, selected)) or strings."""

    def __init__(self, rect, row_h=56):
        self.rect = pygame.Rect(rect)
        self.row_h = row_h
        self.rows = []
        self.scroll = 0
        self.selected = None

    def set_rows(self, rows):
        self.rows = rows
        self.scroll = min(self.scroll, max(0, len(rows) * self.row_h - self.rect.h))

    def draw(self, surf):
        panel(surf, self.rect, SCREEN, 14)
        clip = surf.get_clip()
        surf.set_clip(self.rect.inflate(-6, -6))
        first = int(self.scroll // self.row_h)
        for i in range(first, min(len(self.rows), first + self.rect.h // self.row_h + 2)):
            key, fn = self.rows[i]
            r = pygame.Rect(self.rect.x + 6, self.rect.y + 4 + i * self.row_h - self.scroll, self.rect.w - 12,
                            self.row_h - 4)
            if key == self.selected:
                pygame.draw.rect(surf, (32, 62, 92), r, border_radius=8)
                pygame.draw.rect(surf, LENS, (r.x, r.y + 6, 4, r.h - 12), border_radius=2)
            else:
                pygame.draw.line(surf, LCD_LINE, (r.x + 10, r.bottom + 1), (r.right - 10, r.bottom + 1), 1)
            fn(surf, r, key == self.selected)
        surf.set_clip(clip)
        total = len(self.rows) * self.row_h
        if total > self.rect.h:
            h = max(30, self.rect.h * self.rect.h / total)
            y = self.rect.y + (self.rect.h - h) * self.scroll / max(1, total - self.rect.h)
            pygame.draw.rect(surf, LCD_LINE, (self.rect.right - 8, y, 4, h), border_radius=2)

    def handle(self, ev, pos):
        if ev.type == pygame.MOUSEWHEEL and pos and self.rect.collidepoint(pos):
            total = len(self.rows) * self.row_h
            self.scroll = max(0, min(max(0, total - self.rect.h), self.scroll - ev.y * self.row_h))
            return None
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.rect.collidepoint(pos):
            i = int((pos[1] - self.rect.y - 4 + self.scroll) // self.row_h)
            if 0 <= i < len(self.rows):
                self.selected = self.rows[i][0]
                return self.selected
        return None


_BG = None


def _lens(surf, x, y, r, t):
    """The Pokedex's big blue lens, softly pulsing."""
    pygame.draw.circle(surf, (20, 24, 32), (x, y), r + 6)
    pygame.draw.circle(surf, (240, 244, 248), (x, y), r + 3)
    pulse = 0.85 + 0.15 * (0.5 + 0.5 * __import__("math").sin(t * 2.2))
    pygame.draw.circle(surf, _shade(LENS, 0.55), (x, y), r)
    pygame.draw.circle(surf, _shade(LENS, pulse), (x, y), int(r * 0.82))
    pygame.draw.circle(surf, _shade(LENS, min(1.4, pulse + 0.35)), (x - r // 4, y - r // 4), int(r * 0.4))
    pygame.draw.circle(surf, (255, 255, 255), (x - r // 3, y - r // 3), max(3, r // 6))


def header(surf, title, sub=None, t=None):
    """Every menu wears the Pokedex shell: red band, big blue lens, three status lights, the notched edge."""
    import time as _time
    t = _time.time() if t is None else t
    w = surf.get_width()
    # screens without a subtitle get a slimmer shell (their content starts higher up)
    low, notch = (104, 146) if sub else (78, 104)
    shell = [(0, 0), (w, 0), (w, low), (w * 0.62, low), (w * 0.55, notch), (0, notch)]
    pygame.draw.polygon(surf, SHELL_DARK, [(x, y + 6) for x, y in shell])
    pygame.draw.polygon(surf, SHELL, shell)
    pygame.draw.lines(surf, _shade(SHELL, 1.25), False, [(0, 2), (w, 2)], 2)
    ly, lr = (66, 34) if sub else (50, 28)
    _lens(surf, 22 + lr + 8, ly, lr, t)
    lights_x = 30 + lr * 2 + 24
    for i, col in enumerate(((235, 70, 70), (246, 201, 69), (90, 210, 110))):
        pygame.draw.circle(surf, (20, 24, 32), (lights_x + i * 24, 26 if not sub else 34), 9)
        pygame.draw.circle(surf, col, (lights_x + i * 24, 26 if not sub else 34), 7)
    gfx.text(surf, title, (lights_x - 2, 62 if sub else 54), 42 if len(title) < 16 else 32, TEXT, SHELL_DARK, 3,
             anchor="midleft")
    if sub:
        gfx.text(surf, sub, (lights_x, 104), 16, (255, 222, 226), None, 0, anchor="midleft", chunky=False)


def menu_background(surf, t=0.0):
    """Slate Pokedex screen with faint LCD scanlines (built once)."""
    global _BG
    size = surf.get_size()
    if _BG is None or _BG.get_size() != size:
        _BG = pygame.Surface(size)
        _BG.fill(SCREEN)
        for y in range(0, size[1], 4):
            pygame.draw.line(_BG, (21, 29, 41), (0, y), (size[0], y))
        for y in range(160, size[1], 48):
            for x in range(24, size[0], 48):
                _BG.set_at((x, y), (40, 54, 72))
    surf.blit(_BG, (0, 0))
