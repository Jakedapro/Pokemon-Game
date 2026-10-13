"""Cutscenes for showcases: the battle pauses, black bars slide in, the camera pushes in on the star, a big
portrait card and title slam in, then flash + shake and the action happens.

The "aura" look: the portrait gets a pulsing glow in the event's color, aura flames rise off it, energy rings
burst out when the action fires, lightning crackles around it and the title glows."""
import math
import random

import pygame

from . import gfx
from .audio import AUDIO
from .gfx import H, INK, SPRITES, W, WHITE


_VIGNETTE = None


def _vignette():
    """Dark edges fading smoothly to a clear middle (built once). Filled ellipses written outside-in: each one
    replaces the pixels inside it, so the alpha steps down smoothly toward the center."""
    global _VIGNETTE
    if _VIGNETTE is None:
        v = pygame.Surface((W, H), pygame.SRCALPHA)
        v.fill((0, 0, 0, 210))
        steps = 64
        for i in range(steps):
            k = i / (steps - 1)                      # 0 = outer edge, 1 = center
            a = int(210 * (1 - k) ** 1.8)
            rw, rh = W * (1.5 - 1.0 * k), H * (1.2 - 0.8 * k)
            pygame.draw.ellipse(v, (0, 0, 0, a), (W / 2 - rw / 2, H / 2 - rh / 2, rw, rh))
        _VIGNETTE = v
    return _VIGNETTE


