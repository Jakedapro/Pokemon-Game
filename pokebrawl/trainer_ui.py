"""Trainer card (rank, record, streaks), the legendary collection and the legendary encounter you get after
some wins: the legendary appears, you throw a ball, it wobbles... and it's yours."""
import math
import random
import time

import pygame

from . import gfx, profile, ui
from .app import Scene
from .audio import AUDIO
from .gfx import H, SPRITES, W
from .tournament import short_name

STAT_NAMES = [("hp", "HP"), ("atk", "Attack"), ("def", "Defense"), ("spa", "Sp. Atk"), ("spd", "Sp. Def"),
              ("spe", "Speed")]


def fit(pid, w, h, shiny=False):
    """A sprite scaled to fit inside w x h (wide Pokemon get shrunk instead of spilling out)."""
    img = SPRITES.get(pid, h, shiny=shiny)
    if img.get_width() > w:
        img = SPRITES.get(pid, max(8, int(h * w / img.get_width())), shiny=shiny)
    return img


def type_row(surf, types, cx, y, size=14):
    f = gfx.font(size, False)
    widths = [f.size(t.upper())[0] + 16 for t in types]
    x = cx - (sum(widths) + 6 * (len(types) - 1)) / 2
    for t, w in zip(types, widths):
        gfx.pill(surf, t.upper(), (x + w / 2, y), gfx.type_color(t, 0), size)
        x += w + 6


def sparkles(surf, center, radius, t, seed=0, n=10, color=(255, 240, 150)):
    """Shiny sparkles: little four-point stars popping around a sprite."""
    rng = random.Random(seed)
    for i in range(n):
        ph = rng.random() * 6
        k = (t * 1.3 + ph) % 1.6
        if k > 1.0:
            continue
        a = rng.random() * math.tau
        d = radius * (0.4 + 0.6 * rng.random())
        x, y = center[0] + math.cos(a) * d, center[1] + math.sin(a) * d
        s = 3 + 9 * math.sin(k * math.pi)
        pygame.draw.polygon(surf, color, [(x, y - s), (x + s * 0.25, y), (x, y + s), (x - s * 0.25, y)])
        pygame.draw.polygon(surf, color, [(x - s, y), (x, y + s * 0.25), (x + s, y), (x, y - s * 0.25)])


