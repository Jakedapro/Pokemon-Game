"""Cutscenes for showcases: the battle pauses, black bars slide in, the camera pushes in on the star, a big
portrait card and title slam in, then flash + shake and the action happens."""
import math
import random

import pygame

from . import gfx
from .audio import AUDIO
from .gfx import H, INK, SPRITES, W, WHITE


def _ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


class Cutscene:
    """kind: 'card' (portrait + title), 'vs' (two portraits), 'banner' (title only).
    action() runs once at `action_at` (fraction of the duration) - e.g. spawning Arceus."""

    def __init__(self, kind, duration, focus=None, zoom=1.7, title="", subtitle="", color=(255, 255, 255),
                 portrait=None, portrait2=None, action=None, action_at=0.55, cry=None, sound="select"):
        self.kind = kind
        self.duration = duration
        self.focus = focus
        self.zoom = zoom
        self.title = title
        self.subtitle = subtitle
        self.color = color
        self.portrait = portrait
        self.portrait2 = portrait2
        self.action = action
        self.action_at = action_at
        self.cry = cry
        self.sound = sound
        self.t = 0.0
        self.fired = False
        self.flash = 0.0
        self.rng = random.Random(7)

    @property
    def done(self):
        return self.t >= self.duration

    def update(self, dt, renderer):
        if self.t == 0 and self.sound:
            AUDIO.play(self.sound)
        self.t += dt
        if self.focus:
            renderer.cam_target = (self.focus[0], self.focus[1], self.zoom)
        if not self.fired and self.t >= self.duration * self.action_at:
            self.fired = True
            self.flash = 0.35
            renderer.shake = max(renderer.shake, 0.6)
            AUDIO.play("boom", 0.8)
            if self.cry:
                AUDIO.cry(self.cry, 1.0)
            if self.action:
                self.action()
        self.flash = max(0.0, self.flash - dt)

    # ------------------------------------------------------------------ drawing
    def draw(self, surf):
        d, t = self.duration, self.t
        k = _ease(t / 0.35) * _ease((d - t) / 0.35)
        # color wash + speed lines
        wash = pygame.Surface((W, H), pygame.SRCALPHA)
        wash.fill((*self.color, int(55 * k)))
        surf.blit(wash, (0, 0))
        if k > 0.2:
            cx, cy = W / 2, H / 2
            for i in range(28):
                a = self.rng.random() * math.tau
                r0 = 260 + self.rng.random() * 120
                r1 = r0 + 300 + self.rng.random() * 400
                pygame.draw.line(surf, (255, 255, 255), (cx + math.cos(a) * r0, cy + math.sin(a) * r0),
                                 (cx + math.cos(a) * r1, cy + math.sin(a) * r1), 2)
        # letterbox
        bar = int(130 * k)
        pygame.draw.rect(surf, (0, 0, 0), (0, 0, W, bar))
        pygame.draw.rect(surf, (0, 0, 0), (0, H - bar, W, bar))
        if self.kind == "vs":
            self._draw_vs(surf, t, k)
        elif self.kind == "card":
            self._draw_card(surf, t, k)
        else:
            self._draw_titles(surf, t, k, H * 0.45)
        if self.flash > 0:
            f = pygame.Surface((W, H), pygame.SRCALPHA)
            f.fill((255, 255, 255, int(255 * self.flash / 0.35)))
            surf.blit(f, (0, 0))

    def _draw_titles(self, surf, t, k, y):
        if t > 0.25:
            pop = _ease((t - 0.25) / 0.25)
            gfx.title_text(surf, self.title, (W / 2, y), 64, scale=0.6 + 0.4 * pop, alpha=int(255 * k))
        if self.subtitle and t > 0.6:
            n = int(len(self.subtitle) * min(1.0, (t - 0.6) / 0.6))
            gfx.text(surf, self.subtitle[:n], (W / 2, y + 62), 26, self.color, INK, 3, alpha=int(255 * k))

    def _band(self, surf, y, h, offset, color):
        pts = [(offset - 80, y + h), (offset + W + 80, y + h), (offset + W + 160, y), (offset, y)]
        pygame.draw.polygon(surf, INK, [(px, py + 6) for px, py in pts])
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.polygon(surf, WHITE, pts, 4)

    def _draw_card(self, surf, t, k):
        slide = (1 - _ease(t / 0.45)) * -W
        y, h = 470, 300
        self._band(surf, y, h, slide, tuple(int(c * 0.55) for c in self.color))
        if self.portrait:
            img = SPRITES.get(self.portrait, 300)
            surf.blit(img, img.get_rect(midbottom=(W * 0.3 + slide, y + h + 20)))
        if t > 0.3:
            pop = _ease((t - 0.3) / 0.3)
            size = min(46, int(46 * 16 / max(16, len(self.title))))
            gfx.title_text(surf, self.title, (W * 0.62 - slide * 0.2, y + 110), size, scale=0.5 + 0.5 * pop,
                           alpha=int(255 * k))
        if self.subtitle and t > 0.7:
            n = int(len(self.subtitle) * min(1.0, (t - 0.7) / 0.5))
            gfx.text(surf, self.subtitle[:n], (W * 0.62, y + 180), 22, WHITE, INK, 3, alpha=int(255 * k))

    def _draw_vs(self, surf, t, k):
        a = _ease(t / 0.45)
        for i, pid in enumerate((self.portrait, self.portrait2)):
            if not pid:
                continue
            x = (W * 0.27 - (1 - a) * W) if i == 0 else (W * 0.73 + (1 - a) * W)
            y = 520 if i == 0 else 800
            band_col = gfx.TEAM_COLORS[i]
            self._band(surf, y - 120, 200, (-(1 - a) * W) if i == 0 else ((1 - a) * W), band_col)
            img = SPRITES.get(pid, 260, flip=i == 0)
            surf.blit(img, img.get_rect(midbottom=(x, y + 90)))
        if t > 0.45:
            pop = _ease((t - 0.45) / 0.25)
            gfx.title_text(surf, "VS", (W / 2, 640), 130, scale=2.2 - 1.2 * pop, alpha=int(255 * k))
        gfx.title_text(surf, self.title, (W / 2, 250), 54, alpha=int(255 * k))
