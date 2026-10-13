"""Draws the real-time arena from Sim snapshots: sprites, move labels, beams, blasts, megas, boss bars."""
import math
import random

import pygame

from . import gfx
from .audio import AUDIO
from .battlecore import STATUS_NAMES
from .gfx import H, INK, SPRITES, W, WHITE, type_color

STATUS_COLORS = {"brn": (235, 110, 50), "par": (230, 190, 40), "psn": (160, 70, 170), "tox": (130, 40, 150),
                 "slp": (140, 140, 160), "frz": (110, 200, 230)}


_GLOWS = {}


def glow(surf, x, y, r, color, strength=1.0):
    """Additive light: a soft radial glow added onto whatever is underneath (cached per size and color)."""
    r = max(4, int(r) // 4 * 4)
    key = (r, color, round(strength, 1))
    g = _GLOWS.get(key)
    if g is None:
        g = pygame.Surface((r * 2, r * 2))
        g.fill((0, 0, 0))
        for i in range(r, 0, -2):
            k = (1 - i / r) ** 1.6 * 0.55 * strength
            pygame.draw.circle(g, tuple(min(255, int(c * k)) for c in color), (r, r), i)
        if len(_GLOWS) > 400:
            _GLOWS.clear()
        _GLOWS[key] = g
    surf.blit(g, (int(x) - r, int(y) - r), special_flags=pygame.BLEND_RGB_ADD)


class FX:
    __slots__ = ("kind", "t", "life", "data")

    def __init__(self, kind, life, **data):
        self.kind, self.t, self.life, self.data = kind, 0.0, life, data


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "t", "color", "size", "grav")

    def __init__(self, x, y, vx, vy, life, color, size, grav=0.0):
        self.x, self.y, self.vx, self.vy, self.life, self.color, self.size, self.grav = x, y, vx, vy, life, color, size, grav
        self.t = 0.0


class UnitView:
    __slots__ = ("uid", "team", "form", "x", "y", "hp", "r", "flags", "status", "face", "anim", "target",
                 "flash", "spawn", "name", "seen", "tx", "ty")

    def __init__(self, row, name):
        self.uid = row[0]
        self.flash = 0.0
        self.spawn = 0.0
        self.name = name
        self.update(row)

    def update(self, row, smooth=False):
        (_, self.team, self.form, self.tx, self.ty, self.hp, self.r, self.flags, self.status, self.face,
         self.anim, self.target) = row
        if not smooth or not hasattr(self, "x") or abs(self.tx - self.x) + abs(self.ty - self.y) > 160:
            self.x, self.y = self.tx, self.ty