def rank_bar(surf, rect, data, t):
    rk = profile.rank_of(data["rp"])
    r = pygame.Rect(rect)
    pygame.draw.rect(surf, (14, 18, 26), r, border_radius=r.h // 2)
    if rk["next"]:
        frac = (data["rp"] - rk["floor"]) / max(1, rk["next"] - rk["floor"])
    else:
        frac = 1.0
    fill = r.inflate(-6, -6)
    fill.w = max(fill.h, int(fill.w * min(1.0, frac)))
    pygame.draw.rect(surf, rk["color"], fill, border_radius=fill.h // 2)
    shine = (math.sin(t * 2) * 0.5 + 0.5) * fill.w
    pygame.draw.line(surf, (255, 255, 255), (fill.x + max(0, shine - 20), fill.y + 3),
                     (fill.x + shine, fill.y + 3), 2)
    return rk


class TrainerCard(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.buttons = [ui.Button((40, 900, 640, 110), "Legend collection", (130, 60, 200), 34,
                                  "every legendary and mythical you've caught", tag="legends", icon=150),
                        ui.Button((40, 1160, 200, 70), "Back", ui.PANEL2, 24, tag="back")]

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for b in self.buttons:
                if b.hit(pos):
                    if b.tag == "back":
                        self.app.pop()
                    else:
                        self.app.push(LegendCollection(self.app))

    def draw(self, surf):
        t = self.app.t
        data = profile.load()
        ui.menu_background(surf, t)
        ui.header(surf, "Trainer card", self.app.settings.get("name", "Trainer"))
        ui.panel(surf, (40, 180, 640, 330), ui.SCREEN2, 18)
        rk = profile.rank_of(data["rp"])
        ui.rank_badge(surf, (170, 320), 80, rk, t)
        gfx.text(surf, rk["label"], (290, 270), 34 if len(rk["label"]) < 14 else 28, rk["color"], ui.SHELL_DARK, 2,
                 anchor="midleft")
        gfx.text(surf, f"{data['rp']} RP", (290, 320), 24, ui.TEXT, None, 0, anchor="midleft")
        rank_bar(surf, (290, 350, 360, 26), data, t)
        if rk["next"]:
            nxt = profile.rank_of(rk["next"])["label"]
            gfx.text(surf, f"{rk['next'] - data['rp']} RP to {nxt}", (290, 396), 16, ui.MUTED, None, 0,
                     anchor="midleft", chunky=False)
        else:
            gfx.text(surf, "Top rank. Respect.", (290, 396), 16, ui.SIGNAL, None, 0, anchor="midleft", chunky=False)
        gfx.text(surf, f"Peak: {profile.rank_of(data['peak_rp'])['label']}", (290, 440), 16, ui.MUTED, None, 0,
                 anchor="midleft", chunky=False)
        # the ladder
        for i, (name, need, col) in enumerate(profile.RANKS):
            x = 96 + i * 132
            fake = {"tier": i, "div": "", "color": col}
            on = data["rp"] >= need
            if i:
                pygame.draw.line(surf, col if on else (50, 58, 72), (x - 132 + 34, 572), (x - 34, 572), 4)
            ui.rank_badge(surf, (x, 572), 30 if on else 22, fake, t if on else 0)
            if not on:
                dim = pygame.Surface((70, 70), pygame.SRCALPHA)
                pygame.draw.circle(dim, (24, 33, 46, 170), (35, 35), 26)
                surf.blit(dim, (x - 35, 537))
            gfx.text(surf, name, (x, 624), 15, ui.TEXT if on else (110, 120, 136), None, 0)
            gfx.text(surf, f"{need} RP", (x, 646), 13, ui.MUTED, None, 0, chunky=False)
        # record
        wins = sum(v[0] for k in ("vs", "bots") for v in data[k].values())
        losses = sum(v[1] for k in ("vs", "bots") for v in data[k].values())
        pvp_w = sum(v[0] for v in data["vs"].values())
        pvp_l = sum(v[1] for v in data["vs"].values())
        stats = [("Wins", wins), ("Losses", losses),
                 ("Win rate", f"{int(100 * wins / max(1, wins + losses))}%"),
                 ("PvP", f"{pvp_w}-{pvp_l}"),
                 ("Streak", data["streak"] if data["streak"] >= 0 else f"L{-data['streak']}"),
                 ("Best streak", data["best_streak"])]
        for i, (label, val) in enumerate(stats):
            x, y = 40 + (i % 3) * 216, 690 + (i // 3) * 100
            ui.panel(surf, (x, y, 208, 88), ui.SCREEN2, 12)
            gfx.text(surf, str(val), (x + 104, y + 36), 30, ui.TEXT, None, 0)
            gfx.text(surf, label, (x + 104, y + 70), 15, ui.MUTED, None, 0, chunky=False)
        n = len(profile.legendary_pool(self.app.dex))
        self.buttons[0].sub = f"{len(data['legends'])} / {n} caught"
        for b in self.buttons:
            b.draw(surf)


class LegendCollection(Scene):
    COLS, CW, CH, TOP = 4, 160, 176, 170

    def __init__(self, app):
        super().__init__(app)
        self.pool = profile.legendary_pool(app.dex)
        self.scroll = 0.0
        self.detail = None
        self.back = ui.Button((40, 1180, 200, 70), "Back", ui.PANEL2, 24)
        self.data = profile.load()

    def _cell(self, i):
        x = 40 + (i % self.COLS) * self.CW
        y = self.TOP + (i // self.COLS) * self.CH - self.scroll
        return pygame.Rect(x, y, self.CW - 12, self.CH - 12)

    def handle(self, ev, pos):
        if self.detail is not None:
            if ev.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                self.detail = None
            return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        if ev.type == pygame.MOUSEWHEEL:
            rows = (len(self.pool) + self.COLS - 1) // self.COLS
            self.scroll = max(0, min(rows * self.CH - 980, self.scroll - ev.y * 60))
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.back.hit(pos):
                self.app.pop()
                return
            if pos[1] < self.TOP or pos[1] > 1160:
                return
            for i, e in enumerate(self.pool):
                if self._cell(i).collidepoint(pos) and e["key"] in self.data["legends"]:
                    self.detail = e
                    self.detail_t = self.app.t
                    AUDIO.cry(e["id"], 0.8)

    def draw(self, surf):
        t = self.app.t
        ui.menu_background(surf, t)
        have = self.data["legends"]
        shinies = sum(1 for v in have.values() if v.get("shiny"))
        sub = f"{len(have)} of {len(self.pool)} caught" + (f"  -  {shinies} shiny" if shinies else "")
        clip = surf.get_clip()
        surf.set_clip(pygame.Rect(0, self.TOP - 8, W, 1160 - self.TOP + 8))
        for i, e in enumerate(self.pool):
            r = self._cell(i)
            if r.bottom < self.TOP - 10 or r.top > 1170:
                continue
            got = have.get(e["key"])
            col = (40, 30, 64) if got else (26, 32, 44)
            if got and got.get("shiny"):
                col = (70, 56, 20)
            ui.panel(surf, r, col, 12)
            if got:
                img = fit(e["id"], r.w - 16, 100, got.get("shiny", False))
                surf.blit(img, img.get_rect(center=(r.centerx, r.y + 70)))
                if got.get("shiny"):
                    sparkles(surf, (r.centerx, r.y + 70), 50, t, e["id"], 5)
                gfx.text(surf, short_name(e)[:13], (r.centerx, r.bottom - 26), 15, ui.TEXT, None, 0)
            else:
                img = gfx.silhouette(fit(e["id"], r.w - 16, 100), (8, 10, 16))
                surf.blit(img, img.get_rect(center=(r.centerx, r.y + 70)))
                gfx.text(surf, "???", (r.centerx, r.bottom - 26), 15, (90, 100, 116), None, 0)
            gfx.text(surf, f"#{e['id']:03d}", (r.x + 10, r.y + 14), 12, (110, 120, 140), None, 0,
                     anchor="midleft", chunky=False)
        surf.set_clip(clip)
        ui.header(surf, "Legends", sub)
        # progress bar along the header's bottom edge
        frac = len(have) / max(1, len(self.pool))
        pygame.draw.rect(surf, (14, 18, 26), (40, 150, 640, 10), border_radius=5)
        pygame.draw.rect(surf, ui.SIGNAL, (40, 150, max(10, int(640 * frac)), 10), border_radius=5)
        self.back.draw(surf)
        if not have:
            gfx.text(surf, "Win battles to meet legendaries", (W / 2 + 110, 1215), 17, ui.MUTED, None, 0,
                     chunky=False)
        if self.detail is not None:
            self._draw_detail(surf, self.detail, t - self.detail_t)

    def _draw_detail(self, surf, e, q):
        got = self.data["legends"][e["key"]]
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 190))
        surf.blit(shade, (0, 0))
        k = min(1.0, q / 0.25)
        r = pygame.Rect(0, 0, 620, 920)
        r.center = (W / 2, H / 2 + (1 - k) * 80)
        ui.panel(surf, r, ui.SCREEN2, 22, border=gfx.type_color(e["types"][0], 0))
        img = fit(e["id"], 540, 300, got.get("shiny", False))
        surf.blit(img, img.get_rect(center=(r.centerx, r.y + 210 + math.sin(q * 2) * 6)))
        if got.get("shiny"):
            sparkles(surf, (r.centerx, r.y + 210), 150, q, e["id"], 14)
            gfx.pill(surf, "SHINY", (r.right - 70, r.y + 36), (200, 150, 30), 18)
        gfx.text(surf, short_name(e), (r.centerx, r.y + 400), 40, ui.TEXT, ui.SHELL_DARK, 3)
        kind = "Mythical" if e["mythical"] else "Legendary"
        gfx.text(surf, f"#{e['id']:03d}  -  {kind}  -  Gen {e['gen']}", (r.centerx, r.y + 446), 17, ui.MUTED,
                 None, 0, chunky=False)
        type_row(surf, e["types"], r.centerx, r.y + 486, 16)
        total = sum(e["stats"].values())
        for i, (key, label) in enumerate(STAT_NAMES):
            y = r.y + 540 + i * 44
            v = e["stats"][key]
            gfx.text(surf, label, (r.x + 40, y), 18, ui.MUTED, None, 0, anchor="midleft", chunky=False)
            gfx.text(surf, str(v), (r.x + 200, y), 18, ui.TEXT, None, 0, anchor="midright")
            pygame.draw.rect(surf, (14, 18, 26), (r.x + 220, y - 9, 360, 18), border_radius=9)
            w = int(360 * min(1.0, v / 200) * min(1.0, q / 0.6))
            col = gfx.hsv(min(v, 180) / 180 * 0.35)
            pygame.draw.rect(surf, col, (r.x + 220, y - 9, max(18, w), 18), border_radius=9)
        gfx.text(surf, f"Total {total}", (r.right - 40, r.y + 816), 18, ui.SIGNAL, None, 0, anchor="midright")
        when = time.strftime("%b %d, %Y", time.localtime(got.get("t", 0)))
        gfx.text(surf, f"Caught {when}", (r.x + 40, r.y + 816), 16, ui.MUTED, None, 0, anchor="midleft",
                 chunky=False)
        gfx.text(surf, "tap anywhere to close", (r.centerx, r.bottom - 36), 14, ui.MUTED, None, 0, chunky=False)


class LegendEncounter(Scene):
    """After a win: a legendary appears. Throw the ball, three wobbles, caught. (You always catch it -
    you earned it.)"""

    def __init__(self, app, pid, shiny=False):
        super().__init__(app)
        self.e = app.dex.get(pid)
        self.shiny = shiny
        self.t = 0.0
        self.thrown = None
        self.caught = False
        self.saved = False
        self.rng = random.Random(pid)
        self.parts = []
        self.btn = ui.Button((160, 1080, 400, 100), "Throw Poke Ball", ui.SHELL, 34)
        self.done_btn = ui.Button((160, 1080, 400, 100), "Awesome", (34, 140, 88), 34)
        SPRITES.get(self.e["id"], 340, shiny=shiny)   # load before the reveal
        AUDIO.play("boom")

    def handle(self, ev, pos):
        click = ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1
        key = ev.type == pygame.KEYDOWN and ev.key in (pygame.K_SPACE, pygame.K_RETURN)
        if self.caught and self.thrown is not None and self.t - self.thrown > 6.2:
            if (click and self.done_btn.hit(pos)) or key or (ev.type == pygame.KEYDOWN and
                                                              ev.key == pygame.K_ESCAPE):
                self.app.pop()
            return
        if self.thrown is None and self.t > 2.2 and ((click and self.btn.hit(pos)) or key):
            self.thrown = self.t
            AUDIO.play("ball")

    def update(self, dt):
        self.t += dt
        if self.t - dt < 0.6 <= self.t:
            AUDIO.cry(self.e["id"], 1.0)
            if self.shiny:
                AUDIO.play("tera")
        if self.thrown is not None:
            q = self.t - self.thrown
            for i, at in enumerate((1.6, 2.5, 3.4)):
                if q - dt < at <= q:
                    AUDIO.play("wiggle")
            if q - dt < 4.3 <= q:
                self.caught = True
                AUDIO.play("catch")
                if not self.saved:
                    profile.add_legend(self.e, self.shiny)
                    self.saved = True
                for _ in range(60):
                    a = self.rng.random() * math.tau
                    v = self.rng.uniform(150, 520)
                    self.parts.append([W / 2, 760, math.cos(a) * v, math.sin(a) * v - 200, 1.4,
                                       gfx.hsv(self.rng.random(), 0.5, 1.0)])
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 600 * dt
            p[4] -= dt
        self.parts = [p for p in self.parts if p[4] > 0]

    def _ball(self, surf, x, y, r, angle=0.0):
        ball = pygame.Surface((r * 2 + 8, r * 2 + 8), pygame.SRCALPHA)
        c = r + 4
        pygame.draw.circle(ball, (16, 18, 24), (c, c), r + 3)
        pygame.draw.circle(ball, (240, 242, 246), (c, c), r)
        pygame.draw.rect(ball, (225, 50, 55), (c - r, c - r, r * 2, r), border_top_left_radius=r,
                         border_top_right_radius=r)
        pygame.draw.line(ball, (16, 18, 24), (c - r, c), (c + r, c), max(2, r // 6))
        pygame.draw.circle(ball, (16, 18, 24), (c, c), r // 3)
        pygame.draw.circle(ball, (250, 250, 252), (c, c), r // 3 - 3)
        if angle:
            ball = pygame.transform.rotate(ball, angle)
        surf.blit(ball, ball.get_rect(center=(x, y)))

    def draw(self, surf):
        e, t = self.e, self.t
        col = gfx.type_color(e["types"][0], 0)
        surf.fill(tuple(int(c * 0.18) for c in col))
        # light rays behind the legendary
        rays = pygame.Surface((W, H), pygame.SRCALPHA)
        for i in range(16):
            a = i / 16 * math.tau + t * 0.25
            pts = [(W / 2, 560), (W / 2 + math.cos(a - 0.08) * 1400, 560 + math.sin(a - 0.08) * 1400),
                   (W / 2 + math.cos(a + 0.08) * 1400, 560 + math.sin(a + 0.08) * 1400)]
            pygame.draw.polygon(rays, (*col, 26), pts)
        surf.blit(rays, (0, 0))
        reveal = min(1.0, max(0.0, (t - 0.3) / 0.6))
        q = (t - self.thrown) if self.thrown is not None else None
        inside = q is not None and q > 0.75
        if not inside:
            img = fit(e["id"], 640, 340, self.shiny)
            if reveal < 1:
                img = gfx.silhouette(img, (0, 0, 0)) if reveal < 0.5 else img
            if q is not None and q > 0.55:   # sucked into the ball
                s = max(0.02, 1 - (q - 0.55) / 0.2)
                img = pygame.transform.smoothscale(img, (max(1, int(img.get_width() * s)),
                                                         max(1, int(img.get_height() * s))))
                tint = img.copy()
                tint.fill((255, 120, 120, 0), special_flags=pygame.BLEND_RGBA_ADD)
                img = tint
            y = 720 + math.sin(t * 1.6) * 10
            surf.blit(img, img.get_rect(midbottom=(W / 2, y)))
            if self.shiny and reveal >= 1:
                sparkles(surf, (W / 2, y - 170), 190, t, e["id"], 16)
        if t < 0.35:  # white flash on arrival
            fl = pygame.Surface((W, H))
            fl.fill((255, 255, 255))
            fl.set_alpha(int(255 * (1 - t / 0.35)))
            surf.blit(fl, (0, 0))
        title = "A wild shiny" if self.shiny else "A wild legendary"
        if not self.caught:
            gfx.text(surf, title.upper() + " APPEARED!", (W / 2, 170), 28, ui.SIGNAL, ui.SHELL_DARK, 3,
                     alpha=int(255 * reveal))
            gfx.title_text(surf, short_name(e).upper(), (W / 2, 250), 64 if len(short_name(e)) < 11 else 48,
                           alpha=int(255 * reveal), color=(255, 240, 160) if self.shiny else (255, 255, 255))
            type_row(surf, e["types"], W / 2, 320, 16)
        if q is not None:
            if q < 0.75:   # the throw: an arc from the bottom
                k = q / 0.75
                x = W / 2 + (1 - k) * 160
                y = 1150 - k * 520 + math.sin(k * math.pi) * -260
                self._ball(surf, x, y, 26, angle=-k * 900)
            else:
                # drop to the ground, then wobble three times
                land = min(1.0, (q - 0.75) / 0.4)
                y = 600 + land * 160 - abs(math.sin(land * math.pi * 2)) * 40 * (1 - land)
                ang = 0.0
                for at in (1.6, 2.5, 3.4):
                    if at - 0.3 < q < at + 0.3:
                        ang = math.sin((q - at + 0.3) / 0.6 * math.tau) * 22
                self._ball(surf, W / 2, y, 34, angle=ang)
                if self.caught:
                    for s_ in range(3):  # the three stars
                        a = -math.pi / 2 + (s_ - 1) * 0.6
                        d = 60 + min(1.0, (q - 4.3) / 0.4) * 30
                        x, yy = W / 2 + math.cos(a) * d, y + math.sin(a) * d
                        pygame.draw.circle(surf, (255, 230, 120), (int(x), int(yy)), 6)
        for x, y, vx, vy, life, c in self.parts:
            pygame.draw.circle(surf, c, (int(x), int(y)), max(1, int(5 * life)))
        if self.caught:
            k = min(1.0, (q - 4.3) / 0.4)
            gfx.title_text(surf, "GOTCHA!", (W / 2, 220), 84, alpha=int(255 * k), scale=1.6 - 0.6 * k,
                           color=(255, 230, 110))
            gfx.text(surf, f"{short_name(e)} joined your collection", (W / 2, 310), 24, ui.TEXT, ui.SHELL_DARK, 2,
                     alpha=int(255 * k))
            if q > 5.2:
                n = len(profile.load()["legends"])
                gfx.text(surf, f"{n} / {len(profile.legendary_pool(self.app.dex))} legends", (W / 2, 900), 22,
                         ui.SIGNAL, None, 0)
            if q > 6.2:
                self.done_btn.draw(surf)
        elif self.thrown is None and t > 2.2:
            self.btn.draw(surf)
