"""Small immediate-mode-ish widget kit for the menus (all coordinates are canvas pixels, 720x1280)."""
import pygame

from . import gfx
from .gfx import INK, WHITE

PANEL = (34, 32, 46)
PANEL2 = (52, 48, 68)
ACCENT = (238, 72, 72)
ACCENT2 = (70, 140, 245)
MUTED = (150, 150, 170)


def panel(surf, rect, color=PANEL, radius=14, border=INK):
    pygame.draw.rect(surf, border, pygame.Rect(rect).inflate(6, 6), border_radius=radius + 3)
    pygame.draw.rect(surf, color, rect, border_radius=radius)


class Button:
    def __init__(self, rect, label, color=PANEL2, size=26, sub=None, enabled=True, tag=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.color = color
        self.size = size
        self.sub = sub
        self.enabled = enabled
        self.tag = tag
        self.hover = False

    def draw(self, surf):
        c = self.color if self.enabled else (60, 60, 66)
        if self.hover and self.enabled:
            c = tuple(min(255, v + 25) for v in c)
        panel(surf, self.rect, c, 12)
        cy = self.rect.centery - (10 if self.sub else 0)
        gfx.text(surf, self.label, (self.rect.centerx, cy), self.size, WHITE if self.enabled else MUTED)
        if self.sub:
            gfx.text(surf, self.sub, (self.rect.centerx, cy + self.size * 0.8), 15, (215, 215, 230), ow=1,
                     chunky=False)

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
        return self.rect.x + (self.rect.w * 0.36 if self.label else 16)

    def draw(self, surf):
        panel(surf, self.rect, PANEL2, 10)
        if self.label:
            gfx.text(surf, self.label, (self.rect.x + 14, self.rect.centery), 16, MUTED, anchor="midleft", ow=1)
        left, right = self._left(), self.rect.right - 20
        gfx.text(surf, "<", (left, self.rect.centery), 26)
        gfx.text(surf, ">", (right, self.rect.centery), 26)
        size = 20
        while size > 12 and gfx.font(size).size(self.fmt(self.value))[0] > right - left - 36:
            size -= 1
        gfx.text(surf, self.fmt(self.value), ((left + right) / 2, self.rect.centery), size)

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
        panel(surf, self.rect, (24, 22, 32) if not self.focus else (40, 36, 56), 10,
              border=gfx.TEAM_COLORS[1] if self.focus else INK)
        if self.label:
            gfx.text(surf, self.label, (self.rect.x, self.rect.y - 16), 16, MUTED, anchor="midleft", ow=1)
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
        panel(surf, self.rect, (26, 24, 34), 12)
        clip = surf.get_clip()
        surf.set_clip(self.rect.inflate(-6, -6))
        first = int(self.scroll // self.row_h)
        for i in range(first, min(len(self.rows), first + self.rect.h // self.row_h + 2)):
            key, fn = self.rows[i]
            r = pygame.Rect(self.rect.x + 6, self.rect.y + 4 + i * self.row_h - self.scroll, self.rect.w - 12,
                            self.row_h - 4)
            if key == self.selected:
                pygame.draw.rect(surf, (70, 64, 96), r, border_radius=8)
            elif i % 2:
                pygame.draw.rect(surf, (32, 30, 42), r, border_radius=8)
            fn(surf, r, key == self.selected)
        surf.set_clip(clip)
        total = len(self.rows) * self.row_h
        if total > self.rect.h:
            h = max(30, self.rect.h * self.rect.h / total)
            y = self.rect.y + (self.rect.h - h) * self.scroll / max(1, total - self.rect.h)
            pygame.draw.rect(surf, (90, 86, 110), (self.rect.right - 7, y, 4, h), border_radius=2)

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


def header(surf, title, sub=None):
    gfx.title_text(surf, title, (gfx.W / 2, 70), 52)
    if sub:
        gfx.text(surf, sub, (gfx.W / 2, 118), 20, MUTED, ow=1, chunky=False)


def menu_background(surf, t=0.0):
    surf.fill((22, 20, 30))
    for i in range(14):
        y = (i * 110 + t * 20) % 1400 - 60
        pygame.draw.circle(surf, (30, 28, 42), (80 + (i * 233) % 600, int(y)), 46, 6)