def _lighter(c, k=0.55):
    return tuple(int(v + (255 - v) * k) for v in c)


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
        self.fx = random.Random()
        self.parts = []    # aura flames: [x, y, vx, vy, life, max_life, size, color]
        self.rings = []    # [x, y, radius, life]
        self.bolts = []    # [points, life]
        self.anchors = []  # where the portraits are (screen coords) this frame
        self._glow = {}

    @property
    def done(self):
        return self.t >= self.duration

    def update(self, dt, renderer):
        if self.t == 0 and self.sound:
            AUDIO.play(self.sound)
        self.t += dt
        if self.focus:
            renderer.cam_target = (self.focus[0], self.focus[1], self.zoom)
        self._update_aura(dt)
        if not self.fired and self.t >= self.duration * self.action_at:
            self.fired = True
            self.flash = 0.35
            for ax, ay, _, col in self.anchors:
                for i in range(3):
                    self.rings.append([ax, ay, 20 + i * 40, 0.8 + i * 0.15, col])
                self._burst(ax, ay, 60, col)
            renderer.shake = max(renderer.shake, 0.6)
            AUDIO.play("boom", 0.8)
            if self.cry:
                AUDIO.cry(self.cry, 1.0)
            if self.action:
                self.action()
        self.flash = max(0.0, self.flash - dt)

    # ------------------------------------------------------------------ aura
    def _burst(self, x, y, n, color):
        for _ in range(n):
            a = self.fx.uniform(0, math.tau)
            sp = self.fx.uniform(150, 520)
            life = self.fx.uniform(0.4, 0.9)
            self.parts.append([x, y, math.cos(a) * sp, math.sin(a) * sp, life, life, self.fx.uniform(4, 10),
                               _lighter(color, self.fx.uniform(0.2, 0.9))])

    def _update_aura(self, dt):
        live = self.duration - 0.3 > self.t > 0.2
        for ax, ay, half_w, col in self.anchors:
            if live:  # aura flames rise off the Pokemon
                for _ in range(int(90 * dt) + (1 if self.fx.random() < (90 * dt) % 1 else 0)):
                    life = self.fx.uniform(0.5, 1.1)
                    self.parts.append([ax + self.fx.uniform(-half_w, half_w), ay - self.fx.uniform(0, 30),
                                       self.fx.uniform(-20, 20), -self.fx.uniform(160, 340), life, life,
                                       self.fx.uniform(5, 13), _lighter(col, self.fx.uniform(0.0, 0.8))])
            if live and self.fx.random() < 6 * dt:  # crackling lightning
                x, y = ax + self.fx.uniform(-half_w, half_w), ay - self.fx.uniform(60, 2.4 * half_w)
                pts = [(x, y)]
                for _ in range(6):
                    x += self.fx.uniform(-28, 28)
                    y += self.fx.uniform(-30, 30)
                    pts.append((x, y))
                self.bolts.append([pts, 0.12, col])
        if live and self.anchors and int(self.t / 0.55) != int((self.t - dt) / 0.55):
            for ax, ay, hw, col in self.anchors:
                self.rings.append([ax, ay - hw, 30, 0.7, col])
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[2] += math.sin(p[1] * 0.05) * 40 * dt
            p[4] -= dt
        self.parts = [p for p in self.parts if p[4] > 0]
        for r in self.rings:
            r[2] += 520 * dt
            r[3] -= dt
        self.rings = [r for r in self.rings if r[3] > 0]
        for b in self.bolts:
            b[1] -= dt
        self.bolts = [b for b in self.bolts if b[1] > 0]

    def _glow_layers(self, pid, height, flip, color):
        key = (pid, height, flip, color)
        if key not in self._glow:
            img = SPRITES.get(pid, height, flip=flip)
            sil = gfx.silhouette(img, _lighter(color, 0.35))
            layers = []
            for sc, a in ((1.22, 50), (1.12, 95), (1.05, 160)):
                g = gfx.rescale(sil, (img.get_width() * sc, img.get_height() * sc))
                g.set_alpha(a)
                layers.append(g)
            self._glow[key] = (img, layers)
        return self._glow[key]

    def _draw_glowing(self, surf, pid, height, midbottom, flip=False, color=None):
        """Portrait with a pulsing aura glow behind it; records where it is for flames/rings."""
        color = color or self.color
        img, layers = self._glow_layers(pid, height, flip, color)
        x, y = midbottom
        y += math.sin(self.t * 3.0) * 6  # float
        pulse = 1 + 0.5 * math.sin(self.t * 9)
        for i, g in enumerate(layers):
            jx = self.fx.uniform(-3, 3) * pulse
            jy = self.fx.uniform(-3, 3) * pulse
            r = g.get_rect(midbottom=(x + jx, y + g.get_height() * 0.04 * (len(layers) - i) + jy))
            surf.blit(g, r)
        surf.blit(img, img.get_rect(midbottom=(x, y)))
        self.anchors.append((x, y - 10, img.get_width() * 0.38, color))

    def _draw_aura_fx(self, surf, k):
        if k <= 0:
            return
        layer = pygame.Surface((W, H), pygame.SRCALPHA)
        for x, y, r, life, col in self.rings:
            a = int(220 * min(1.0, life / 0.5) * k)
            pygame.draw.circle(layer, (*_lighter(col, 0.5), a), (int(x), int(y)), int(r),
                               max(2, int(10 * life)))
        for p in self.parts:
            f = p[4] / p[5]
            sz = max(1, int(p[6] * (0.4 + 0.6 * f)))
            a = int(230 * f * k)
            pygame.draw.ellipse(layer, (*p[7], a), (p[0] - sz / 2, p[1] - sz * 1.6, sz, sz * 3.2))
        for pts, life, col in self.bolts:
            pygame.draw.lines(layer, (*_lighter(col, 0.4), int(255 * k)), False, pts, 5)
            pygame.draw.lines(layer, (255, 255, 255, int(255 * k)), False, pts, 2)
        surf.blit(layer, (0, 0))

    def _glow_title(self, surf, s, pos, size, scale, alpha):
        sz = int(size * scale)
        glow = int(alpha * (0.45 + 0.25 * math.sin(self.t * 10)))
        gfx.text(surf, s, pos, sz, _lighter(self.color, 0.3), _lighter(self.color, 0.1), min(9, max(5, sz // 6)),
                 alpha=glow)
        gfx.title_text(surf, s, pos, size, scale=scale, alpha=alpha)

    # ------------------------------------------------------------------ drawing
    def draw(self, surf):
        d, t = self.duration, self.t
        k = _ease(t / 0.35) * _ease((d - t) / 0.35)
        self.anchors = []
        # darken + color wash + vignette, then speed lines
        wash = pygame.Surface((W, H), pygame.SRCALPHA)
        wash.fill((*(int(c * 0.25) for c in self.color), int(150 * k)))
        surf.blit(wash, (0, 0))
        vig = _vignette()
        vig.set_alpha(int(255 * k))
        surf.blit(vig, (0, 0))
        if k > 0.2:
            cx, cy = W / 2, H / 2
            for i in range(28):
                a = self.rng.random() * math.tau
                r0 = 260 + self.rng.random() * 120
                r1 = r0 + 300 + self.rng.random() * 400
                pygame.draw.line(surf, _lighter(self.color, 0.6), (cx + math.cos(a) * r0, cy + math.sin(a) * r0),
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
            self._glow_title(surf, self.title, (W / 2, y), 64, 0.6 + 0.4 * pop, int(255 * k))
        if self.subtitle and t > 0.6:
            n = int(len(self.subtitle) * min(1.0, (t - 0.6) / 0.6))
            gfx.text(surf, self.subtitle[:n], (W / 2, y + 62), 26, self.color, INK, 3, alpha=int(255 * k))

    def _band(self, surf, y, h, offset, color):
        pts = [(offset - 80, y + h), (offset + W + 80, y + h), (offset + W + 160, y), (offset, y)]
        pygame.draw.polygon(surf, INK, [(px, py + 6) for px, py in pts])
        pygame.draw.polygon(surf, (18, 14, 26), pts)
        # energy streaks across the band in the event color
        for i in range(5):
            yy = y + 30 + i * (h - 60) / 4
            off = (self.t * (500 + i * 90) + i * 170) % (W + 300) - 150
            pygame.draw.line(surf, tuple(int(c * 0.6) for c in color), (offset + off - 120, yy), (offset + off, yy), 3)
        pygame.draw.polygon(surf, _lighter(color, 0.3), pts, 5)
        pygame.draw.polygon(surf, WHITE, pts, 2)

    def _draw_card(self, surf, t, k):
        slide = (1 - _ease(t / 0.45)) * -W
        y, h = 470, 300
        self._band(surf, y, h, slide, self.color)
        if self.portrait:
            self._draw_glowing(surf, self.portrait, 300, (W * 0.3 + slide, y + h + 20))
        self._draw_aura_fx(surf, k)
        if t > 0.3:
            pop = _ease((t - 0.3) / 0.3)
            size = min(46, int(46 * 16 / max(16, len(self.title))))
            self._glow_title(surf, self.title, (W * 0.62 - slide * 0.2, y + 110), size, 0.5 + 0.5 * pop,
                             int(255 * k))
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
            self._draw_glowing(surf, pid, 260, (x, y + 90), flip=i == 0, color=band_col)
        self._draw_aura_fx(surf, k)
        if t > 0.45:
            pop = _ease((t - 0.45) / 0.25)
            self._glow_title(surf, "VS", (W / 2, 640), 130, 2.2 - 1.2 * pop, int(255 * k))
        self._glow_title(surf, self.title, (W / 2, 250), 54, 1.0, int(255 * k))


# the 18 plate colors around Arceus' Judgment wheel
PLATE_TYPES = ["normal", "fire", "water", "electric", "grass", "ice", "fighting", "poison", "ground", "flying",
               "psychic", "bug", "rock", "ghost", "dragon", "dark", "steel", "fairy"]


class Descent(Cutscene):
    """Arceus floats down from the sky through god rays, its Judgment wheel turning behind it, cries out, then
    drops legendaries into the arena in pillars of light one by one, and rises back up and leaves.

    drops: [(pokemon_id, name, (world_x, world_y))]; on_drop(i) spawns drop i in the battle."""

    DOWN, CRY, FIRST, GAP = 2.4, 2.6, 3.2, 1.0

    def __init__(self, arceus_id, drops, group_title, center, on_drop):
        self.leave = self.FIRST + len(drops) * self.GAP + 0.6
        super().__init__("descent", self.leave + 1.8, focus=center, zoom=1.12, title="ARCEUS DESCENDS",
                         subtitle=f"AND BRINGS {group_title}!", color=(255, 205, 90), sound=None)
        self.arceus = arceus_id
        self.drops = drops
        self.on_drop = on_drop
        self.dropped = set()
        self.renderer = None

    def update(self, dt, renderer):
        self.renderer = renderer
        if self.t == 0:
            AUDIO.play("beam", 0.9)
        prev, self.t = self.t, self.t + dt
        renderer.cam_target = (self.focus[0], self.focus[1], self.zoom)
        self._update_aura(dt)
        if prev < self.CRY <= self.t:  # Arceus arrives: cry, flash, shockwave
            self.flash = 0.35
            renderer.shake = max(renderer.shake, 0.8)
            AUDIO.play("boom", 0.9)
            AUDIO.cry(self.arceus, 1.0)
            for ax, ay, _, col in self.anchors[:1]:
                for i in range(4):
                    self.rings.append([ax, ay - 60, 20 + i * 50, 0.9 + i * 0.12, col])
                self._burst(ax, ay - 60, 80, col)
        for i, (pid, _name, _pos) in enumerate(self.drops):
            at = self.FIRST + i * self.GAP
            if prev < at <= self.t and i not in self.dropped:
                self.dropped.add(i)
                self.on_drop(i)
                self.flash = 0.2
                renderer.shake = max(renderer.shake, 0.5)
                AUDIO.play("boom", 0.8)
                AUDIO.cry(pid, 0.9)
                sx, sy = self._screen(i)
                self.rings.append([sx, sy, 20, 0.8, (255, 240, 180)])
                self._burst(sx, sy, 40, (255, 225, 140))
        self.flash = max(0.0, self.flash - dt)

    def _screen(self, i):
        x, y = self.drops[i][2]
        return self.renderer.world_to_screen(x, y) if self.renderer else (x, y)

    def _arceus_y(self):
        t = self.t
        top, rest = -260, H * 0.37
        if t < self.DOWN:
            return top + (rest - top) * _ease(t / self.DOWN)
        if t < self.leave:
            return rest
        return rest + (top - 140 - rest) * min(1.0, ((t - self.leave) / 1.2) ** 2)

    def draw(self, surf):
        d, t = self.duration, self.t
        k = _ease(t / 0.5) * _ease((d - t) / 0.5)
        self.anchors = []
        # the sky darkens
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((14, 10, 30, int(150 * k)))
        surf.blit(shade, (0, 0))
        vig = _vignette()
        vig.set_alpha(int(200 * k))
        surf.blit(vig, (0, 0))
        # god rays fanning down from above
        ay = self._arceus_y()
        rays = pygame.Surface((W, H), pygame.SRCALPHA)
        for i in range(9):
            a = -0.9 + i * 0.225 + math.sin(t * 0.7 + i) * 0.05
            spread = 0.05 + 0.02 * math.sin(t * 2 + i * 1.7)
            pts = [(W / 2, -80), (W / 2 + math.sin(a - spread) * 1800, -80 + math.cos(a - spread) * 1800),
                   (W / 2 + math.sin(a + spread) * 1800, -80 + math.cos(a + spread) * 1800)]
            pygame.draw.polygon(rays, (255, 230, 150, int(38 * k)), pts)
        surf.blit(rays, (0, 0))
        # pillars of light where the legendaries land
        for i in range(len(self.drops)):
            at = self.FIRST + i * self.GAP
            p = (t - (at - 0.35)) / 1.1
            if 0 <= p <= 1:
                sx, sy = self._screen(i)
                wdt = 90 * (1 - p) ** 0.5 if p > 0.32 else 90 * (p / 0.32)
                beam = pygame.Surface((W, H), pygame.SRCALPHA)
                pygame.draw.rect(beam, (255, 235, 170, int(120 * k)), (sx - wdt / 2, 0, wdt, sy))
                pygame.draw.rect(beam, (255, 255, 255, int(220 * k)), (sx - wdt / 6, 0, wdt / 3, sy))
                pygame.draw.ellipse(beam, (255, 240, 190, int(160 * k)), (sx - wdt, sy - wdt / 4, wdt * 2, wdt / 2))
                surf.blit(beam, (0, 0))
            if at <= t < at + 1.6:  # name pops up over the new arrival
                sx, sy = self._screen(i)
                pop = _ease((t - at) / 0.25)
                fade = int(255 * min(1.0, (at + 1.6 - t) / 0.4) * k)
                self._glow_title(surf, self.drops[i][1].upper(), (sx, sy - 120), 34, 0.6 + 0.4 * pop, fade)
        # the Judgment wheel behind Arceus
        if ay > -200:
            cx, cy = W / 2, ay - 120
            rad = 170
            ring = pygame.Surface((W, H), pygame.SRCALPHA)
            pygame.draw.circle(ring, (255, 220, 120, int(150 * k)), (int(cx), int(cy)), rad, 6)
            pygame.draw.circle(ring, (255, 245, 210, int(90 * k)), (int(cx), int(cy)), rad - 18, 2)
            for j, typ in enumerate(PLATE_TYPES):
                a = j / len(PLATE_TYPES) * math.tau + t * 0.8
                px, py = cx + math.cos(a) * rad, cy + math.sin(a) * rad
                pygame.draw.circle(ring, (*gfx.type_color(typ, 0), int(255 * k)), (int(px), int(py)), 11)
                pygame.draw.circle(ring, (255, 255, 255, int(255 * k)), (int(px), int(py)), 11, 2)
            surf.blit(ring, (0, 0))
            self._draw_glowing(surf, self.arceus, 290, (W / 2, ay + 30))
        # the new arrivals stand in the light, glowing, until the scene ends
        for i, (pid, _name, _pos) in enumerate(self.drops):
            if t >= self.FIRST + i * self.GAP:
                sx, sy = self._screen(i)
                self._draw_glowing(surf, pid, 120, (sx, sy + 30), color=(255, 235, 170))
        self._draw_aura_fx(surf, k)
        # letterbox + titles
        bar = int(110 * k)
        pygame.draw.rect(surf, (0, 0, 0), (0, 0, W, bar))
        pygame.draw.rect(surf, (0, 0, 0), (0, H - bar, W, bar))
        if 0.8 < t < self.leave + 0.8:
            pop = _ease((t - 0.8) / 0.3)
            self._glow_title(surf, self.title, (W / 2, 62), 50, 0.6 + 0.4 * pop, int(255 * k))
        if self.subtitle and t > self.CRY:
            n = int(len(self.subtitle) * min(1.0, (t - self.CRY) / 0.8))
            size = 28
            while size > 16 and gfx.font(size, True).size(self.subtitle)[0] > W - 40:
                size -= 2
            gfx.text(surf, self.subtitle[:n], (W / 2, H - 56), size, (255, 225, 140), INK, 3, alpha=int(255 * k))
        if self.flash > 0:
            f = pygame.Surface((W, H), pygame.SRCALPHA)
            f.fill((255, 250, 230, int(255 * min(1.0, self.flash / 0.35))))
            surf.blit(f, (0, 0))
