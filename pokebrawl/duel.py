"""The final fight as a movie: when the last two Pokemon face off, the showcase switches from the arena to a
duel stage - big fighters on a sky split diagonally into their colors, big HP bars, every move called out and
animated across the screen, damage numbers, slow motion on crits and super-effective hits, and eye-to-eye
"clash" beats. The battle itself keeps running in the sim; this only changes how it's shown."""
import math
import random

import pygame

from . import gfx
from .audio import AUDIO
from .cinematics import AttackFX, Cutscene, _ease, _lighter, _vignette, draw_plate, eye_strip
from .gfx import INK, SPRITES, WHITE


class DuelView:
    CLASH_EVERY = 9.0
    CLASH_LEN = 1.1

    def __init__(self, scene, a, b):
        self.sc = scene
        self.W, self.H = scene.size
        self.uids = (a.uid, b.uid)
        self.colors = {a.uid: gfx.TEAM_COLORS[a.team % 4], b.uid: gfx.TEAM_COLORS[b.team % 4]}
        if self.colors[a.uid] == self.colors[b.uid]:
            self.colors[b.uid] = (255, 200, 60)
        self.t = 0.0
        self.attacks = []          # [AttackFX, t]
        self.pops = []             # [text, x, y, t, color, size]
        self.callouts = []         # [text, color, uid, t]
        self.shake = {u: 0.0 for u in self.uids}
        self.hitflash = {u: 0.0 for u in self.uids}
        self.hp_shown = {u: self._unit(u).mon.hp_frac() for u in self.uids}
        self.slowmo = 0.0
        self.punch = 0.0
        self.big_text = None       # (text, color, t)
        self.clash = None          # time a clash beat started
        self.next_clash = 4.0
        self.fight_t = 0.0         # sim seconds the duel has been running
        self.sudden = None         # time Sudden Death started
        self._drain = {}
        self.helper = Cutscene("duel", 999, size=scene.size, sound=None)  # borrows the aura/glow drawing
        self.helper.shatter = False
        self.rng = random.Random(7)
        self._bg = None
        AUDIO.play("count")

    # ------------------------------------------------------------------ layout
    def _unit(self, uid):
        return self.sc.sim.by_id[uid]

    def pos(self, uid):
        """Where each fighter stands (screen): first one low-left facing right, second high-right facing left."""
        if uid == self.uids[0]:
            return self.W * 0.28, self.H * 0.74
        return self.W * 0.72, self.H * 0.52

    def height(self, uid):
        base = min(self.W, self.H * 0.6)
        u = self._unit(uid)
        grow = 1.35 if u.mon.gmaxed else 1.0
        return int(base * (0.5 if uid == self.uids[0] else 0.42) * grow) // 8 * 8

    # ------------------------------------------------------------------ battle events
    def time_scale(self):
        """How fast the sim runs during the duel (slower than the arena, much slower in slow motion)."""
        if self.clash is not None:
            return 0.0
        return 0.3 if self.slowmo > 0 else 0.7

    def feed(self, events):
        for ev in events:
            kind = ev[0]
            if kind == "use" and ev[1] in self.uids:
                uid = ev[1]
                other = self.uids[1] if uid == self.uids[0] else self.uids[0]
                (sx, sy), (ex, ey) = self.pos(uid), self.pos(other)
                cls = "phys" if ev[4] in ("melee", "dash") else "spec"
                self.attacks.append([AttackFX(ev[3], cls, (sx, sy - self.height(uid) * 0.45),
                                              (ex, ey - self.height(other) * 0.45)), 0.0])
                self.callouts.append([ev[2].upper(), gfx.type_color(ev[3], 0), uid, 0.0])
                self.callouts = self.callouts[-2:]
            elif kind == "hit" and ev[1] in self.uids:
                uid, pct, eff, crit = ev[1], ev[2], ev[3], ev[4]
                self.shake[uid] = 0.45
                self.hitflash[uid] = 0.25
                x, y = self.pos(uid)
                col = (255, 120, 120) if eff > 1 else (230, 230, 240) if eff == 1 else (170, 170, 190)
                self.pops.append([f"-{pct:g}%", x + self.rng.uniform(-40, 40), y - self.height(uid) * 0.9, 0.0, col,
                                  40 if (crit or eff > 1) else 30])
                if crit or eff > 1:
                    self.slowmo = 0.6
                    self.punch = 0.3
                    self.big_text = ("CRITICAL HIT!" if crit else "SUPER EFFECTIVE!", (255, 90, 90) if crit else
                                     (255, 200, 60), 0.0)
                    AUDIO.play("hit_super", 0.9)

    # ------------------------------------------------------------------ timeline
    def update(self, dt):
        self.t += dt
        for u in self.uids:
            self.shake[u] = max(0.0, self.shake[u] - dt)
            self.hitflash[u] = max(0.0, self.hitflash[u] - dt)
            unit = self.sc.sim.by_id.get(u)
            if unit:
                cur, goal = self.hp_shown[u], unit.mon.hp_frac()
                step = dt * 0.8
                self.hp_shown[u] = goal if abs(goal - cur) <= step else cur + step * (1 if goal > cur else -1)
        for a in self.attacks:
            a[1] += dt
        self.attacks = [a for a in self.attacks if a[1] < 0.7]
        for p in self.pops:
            p[3] += dt
        self.pops = [p for p in self.pops if p[3] < 1.1]
        for c in self.callouts:
            c[3] += dt
        self.callouts = [c for c in self.callouts if c[3] < 1.3]
        self.slowmo = max(0.0, self.slowmo - dt)
        self.punch = max(0.0, self.punch - dt)
        if self.big_text and self.t - self.big_text[2] > 1.2 and self.big_text[2] > 0:
            self.big_text = None
        elif self.big_text and self.big_text[2] == 0.0:
            self.big_text = (self.big_text[0], self.big_text[1], self.t)
        alive = all(self.sc.sim.by_id[u].alive for u in self.uids)
        if self.clash is None and alive and self.t >= self.next_clash:
            self.clash = self.t
            AUDIO.play("boom", 0.7)
            AUDIO.play("tera", 0.6)
        if self.clash is not None and self.t - self.clash >= self.CLASH_LEN:
            self.clash = None
            self.next_clash = self.t + self.CLASH_EVERY
        self.helper.t += dt
        self.helper._update_aura(dt)

    SUDDEN_AFTER = 18.0

    def sim_tick(self, sim_dt):
        """Called with the sim time each step: past SUDDEN_AFTER both fighters lose HP faster and faster (it
        bypasses abilities like Wonder Guard, so every duel ends). The KO counts for the other fighter."""
        self.fight_t += sim_dt
        if self.fight_t < self.SUDDEN_AFTER:
            return
        if self.sudden is None:
            self.sudden = self.t
            AUDIO.play("boom", 0.9)
        rate = 0.02 + 0.012 * (self.fight_t - self.SUDDEN_AFTER)
        sim = self.sc.sim
        for i, uid in enumerate(self.uids):
            u, other = sim.by_id[uid], sim.by_id[self.uids[1 - i]]
            if not u.alive:
                continue
            self._drain[uid] = self._drain.get(uid, 0.0) + u.mon.maxhp * rate * sim_dt
            if self._drain[uid] >= 1:
                whole = int(self._drain[uid])
                self._drain[uid] -= whole
                sim._hurt(u, whole, other, chip=True, guard=False)

    def interest(self):
        return 2 if (self.clash is not None or self.slowmo > 0 or self.t < 2.5) else 1

    # ------------------------------------------------------------------ drawing
    def _background(self):
        if self._bg is None:
            bg = pygame.Surface((self.W, self.H))
            a, b = (self._unit(u).mon.types[0] for u in self.uids)
            ca, cb = gfx.type_color(a, 2), gfx.type_color(b, 2)
            for y in range(0, self.H, 4):  # each side: its fighter's type color, darker toward the top
                k = 0.35 + 0.65 * y / self.H
                pygame.draw.line(bg, tuple(int(c * k) for c in ca), (0, y), (self.W, y), 4)
            right = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            for y in range(0, self.H, 4):
                k = 0.35 + 0.65 * (1 - y / self.H)
                pygame.draw.line(right, (*tuple(int(c * k) for c in cb), 255), (0, y), (self.W, y), 4)
            mask = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            pygame.draw.polygon(mask, (255, 255, 255, 255), [(self.W * 0.62, 0), (self.W, 0), (self.W, self.H),
                                                             (self.W * 0.38, self.H)])
            right.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            bg.blit(right, (0, 0))
            self._bg = bg
        return self._bg

    def _seam(self, surf):
        """Crackling lightning along the diagonal split."""
        x0, x1 = self.W * 0.62, self.W * 0.38
        pts = []
        for i in range(13):
            q = i / 12
            jitter = self.rng.uniform(-14, 14)
            pts.append((x0 + (x1 - x0) * q + jitter, self.H * q))
        pygame.draw.lines(surf, (255, 255, 255), False, pts, 5)
        pygame.draw.lines(surf, (255, 240, 180), False, pts, 2)

    def _hp_bar(self, surf, uid, rect, right):
        u = self.sc.sim.by_id[uid]
        col = self.colors[uid]
        x, y, w, h = rect
        pygame.draw.rect(surf, (0, 0, 0), (x - 3, y - 3, w + 6, h + 6), border_radius=8)
        pygame.draw.rect(surf, (40, 40, 52), (x, y, w, h), border_radius=6)
        frac = max(0.0, self.hp_shown[uid])
        fw = int(w * frac)
        fill = gfx.hp_color(frac)
        if right:
            pygame.draw.rect(surf, fill, (x + w - fw, y, fw, h), border_radius=6)
        else:
            pygame.draw.rect(surf, fill, (x, y, fw, h), border_radius=6)
        name = u.mon.name.upper()
        draw_plate(surf, name, (x + (w - 80 if right else 80), y - 30), 22, col, 1.0, angle=-3)
        gfx.text(surf, f"{int(math.ceil(frac * 100))}%", (x + (8 if right else w - 8), y + h / 2), 20, WHITE, INK, 2,
                 anchor="midleft" if right else "midright")

    def draw(self, surf):
        k = _ease(self.t / 0.4)
        surf.blit(self._background(), (0, 0))
        # speed lines in the sky
        for i in range(16):
            y = (i * 97 + self.t * 260) % self.H
            pygame.draw.line(surf, (255, 255, 255), (0, y), (self.W * 0.25, y + 30), 1)
            pygame.draw.line(surf, (255, 255, 255), (self.W * 0.75, self.H - y), (self.W, self.H - y - 30), 1)
        self._seam(surf)
        self.helper.anchors = []
        for uid in self.uids:  # fighters on glowing platforms
            u = self.sc.sim.by_id[uid]
            if not u.alive and self.hp_shown[uid] <= 0.01:
                continue
            x, y = self.pos(uid)
            hgt = self.height(uid)
            pygame.draw.ellipse(surf, (0, 0, 0), (x - hgt * 0.55, y - 18, hgt * 1.1, 40))
            pygame.draw.ellipse(surf, _lighter(self.colors[uid], 0.2), (x - hgt * 0.5, y - 14, hgt, 30), 3)
            dx = math.sin(self.shake[uid] * 70) * 12 * (self.shake[uid] > 0)
            bob = math.sin(self.t * 3 + (0 if uid == self.uids[0] else 1.5)) * 6
            flip = uid == self.uids[0]
            if self.hitflash[uid] > 0:
                img = SPRITES.get(u.mon.entry["id"], hgt, flip=flip, white=0.8)
                surf.blit(img, img.get_rect(midbottom=(x + dx, y + bob)))
            else:
                self.helper._draw_glowing(surf, u.mon.entry["id"], hgt, (x + dx, y + bob), flip=flip,
                                          color=self.colors[uid])
        self.helper._draw_aura_fx(surf, k)
        for fx, t in self.attacks:
            fx.draw(surf, t / 0.5)
        for text, x, y, t, col, size in self.pops:
            gfx.text(surf, text, (x, y - t * 70), size, col, INK, 3, alpha=int(255 * min(1.0, (1.1 - t) / 0.3)))
        for text, col, uid, t in self.callouts:  # move names called out next to the attacker
            x, y = self.pos(uid)
            pop = _ease(t / 0.15)
            alpha = int(255 * min(1.0, (1.3 - t) / 0.3))
            draw_plate(surf, text, (x, y - self.height(uid) - 40), 26, col, 1.4 - 0.4 * pop, alpha,
                       angle=-4 if uid == self.uids[0] else 4)
        # HP bars
        bw = self.W * 0.4
        self._hp_bar(surf, self.uids[0], (24, 140, bw, 22), False)
        self._hp_bar(surf, self.uids[1], (self.W - 24 - bw, 140, bw, 22), True)
        if self.big_text:
            q = self.t - self.big_text[2]
            draw_plate(surf, self.big_text[0], (self.W / 2, self.H * 0.36), 40, self.big_text[1],
                       1.5 - 0.5 * _ease(q / 0.15), int(255 * min(1.0, (1.2 - q) / 0.3)), angle=-5)
        if self.sudden is not None and self.t - self.sudden < 2.0:
            q = self.t - self.sudden
            draw_plate(surf, "SUDDEN DEATH", (self.W / 2, self.H * 0.3), 50, (255, 70, 70),
                       1.6 - 0.6 * _ease(q / 0.2), int(255 * min(1.0, (2.0 - q) / 0.4)), angle=-6)
        if self.sudden is not None:  # red pulse at the edges while the clock bleeds them out
            edge = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            a = int(60 + 50 * math.sin(self.t * 6))
            pygame.draw.rect(edge, (255, 30, 40, a), (0, 0, self.W, self.H), 26)
            surf.blit(edge, (0, 0))
        if self.t < 2.4:
            q = self.t
            draw_plate(surf, "FINAL BATTLE", (self.W / 2, self.H * 0.3), 52, (255, 200, 60),
                       1.6 - 0.6 * _ease(q / 0.25), int(255 * min(1.0, (2.4 - q) / 0.4)), angle=-6)
        if self.clash is not None:  # eye-to-eye beat
            q = self.t - self.clash
            shade = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 230))
            surf.blit(shade, (0, 0))
            hgt = self.H * 0.22
            a, b = (self.sc.sim.by_id[u] for u in self.uids)
            eye_strip(surf, a.mon.entry["id"], (0, self.H * 0.26, self.W, hgt), q, self.colors[a.uid], flip=True)
            eye_strip(surf, b.mon.entry["id"], (0, self.H * 0.54, self.W, hgt), q, self.colors[b.uid])
            draw_plate(surf, "CLASH!", (self.W / 2, self.H * 0.5), 56, (255, 230, 120), 1.5 - 0.5 * _ease(q / 0.2),
                       angle=-6)
        vig = _vignette((self.W, self.H))
        vig.set_alpha(160)
        surf.blit(vig, (0, 0))
        bar = 70
        pygame.draw.rect(surf, (0, 0, 0), (0, 0, self.W, bar))
        pygame.draw.rect(surf, (0, 0, 0), (0, self.H - bar, self.W, bar))
        if self.punch > 0:  # camera punch: zoom the whole frame in for a beat
            z = 1 + 0.08 * (self.punch / 0.3)
            frame = surf.copy()
            big = gfx.rescale(frame, (int(self.W * z), int(self.H * z)))
            surf.blit(big, ((self.W - big.get_width()) // 2, (self.H - big.get_height()) // 2))
