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


_VIGNETTE = {}


def _vignette(size=None):
    """Dark edges fading smoothly to a clear middle (built once per size). Filled ellipses written outside-in:
    each one replaces the pixels inside it, so the alpha steps down smoothly toward the center."""
    w, h = size or (W, H)
    if (w, h) not in _VIGNETTE:
        v = pygame.Surface((w, h), pygame.SRCALPHA)
        v.fill((0, 0, 0, 210))
        steps = 64
        for i in range(steps):
            k = i / (steps - 1)                      # 0 = outer edge, 1 = center
            a = int(210 * (1 - k) ** 1.8)
            rw, rh = w * (1.5 - 1.0 * k), h * (1.2 - 0.8 * k)
            pygame.draw.ellipse(v, (0, 0, 0, a), (w / 2 - rw / 2, h / 2 - rh / 2, rw, rh))
        _VIGNETTE[(w, h)] = v
    return _VIGNETTE[(w, h)]


_PLATES = {}


def plate(text, size, color, angle=-4.0):
    """Persona-style title plate: the name on a slanted dark plate with a color edge and a cyan/magenta glitch
    split, tilted a few degrees. Cached."""
    key = (text, size, color, angle)
    if key in _PLATES:
        return _PLATES[key]
    img = gfx.text_image(text, size, WHITE, INK, max(2, size // 14))
    tw, th = img.get_size()
    sl = th * 0.45                      # slant
    pw, ph = tw + size, th + size // 3
    m = 14
    base = pygame.Surface((int(pw + sl + m * 2 + 12), int(ph + m * 2 + 12)), pygame.SRCALPHA)
    pts = [(m + sl, m), (m + sl + pw, m), (m + pw, m + ph), (m, m + ph)]
    pygame.draw.polygon(base, (0, 0, 0, 200), [(x + 9, y + 9) for x, y in pts])
    pygame.draw.polygon(base, (16, 12, 26), pts)
    stripe = [(m + sl, m), (m + sl + pw, m), (m + sl + pw - sl * 0.3, m + ph * 0.3), (m + sl * 0.7, m + ph * 0.3)]
    pygame.draw.polygon(base, tuple(int(c * 0.55) for c in color), stripe)
    pygame.draw.polygon(base, color, pts, 4)
    base.blit(img, img.get_rect(center=(m + sl / 2 + pw / 2, m + ph / 2 + 2)))
    out = pygame.Surface((base.get_width() + 16, base.get_height()), pygame.SRCALPHA)
    for tint, dx in (((0, 230, 255), 0), ((255, 40, 160), 16)):  # glitch split
        ghost = gfx.silhouette(base, tint)
        ghost.set_alpha(110)
        out.blit(ghost, (dx, 0))
    out.blit(base, (8, 0))
    out = pygame.transform.rotozoom(out, angle, 1.0)
    if len(_PLATES) > 120:
        _PLATES.clear()
    _PLATES[key] = out
    return out


def draw_plate(surf, text, center, size, color, scale=1.0, alpha=255, angle=-4.0):
    img = plate(text, size, color, angle)
    if abs(scale - 1.0) > 0.02:
        img = pygame.transform.rotozoom(img, 0, scale)
    elif alpha < 255:
        img = img.copy()
    if alpha < 255:
        img.set_alpha(max(0, alpha))
    surf.blit(img, img.get_rect(center=(int(center[0]), int(center[1]))))


def eye_strip(surf, pid, rect, t, color, flip=False):
    """Anime close-up: the top of the Pokemon (where the eyes are) blown up across a letterboxed strip, slowly
    pushing in, with speed lines behind and a glint sweeping across."""
    rect = pygame.Rect(rect)
    pygame.draw.rect(surf, tuple(int(c * 0.18) for c in color), rect)
    rng = random.Random(pid)
    for i in range(18):  # horizontal speed lines
        y = rect.y + rng.random() * rect.h
        x0 = (rng.random() * rect.w * 1.5 + t * 1400 * (0.5 + rng.random())) % (rect.w + 300) - 300
        pygame.draw.line(surf, _lighter(color, 0.3), (rect.x + x0, y), (rect.x + x0 + 160, y), 2)
    base = SPRITES.base(pid)
    if base is not None:
        bb = base.get_bounding_rect()
        if bb.w > 2 and bb.h > 2:
            # the head: sprites face left, so it's in the upper-front part of the picture
            crop = base.subsurface(pygame.Rect(bb.x, bb.y, max(2, int(bb.w * 0.62)), max(2, int(bb.h * 0.5)))).copy()
            if flip:
                crop = pygame.transform.flip(crop, True, False)
            zoom = 1.0 + 0.08 * min(1.0, t / 0.8)
            w = rect.w * 0.95 * zoom
            h = crop.get_height() * w / crop.get_width()
            big = gfx.rescale(crop, (w, h))
            clip = surf.get_clip()
            surf.set_clip(rect)
            surf.blit(big, big.get_rect(center=(rect.centerx, rect.centery + h * 0.08)))
            # glint
            gx = rect.x - 200 + (t / 0.7) * (rect.w + 400)
            glint = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            pygame.draw.polygon(glint, (255, 255, 255, 70), [(gx - rect.x, 0), (gx - rect.x + 60, 0),
                                                             (gx - rect.x - 40, rect.h), (gx - rect.x - 100, rect.h)])
            surf.blit(glint, rect.topleft)
            surf.set_clip(clip)
    pygame.draw.line(surf, color, rect.topleft, rect.topright, 4)
    pygame.draw.line(surf, color, rect.bottomleft, rect.bottomright, 4)


class Shatter:
    """The current frame cracks and blows apart into spinning triangular glass shards."""

    def __init__(self, frame, seed=5):
        w, h = frame.get_size()
        rng = random.Random(seed)
        cols = 8
        rows = max(8, int(cols * h / w))
        cw, ch = w / cols, h / rows
        self.pieces = []
        for r in range(rows):
            for c in range(cols):
                rect = pygame.Rect(int(c * cw), int(r * ch), int(cw) + 2, int(ch) + 2).clip(frame.get_rect())
                cell = frame.subsurface(rect).copy().convert_alpha() if pygame.display.get_surface() else \
                    frame.subsurface(rect).copy()
                rw, rh = rect.size
                for tri in (((0, 0), (rw, 0), (0, rh)), ((rw, 0), (rw, rh), (0, rh))):
                    img = pygame.Surface((rw, rh), pygame.SRCALPHA)
                    img.blit(cell, (0, 0))
                    mask = pygame.Surface((rw, rh), pygame.SRCALPHA)
                    pygame.draw.polygon(mask, (255, 255, 255, 255), tri)
                    img.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                    pygame.draw.polygon(img, (255, 255, 255, 160), tri, 1)
                    tx = sum(p[0] for p in tri) / 3 + rect.x
                    ty = sum(p[1] for p in tri) / 3 + rect.y
                    cx, cy = tx - w / 2, ty - h / 2
                    d = math.hypot(cx, cy) or 1
                    sp = rng.uniform(1300, 2600) * (0.6 + 0.6 * d / math.hypot(w / 2, h / 2))
                    self.pieces.append([img, rect.center, cx / d * sp, cy / d * sp - rng.uniform(200, 600),
                                        rng.uniform(-720, 720), d / math.hypot(w, h) * 0.06])
        self.cracks = []
        for i in range(10):  # crack lines from the center
            a = i / 10 * math.tau + rng.uniform(-0.2, 0.2)
            x, y, pts = w / 2, h / 2, [(w / 2, h / 2)]
            for _ in range(7):
                x += math.cos(a) * rng.uniform(60, 150) + rng.uniform(-30, 30)
                y += math.sin(a) * rng.uniform(60, 150) + rng.uniform(-30, 30)
                pts.append((x, y))
            self.cracks.append(pts)
        self.frame = frame

    CRACK = 0.09

    def draw(self, surf, t):
        """t: seconds since the shatter started. Returns False once every shard is gone."""
        if self.frame is None:
            return False
        if t < self.CRACK:
            surf.blit(self.frame, (0, 0))
            for pts in self.cracks:
                n = max(2, int(len(pts) * min(1.0, t / self.CRACK * 1.4)))
                pygame.draw.lines(surf, (255, 255, 255), False, pts[:n], 3)
            return True
        tt = t - self.CRACK
        alive = False
        sh = surf.get_height()
        for img, (x, y), vx, vy, spin, delay in self.pieces:
            q = tt - delay
            if q < 0:
                surf.blit(img, img.get_rect(center=(x, y)))
                alive = True
                continue
            px, py = x + vx * q, y + vy * q + 2400 * q * q
            if py > sh + 150 or px < -150 or px > surf.get_width() + 150 or py < -300:
                continue
            alive = True
            rot = pygame.transform.rotate(img, spin * q)
            surf.blit(rot, rot.get_rect(center=(px, py)))
        return alive


def _lighter(c, k=0.55):
    return tuple(int(v + (255 - v) * k) for v in c)


def _ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


class Cutscene:
    """kind: 'card' (portrait + title), 'vs' (two portraits), 'banner' (title only).
    action() runs once at `action_at` (fraction of the duration) - e.g. spawning Arceus."""

    def __init__(self, kind, duration, focus=None, zoom=1.7, title="", subtitle="", color=(255, 255, 255),
                 portrait=None, portrait2=None, action=None, action_at=0.55, cry=None, sound="select", size=None):
        self.W, self.H = size or (W, H)   # screen size (wide battle royales are landscape)
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
        self.minor = False      # quick cards (mega evolutions) skip the eye close-up
        self.eye = 0.0          # length of the anime eye close-up that opens big cutscenes
        self.shatter = kind in ("card", "vs", "finisher", "descent")
        self._shatter = None
        self._started = False

    @property
    def done(self):
        return self.t >= self.duration

    def skip(self):
        self.t = self.duration

    EYE = 0.75

    def _start(self):
        """First frame: big cards and VS screens open on an eye close-up (the rest of the timeline shifts)."""
        self._started = True
        if self.kind in ("card", "vs") and self.portrait and not self.minor:
            at = self.duration * self.action_at
            self.eye = self.EYE
            self.duration += self.eye
            self.action_at = (at + self.eye) / self.duration
            AUDIO.play("select", 0.8)

    def update(self, dt, renderer):
        if not self._started:
            self._start()
        if self.t == 0 and self.sound:
            AUDIO.play(self.sound)
        if self.eye and self.t < self.eye <= self.t + dt:
            AUDIO.play("boom", 0.6)  # smash cut from the eyes to the reveal
            self.flash = 0.2
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
        layer = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
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
        """Title with a pulsing colored glow. Rendered once at full size and scaled for the pop-in (building
        a big outlined title at every in-between size would stall the frame)."""
        glow_img = gfx.text_image(s, size, _lighter(self.color, 0.3), _lighter(self.color, 0.1),
                                  min(9, max(5, size // 6)))
        main = gfx.text_image(s, size, WHITE, INK, max(2, size // 14))
        for img, a in ((glow_img, int(alpha * (0.45 + 0.25 * math.sin(self.t * 10)))), (main, alpha)):
            if abs(scale - 1.0) > 0.02:
                img = gfx.rescale(img, (img.get_width() * scale, img.get_height() * scale))
            elif a < 255:
                img = img.copy()
            if a < 255:
                img.set_alpha(max(0, a))
            surf.blit(img, img.get_rect(center=(int(pos[0]), int(pos[1]))))

    # ------------------------------------------------------------------ drawing
    def _begin_draw(self, surf):
        if self.shatter and self._shatter is None:
            self._shatter = Shatter(surf.copy())

    def _end_draw(self, surf):
        """Glass shards of the previous frame fly off on top of the new scene."""
        if self._shatter is not None and self.t < 1.2:
            if not self._shatter.draw(surf, self.t):
                self._shatter.frame = None

    def _draw_eye_shot(self, surf, t):
        surf.fill((0, 0, 0))
        if self.kind == "vs" and self.portrait2:
            hgt = self.H * 0.26
            eye_strip(surf, self.portrait, (0, self.H * 0.2, self.W, hgt), t, gfx.TEAM_COLORS[0], flip=True)
            eye_strip(surf, self.portrait2, (0, self.H * 0.54, self.W, hgt), t, gfx.TEAM_COLORS[1])
            draw_plate(surf, "VS", (self.W / 2, self.H * 0.5), 60, self.color, 1.0 + 0.4 * (1 - _ease(t / 0.2)))
        else:
            hgt = self.H * 0.3
            eye_strip(surf, self.portrait, (0, self.H / 2 - hgt / 2, self.W, hgt), t, self.color)
        if self.flash > 0:
            f = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            f.fill((255, 255, 255, int(255 * min(1.0, self.flash / 0.35))))
            surf.blit(f, (0, 0))

    def draw(self, surf):
        self._begin_draw(surf)
        if self.eye and self.t < self.eye:
            self._draw_eye_shot(surf, self.t)
            self._end_draw(surf)
            return
        d, t = self.duration - self.eye, self.t - self.eye
        k = _ease(t / 0.35) * _ease((d - t) / 0.35)
        if self.eye:
            k = _ease((d - t) / 0.35)  # coming out of the eye shot: no fade-in, a hard cut
        self.anchors = []
        # darken + color wash + vignette, then speed lines
        wash = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        wash.fill((*(int(c * 0.25) for c in self.color), int(150 * k)))
        surf.blit(wash, (0, 0))
        vig = _vignette((self.W, self.H))
        vig.set_alpha(int(255 * k))
        surf.blit(vig, (0, 0))
        if k > 0.2:
            cx, cy = self.W / 2, self.H / 2
            for i in range(28):
                a = self.rng.random() * math.tau
                r0 = 260 + self.rng.random() * 120
                r1 = r0 + 300 + self.rng.random() * 400
                pygame.draw.line(surf, _lighter(self.color, 0.6), (cx + math.cos(a) * r0, cy + math.sin(a) * r0),
                                 (cx + math.cos(a) * r1, cy + math.sin(a) * r1), 2)
        # letterbox
        bar = int(130 * k)
        pygame.draw.rect(surf, (0, 0, 0), (0, 0, self.W, bar))
        pygame.draw.rect(surf, (0, 0, 0), (0, self.H - bar, self.W, bar))
        if self.kind == "vs":
            self._draw_vs(surf, t, k)
        elif self.kind == "card":
            self._draw_card(surf, t, k)
        else:
            self._draw_titles(surf, t, k, self.H * 0.45)
        if self.flash > 0:
            f = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            f.fill((255, 255, 255, int(255 * min(1.0, self.flash / 0.35))))
            surf.blit(f, (0, 0))
        self._end_draw(surf)

    def _draw_titles(self, surf, t, k, y):
        if t > 0.25:
            pop = _ease((t - 0.25) / 0.25)
            self._glow_title(surf, self.title, (self.W / 2, y), 64, 0.6 + 0.4 * pop, int(255 * k))
        if self.subtitle and t > 0.6:
            n = int(len(self.subtitle) * min(1.0, (t - 0.6) / 0.6))
            gfx.text(surf, self.subtitle[:n], (self.W / 2, y + 62), 26, self.color, INK, 3, alpha=int(255 * k))

    def _band(self, surf, y, h, offset, color):
        pts = [(offset - 80, y + h), (offset + self.W + 80, y + h), (offset + self.W + 160, y), (offset, y)]
        pygame.draw.polygon(surf, INK, [(px, py + 6) for px, py in pts])
        pygame.draw.polygon(surf, (18, 14, 26), pts)
        # energy streaks across the band in the event color
        for i in range(5):
            yy = y + 30 + i * (h - 60) / 4
            off = (self.t * (500 + i * 90) + i * 170) % (self.W + 300) - 150
            pygame.draw.line(surf, tuple(int(c * 0.6) for c in color), (offset + off - 120, yy), (offset + off, yy), 3)
        pygame.draw.polygon(surf, _lighter(color, 0.3), pts, 5)
        pygame.draw.polygon(surf, WHITE, pts, 2)

    def _draw_card(self, surf, t, k):
        slide = (1 - _ease(t / 0.45)) * -self.W
        y, h = 470, 300
        self._band(surf, y, h, slide, self.color)
        if self.portrait:
            self._draw_glowing(surf, self.portrait, 300, (self.W * 0.3 + slide, y + h + 20))
        self._draw_aura_fx(surf, k)
        if t > 0.3:
            pop = _ease((t - 0.3) / 0.2)
            size = min(40, int(40 * 16 / max(16, len(self.title))))
            draw_plate(surf, self.title, (self.W * 0.62 - slide * 0.2, y + 100), size, _lighter(self.color, 0.2),
                       1.6 - 0.6 * pop, int(255 * k))
        if self.subtitle and t > 0.7:
            n = int(len(self.subtitle) * min(1.0, (t - 0.7) / 0.5))
            gfx.text(surf, self.subtitle[:n], (self.W * 0.62, y + 180), 22, WHITE, INK, 3, alpha=int(255 * k))

    def _draw_vs(self, surf, t, k):
        a = _ease(t / 0.45)
        for i, pid in enumerate((self.portrait, self.portrait2)):
            if not pid:
                continue
            x = (self.W * 0.27 - (1 - a) * self.W) if i == 0 else (self.W * 0.73 + (1 - a) * self.W)
            y = 520 if i == 0 else 800
            band_col = gfx.TEAM_COLORS[i]
            self._band(surf, y - 120, 200, (-(1 - a) * self.W) if i == 0 else ((1 - a) * self.W), band_col)
            self._draw_glowing(surf, pid, 260, (x, y + 90), flip=i == 0, color=band_col)
        self._draw_aura_fx(surf, k)
        if t > 0.45:
            pop = _ease((t - 0.45) / 0.25)
            self._glow_title(surf, "VS", (self.W / 2, 640), 130, 2.2 - 1.2 * pop, int(255 * k))
        draw_plate(surf, self.title, (self.W / 2, 250), 46, self.color, 1.0, int(255 * k))


# the 18 plate colors around Arceus' Judgment wheel
PLATE_TYPES = ["normal", "fire", "water", "electric", "grass", "ice", "fighting", "poison", "ground", "flying",
               "psychic", "bug", "rock", "ghost", "dragon", "dark", "steel", "fairy"]


class Descent(Cutscene):
    """Arceus floats down from the sky through god rays, its Judgment wheel turning behind it, cries out, then
    drops legendaries into the arena in pillars of light one by one, and rises back up and leaves.

    drops: [(pokemon_id, name, (world_x, world_y))]; on_drop(i) spawns drop i in the battle."""

    DOWN, CRY, FIRST, GAP = 2.4, 2.6, 3.2, 1.0

    SLAM = 3.6  # rare variant: Arceus crashes into the arena itself

    def __init__(self, arceus_id, drops, group_title, center, on_drop, lands=False, size=None):
        self.lands = lands
        self.leave = 99.0 if lands else self.FIRST + len(drops) * self.GAP + 0.6
        super().__init__("descent", self.SLAM + 2.2 if lands else self.leave + 1.8, focus=center, zoom=1.12,
                         title="ARCEUS DESCENDS",
                         subtitle="...AND JOINS THE FIGHT ITSELF!" if lands else f"AND BRINGS {group_title}!",
                         color=(255, 205, 90), sound=None, size=size)
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
        if self.lands and prev < self.SLAM <= self.t:
            self.on_drop(0)
            self.flash = 0.35
            renderer.shake = max(renderer.shake, 1.0)
            AUDIO.play("boom", 1.0)
            sx, sy = self._screen(0)
            for i in range(4):
                self.rings.append([sx, sy, 20 + i * 60, 0.9 + i * 0.1, (255, 230, 150)])
            self._burst(sx, sy, 90, (255, 220, 120))
            return
        for i, (pid, _name, _pos) in enumerate(self.drops):
            if self.lands:
                break
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
        top, rest = -260, self.H * 0.37
        if t < self.DOWN:
            return top + (rest - top) * _ease(t / self.DOWN)
        if self.lands:
            if t < self.CRY + 0.4:
                return rest
            gy = self._screen(0)[1] - 30
            return rest + (gy - rest) * min(1.0, ((t - self.CRY - 0.4) / (self.SLAM - self.CRY - 0.4)) ** 2)
        if t < self.leave:
            return rest
        return rest + (top - 140 - rest) * min(1.0, ((t - self.leave) / 1.2) ** 2)

    def draw(self, surf):
        self._begin_draw(surf)
        d, t = self.duration, self.t
        k = _ease(t / 0.5) * _ease((d - t) / 0.5)
        self.anchors = []
        # the sky darkens
        shade = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        shade.fill((14, 10, 30, int(150 * k)))
        surf.blit(shade, (0, 0))
        vig = _vignette((self.W, self.H))
        vig.set_alpha(int(200 * k))
        surf.blit(vig, (0, 0))
        # god rays fanning down from above
        ay = self._arceus_y()
        rays = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        for i in range(9):
            a = -0.9 + i * 0.225 + math.sin(t * 0.7 + i) * 0.05
            spread = 0.05 + 0.02 * math.sin(t * 2 + i * 1.7)
            pts = [(self.W / 2, -80), (self.W / 2 + math.sin(a - spread) * 1800, -80 + math.cos(a - spread) * 1800),
                   (self.W / 2 + math.sin(a + spread) * 1800, -80 + math.cos(a + spread) * 1800)]
            pygame.draw.polygon(rays, (255, 230, 150, int(38 * k)), pts)
        surf.blit(rays, (0, 0))
        # pillars of light where the legendaries land
        for i in range(0 if self.lands else len(self.drops)):
            at = self.FIRST + i * self.GAP
            p = (t - (at - 0.35)) / 1.1
            if 0 <= p <= 1:
                sx, sy = self._screen(i)
                wdt = 90 * (1 - p) ** 0.5 if p > 0.32 else 90 * (p / 0.32)
                beam = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
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
        landed = self.lands and t >= self.SLAM
        if landed:  # Arceus stands in the arena now, burning gold
            sx, sy = self._screen(0)
            self._draw_glowing(surf, self.arceus, 170, (sx, sy + 30))
        elif ay > -200:
            cx, cy = self.W / 2, ay - 120
            rad = 170
            ring = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            pygame.draw.circle(ring, (255, 220, 120, int(150 * k)), (int(cx), int(cy)), rad, 6)
            pygame.draw.circle(ring, (255, 245, 210, int(90 * k)), (int(cx), int(cy)), rad - 18, 2)
            for j, typ in enumerate(PLATE_TYPES):
                a = j / len(PLATE_TYPES) * math.tau + t * 0.8
                px, py = cx + math.cos(a) * rad, cy + math.sin(a) * rad
                pygame.draw.circle(ring, (*gfx.type_color(typ, 0), int(255 * k)), (int(px), int(py)), 11)
                pygame.draw.circle(ring, (255, 255, 255, int(255 * k)), (int(px), int(py)), 11, 2)
            surf.blit(ring, (0, 0))
            self._draw_glowing(surf, self.arceus, 290, (self.W / 2, ay + 30))
        # the new arrivals stand in the light, glowing, until the scene ends
        for i, (pid, _name, _pos) in enumerate(self.drops):
            if not self.lands and t >= self.FIRST + i * self.GAP:
                sx, sy = self._screen(i)
                self._draw_glowing(surf, pid, 120, (sx, sy + 30), color=(255, 235, 170))
        self._draw_aura_fx(surf, k)
        # letterbox + titles
        bar = int(110 * k)
        pygame.draw.rect(surf, (0, 0, 0), (0, 0, self.W, bar))
        pygame.draw.rect(surf, (0, 0, 0), (0, self.H - bar, self.W, bar))
        if 0.8 < t < self.leave + 0.8:
            pop = _ease((t - 0.8) / 0.2)
            draw_plate(surf, self.title, (self.W / 2, 62), 40, self.color, 1.6 - 0.6 * pop, int(255 * k))
        if self.subtitle and t > self.CRY:
            n = int(len(self.subtitle) * min(1.0, (t - self.CRY) / 0.8))
            size = 28
            while size > 16 and gfx.font(size, True).size(self.subtitle)[0] > self.W - 40:
                size -= 2
            gfx.text(surf, self.subtitle[:n], (self.W / 2, self.H - 56), size, (255, 225, 140), INK, 3, alpha=int(255 * k))
        if self.flash > 0:
            f = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            f.fill((255, 250, 230, int(255 * min(1.0, self.flash / 0.35))))
            surf.blit(f, (0, 0))
        self._end_draw(surf)


# how each type's finishing attack looks: (style, particle shape)
FINISH_STYLE = {
    "fire": ("stream", "flame"), "water": ("wave", "drop"), "electric": ("bolt", "spark"),
    "grass": ("stream", "leaf"), "ice": ("stream", "shard"), "fighting": ("slash", "spark"),
    "poison": ("stream", "bubble"), "ground": ("quake", "rock"), "flying": ("slash", "wind"),
    "psychic": ("rings", "spark"), "bug": ("stream", "leaf"), "rock": ("quake", "rock"),
    "ghost": ("rings", "bubble"), "dragon": ("beam", "spark"), "dark": ("slash", "shard"),
    "steel": ("slash", "shard"), "fairy": ("rings", "star"), "normal": ("slash", "spark"),
}


class AttackFX:
    """A finisher's type-themed attack, reused small for every hit in 1v1 battles."""

    def __init__(self, mtype, cls, start, end):
        self.color = gfx.type_color(mtype, 0)
        self.style, self.shape = FINISH_STYLE.get(mtype, ("slash", "spark"))
        if cls == "phys" and self.style in ("stream", "rings", "beam"):
            self.style = "slash"
        self.fx = random.Random(hash(mtype) & 0xFFFF)
        self.W, self.H = W, H
        # Finisher._draw_attack aims from (ax, ay - 80) to (dx, dy - 60)
        self.ax, self.ay = start[0], start[1] + 80
        self.dx, self.dy = end[0], end[1] + 60

    def draw(self, surf, p):
        Finisher._draw_attack(self, surf, max(0.0, min(1.0, p)))

    def _shape(self, *a, **k):
        return Finisher._shape(self, *a, **k)


class Finisher(Cutscene):
    """The knockout blow in a 1v1, as a short anime-style cutscene:
    freeze + zoom on the attacker with the move name -> type-themed attack flies across -> black/white impact
    frame -> the defender shatters in slow motion with K.O.! (FINISH! for the last Pokemon)."""

    CHARGE, RELEASE, IMPACT, AFTER = 0.25, 1.05, 1.55, 1.8
    EYES = (0.42, 0.98)

    def __init__(self, attacker_id, defender_id, move_name, mtype, cls, mine, final=False, size=None):
        color = gfx.type_color(mtype, 0)
        super().__init__("finisher", 3.6 if final else 3.0, title=move_name.upper(), color=color, sound=None,
                         size=size)
        self.attacker, self.defender = attacker_id, defender_id
        self.mtype, self.cls, self.mine, self.final = mtype, cls, mine, final
        self.style, self.shape = FINISH_STYLE.get(mtype, ("slash", "spark"))
        if cls == "phys" and self.style in ("stream", "rings", "beam"):
            self.style = "slash"
        self.shards = []
        self.skipped = False
        # attacker on the left when it's yours, on the right when it's theirs
        self.ax, self.dx = (self.W * 0.28, self.W * 0.72) if mine else (self.W * 0.72, self.W * 0.28)
        self.ay, self.dy = self.H * 0.58, self.H * 0.42

    def skip(self):
        self.t = self.duration

    def update(self, dt, renderer=None):
        prev = self.t
        # slow motion right after the impact
        rate = 0.45 if self.IMPACT <= self.t < self.IMPACT + 0.7 else 1.0
        self.t += dt * rate
        t = self.t
        if prev == 0:
            AUDIO.play("select")
        if prev < self.CHARGE <= t:
            AUDIO.play("mega", 0.6)
        if prev < self.RELEASE <= t:
            AUDIO.play("beam" if self.cls == "spec" else "melee", 1.0)
        if prev < self.IMPACT <= t:
            AUDIO.play("hit_super", 1.0)
            AUDIO.play("boom", 0.9)
            AUDIO.cry(self.defender, 0.9)
            self.flash = 0.25
            for _ in range(46):  # the defender shatters
                a = self.fx.uniform(0, math.tau)
                sp = self.fx.uniform(120, 620)
                self.shards.append([self.dx, self.dy, math.cos(a) * sp, math.sin(a) * sp - 120,
                                    self.fx.uniform(6, 16), self.fx.uniform(0, math.tau), self.fx.uniform(-9, 9)])
            for i in range(4):
                self.rings.append([self.dx, self.dy, 20 + i * 50, 0.8 + i * 0.12, self.color])
        if self.final and prev < self.IMPACT + 0.9 <= t:
            AUDIO.play("win", 0.7)
        self._update_aura(dt * rate)
        for s in self.shards:
            s[0] += s[2] * dt * rate
            s[1] += s[3] * dt * rate
            s[3] += 900 * dt * rate
            s[5] += s[6] * dt * rate
        self.flash = max(0.0, self.flash - dt)

    # ------------------------------------------------------------------ drawing
    def _shape(self, surf, shape, x, y, size, col, ang=0.0):
        if shape == "flame":
            pygame.draw.ellipse(surf, col, (x - size / 2, y - size, size, size * 2))
            pygame.draw.ellipse(surf, (255, 240, 180), (x - size / 4, y - size / 2, size / 2, size))
        elif shape == "leaf":
            pts = [(x + math.cos(ang) * size, y + math.sin(ang) * size),
                   (x + math.cos(ang + 1.6) * size * 0.4, y + math.sin(ang + 1.6) * size * 0.4),
                   (x - math.cos(ang) * size, y - math.sin(ang) * size),
                   (x + math.cos(ang - 1.6) * size * 0.4, y + math.sin(ang - 1.6) * size * 0.4)]
            pygame.draw.polygon(surf, col, pts)
        elif shape in ("shard", "rock"):
            pts = [(x + math.cos(ang + k * 2.1) * size * (1 if k % 2 == 0 else 0.6),
                    y + math.sin(ang + k * 2.1) * size * (1 if k % 2 == 0 else 0.6)) for k in range(3)]
            pygame.draw.polygon(surf, col if shape == "shard" else (150, 120, 80), pts)
            pygame.draw.polygon(surf, (255, 255, 255) if shape == "shard" else INK, pts, 1)
        elif shape == "star":
            pts = [(x + math.cos(ang + k * math.pi / 5) * (size if k % 2 == 0 else size * 0.45),
                    y + math.sin(ang + k * math.pi / 5) * (size if k % 2 == 0 else size * 0.45)) for k in range(10)]
            pygame.draw.polygon(surf, (255, 230, 250), pts)
        elif shape in ("bubble", "drop"):
            pygame.draw.circle(surf, col, (int(x), int(y)), int(size))
            pygame.draw.circle(surf, (255, 255, 255), (int(x - size / 3), int(y - size / 3)), max(1, int(size / 4)))
        else:  # spark / wind
            pygame.draw.circle(surf, (255, 255, 255), (int(x), int(y)), max(2, int(size / 2)))
            pygame.draw.circle(surf, col, (int(x), int(y)), int(size), 2)

    def _draw_attack(self, surf, p):
        """p: 0..1 progress of the attack traveling from attacker to defender."""
        col, light = self.color, _lighter(self.color, 0.5)
        sx, sy, ex, ey = self.ax, self.ay - 80, self.dx, self.dy - 60
        hx, hy = sx + (ex - sx) * p, sy + (ey - sy) * p
        layer = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        if self.style == "beam":
            for wdt, a in ((70, 90), (40, 170), (14, 255)):
                pygame.draw.line(layer, (*(light if wdt < 30 else col), a), (sx, sy), (hx, hy), wdt)
            pygame.draw.circle(layer, (*light, 220), (int(hx), int(hy)), 46)
        elif self.style == "bolt":
            pts, n = [(sx, sy)], 9
            for i in range(1, n):
                q = i / n * p
                pts.append((sx + (ex - sx) * q + self.fx.uniform(-30, 30), sy + (ey - sy) * q + self.fx.uniform(-30, 30)))
            pts.append((hx, hy))
            pygame.draw.lines(layer, (*col, 200), False, pts, 14)
            pygame.draw.lines(layer, (255, 255, 255, 255), False, pts, 5)
        elif self.style == "rings":
            for i in range(5):
                q = max(0.0, p - i * 0.12)
                rx, ry = sx + (ex - sx) * q, sy + (ey - sy) * q
                pygame.draw.circle(layer, (*col, 200), (int(rx), int(ry)), int(30 + q * 50), 6)
        elif self.style == "slash":
            for i in range(3):  # three slash streaks crossing the defender
                q = min(1.0, max(0.0, p * 1.6 - i * 0.25))
                if q <= 0:
                    continue
                ang = -0.7 + i * 0.7
                L = 260 * q
                cx, cy = ex, ey
                p0 = (cx - math.cos(ang) * L, cy - math.sin(ang) * L)
                p1 = (cx + math.cos(ang) * L, cy + math.sin(ang) * L)
                pygame.draw.line(layer, (*col, 200), p0, p1, 18)
                pygame.draw.line(layer, (255, 255, 255, 255), p0, p1, 5)
            # the attacker dashes across
            pygame.draw.line(layer, (*light, 120), (sx, sy), (hx, hy), 30)
        elif self.style == "quake":
            for i in range(8):
                q = max(0.0, p - i * 0.06)
                rx = sx + (ex - sx) * q + self.fx.uniform(-20, 20)
                ry = sy + (ey - sy) * q + 60
                self._shape(layer, "rock", rx, ry - q * 40, 22, col, q * 6 + i)
        elif self.style == "wave":
            for i in range(14):
                q = max(0.0, p - i * 0.03)
                rx, ry = sx + (ex - sx) * q, sy + (ey - sy) * q + math.sin(q * 12 + i) * 30
                pygame.draw.circle(layer, (*col, 170), (int(rx), int(ry)), int(26 + 18 * math.sin(i)))
                pygame.draw.circle(layer, (255, 255, 255, 200), (int(rx), int(ry - 10)), 8)
        else:  # stream of shaped particles (fire, grass leaves, ice shards, poison bubbles...)
            for i in range(26):
                q = max(0.0, p - i * 0.025)
                if q <= 0:
                    continue
                spread = math.sin(i * 1.7) * 26
                rx, ry = sx + (ex - sx) * q + spread, sy + (ey - sy) * q + math.cos(i * 2.3) * 22
                self._shape(layer, self.shape, rx, ry, 14 + (i % 4) * 4, col, q * 8 + i)
        surf.blit(layer, (0, 0))

    def draw(self, surf):
        self._begin_draw(surf)
        d, t = self.duration, self.t
        k = _ease(t / 0.2) * _ease((d - t) / 0.35)
        self.anchors = []
        impact_frame = self.IMPACT <= t < self.IMPACT + 0.12
        if impact_frame:
            # anime impact frame: everything black, the defender a white cut-out, the attack in white
            surf.fill((0, 0, 0))
            img = SPRITES.get(self.defender, 280, flip=not self.mine)
            sil = gfx.silhouette(img, (255, 255, 255))
            surf.blit(sil, sil.get_rect(midbottom=(self.dx, self.dy + 140)))
            for i in range(14):
                a = i / 14 * math.tau
                pygame.draw.line(surf, (255, 255, 255), (self.dx + math.cos(a) * 160, self.dy + math.sin(a) * 160),
                                 (self.dx + math.cos(a) * 900, self.dy + math.sin(a) * 900), 3)
            return
        # its own stage: the battle fades out behind a dark backdrop in the move's color
        wash = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        wash.fill((*(int(c * 0.16) for c in self.color), int(255 * k)))
        surf.blit(wash, (0, 0))
        glow = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        for i in range(6):
            pygame.draw.circle(glow, (*self.color, int(14 * k)), (int(self.W / 2), int(self.H / 2)), 520 - i * 70)
        surf.blit(glow, (0, 0))
        vig = _vignette((self.W, self.H))
        vig.set_alpha(int(255 * k))
        surf.blit(vig, (0, 0))
        if k > 0.2:
            for i in range(30):
                a = self.rng.random() * math.tau
                r0 = 300 + self.rng.random() * 100
                r1 = r0 + 400 + self.rng.random() * 400
                pygame.draw.line(surf, _lighter(self.color, 0.6), (self.W / 2 + math.cos(a) * r0, self.H / 2 + math.sin(a) * r0),
                                 (self.W / 2 + math.cos(a) * r1, self.H / 2 + math.sin(a) * r1), 2)
        # attacker slams in, glowing in the move's color
        slide = (1 - _ease((t - 0.05) / 0.3)) * (-self.W if self.mine else self.W)
        self._draw_glowing(surf, self.attacker, 300, (self.ax + slide, self.ay + 140), flip=self.mine)
        # defender: shakes after the hit, then is gone (shattered)
        if t < self.IMPACT:
            img = SPRITES.get(self.defender, 240, flip=not self.mine)
            surf.blit(img, img.get_rect(midbottom=(self.dx, self.dy + 120)))
        elif t < self.IMPACT + 0.25:
            img = SPRITES.get(self.defender, 240, flip=not self.mine, white=0.8)
            jx = self.fx.uniform(-14, 14)
            surf.blit(img, img.get_rect(midbottom=(self.dx + jx, self.dy + 120)))
        # the attack itself
        if self.RELEASE <= t < self.IMPACT:
            self._draw_attack(surf, (t - self.RELEASE) / (self.IMPACT - self.RELEASE))
        for x, y, vx, vy, size, ang, spin in self.shards:
            self._shape(surf, "shard", x, y, size, _lighter(self.color, 0.3), ang)
        self._draw_aura_fx(surf, k)
        # letterbox
        bar = int(120 * k)
        pygame.draw.rect(surf, (0, 0, 0), (0, 0, self.W, bar))
        pygame.draw.rect(surf, (0, 0, 0), (0, self.H - bar, self.W, bar))
        # the attacker locks eyes before letting go
        if self.EYES[0] <= t < self.EYES[1]:
            q = t - self.EYES[0]
            hgt = self.H * 0.2 * min(1.0, q / 0.08)
            eye_strip(surf, self.attacker, (0, self.H * 0.42 - hgt / 2, self.W, hgt), q, self.color, flip=self.mine)
        # move name slams in
        if self.CHARGE <= t < self.IMPACT + 0.2:
            pop = _ease((t - self.CHARGE) / 0.15)
            size = min(56, int(56 * 12 / max(12, len(self.title))))
            draw_plate(surf, self.title, (self.W / 2, 210), size, self.color, 1.7 - 0.7 * pop, int(255 * k))
            gfx.pill(surf, self.mtype.upper(), (self.W / 2, 286), self.color, 18)
        # K.O.!
        if t >= self.IMPACT + 0.2:
            q = t - self.IMPACT - 0.2
            pop = _ease(q / 0.25)
            word = "FINISH!" if self.final else "K.O.!"
            self._glow_title(surf, word, (self.W / 2, self.H * 0.5), 150 if self.final else 130, 2.0 - pop, int(255 * k))
        if self.flash > 0:
            f = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            f.fill((255, 255, 255, int(255 * min(1.0, self.flash / 0.25))))
            surf.blit(f, (0, 0))
        self._end_draw(surf)


def _helix(surf, a, b, t, width=4, phase=0.0, amp=18):
    """Two twisting strands of rainbow light from a to b (the Key Stone / Mega Stone link)."""
    (x0, y0), (x1, y1) = a, b
    n = 28
    L = math.hypot(x1 - x0, y1 - y0) or 1
    nx, ny = -(y1 - y0) / L, (x1 - x0) / L
    for strand in (0, math.pi):
        pts = []
        for i in range(n + 1):
            q = i / n
            off = math.sin(q * 10 + t * 12 + strand + phase) * amp
            pts.append((x0 + (x1 - x0) * q + nx * off, y0 + (y1 - y0) * q + ny * off))
        for i in range(n):
            pygame.draw.line(surf, gfx.hsv(i / n + t * 0.8), pts[i], pts[i + 1], width)


def mega_symbol(surf, center, r, t, color, alpha=255):
    """The Mega Evolution emblem: a ring with a twisting DNA helix inside."""
    layer = pygame.Surface((r * 2 + 20, r * 2 + 20), pygame.SRCALPHA)
    c = (r + 10, r + 10)
    pygame.draw.circle(layer, (*color, alpha), c, r, max(4, r // 10))
    pygame.draw.circle(layer, (255, 255, 255, alpha), c, int(r * 0.86), 2)
    for strand in (0, math.pi):
        pts = []
        for i in range(33):
            q = i / 32
            ang = math.pi * 0.75 + q * math.pi * 1.5 + t * 0.6
            rr = r * (0.15 + 0.6 * q)
            off = math.sin(q * 9 + strand + t * 4) * r * 0.08
            pts.append((c[0] + math.cos(ang) * (rr + off), c[1] + math.sin(ang) * (rr + off)))
        pygame.draw.lines(layer, (*_lighter(color, 0.4), alpha), False, pts, max(3, r // 14))
    surf.blit(layer, layer.get_rect(center=(int(center[0]), int(center[1]))))


class MegaEvolution(Cutscene):
    """Key Stone and Mega Stone link up -> the Pokemon is wrapped in a rainbow cocoon -> it cracks -> the Mega
    form bursts out in front of a giant Mega symbol."""

    LINK, COCOON, CRACK = 0.75, 1.9, 2.05

    def __init__(self, base_id, form_id, title, subtitle="MEGA EVOLUTION", color=(170, 90, 230), focus=None,
                 size=None, duration=3.7):
        super().__init__("mega", duration, focus=focus, zoom=1.6, title=title.upper(), subtitle=subtitle,
                         color=color, portrait=form_id, sound=None, size=size)
        self.base_id, self.form_id = base_id, form_id
        self.renderer = None

    def update(self, dt, renderer=None):
        prev, self.t = self.t, self.t + dt
        if renderer is not None and self.focus:
            renderer.cam_target = (self.focus[0], self.focus[1], self.zoom)
        if prev == 0:
            AUDIO.play("mega", 0.9)
        if prev < self.LINK <= self.t:
            AUDIO.play("tera", 0.7)
        if prev < self.CRACK <= self.t:
            self.flash = 0.35
            AUDIO.play("boom", 1.0)
            AUDIO.cry(self.form_id, 1.0)
            if renderer is not None:
                renderer.shake = max(renderer.shake, 0.8)
            for i in range(4):
                self.rings.append([self.W / 2, self.H * 0.5, 30 + i * 50, 0.9 + i * 0.1, self.color])
            self._burst(self.W / 2, self.H * 0.5, 90, self.color)
        self._update_aura(dt)
        self.flash = max(0.0, self.flash - dt)

    def draw(self, surf):
        self._begin_draw(surf)
        d, t = self.duration, self.t
        k = _ease(t / 0.3) * _ease((d - t) / 0.35)
        self.anchors = []
        cx, cy = self.W / 2, self.H * 0.5
        bg = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        bg.fill((*(int(c * 0.12) for c in self.color), int(245 * k)))
        surf.blit(bg, (0, 0))
        vig = _vignette((self.W, self.H))
        vig.set_alpha(int(255 * k))
        surf.blit(vig, (0, 0))
        if t < self.CRACK:
            # Key Stone (left) and Mega Stone (right), linked by the helix
            ks, ms = (self.W * 0.14, self.H * 0.26), (self.W * 0.86, self.H * 0.26)
            for pos, col in ((ks, (120, 200, 255)), (ms, self.color)):
                pygame.draw.circle(surf, _lighter(col, 0.2), (int(pos[0]), int(pos[1])), 30)
                pygame.draw.circle(surf, (255, 255, 255), (int(pos[0]), int(pos[1])), 30, 3)
                _helix(surf, (pos[0] - 14, pos[1]), (pos[0] + 14, pos[1]), t, 2, amp=8)
            p = min(1.0, t / self.LINK)
            _helix(surf, ks, (ks[0] + (cx - ks[0]) * p, ks[1] + (cy - 60 - ks[1]) * p), t, 5)
            _helix(surf, ms, (ms[0] + (cx - ms[0]) * p, ms[1] + (cy - 60 - ms[1]) * p), t, 5, phase=1.3)
            # the base Pokemon, turning to light inside a spinning rainbow cocoon
            if t > self.LINK * 0.6:
                q = min(1.0, (t - self.LINK * 0.6) / (self.COCOON - self.LINK * 0.6))
                img = SPRITES.get(self.base_id, 300, white=round(min(1.0, q * 1.2), 1))
                surf.blit(img, img.get_rect(center=(cx, cy)))
                for i in range(7):
                    a0 = i / 7 * math.tau + t * (4 + i)
                    rr = 170 + 20 * math.sin(t * 6 + i) - q * 40
                    rect = pygame.Rect(cx - rr, cy - rr * 1.15, rr * 2, rr * 2.3)
                    pygame.draw.arc(surf, gfx.hsv(i / 7 + t * 0.5), rect, a0, a0 + 1.6 + q, 7)
                if t > self.COCOON:  # cracks across the cocoon
                    rng = random.Random(3)
                    for _ in range(8):
                        a = rng.random() * math.tau
                        x, y, pts = cx, cy, [(cx, cy)]
                        for _ in range(4):
                            x += math.cos(a) * rng.uniform(30, 70)
                            y += math.sin(a) * rng.uniform(30, 70)
                            pts.append((x, y))
                        pygame.draw.lines(surf, (255, 255, 255), False, pts, 4)
        else:
            q = t - self.CRACK
            mega_symbol(surf, (cx, cy - 20), int(260 + 30 * math.sin(t * 2)), t, self.color, int(200 * k))
            self._draw_glowing(surf, self.form_id, 340, (cx, cy + 190))
            self._draw_aura_fx(surf, k)
            pop = _ease(q / 0.2)
            size = min(44, int(44 * 16 / max(16, len(self.title))))
            draw_plate(surf, self.title, (cx, self.H * 0.17), size, _lighter(self.color, 0.15), 1.6 - 0.6 * pop,
                       int(255 * k))
            if self.subtitle and q > 0.3:
                n = int(len(self.subtitle) * min(1.0, (q - 0.3) / 0.5))
                gfx.text(surf, self.subtitle[:n], (cx, self.H * 0.83), 26, _lighter(self.color, 0.5), INK, 3,
                         alpha=int(255 * k))
        if t < self.CRACK:
            self._draw_aura_fx(surf, k)
        bar = int(100 * k)
        pygame.draw.rect(surf, (0, 0, 0), (0, 0, self.W, bar))
        pygame.draw.rect(surf, (0, 0, 0), (0, self.H - bar, self.W, bar))
        if self.flash > 0:
            f = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            f.fill((255, 255, 255, int(255 * min(1.0, self.flash / 0.35))))
            surf.blit(f, (0, 0))
        self._end_draw(surf)


class Gigantamax(Cutscene):
    """The sky turns crimson, red clouds swirl, a red silhouette grows to giant size, then the Gigantamax form
    towers over everything with red clouds circling its head."""

    GROW, BURST = (0.45, 1.9), 1.95

    def __init__(self, base_id, form_id, name, move_name, focus=None, size=None):
        super().__init__("gmax", 3.9, focus=focus, zoom=1.3, title="GIGANTAMAX!", subtitle=f"G-MAX {move_name.upper()}",
                         color=(230, 40, 70), portrait=form_id, sound=None, size=size)
        self.base_id, self.form_id, self.name = base_id, form_id, name
        self.clouds = [(random.random() * 1.0, random.uniform(0.6, 1.4), random.uniform(40, 90)) for _ in range(16)]

    def update(self, dt, renderer=None):
        prev, self.t = self.t, self.t + dt
        if renderer is not None and self.focus:
            renderer.cam_target = (self.focus[0], self.focus[1], self.zoom)
            if self.GROW[0] < self.t < self.GROW[1]:
                renderer.shake = max(renderer.shake, 0.25)
        if prev == 0:
            AUDIO.play("beam", 0.9)
        if prev < self.BURST <= self.t:
            self.flash = 0.4
            AUDIO.play("boom", 1.0)
            AUDIO.cry(self.form_id, 1.0)
            if renderer is not None:
                renderer.shake = max(renderer.shake, 1.0)
            self._burst(self.W / 2, self.H * 0.45, 90, self.color)
        self._update_aura(dt)
        self.flash = max(0.0, self.flash - dt)

    def _sky(self, surf, k):
        top, bot = (40, 4, 12), (150, 20, 40)
        sky = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        for y in range(0, self.H, 8):
            q = y / self.H
            col = tuple(int(top[i] + (bot[i] - top[i]) * q) for i in range(3))
            pygame.draw.rect(sky, (*col, int(250 * k)), (0, y, self.W, 8))
        surf.blit(sky, (0, 0))
        for i, (ph, sp, r) in enumerate(self.clouds):  # swirling dark clouds near the top
            a = ph * math.tau + self.t * sp * 0.6
            x = self.W / 2 + math.cos(a) * self.W * 0.45
            y = self.H * 0.16 + math.sin(a) * self.H * 0.06
            pygame.draw.circle(surf, (70, 10, 26), (int(x), int(y)), int(r))
            pygame.draw.circle(surf, (120, 20, 44), (int(x), int(y - r * 0.3)), int(r * 0.7))

    def draw(self, surf):
        self._begin_draw(surf)
        d, t = self.duration, self.t
        k = _ease(t / 0.35) * _ease((d - t) / 0.35)
        self.anchors = []
        self._sky(surf, k)
        cx, ground = self.W / 2, self.H * 0.86
        # red energy pillars rising from the ground
        layer = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        for i in range(5):
            x = cx + (i - 2) * 120 + math.sin(t * 3 + i) * 20
            wdt = 40 + 20 * math.sin(t * 7 + i)
            pygame.draw.rect(layer, (255, 60, 90, int(70 * k)), (x - wdt / 2, 0, wdt, ground))
        surf.blit(layer, (0, 0))
        if t < self.BURST:
            q = max(0.0, min(1.0, (t - self.GROW[0]) / (self.GROW[1] - self.GROW[0])))
            hgt = int(140 + (self.H * 1.05 - 140) * q ** 1.6) // 8 * 8
            img = SPRITES.get(self.base_id, max(16, hgt))
            sil = gfx.silhouette(img, (255, 50, 80))
            core = gfx.silhouette(img, (60, 0, 12))
            surf.blit(sil, sil.get_rect(midbottom=(cx + 6, ground + 6)))
            surf.blit(core, core.get_rect(midbottom=(cx, ground)))
        else:
            q = t - self.BURST
            hgt = int(self.H * 0.72)
            self._draw_glowing(surf, self.form_id, hgt, (cx, ground), color=self.color)
            head_y = ground - hgt * 0.95
            for i in range(9):  # the Gigantamax cloud crown
                a = i / 9 * math.tau + t * 1.4
                x = cx + math.cos(a) * self.W * 0.3
                y = head_y + math.sin(a) * 40
                pygame.draw.circle(surf, (150, 20, 45), (int(x), int(y)), 34)
                pygame.draw.circle(surf, (230, 60, 90), (int(x), int(y - 6)), 22)
            self._draw_aura_fx(surf, k)
            pop = _ease(q / 0.2)
            draw_plate(surf, self.title, (cx, self.H * 0.12), 54, self.color, 1.6 - 0.6 * pop, int(255 * k), angle=-6)
            draw_plate(surf, self.name.upper(), (cx, self.H * 0.12 + 74), 26, (255, 160, 180), 1.0, int(255 * k))
            if q > 0.3:
                n = int(len(self.subtitle) * min(1.0, (q - 0.3) / 0.5))
                gfx.text(surf, self.subtitle[:n], (cx, self.H * 0.93), 30, (255, 200, 210), INK, 3,
                         alpha=int(255 * k))
        if self.flash > 0:
            f = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            f.fill((255, 230, 235, int(255 * min(1.0, self.flash / 0.4))))
            surf.blit(f, (0, 0))
        self._end_draw(surf)


def subtitle(surf, speaker, text, t, length, color=(200, 120, 255)):
    """Movie subtitle: speaker name tag and the line typing out in time with the voice."""
    w, h = surf.get_size()
    n = int(len(text) * min(1.0, t / max(0.6, length * 0.8)))
    box = pygame.Rect(40, h - 250, w - 80, 120)
    shade = pygame.Surface(box.size, pygame.SRCALPHA)
    shade.fill((8, 6, 14, 200))
    surf.blit(shade, box.topleft)
    pygame.draw.rect(surf, color, box, 2, border_radius=6)
    gfx.pill(surf, speaker.upper(), (box.x + 70, box.y), color, 16)
    words, line, lines = text[:n].split(" "), "", []
    f = gfx.font(26, False)
    for word in words:
        trial = (line + " " + word).strip()
        if f.size(trial)[0] > box.w - 40:
            lines.append(line)
            line = word
        else:
            line = trial
    lines.append(line)
    for i, ln in enumerate(lines[-2:]):
        gfx.text(surf, ln, (box.x + 20, box.y + 42 + i * 34), 26, WHITE, INK, 2, anchor="midleft", chunky=False)


# original lines - Mewtwo talks while it wipes the field
MEWTWO_RAMPAGE = ["You are all beneath me.", "Is this truly all your world can offer?",
                  "I was created to surpass every Pokemon. Witness it.", "Kneel. Or be erased."]
MEWTWO_WIN = "Remember the name. Mewtwo."


class Rampage(Cutscene):
    """Mewtwo has had enough: eye close-up, it rises in a storm of psychic power with rocks lifting off the
    ground, says its line, then a psychic shockwave rips through everyone nearby (action)."""

    BLAST_PAD = 0.9

    def __init__(self, pid, line, action, focus=None, size=None, speaker="mewtwo"):
        from .audio import voice_length, voice_path
        import os
        vp = voice_path(speaker, line)
        self.line_len = voice_length(vp) if os.path.exists(vp) else len(line) * 0.075
        dur = 0.8 + max(2.2, self.line_len) + self.BLAST_PAD + 0.9
        super().__init__("rampage", dur, focus=focus, zoom=1.7, title="MEWTWO IS UNSTOPPABLE", color=(170, 80, 255),
                         portrait=pid, action=action, action_at=(dur - 0.9) / dur, cry=pid, sound=None, size=size)
        self.line, self.speaker = line, speaker
        self.spoke = False
        self.rocks = [(random.uniform(0, math.tau), random.uniform(140, 300), random.uniform(10, 24),
                       random.uniform(0.4, 1.2)) for _ in range(22)]

    EYE_T = 0.8

    def update(self, dt, renderer):
        if self.t >= self.EYE_T and not self.spoke:
            self.spoke = True
            AUDIO.voice(self.speaker, self.line)
            AUDIO.play("tera", 0.6)
        super().update(dt, renderer)

    def draw(self, surf):
        self._begin_draw(surf)
        t, d = self.t, self.duration
        if t < self.EYE_T:
            surf.fill((0, 0, 0))
            hgt = self.H * 0.3
            eye_strip(surf, self.portrait, (0, self.H / 2 - hgt / 2, self.W, hgt), t, self.color)
            self._end_draw(surf)
            return
        q = t - self.EYE_T
        k = _ease((d - t) / 0.4)
        self.anchors = []
        bg = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        bg.fill((20, 6, 34, int(235 * k)))
        surf.blit(bg, (0, 0))
        vig = _vignette((self.W, self.H))
        vig.set_alpha(int(255 * k))
        surf.blit(vig, (0, 0))
        cx, cy = self.W / 2, self.H * 0.5
        for i in range(4):  # distortion rings pulsing out of it
            rr = ((q * 260 + i * 120) % 520)
            pygame.draw.circle(surf, _lighter(self.color, 0.3), (int(cx), int(cy - 60)), int(rr), 2)
        for a, r, size, sp in self.rocks:  # rocks torn off the ground, orbiting and rising
            ang = a + q * sp * 1.6
            x = cx + math.cos(ang) * r
            y = cy + 120 - q * 60 * sp + math.sin(ang) * r * 0.35
            pts = [(x + math.cos(ang + j * 2.1) * size, y + math.sin(ang + j * 2.1) * size * 0.8) for j in range(3)]
            pygame.draw.polygon(surf, (110, 90, 120), pts)
            pygame.draw.polygon(surf, _lighter(self.color, 0.4), pts, 2)
        float_y = math.sin(q * 2.5) * 10 - min(1.0, q / 0.6) * 40
        self._draw_glowing(surf, self.portrait, 330, (cx, cy + 170 + float_y))
        self._draw_aura_fx(surf, k)
        pop = _ease(q / 0.2)
        draw_plate(surf, self.title, (cx, self.H * 0.14), 34, self.color, 1.5 - 0.5 * pop, int(255 * k))
        if q < self.line_len + 0.8:
            subtitle(surf, self.speaker, self.line, q, self.line_len)
        if self.flash > 0:
            f = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            f.fill((235, 200, 255, int(255 * min(1.0, self.flash / 0.35))))
            surf.blit(f, (0, 0))
        self._end_draw(surf)
