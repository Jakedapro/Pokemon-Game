"""Weather on the 1v1 battle screen: rain streaks, harsh sunlight, a sandstorm or snow, fading in and out
as the weather changes."""
import math
import random

import pygame

TINT = {"rain": (20, 40, 90, 70), "sun": (255, 150, 40, 46), "sand": (150, 110, 50, 80), "snow": (190, 215, 255, 50)}


class WeatherFX:
    def __init__(self, size):
        self.W, self.H = size
        self.kind = None
        self.level = 0.0       # 0..1 fade
        self.t = 0.0
        self.rng = random.Random(7)
        self.parts = []
        self._tints = {}

    def update(self, dt, kind):
        self.t += dt
        if kind != self.kind:   # fade the old weather out first, then the new one in
            self.level = max(0.0, self.level - dt * 1.5)
            if self.level <= 0:
                self.kind = kind
                self.parts = []
        elif kind:
            self.level = min(1.0, self.level + dt * 0.8)
        if not self.kind:
            return
        want = {"rain": 140, "sun": 0, "sand": 160, "snow": 110}[self.kind]
        fresh = not self.parts   # weather just started: fill the whole screen, not only the top
        while len(self.parts) < want:
            self.parts.append(self._spawn(initial=fresh))
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            if self.kind == "snow":
                p[0] += math.sin(self.t * 1.5 + p[4] * 6) * 20 * dt
        self.parts = [p for p in self.parts if -60 < p[0] < self.W + 60 and p[1] < self.H + 40]

    def _spawn(self, initial=False):
        r = self.rng
        y = r.uniform(-self.H, 0) if not initial else r.uniform(-self.H, self.H)
        if self.kind == "rain":
            return [r.uniform(-100, self.W + 100), y, -160, r.uniform(1100, 1500), r.random()]
        if self.kind == "snow":
            return [r.uniform(-20, self.W + 20), y, r.uniform(-20, 20), r.uniform(50, 130), r.random()]
        # sand: blows sideways
        return [r.uniform(-self.W, 0) if not initial else r.uniform(-60, self.W), r.uniform(0, self.H),
                r.uniform(500, 900), r.uniform(-30, 60), r.random()]

    def _tint(self, kind):
        if kind not in self._tints:
            s = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            r, g, b, a = TINT[kind]
            for y in range(0, self.H, 8):   # stronger toward the top
                k = 1.25 - 0.5 * y / self.H
                pygame.draw.rect(s, (r, g, b, int(min(255, a * k))), (0, y, self.W, 8))
            self._tints[kind] = s
        return self._tints[kind]

    def draw_back(self, surf):
        """Over the background, behind the Pokemon."""
        if not self.kind or self.level <= 0:
            return
        tint = self._tint(self.kind)
        tint.set_alpha(int(255 * self.level))
        surf.blit(tint, (0, 0))
        if self.kind == "sun":   # god rays from the top-right corner
            rays = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            ox, oy = self.W * 0.92, -40
            for i in range(7):
                a = math.radians(100 + i * 11 + math.sin(self.t * 0.5 + i) * 2)
                w = 0.035 + 0.015 * math.sin(self.t * 0.8 + i * 1.7)
                pts = [(ox, oy), (ox + math.cos(a - w) * 1800, oy + math.sin(a - w) * 1800),
                       (ox + math.cos(a + w) * 1800, oy + math.sin(a + w) * 1800)]
                pygame.draw.polygon(rays, (255, 220, 140, int(34 * self.level)), pts)
            surf.blit(rays, (0, 0))
            for k, rad in ((90, 110), (60, 70), (40, 40)):
                g = pygame.Surface((rad * 2, rad * 2), pygame.SRCALPHA)
                pygame.draw.circle(g, (255, 240, 180, int(k * self.level)), (rad, rad), rad)
                surf.blit(g, (ox - rad, oy + 40 - rad))

    def draw_front(self, surf):
        """In front of the Pokemon: the falling / blowing particles."""
        if not self.kind or self.level <= 0:
            return
        lay = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        a = self.level
        if self.kind == "rain":
            for x, y, vx, vy, s in self.parts:
                pygame.draw.line(lay, (180, 210, 255, int(150 * a * (0.5 + s * 0.5))), (x, y),
                                 (x + vx * 0.03, y + vy * 0.03), 2 if s > 0.7 else 1)
        elif self.kind == "snow":
            for x, y, vx, vy, s in self.parts:
                pygame.draw.circle(lay, (255, 255, 255, int(220 * a)), (int(x), int(y)), 2 + int(s * 3))
        elif self.kind == "sand":
            for x, y, vx, vy, s in self.parts:
                col = (220, 180, 110, int(170 * a))
                if s > 0.6:
                    pygame.draw.line(lay, col, (x, y), (x - 26 * s, y - 2), 2)
                else:
                    pygame.draw.circle(lay, col, (int(x), int(y)), 2)
        elif self.kind == "sun":
            flick = 0.5 + 0.5 * math.sin(self.t * 3)
            for i, (fx, fy, r) in enumerate(((0.75, 0.2, 16), (0.6, 0.38, 10), (0.42, 0.6, 22))):
                pygame.draw.circle(lay, (255, 230, 170, int((30 + 20 * flick) * a)), (int(self.W * fx),
                                                                                        int(self.H * fy)), r)
        surf.blit(lay, (0, 0))