class ArenaRenderer:
    """mode: 'showcase' (big crowds, no per-unit HP bars) or 'team' (6v6 with HP bars/names)."""

    def __init__(self, dex, roster, mode="team", my_team=None, team_names=None, size=None):
        self.W, self.H = size or (W, H)   # the world and the screen are the same size (wide royales: landscape)
        self.dex = dex
        self.roster = {int(k): v for k, v in roster.items()}
        self.mode = mode
        self.my_team = my_team
        self.team_names = team_names or ["Team 1", "Team 2"]
        self.bg = gfx.arena_background(size=(self.W, self.H))
        self.world = gfx.new_surface((self.W, self.H))
        self.units = {}
        self.dead = []          # fading corpses
        self.fx = []
        self.particles = []
        self.projectiles = []
        self.weather = None
        self.t = 0.0
        self.cam = [self.W / 2, self.H / 2, 1.0]
        self.cam_target = None  # (x, y, zoom) override
        self.auto_zoom = mode == "showcase"
        self.selected = None
        self.labels_alive = 0
        self.show_units = True
        self.hidden = set()     # uids not drawn (still in their balls)
        self.shiny = set()      # shiny uids: they twinkle
        self.white = {}         # uid -> whiteness (capture effect)
        self.scale_over = {}    # uid -> scale override
        self.rng = random.Random(3)
        self.last_snapshot_t = 0.0
        self.shake = 0.0
        self.show_boss_bars = True
        self.smooth = False
        self.zone = None        # battle royale storm [cx, cy, r]
        self.kills = []         # (killer, victim, time) for the kill feed
        self.gold_from = 2      # teams from here on are event bosses (gold outline)
        self.domain = None
        self._cracks = None

    # ------------------------------------------------------------------ feeding state
    def feed(self, snap):
        seen = set()
        for row in snap["u"]:
            uid = row[0]
            seen.add(uid)
            if uid in self.units:
                self.units[uid].update(row, self.smooth)
            else:
                info = self.roster.get(uid, {})
                self.units[uid] = UnitView(row, info.get("name", "?"))
        for uid in list(self.units):
            if uid not in seen:
                del self.units[uid]
        self.projectiles = [] if snap.get("over") else snap["p"]
        self.weather = snap.get("w")
        self.zone = snap.get("z")
        for ev in snap["e"]:
            self._event(ev)

    def unit_name(self, uid):
        u = self.units.get(uid)
        if u:
            e = self.dex.all.get(u.form)
            if e:
                return e["name"]
        return self.roster.get(uid, {}).get("name", "?")

    def _label(self, uid, text, ttype, color=None):
        u = self.units.get(uid)
        if not u:
            return
        cap = 70 if self.mode == "showcase" else 30
        if self.labels_alive > cap:
            return
        up = text.upper()
        for f in self.fx:  # the same word already floating nearby: don't stack another copy on it
            if f.kind == "label" and f.data["text"] == up and f.t < 0.6 and \
                    abs(f.data["x"] - u.x) < 90 and abs(f.data["y"] - u.y) < 70:
                return
        self.fx.append(FX("label", 0.9, uid=uid, text=text.upper(), color=color or type_color(ttype),
                          x=u.x, y=u.y - u.r * 1.3))

    def _burst(self, x, y, color, n=8, speed=120, size=3, life=0.5, grav=0.0):
        for _ in range(n):
            a = self.rng.random() * math.tau
            s = speed * (0.4 + self.rng.random() * 0.8)
            self.particles.append(Particle(x, y, math.cos(a) * s, math.sin(a) * s, life * (0.6 + self.rng.random() * 0.6),
                                          color, size, grav))

    def _event(self, ev):
        kind = ev[0]
        if kind == "use":
            _, uid, name, mtype, mkind = ev
            self._label(uid, name, mtype)
            if mkind == "melee":
                AUDIO.play("melee", 0.6)
        elif kind == "charge":
            self._label(ev[1], ev[2], ev[3])
        elif kind == "label":
            self._label(ev[1], ev[2], ev[3])
        elif kind == "hit":
            _, uid, pct, eff, crit = ev
            AUDIO.play("hit_super" if eff > 1 else "hit_weak" if eff < 1 else "hit",
                       0.5 if self.mode == "showcase" else 0.8)
            u = self.units.get(uid)
            if u:
                u.flash = 0.14
                col = (255, 240, 120) if eff > 1 else (255, 255, 255)
                self._burst(u.x, u.y - u.r * 0.3, col, 5 if self.mode == "showcase" else 9, 110, 3, 0.35)
                if crit and self.mode != "showcase":
                    self._label(uid, "CRITICAL", "fighting")
                if eff > 1 and self.mode != "showcase":
                    self.fx.append(FX("pop", 0.6, x=u.x, y=u.y - u.r, text="SUPER EFFECTIVE", color=(255, 220, 80)))
        elif kind == "miss":
            AUDIO.play("miss", 0.5)
            u = self.units.get(ev[1])
            if u:
                self.fx.append(FX("pop", 0.7, x=u.x, y=u.y - u.r * 1.6, text="MISSED", color=(230, 230, 240)))
        elif kind == "beam":
            _, uid, x1, y1, x2, y2, mtype, width = ev
            AUDIO.play("beam", 0.5)
            self.fx.append(FX("beam", 0.28, x1=x1, y1=y1, x2=x2, y2=y2, type=mtype, w=width))
        elif kind == "melee":
            u, t = self.units.get(ev[1]), self.units.get(ev[2])
            if u and t:
                self.fx.append(FX("slash", 0.2, x=t.x, y=t.y - t.r * 0.3, a=self.rng.random() * math.pi))
        elif kind == "aoe":
            _, x, y, rad, mtype, delay, key = ev
            self.fx.append(FX("telegraph", delay, x=x, y=y, r=rad, type=mtype))
        elif kind == "blast":
            _, x, y, rad, mtype = ev
            AUDIO.play("blast", 0.55)
            self._blast(x, y, rad, mtype)
        elif kind == "impact":
            _, x, y, mtype = ev
            AUDIO.play("impact", 0.4)
            self._burst(x, y, type_color(mtype, 1), 6, 90, 3, 0.3)
        elif kind == "boom":
            _, x, y, rad = ev
            AUDIO.play("boom", 0.9)
            self.fx.append(FX("boom", 0.7, x=x, y=y, r=rad))
            self._burst(x, y, (255, 200, 80), 30, 260, 5, 0.7)
            self._burst(x, y, (120, 110, 110), 18, 120, 7, 1.0)
            self.shake = 0.35
        elif kind == "gmax":
            u = self.units.get(ev[1])
            if u:
                self._burst(u.x, u.y, (255, 60, 80), 40, 300, 6, 0.9)
                self._burst(u.x, u.y - u.r, (255, 150, 170), 24, 200, 4, 0.7)
                self._label(ev[1], "GIGANTAMAX!", "fire", (220, 30, 60))
                self.fx.append(FX("ring", 0.8, x=u.x, y=u.y, r=u.r * 3, color=(230, 40, 70), light=(255, 170, 190)))
            self.shake = max(self.shake, 0.5)
            AUDIO.play("mega", 0.9)
        elif kind == "gmax_end":
            u = self.units.get(ev[1])
            if u:
                self._burst(u.x, u.y, (255, 200, 210), 24, 160, 4, 0.6)
        elif kind == "faint":
            _, uid, x, y, form = ev[:5]
            u = self.units.get(uid)
            if len(ev) > 5:
                self.kills.append((self.unit_name(ev[5]) if ev[5] else "The storm", self.unit_name(uid), self.t))
                self.kills = self.kills[-5:]
            r = u.r if u else 14
            face = u.face if u else 1
            team = u.team if u else 0
            self.dead.append([form, x, y, r, 0.0, face, team])
            AUDIO.play("faint", 0.4 if self.mode == "showcase" else 0.7)
            if self.mode != "showcase":
                AUDIO.cry(form, 0.8)
            self._burst(x, y, (235, 235, 235), 8, 50, 6, 0.6)
        elif kind == "mega":
            _, uid, form, name = ev
            AUDIO.play("mega", 0.9)
            AUDIO.cry(form, 1.0)
            u = self.units.get(uid)
            if u:
                self.fx.append(FX("mega", 1.6, uid=uid, form=form, name=name.upper()))
                self._burst(u.x, u.y, (255, 255, 255), 24, 200, 4, 0.8)
        elif kind == "tera":
            _, uid, ttype = ev
            AUDIO.play("tera", 0.9)
            u = self.units.get(uid)
            if u:
                self.fx.append(FX("tera", 1.4, uid=uid, type=ttype))
                self._burst(u.x, u.y, type_color(ttype, 1), 28, 220, 5, 0.9)
                self._label(uid, f"TERA {ttype.upper()}", ttype)
        elif kind == "status":
            _, uid, st = ev
            if st in STATUS_COLORS:
                AUDIO.play("status", 0.5)
                u = self.units.get(uid)
                if u:
                    self._burst(u.x, u.y, STATUS_COLORS[st], 8, 70, 3, 0.5)
        elif kind == "heal":
            AUDIO.play("heal", 0.5)
            u = self.units.get(ev[1])
            if u:
                for _ in range(5 if ev[2] else 2):
                    self.particles.append(Particle(u.x + self.rng.uniform(-u.r, u.r), u.y, 0, -50, 0.8,
                                                   (120, 240, 120), 4))
        elif kind == "boost":
            AUDIO.play("boost" if ev[2] else "drop", 0.45)
            u = self.units.get(ev[1])
            if u:
                col = (255, 110, 90) if ev[2] else (90, 150, 255)
                for i in range(3):
                    self.particles.append(Particle(u.x + (i - 1) * u.r * 0.5, u.y, 0, -70 if ev[2] else 70, 0.6,
                                                   col, 4))
        elif kind == "protect":
            pass
        elif kind == "domain":
            self.domain = ev[1]
        elif kind == "weather":
            if ev[1]:
                self.fx.append(FX("banner", 1.8, text={"rain": "HEAVY RAIN", "sun": "HARSH SUNLIGHT",
                                                       "sand": "SANDSTORM", "snow": "SNOW"}.get(ev[1], ev[1]).upper()))

    def _blast(self, x, y, rad, mtype):
        col, light, dark = gfx.COLORS.get(mtype, gfx.COLORS["normal"])
        if mtype == "water":
            self.fx.append(FX("column", 0.6, x=x, y=y, w=max(26, rad * 0.45), color=col, light=light))
        elif mtype == "electric":
            self.fx.append(FX("bolt", 0.35, x=x, y=y, color=light))
        elif mtype in ("ground", "rock"):
            for _ in range(10):
                self.particles.append(Particle(x + self.rng.uniform(-rad, rad) * 0.7, y + self.rng.uniform(-rad, rad) * 0.5,
                                               self.rng.uniform(-40, 40), self.rng.uniform(-160, -60), 0.7, dark, 6, 400))
            self.shake = max(self.shake, 0.15)
        elif mtype == "dragon":
            self.fx.append(FX("meteor", 0.5, x=x, y=y, color=col))
        self.fx.append(FX("ring", 0.45, x=x, y=y, r=rad, color=col, light=light))
        self._burst(x, y, light, 14, rad * 2.2, 4, 0.45)

    # ------------------------------------------------------------------ update
    def update(self, dt):
        self.t += dt
        self.shake = max(0.0, self.shake - dt)
        k_move = min(1.0, dt * 16)
        for u in self.units.values():
            u.flash = max(0.0, u.flash - dt)
            u.spawn += dt
            u.x += (u.tx - u.x) * k_move
            u.y += (u.ty - u.y) * k_move
        for d in self.dead:
            d[4] += dt
        self.dead = [d for d in self.dead if d[4] < 0.7]
        keep = []
        self.labels_alive = 0
        for f in self.fx:
            f.t += dt
            if f.t < f.life:
                keep.append(f)
                if f.kind == "label":
                    self.labels_alive += 1
        self.fx = keep
        ps = []
        for p in self.particles:
            p.t += dt
            if p.t < p.life:
                p.vy += p.grav * dt
                p.x += p.vx * dt
                p.y += p.vy * dt
                p.vx *= 0.96
                p.vy *= 0.96 if p.grav == 0 else 1
                ps.append(p)
        self.particles = ps[-1500:]
        # camera
        tx, ty, tz = self.W / 2, self.H / 2, 1.0
        if self.cam_target:
            tx, ty, tz = self.cam_target
        elif self.auto_zoom and self.units:
            alive = list(self.units.values())
            if len(alive) <= 8:
                xs = [u.x for u in alive]
                ys = [u.y for u in alive]
                cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
                span = max(max(xs) - min(xs) + 260, (max(ys) - min(ys) + 360) * self.W / self.H)
                tz = max(1.0, min(1.8, self.W / span))
                tx, ty = cx, cy
        k = min(1.0, dt * 2.0)
        self.cam[0] += (tx - self.cam[0]) * k
        self.cam[1] += (ty - self.cam[1]) * k
        self.cam[2] += (tz - self.cam[2]) * k

    # ------------------------------------------------------------------ drawing
    def view_rect(self):
        z = self.cam[2]
        vw, vh = self.W / z, self.H / z
        x = min(max(self.cam[0] - vw / 2, 0), self.W - vw)
        y = min(max(self.cam[1] - vh / 2, 0), self.H - vh)
        return pygame.Rect(int(x), int(y), int(vw), int(vh))

    def world_to_screen(self, x, y):
        r = self.view_rect()
        return (x - r.x) * self.W / r.w, (y - r.y) * self.H / r.h

    def screen_to_world(self, x, y):
        r = self.view_rect()
        return r.x + x * r.w / self.W, r.y + y * r.h / self.H

    def unit_at(self, sx, sy):
        wx, wy = self.screen_to_world(sx, sy)
        best, bd = None, 1e9
        for u in self.units.values():
            d = math.hypot(u.x - wx, u.y - (wy + u.r * 0.3))
            if d < u.r * 1.4 and d < bd:
                best, bd = u, d
        return best

    def draw(self, surf):
        w = self.world
        w.blit(self.bg, (0, 0))
        self._draw_domain_under(w)
        self._draw_weather_under(w)
        for f in self.fx:
            if f.kind == "telegraph":
                p = f.t / f.life
                col = type_color(f.data["type"])
                rr = int(f.data["r"] * (0.4 + 0.6 * p))
                pygame.draw.circle(w, col, (f.data["x"], f.data["y"]), rr, 2)
        # shadows
        for u in self.units.values():
            if u.uid in self.hidden:
                continue
            sw = int(u.r * 1.6)
            sh = pygame.Rect(0, 0, sw, max(4, sw // 3))
            sh.center = (int(u.x), int(u.y + u.r * 0.55))
            pygame.draw.ellipse(w, (130, 96, 70), sh)
        # corpses
        for form, x, y, r, t, face, team in self.dead:
            a = 1 - t / 0.7
            img = SPRITES.get(form, r * 2.3 * (0.6 + 0.4 * a), flip=face > 0, white=0.6)
            img = img.copy()
            img.set_alpha(int(200 * a))
            w.blit(img, img.get_rect(midbottom=(x, y + r * 0.6 - t * 30)))
        # units sorted by y
        for u in sorted(self.units.values(), key=lambda u: u.y):
            if u.uid in self.hidden:
                continue
            self._draw_unit(w, u)
        # projectiles
        for x, y, mtype in self.projectiles:
            col, light, _ = gfx.COLORS.get(mtype, gfx.COLORS["normal"])
            glow(w, x, y, 24, col)
            pygame.draw.circle(w, col, (x, y), 7)
            pygame.draw.circle(w, light, (x, y), 4)
        for f in self.fx:
            self._draw_fx(w, f)
        for p in self.particles:
            a = 1 - p.t / p.life
            s = max(1, int(p.size * (0.5 + a * 0.5)))
            pygame.draw.rect(w, p.color, (int(p.x) - s // 2, int(p.y) - s // 2, s, s))
        self._draw_weather_over(w)
        self._draw_domain_over(w)
        self._draw_zone(w)
        # camera
        r = self.view_rect()
        if self.shake > 0:
            r.x += int(self.rng.uniform(-6, 6) * self.shake * 3)
            r.y += int(self.rng.uniform(-6, 6) * self.shake * 3)
            r.clamp_ip(pygame.Rect(0, 0, self.W, self.H))
        if r.w >= self.W - 1:
            surf.blit(w, (0, 0))
        else:
            surf.blit(gfx.rescale(w.subsurface(r), (self.W, self.H)), (0, 0))
        # screen-space overlays
        for f in self.fx:
            if f.kind in ("label", "pop", "mega", "banner"):
                self._draw_overlay_fx(surf, f)
        if self.mode == "team":
            for u in self.units.values():
                if u.uid not in self.hidden:
                    self._draw_unit_hud(surf, u)
        if self.show_boss_bars:
            self._draw_boss_bars(surf)

    def _twinkle(self, w, rect, uid):
        """Shiny Pokemon: little four-point stars popping around them."""
        for i in range(3):
            k = (self.t * 1.1 + i * 0.37 + uid * 0.13) % 1.0
            if k > 0.6:
                continue
            a = (uid * 2.4 + i * 2.1 + math.floor(self.t * 1.1 + i * 0.37 + uid * 0.13) * 1.7) % math.tau
            x = rect.centerx + math.cos(a) * rect.w * 0.55
            y = rect.centery + math.sin(a) * rect.h * 0.55
            s = 2 + 6 * math.sin(k / 0.6 * math.pi)
            col = (255, 240, 160)
            pygame.draw.polygon(w, col, [(x, y - s), (x + s * 0.3, y), (x, y + s), (x - s * 0.3, y)])
            pygame.draw.polygon(w, col, [(x - s, y), (x, y + s * 0.3), (x + s, y), (x, y - s * 0.3)])

    def _draw_unit(self, w, u):
        hgt = u.r * 2.3 * self.scale_over.get(u.uid, 1.0) * min(1.0, 0.3 + u.spawn * 3)
        outline = None
        if self.mode == "team":
            outline = gfx.TEAM_COLORS[u.team % 4]
        elif u.team >= self.gold_from:
            outline = (255, 210, 60)  # event bosses (Arceus, primals...) glow gold
        elif u.flags & 1:
            outline = (230, 50, 50)
        white = self.white.get(u.uid, 0.0)
        if u.flash > 0:
            white = max(white, 0.7)
        if u.status in ("frz",):
            white = max(white, 0.3)
        if u.flags & 32:  # terastallized: crystal outline in the tera type's color
            outline = type_color(self.roster.get(u.uid, {}).get("tera", "normal"), 1)
        img = SPRITES.get(u.form, hgt, flip=u.face > 0, outline=outline, white=round(white, 1))
        bob = math.sin(self.t * 6 + u.uid) * 1.5 if u.status not in ("slp", "frz") else 0
        lunge = u.anim * 18 * u.face
        rect = img.get_rect(midbottom=(int(u.x + lunge), int(u.y + u.r * 0.6 + bob)))
        if u.flags & 16:  # protect shield
            pygame.draw.circle(w, (120, 240, 140), rect.center, int(u.r * 1.4), 2)
        if u.flags & 8:   # charging glow
            pygame.draw.circle(w, (255, 255, 200), rect.center, int(u.r * 1.3 + math.sin(self.t * 20) * 3), 2)
        if self.selected == u.uid:
            pygame.draw.ellipse(w, (255, 255, 120), (u.x - u.r * 1.1, u.y + u.r * 0.3, u.r * 2.2, u.r * 0.8), 3)
        if u.flags & 128:  # Gigantamax: red glow and the swirling red clouds over its head
            glow(w, rect.centerx, rect.centery, u.r * 2.2, (200, 30, 60), 0.9)
        w.blit(img, rect)
        if u.uid in self.shiny:
            self._twinkle(w, rect, u.uid)
        if u.flags & 128:
            for i in range(7):
                a = i / 7 * math.tau + self.t * 1.2
                cx = rect.centerx + math.cos(a) * u.r * 0.9
                cy = rect.top + 4 + math.sin(a) * u.r * 0.22
                pygame.draw.circle(w, (150, 20, 45), (int(cx), int(cy)), int(u.r * 0.26))
                pygame.draw.circle(w, (230, 60, 90), (int(cx), int(cy - 2)), int(u.r * 0.17))
        if u.flags & 32:
            col = type_color(self.roster.get(u.uid, {}).get("tera", "normal"), 1)
            cx, top = rect.centerx, rect.top - 6
            pygame.draw.polygon(w, col, [(cx, top - 12), (cx + 7, top - 4), (cx, top + 4), (cx - 7, top - 4)])
            pygame.draw.polygon(w, (255, 255, 255), [(cx, top - 12), (cx + 7, top - 4), (cx, top + 4),
                                                     (cx - 7, top - 4)], 2)
        if u.status and self.mode == "showcase":
            gfx.pill(w, STATUS_NAMES.get(u.status, u.status.upper()), (u.x, rect.bottom + 6),
                     STATUS_COLORS.get(u.status, (120, 120, 120)), 9)

    def _draw_unit_hud(self, surf, u):
        sx, sy = self.world_to_screen(u.x, u.y)
        z = self.cam[2]
        top = sy - u.r * 1.45 * z * self.scale_over.get(u.uid, 1.0)
        bw = int(max(44, u.r * 2.4) * min(z, 1.3))
        gfx.hp_bar(surf, (int(sx - bw / 2), int(top - 6), bw, 6), u.hp)
        if u.status:
            gfx.pill(surf, STATUS_NAMES.get(u.status, ""), (sx, top - 16), STATUS_COLORS.get(u.status, (100,) * 3), 10)
        if u.flags & 4 and u.team == self.my_team:
            gfx.pill(surf, "MEGA READY", (sx, sy + u.r * 0.9 * z + 10), (150, 80, 220), 10)

    def _draw_fx(self, w, f):
        p = f.t / f.life
        d = f.data
        if f.kind == "beam":
            col, light, _ = gfx.COLORS.get(d["type"], gfx.COLORS["normal"])
            width = max(1, int(d["w"] * (1 - p * 0.7)))
            pygame.draw.line(w, col, (d["x1"], d["y1"]), (d["x2"], d["y2"]), width + 4)
            pygame.draw.line(w, light, (d["x1"], d["y1"]), (d["x2"], d["y2"]), max(1, width // 2))
            pygame.draw.circle(w, light, (d["x2"], d["y2"]), int(8 + 10 * p))
            for i in range(5):  # the beam lights up the ground along its path
                q = i / 4
                glow(w, d["x1"] + (d["x2"] - d["x1"]) * q, d["y1"] + (d["y2"] - d["y1"]) * q, 20 + width * 2, col,
                     1 - p * 0.7)
            glow(w, d["x2"], d["y2"], 44, light, 1 - p * 0.5)
        elif f.kind == "slash":
            a = d["a"]
            L = 16
            for o in (-5, 0, 5):
                x1, y1 = d["x"] + math.cos(a) * L + o, d["y"] + math.sin(a) * L
                x2, y2 = d["x"] - math.cos(a) * L + o, d["y"] - math.sin(a) * L
                pygame.draw.line(w, (255, 255, 255), (x1, y1), (x2, y2), 2)
        elif f.kind == "ring":
            rr = int(d["r"] * (0.5 + p * 0.7))
            glow(w, d["x"], d["y"], rr * 1.1, d["color"], 1 - p)
            pygame.draw.circle(w, d["color"], (d["x"], d["y"]), rr, max(1, int(8 * (1 - p))))
            pygame.draw.circle(w, d["light"], (d["x"], d["y"]), int(rr * 0.85), max(1, int(3 * (1 - p))))
        elif f.kind == "column":
            hgt = d["y"] - 40
            cw = int(d["w"] * (1 - p * 0.5))
            col = pygame.Surface((cw, hgt), pygame.SRCALPHA)
            col.fill((*d["color"], int(200 * (1 - p))))
            for i in range(0, cw, 6):
                pygame.draw.line(col, (*d["light"], int(230 * (1 - p))), (i, 0), (i, hgt), 2)
            w.blit(col, (d["x"] - cw // 2, 40))
            pygame.draw.ellipse(w, d["light"], (d["x"] - cw, d["y"] - 10, cw * 2, 20), 3)
        elif f.kind == "bolt":
            pts = [(d["x"] + self.rng.uniform(-14, 14), d["y"] - 260 + i * 52) for i in range(5)] + [(d["x"], d["y"])]
            glow(w, d["x"], d["y"], 70, d["color"], 1.2 * (1 - p))
            pygame.draw.lines(w, d["color"], False, pts, 5)
            pygame.draw.lines(w, (255, 255, 255), False, pts, 2)
        elif f.kind == "meteor":
            y = d["y"] - 300 * (1 - p)
            pygame.draw.circle(w, d["color"], (d["x"] + 60 * (1 - p), y), 14)
            pygame.draw.circle(w, (255, 200, 120), (d["x"] + 60 * (1 - p), y), 7)
        elif f.kind == "tera":
            u = self.units.get(d["uid"])
            if u:
                col = type_color(d["type"], 1)
                rr = u.r * (1.2 + p * 1.8)
                pts = [(u.x + math.cos(a) * rr, u.y - u.r * 0.4 + math.sin(a) * rr)
                       for a in [i * math.tau / 6 + p * 2 for i in range(6)]]
                pygame.draw.polygon(w, col, pts, max(1, int(6 * (1 - p))))
                pygame.draw.polygon(w, (255, 255, 255), pts, max(1, int(2 * (1 - p))))
        elif f.kind == "godbeam":
            a = 1 - p
            bw = int(90 * (0.4 + 0.6 * math.sin(min(1.0, p * 3) * math.pi / 2)) * a) + 4
            beam = pygame.Surface((bw * 2, d["y"] + 40), pygame.SRCALPHA)
            for i in range(bw, 0, -6):
                pygame.draw.rect(beam, (255, 235, 150, int(40 * a)), (bw - i, 0, i * 2, d["y"] + 40))
            pygame.draw.rect(beam, (255, 255, 230, int(220 * a)), (bw - bw // 4, 0, bw // 2, d["y"] + 40))
            w.blit(beam, (d["x"] - bw, 0))
            for k in range(3):
                rr = int((60 + 140 * ((p * 2 + k / 3) % 1)) * 1.0)
                pygame.draw.ellipse(w, (255, 220, 120), (d["x"] - rr, d["y"] - rr / 3, rr * 2, rr * 2 / 3), 3)
        elif f.kind == "boom":
            rr = int(d["r"] * (0.3 + p))
            glow(w, d["x"], d["y"], rr * 1.4, (255, 170, 80), 1.3 * (1 - p))
            pygame.draw.circle(w, (255, 230, 140), (d["x"], d["y"]), rr, max(1, int(14 * (1 - p))))
            pygame.draw.circle(w, (255, 140, 60), (d["x"], d["y"]), int(rr * 0.7), max(1, int(8 * (1 - p))))

    def _draw_overlay_fx(self, surf, f):
        p = f.t / f.life
        d = f.data
        if f.kind == "label":
            u = self.units.get(d["uid"])
            if u:
                d["x"], d["y"] = u.x, u.y - u.r * 1.3
            sx, sy = self.world_to_screen(d["x"], d["y"] - p * 22)
            alpha = 255 if p < 0.7 else int(255 * (1 - (p - 0.7) / 0.3))
            size = 11 if self.mode == "showcase" and self.cam[2] < 1.2 else 15
            gfx.pill(surf, d["text"], (sx, sy - (0 if self.mode == "showcase" else 18)), d["color"], size,
                     alpha=alpha)
        elif f.kind == "pop":
            sx, sy = self.world_to_screen(d["x"], d["y"] - p * 26)
            gfx.text(surf, d["text"], (sx, sy), 16, d["color"], alpha=int(255 * (1 - p)))
        elif f.kind == "mega":
            u = self.units.get(d["uid"])
            if not u:
                return
            sx, sy = self.world_to_screen(u.x, u.y - u.r * 0.4)
            z = self.cam[2]
            rr = u.r * z * (1.3 + p * 1.2)
            if p < 0.85:
                gfx.rainbow_ring(surf, (sx, sy), rr, self.t, max(3, int(6 * z)))
                glow = pygame.Surface((int(rr * 2), int(rr * 2)), pygame.SRCALPHA)
                pygame.draw.circle(glow, (255, 255, 255, int(150 * (1 - p))), (int(rr), int(rr)), int(rr))
                surf.blit(glow, (sx - rr, sy - rr))
            # portrait card + name
            card = 64
            cx, cy = sx + u.r * z + 20, sy - u.r * z - 40
            cx = min(max(cx, card), self.W - card)
            cy = max(cy, 90)
            box = pygame.Rect(0, 0, card, card)
            box.center = (cx, cy)
            pygame.draw.rect(surf, INK, box.inflate(6, 6), border_radius=4)
            e = self.dex.all.get(d["form"])
            pygame.draw.rect(surf, type_color(e["types"][0], 1) if e else (200, 200, 200), box, border_radius=3)
            img = SPRITES.get(d["form"], card - 8)
            surf.blit(img, img.get_rect(center=box.center))
            gfx.text(surf, d["name"], (sx, sy - u.r * z - 8), 18, (200, 255, 170))
        elif f.kind == "banner":
            a = 255 if p < 0.75 else int(255 * (1 - (p - 0.75) / 0.25))
            gfx.text(surf, d["text"], (self.W / 2, self.H * 0.42), 46, (255, 255, 255), alpha=a, ow=3)

    def _draw_boss_bars(self, surf):
        bosses = [u for u in self.units.values() if u.flags & 1 and u.uid not in self.hidden]
        if not bosses:
            return
        bosses.sort(key=lambda u: (-u.r, u.uid))
        main = bosses[0]
        x, y, w = 140, 80, self.W - 280
        gfx.text(surf, self.unit_name(main.uid).upper(), (self.W / 2, y - 12), 18, WHITE)
        pygame.draw.rect(surf, INK, (x - 2, y - 2, w + 4, 16), border_radius=4)
        pygame.draw.rect(surf, (70, 30, 30), (x, y, w, 12), border_radius=3)
        pygame.draw.rect(surf, (225, 60, 50), (x, y, int(w * main.hp), 12), border_radius=3)
        gfx.text(surf, f"{int(math.ceil(main.hp * 100))}%", (x + w + 6, y + 6), 14, WHITE, anchor="midleft")
        others = bosses[1:4]
        if others:
            ow = (w - 10 * (len(others) - 1)) // len(others)
            for i, u in enumerate(others):
                ox = x + i * (ow + 10)
                gfx.text(surf, self.unit_name(u.uid).upper()[:16], (ox, y + 26), 12, WHITE, anchor="midleft", ow=1)
                pygame.draw.rect(surf, INK, (ox - 1, y + 35, ow + 2, 9), border_radius=3)
                pygame.draw.rect(surf, (70, 30, 30), (ox, y + 36, ow, 7), border_radius=2)
                pygame.draw.rect(surf, (225, 60, 50), (ox, y + 36, int(ow * u.hp), 7), border_radius=2)

    def god_beam(self, x, y):
        self.fx.append(FX("godbeam", 2.4, x=x, y=y))
        for _ in range(40):
            a = self.rng.random() * math.tau
            sp = 120 + self.rng.random() * 260
            self.particles.append(Particle(x, y, math.cos(a) * sp, math.sin(a) * sp * 0.5, 1.2,
                                           (255, 230, 140), 5))

    def _crack_lines(self):
        if self._cracks is None:
            rng = random.Random(11)
            self._cracks = []
            for _ in range(16):
                x, y = rng.uniform(80, self.W - 80), rng.uniform(120, self.H - 120)
                pts = [(x, y)]
                for _ in range(rng.randint(4, 8)):
                    x += rng.uniform(-60, 60)
                    y += rng.uniform(-60, 60)
                    pts.append((x, y))
                self._cracks.append(pts)
        return self._cracks

    def _draw_domain_under(self, w):
        d = self.domain
        if d == "sea":
            tint = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            tint.fill((40, 110, 220, 95))
            w.blit(tint, (0, 0))
            for row in range(0, self.H, 46):  # rolling waves
                pts = [(x, row + math.sin(x / 40 + self.t * 2 + row) * 6) for x in range(0, self.W + 20, 20)]
                pygame.draw.lines(w, (150, 200, 255), False, pts, 2)
        elif d == "land":
            tint = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            tint.fill((200, 70, 20, 80))
            w.blit(tint, (0, 0))
            glow = 160 + int(80 * math.sin(self.t * 3))
            for pts in self._crack_lines():
                pygame.draw.lines(w, (90, 20, 10), False, pts, 9)
                pygame.draw.lines(w, (255, glow, 40), False, pts, 4)
        elif d == "sky":
            tint = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            tint.fill((60, 190, 120, 50))
            w.blit(tint, (0, 0))

    def _draw_zone(self, w):
        if not self.zone:
            return
        cx, cy, r = self.zone
        storm = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        storm.fill((90, 30, 140, 110))
        pygame.draw.circle(storm, (0, 0, 0, 0), (int(cx), int(cy)), int(r))   # clear inside (no blending)
        w.blit(storm, (0, 0))
        pulse = 0.5 + 0.5 * math.sin(self.t * 5)
        pygame.draw.circle(w, (200, 120, 255), (int(cx), int(cy)), int(r), 4)
        pygame.draw.circle(w, (255, 220, 255), (int(cx), int(cy)), int(r + 3 + pulse * 3), 1)
        for i in range(24):  # crackles on the storm wall
            a = i / 24 * math.tau + self.t * 0.4
            if self.rng.random() < 0.3:
                x0, y0 = cx + math.cos(a) * r, cy + math.sin(a) * r
                pygame.draw.line(w, (230, 180, 255), (x0, y0), (x0 + self.rng.uniform(-10, 10),
                                                                 y0 + self.rng.uniform(-10, 10)), 2)

    def _draw_domain_over(self, w):
        d = self.domain
        if d == "land":
            for i in range(40):  # embers rising
                x = (i * 97 + math.sin(self.t + i) * 30) % self.W
                y = self.H - (i * 131 + self.t * 90) % self.H
                pygame.draw.circle(w, (255, 150 + (i * 7) % 100, 40), (int(x), int(y)), 2)
        elif d == "sea":
            for i in range(140):  # heavy rain
                x = (i * 53 + self.t * 260) % self.W
                y = (i * 89 + self.t * 1300) % self.H
                pygame.draw.line(w, (190, 220, 255), (x, y), (x - 6, y + 24), 2)
        elif d == "sky":
            for i in range(30):  # wind streaks
                x = (i * 151 + self.t * 900) % (self.W + 300) - 150
                y = (i * 97) % self.H
                pygame.draw.line(w, (200, 255, 220), (x, y), (x + 120, y - 10), 2)

    def _draw_weather_under(self, w):
        if self.weather == "sun":
            tint = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            tint.fill((255, 200, 80, 40))
            w.blit(tint, (0, 0))

    def _draw_weather_over(self, w):
        if self.weather == "rain":
            for i in range(90):
                x = (i * 97 + self.t * 220) % self.W
                y = (i * 151 + self.t * 900) % self.H
                pygame.draw.line(w, (170, 200, 255), (x, y), (x - 4, y + 16), 1)
        elif self.weather == "sand":
            for i in range(120):
                x = (i * 83 + self.t * 400) % self.W
                y = (i * 131 + math.sin(self.t + i) * 20) % self.H
                pygame.draw.rect(w, (220, 190, 130), (x, y, 3, 2))
        elif self.weather == "snow":
            for i in range(100):
                x = (i * 71 + math.sin(self.t * 2 + i) * 15) % self.W
                y = (i * 113 + self.t * 80) % self.H
                pygame.draw.circle(w, (250, 250, 255), (x, y), 2)
