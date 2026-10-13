"""Showcase mode: scripted mass battles (e.g. Gen 1 vs Gen 3) with intro, countdown, boss bars and a
trainer-catches-the-winner finale. Can play live or render straight to an MP4."""
import glob
import json
import math
import os
import random

import pygame

from . import gfx
from .audio import AUDIO
from .cinematics import Cutscene, Descent
from .gfx import H, INK, SPRITES, W
from .pokedex import prefetch
from .render import ArenaRenderer
from .sim import ARENA, Sim
from .team import auto_member

SHOWCASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "showcases")

DEFAULTS = {
    "title": "Gen 1 vs Gen 3!",
    "subtitle": "WHO WILL WIN???",
    "teams": [{"name": "Gen 1", "filter": {"gen": 1}}, {"name": "Gen 3", "filter": {"gen": 3}}],
    "bosses": "legendary",     # "legendary" | "none" | list of names
    "megas": True,
    "level": 50,
    "hp_mult": 12,
    "boss_hp_mult": 3,
    "max_per_team": 250,
    "speed": 1.0,
    "seed": None,
    "finale": True,
    "events": "random",        # "random" | "none" | "chaos" | list of: arceus, primal, rayquaza, meteor
    "mode": "teams",           # "teams" | "royale" (every Pokemon for itself + a shrinking storm)
}
EVENTS = ["arceus", "primal", "rayquaza", "meteor"]
# who Arceus brings down with it
ARCEUS_GROUPS = [
    ("THE CREATION TRIO", ["dialga", "palkia", "giratina"]),
    ("THE LEGENDARY BIRDS", ["articuno", "zapdos", "moltres"]),
    ("THE LEGENDARY BEASTS", ["raikou", "entei", "suicune"]),
    ("THE LAKE GUARDIANS", ["uxie", "mesprit", "azelf"]),
    ("THE SWORDS OF JUSTICE", ["cobalion", "terrakion", "virizion"]),
    ("THE WEATHER TRIO", ["kyogre", "groudon", "rayquaza"]),
    ("THE TAO TRIO", ["reshiram", "zekrom", "kyurem"]),
]
DOMAIN_TEXT = {"sea": ("DOMAIN: ENDLESS OCEAN", (60, 130, 255)), "land": ("DOMAIN: SCORCHED EARTH", (255, 110, 40)),
               "sky": ("DELTA STREAM: THE SKY CALMS", (80, 220, 140))}


def list_presets():
    out = []
    for path in sorted(glob.glob(os.path.join(SHOWCASE_DIR, "*.json"))):
        try:
            with open(path) as f:
                cfg = json.load(f)
            out.append((path, cfg.get("title", os.path.basename(path))))
        except (OSError, ValueError):
            pass
    return out


def load_config(path_or_dict):
    cfg = dict(DEFAULTS)
    if isinstance(path_or_dict, dict):
        cfg.update(path_or_dict)
    else:
        with open(path_or_dict) as f:
            cfg.update(json.load(f))
    return cfg


def build_teams(dex, cfg, rng):
    teams, names = [], []
    bosses = cfg.get("bosses", "legendary")
    boss_names = {dex.get(b)["id"] for b in bosses if dex.get(b)} if isinstance(bosses, list) else set()
    for t in cfg["teams"]:
        pool = dex.filter(t.get("filter", t))
        if t.get("count"):
            pool = rng.sample(pool, min(t["count"], len(pool)))
        pool = pool[: cfg.get("max_per_team", 250)]
        specs = []
        for e in pool:
            is_boss = (bosses == "legendary" and (e["legendary"] or e["mythical"])) or e["id"] in boss_names
            m = auto_member(dex, e, rng, None, allow_mega=cfg.get("megas", True), level=cfg.get("level", 50),
                            comp=False)
            specs.append({"member": m, "boss": is_boss})
        # spread bosses through the front rows like the video
        rng.shuffle(specs)
        teams.append(specs)
        names.append(t.get("name", f"Team {len(names) + 1}"))
    if cfg.get("mode") == "royale":
        return royale_teams(dex, [s for t in teams for s in t], rng)
    return teams, names


def royale_teams(dex, specs, rng):
    """Battle royale: every Pokemon is its own team, scattered around the arena (no species twice)."""
    seen, uniq = set(), []
    for sp in specs:
        if sp["member"].species not in seen:
            seen.add(sp["member"].species)
            uniq.append(sp)
    n = len(uniq)
    gap = max(26.0, min(90.0, math.sqrt((ARENA[2] - ARENA[0]) * (ARENA[3] - ARENA[1]) / max(1, n)) * 0.8))
    placed = []
    for sp in uniq:
        for _ in range(60):
            x = rng.uniform(ARENA[0] + 40, ARENA[2] - 40)
            y = rng.uniform(ARENA[1] + 60, ARENA[3] - 60)
            if all((x - px) ** 2 + (y - py) ** 2 > gap * gap for px, py in placed):
                break
        placed.append((x, y))
        sp["pos"] = (x, y)
    return [[sp] for sp in uniq], [dex.all[sp["member"].species]["name"] for sp in uniq]


class ShowcaseScene:
    """Plays one showcase. `done` becomes True at the end."""

    def __init__(self, dex, cfg, progress=None):
        self.dex = dex
        self.cfg = cfg
        seed = cfg.get("seed")
        if seed is None:
            seed = random.randrange(1 << 30)
        self.seed = seed
        self.rng = random.Random(seed)
        teams, self.team_names = build_teams(dex, cfg, self.rng)
        ids = {s["member"].species for t in teams for s in t} | {m for t in teams for s in t for m in
                                                                  ([s["member"].mega] if s["member"].mega else [])}
        self.events_plan = self._plan_events(cfg)
        for key in ("arceus", "kyogre-primal", "groudon-primal", "rayquaza-mega", "deoxys",
                    *(k for _, ks in ARCEUS_GROUPS for k in ks)):
            e = dex.get(key)
            if e:
                ids.add(e["id"])
        prefetch(list(ids), progress)
        self.royale = cfg.get("mode") == "royale"
        n = max(len(t) for t in teams) if not self.royale else len(teams) // 2
        radius = 13 if n > 40 else 17 if n > 12 else 24
        mega = "auto" if cfg.get("megas", True) else "off"
        zone = {"start": 12, "end": 12 + max(45, min(80, len(teams) * 0.6)), "min": 60} if self.royale else None
        self.sim = Sim(dex, teams, seed=seed, hp_mult=cfg["hp_mult"], boss_hp_mult=cfg["boss_hp_mult"],
                       radius=radius, mega={i: mega for i in range(len(teams))},
                       ai={0: "normal", 1: "normal"}, time_ramp=cfg.get("time_ramp", 80) + (60 if self.royale else 0),
                       zone=zone)
        self.r = ArenaRenderer(dex, self.sim.roster(), mode="showcase", team_names=self.team_names)
        if self.royale:
            self.r.gold_from = len(teams)  # only event bosses glow gold
        self.r.feed(self.sim.snapshot())
        self.r.hidden = {u.uid for u in self.sim.units}
        self.r.auto_zoom = False
        self.r.show_boss_bars = False
        self.t = 0.0
        self.phase = "intro"
        self.done = False
        self.end_t = None
        self.balls = {u.uid: (u.x, u.y) for u in self.sim.units}
        self.popped = set()
        self.ball_size = 22 if radius < 16 else 30
        self.finale = None
        self.speed = cfg.get("speed", 1.0)
        self.paused = False
        self.mvp = None
        self.counts = [len(t) for t in teams]
        self.intro_len = 7.6
        self.cues = set()
        self.cutscene = None
        self.cutscenes = []
        self.start_units = len(self.sim.units)
        self.mega_scenes = 0
        self.level = cfg.get("level", 50)
        self.storm_msg = None

    # ------------------------------------------------------------------ events + cutscenes
    def _plan_events(self, cfg):
        ev = cfg.get("events", "random")
        if ev in (None, "none", False):
            names = []
        elif ev == "chaos":
            names = list(EVENTS)
            self.rng.shuffle(names)
        elif ev == "random":
            names = [self.rng.choice(EVENTS)]
            if self.rng.random() < 0.35:
                names.append(self.rng.choice([e for e in EVENTS if e != names[0]]))
        else:
            names = [e for e in ev if e in EVENTS]
        fracs, times = [0.7, 0.45, 0.3, 0.18], [16, 30, 44, 58]
        return [{"name": n, "frac": fracs[i % 4], "time": times[i % 4], "done": False} for i, n in enumerate(names)]

    def _new_team(self, name):
        self.team_names.append(name)
        return len(self.team_names) - 1

    def _spawn(self, key, team_name, pos, hp_scale=2.0, radius_scale=1.2, signature=None, team=None, floor=0.3):
        entry = self.dex.get(key)
        m = auto_member(self.dex, entry, self.rng, None, allow_mega=False, level=self.level + 10, comp=False)
        sig = self.dex.move(signature) if signature else None
        if sig and sig["id"] not in m.moves:
            m.moves = [sig["id"]] + m.moves[:3]
        hp_scale *= min(1.0, max(floor, self.start_units / 180))  # don't steamroll small fights
        team = self._new_team(team_name) if team is None else team
        u = self.sim.spawn(m, team, pos, boss=True, hp_scale=hp_scale,
                           radius_scale=radius_scale)
        self.r.roster[u.uid] = self.sim.roster()[u.uid]
        return u

    def _trigger(self, name):
        cx, cy = (ARENA[0] + ARENA[2]) / 2, (ARENA[1] + ARENA[3]) / 2
        if name == "arceus":
            # Arceus doesn't fight: it drops off a legendary trio that fights for itself
            title, keys = self.rng.choice(ARCEUS_GROUPS)
            entries = [self.dex.get(k) for k in keys]
            entries = [e for e in entries if e]
            # small fights get fewer gifts so the original teams still have a chance
            keep = 1 if self.start_units < 16 else 2 if self.start_units < 40 else 3
            entries = self.rng.sample(entries, min(keep, len(entries)))
            if keep == 1:
                title = f"{entries[0]['name'].upper()} FROM {title}"
            team = self._new_team("Arceus' Chosen")
            spots = [(cx, cy + 150)] if len(entries) == 1 else [(cx - 170, cy + 40), (cx + 170, cy + 40), (cx, cy + 150)]
            drops = [(e["id"], e["name"], spots[i % 3]) for i, e in enumerate(entries)]

            def drop(i):
                u = self._spawn(entries[i]["key"], "Arceus' Chosen", drops[i][2], hp_scale=1.0,
                                radius_scale=1.1, team=team, floor=0.08)
                self.r.god_beam(u.x, u.y)
            self.cutscenes.append(Descent(self.dex.get("arceus")["id"], drops, title, (cx, cy), drop))
        elif name == "primal":
            for key, nm, pos, dom, weather in (("kyogre-primal", "Primal Kyogre", (cx - 160, cy - 260), "sea", "rain"),
                                               ("groudon-primal", "Primal Groudon", (cx + 160, cy + 260), "land", "sun")):
                def act(key=key, nm=nm, pos=pos, dom=dom, weather=weather):
                    self._spawn(key, nm, pos, signature="origin-pulse" if dom == "sea" else "precipice-blades")
                    self.sim.set_weather(weather, 9999)
                    self.sim.set_domain(dom)
                sub = DOMAIN_TEXT[dom][0] if dom == "sea" else "DOMAIN CLASH!"
                pid = self.dex.get(key)["id"]
                self.cutscenes.append(Cutscene("card", 3.6, pos, 1.6, f"{nm.upper()} AWAKENS", sub,
                                               DOMAIN_TEXT[dom][1], pid, action=act, cry=pid))
        elif name == "rayquaza":
            pid = self.dex.get("rayquaza-mega")["id"]

            def act():
                self._spawn("rayquaza-mega", "Mega Rayquaza", (cx, ARENA[1] + 200), signature="dragon-ascent")
                self.sim.weather = None
                self.sim.emit("weather", None)
                self.sim.set_domain("sky")
            self.cutscenes.append(Cutscene("card", 3.8, (cx, ARENA[1] + 260), 1.5, "THE SKY LORD DESCENDS",
                                           DOMAIN_TEXT["sky"][0], DOMAIN_TEXT["sky"][1], pid, action=act, cry=pid))
        elif name == "meteor":
            def act():
                for i in range(24):
                    self.sim.env_blast(self.rng.uniform(ARENA[0] + 40, ARENA[2] - 40),
                                       self.rng.uniform(ARENA[1] + 60, ARENA[3] - 60), 80, 0.2, "dragon",
                                       0.4 + i * 0.18)
            pid = self.dex.get("deoxys")["id"]
            self.cutscenes.append(Cutscene("card", 3.0, (cx, cy), 1.0, "METEOR SHOWER", "THE SKY IS FALLING!",
                                           (230, 80, 80), pid, action=act, cry=pid))

    def _scan_events(self, events):
        for ev in events:
            if ev[0] != "mega":
                continue
            _, uid, form_id, name = ev
            u = self.sim.by_id.get(uid)
            key = self.dex.all.get(form_id, {}).get("key", "")
            pos = (u.x, u.y) if u else None
            if "primal" in key:
                dom = "sea" if "kyogre" in key else "land"
                clash = self.sim.domain not in (None, dom) or any(
                    x.alive and "primal" in x.mon.entry["key"] and x is not u for x in self.sim.units)
                sub = "DOMAIN CLASH!" if clash else DOMAIN_TEXT[dom][0]
                self.cutscenes.append(Cutscene("card", 3.4, pos, 1.7, "PRIMAL REVERSION", sub, DOMAIN_TEXT[dom][1],
                                               form_id, cry=form_id, action_at=0.35))
            elif key == "rayquaza-mega":
                self.cutscenes.append(Cutscene("card", 3.2, pos, 1.7, "MEGA RAYQUAZA", DOMAIN_TEXT["sky"][0],
                                               DOMAIN_TEXT["sky"][1], form_id, cry=form_id, action_at=0.35))
            elif u and u.boss and self.mega_scenes < 3:
                self.mega_scenes += 1
                self.cutscenes.append(Cutscene("card", 2.0, pos, 1.8, name.upper(), "MEGA EVOLUTION!",
                                               (170, 90, 230), form_id, cry=form_id, action_at=0.3))

    def _check_triggers(self):
        alive = [u for u in self.sim.units if u.alive]
        frac = len(alive) / max(1, self.start_units)
        bt = self.t - self.intro_len
        for e in self.events_plan:
            if not e["done"] and (frac <= e["frac"] or bt >= e["time"]) and len(alive) >= 2:
                e["done"] = True
                self._trigger(e["name"])
                break
        if len(alive) == 2 and alive[0].team != alive[1].team and self.start_units > 2 and self._once("final"):
            a, b = alive
            self.cutscenes.append(Cutscene("vs", 3.0, ((a.x + b.x) / 2, (a.y + b.y) / 2), 1.5, "FINAL SHOWDOWN",
                                           color=(255, 190, 60), portrait=a.mon.entry["id"],
                                           portrait2=b.mon.entry["id"], action_at=0.45, sound="count"))

    def _once(self, key):
        if key in self.cues:
            return False
        self.cues.add(key)
        return True

    # ------------------------------------------------------------------ input
    def handle(self, ev, pos=None):
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_SPACE:
                self.paused = not self.paused
            elif ev.key in (pygame.K_RIGHT, pygame.K_EQUALS, pygame.K_PLUS):
                self.speed = min(8.0, self.speed * 2)
            elif ev.key in (pygame.K_LEFT, pygame.K_MINUS):
                self.speed = max(0.25, self.speed / 2)
            elif ev.key == pygame.K_ESCAPE:
                self.done = True

    # ------------------------------------------------------------------ timeline
    def update(self, dt):
        if self.paused:
            return
        self.t += dt
        t = self.t
        if self._once("music"):
            AUDIO.music("showcase")
        if self.phase == "intro":
            for i, at in enumerate((5.0, 5.8, 6.6)):
                if t >= at and self._once(f"count{i}"):
                    AUDIO.play("count")
            # balls pop open left->right starting at 2.0s
            if t > 2.0:
                xs = sorted(self.balls.items(), key=lambda kv: kv[1][0] + kv[1][1] * 0.05)
                n = int(min(1.0, (t - 2.0) / 0.9) * len(xs))
                for uid, (x, y) in xs[:n]:
                    if uid not in self.popped:
                        self.popped.add(uid)
                        self.r.hidden.discard(uid)
                        if uid in self.r.units:
                            self.r.units[uid].spawn = 0.0
                        self.r._burst(x, y, (240, 240, 240), 3, 60, 7, 0.5)
                        AUDIO.play("ball", 0.45)
            if t >= self.intro_len:
                AUDIO.play("go")
                self.phase = "battle"
                self.r.auto_zoom = True
                self.r.show_boss_bars = True
            self.r.update(dt)
            return
        if self.phase == "battle":
            if self.cutscene is None and self.cutscenes:
                self.cutscene = self.cutscenes.pop(0)
            if self.cutscene is not None:
                self.cutscene.update(dt, self.r)
                self.r.feed(self.sim.snapshot())
                self.r.update(dt)
                if self.cutscene.done:
                    self.cutscene = None
                    self.r.cam_target = None
                return
            steps = max(1, int(round(self.speed)))
            for _ in range(steps):
                self.sim.step(dt * self.speed / steps)
                snap = self.sim.snapshot()
                self._scan_events(snap["e"])
                for ev in snap["e"]:
                    if ev[0] == "zone":
                        self.storm_msg = (ev[1], self.t)
                        AUDIO.play("count")
                self.r.feed(snap)
                if self.cutscenes:
                    break
            self._check_triggers()
            self.r.update(dt)
            self.counts = [sum(1 for u in self.sim.units if u.alive and u.team == i)
                           for i in range(len(self.team_names))]
            if self.sim.over:
                self.phase = "won"
                self.end_t = t
                alive = [u for u in self.sim.units if u.alive]
                self.mvp = max(alive, key=lambda u: (u.kills, u.mon.hp_frac())) if alive else None
            return
        self.r.update(dt)
        since = t - self.end_t
        if self.phase == "won":
            if since > 0.4 and self._once("win"):
                AUDIO.play("win")
                if self.mvp:
                    AUDIO.cry(self.mvp.mon.entry["id"], 1.0)
            if since > 3.0:
                if self.cfg.get("finale", True) and self.mvp:
                    self._start_finale()
                else:
                    self.phase = "outro"
            return
        if self.phase == "finale":
            self._update_finale(dt)
            return
        if self.phase == "outro" and since > 6.0:
            self.done = True

    def _start_finale(self):
        self.phase = "finale"
        m = self.mvp
        # everyone else on the winning team returns to their ball
        for u in self.sim.units:
            if u.alive and u is not m:
                self.r.hidden.add(u.uid)
                self.r._burst(u.x, u.y, (255, 120, 120), 6, 60, 4, 0.5)
        mv = self.r.units.get(m.uid)
        self.target = (mv.x, mv.y) if mv else (m.x, m.y)
        tx = self.target[0] - 75 if self.target[0] > ARENA[0] + 200 else self.target[0] + 75
        self.finale = {"t": 0.0, "start": (ARENA[0] - 30 if tx < self.target[0] else ARENA[2] + 30, self.target[1] + 10),
                       "stop": (tx, self.target[1] + 10), "stage": "walk"}
        self.r.cam_target = (self.target[0] + (tx - self.target[0]) / 2, self.target[1] - 10, 4.2)

    # catch timeline (seconds since the finale started)
    THROW, HIT, ABSORB, CLOSE, LAND = 2.0, 2.75, 2.95, 3.75, 4.35
    SHAKES = (4.75, 5.65, 6.55)
    CAUGHT, END = 7.45, 12.0

    def _update_finale(self, dt):
        f = self.finale
        f["t"] += dt
        t = f["t"]
        uid = self.mvp.uid
        tx, ty = self.target
        if t > self.THROW and self._once("throw"):
            AUDIO.play("select")
        if t > self.HIT and self._once("hit"):
            AUDIO.play("ball")
            self.r._burst(tx, ty, (255, 255, 255), 10, 120, 4, 0.4)
        if t > self.ABSORB and self._once("absorb"):
            self.r.hidden.add(uid)          # we draw it ourselves while it turns into red energy
            AUDIO.play("beam", 0.7)
        if t > self.CLOSE and self._once("close"):
            AUDIO.play("ball")
            self.r._burst(tx, ty - 40, (255, 90, 90), 14, 110, 4, 0.5)
        for k, at in enumerate(self.SHAKES):
            if t > at and self._once(f"wiggle{k}"):
                AUDIO.play("wiggle")
        if t > self.CAUGHT and self._once("caught"):
            AUDIO.play("ball")
            AUDIO.play("catch")
            gy = self._ball_ground()
            self.r._burst(tx, gy, (255, 240, 120), 30, 180, 5, 1.0)
            f["stars"] = [(math.cos(a) * sp, -abs(math.sin(a)) * sp - 60, a)
                          for a, sp in ((i * 0.55, 160 + (i % 3) * 50) for i in range(12))]
        sx_, _ = f["stop"]
        if t > self.THROW + 0.4:  # push in on the ball, keeping the trainer in shot
            z_in = 4.8 if t < self.CAUGHT + 1.2 else 5.2
            self.r.cam_target = (tx + (sx_ - tx) * 0.3, ty - 15, z_in)
        if t > self.END:
            self.done = True

    def _ball_ground(self):
        u = self.r.units.get(self.mvp.uid)
        return self.target[1] + (u.r * 0.6 if u else 12) - 6

    def _ball_pos(self, t):
        """World position + rotation of the ball at finale time t (after the throw)."""
        f, (tx, ty) = self.finale, self.target
        x, y = f["stop"]
        top = ty - 34                       # where the ball hovers while it opens
        if t < self.HIT:                    # throw arc
            p = (t - self.THROW) / (self.HIT - self.THROW)
            return x + (tx - x) * p, (y - 30) + (top - (y - 30)) * p - math.sin(p * math.pi) * 70, -p * 900
        if t < self.CLOSE:                  # bounce back up a little and hover
            p = min(1.0, (t - self.HIT) / 0.25)
            return tx, top - math.sin(p * math.pi / 2) * 14 + math.sin(t * 9) * 2, 0
        gy = self._ball_ground()
        if t < self.LAND:                   # drop with two bounces
            p = (t - self.CLOSE) / (self.LAND - self.CLOSE)
            h = (top - 14) - gy             # negative: above the ground
            if p < 0.55:
                q = p / 0.55
                return tx, gy + h * (1 - q * q), 0
            q = (p - 0.55) / 0.45
            bounce = abs(math.sin(q * math.pi * 2)) * (1 - q) * 22
            return tx, gy - bounce, 0
        ang = 0
        for at in self.SHAKES:
            if at <= t < at + 0.55:
                ph = (t - at) / 0.55
                ang = math.sin(ph * math.pi * 2) * 28 * (1 - ph * 0.3)
        return tx + ang * 0.15, gy, ang

    # ------------------------------------------------------------------ drawing
    def draw(self, surf):
        self.r.draw(surf)
        t = self.t
        if self.phase == "intro":
            self._draw_balls(surf, t)
            if t > 3.0:
                k = min(1.0, (t - 3.0) / 0.35)
                sc = 1.0 + 0.25 * math.sin(k * math.pi) if k < 1 else 1.0
                gfx.title_text(surf, self.cfg["title"], (W / 2, H * 0.40), 56, scale=sc)
            if t > 4.0 and self.cfg.get("subtitle"):
                gfx.title_text(surf, self.cfg["subtitle"], (W / 2, H * 0.40 + 66), 40)
            for i, n in enumerate(("3", "2", "1")):
                start = 5.0 + i * 0.8
                if start <= t < start + 0.8:
                    k = (t - start) / 0.8
                    gfx.title_text(surf, n, (W / 2, H * 0.40 + 150), 110, scale=1.4 - 0.4 * k,
                                     alpha=int(255 * (1 - max(0, k - 0.6) / 0.4)))
        if self.phase == "battle" and self.t - self.intro_len < 0.9:
            k = (self.t - self.intro_len) / 0.9
            gfx.title_text(surf, "FIGHT!", (W / 2, H * 0.47), 100, scale=1 + k * 0.3,
                             alpha=int(255 * (1 - k)))
        if self.phase in ("battle", "won") and self.cutscene is None:
            self._draw_counts(surf)
        if self.cutscene is not None:
            self.cutscene.draw(surf)
        if self.phase in ("won", "outro") or (self.phase == "finale" and self.finale["t"] < 1.2):
            name = self.team_names[self.sim.winner] if self.sim.winner is not None else "Nobody"
            gfx.title_text(surf, f"{name} WINS!", (W / 2, H * 0.30), 64)
            if self.mvp:
                gfx.text(surf, f"MVP: {self.mvp.mon.name}  ({self.mvp.kills} KOs)", (W / 2, H * 0.30 + 60), 26)
        if self.phase == "finale":
            self._draw_finale(surf)
        if self.paused:
            gfx.text(surf, "PAUSED", (W / 2, H / 2), 48)
        if self.speed != 1.0 and self.phase == "battle":
            gfx.text(surf, f"x{self.speed:g}", (W - 50, H - 30), 22)

    def _draw_balls(self, surf, t):
        img = gfx.ball_sprite(self.ball_size)
        for uid, (x, y) in self.balls.items():
            if uid in self.popped:
                continue
            row_delay = ((y - ARENA[1]) % 400) / 400 * 0.5 if y < H / 2 else ((ARENA[3] - y) % 400) / 400 * 0.5
            k = max(0.0, min(1.0, (t - row_delay) / 0.6))
            if k <= 0:
                continue
            bounce = abs(math.sin(k * math.pi * 2.5)) * (1 - k) * 40
            yy = y - (1 - k) * 260 - bounce
            sx, sy = self.r.world_to_screen(x, yy)
            surf.blit(img, img.get_rect(center=(sx, sy)))

    def _draw_royale_hud(self, surf):
        left = sum(1 for u in self.sim.units if u.alive)
        ui_w = 190
        pygame.draw.rect(surf, INK, (W / 2 - ui_w / 2, H - 62, ui_w, 48), border_radius=12)
        gfx.text(surf, f"{left} LEFT", (W / 2, H - 38), 30, (255, 230, 120) if left <= 10 else (255, 255, 255))
        now = self.r.t
        for i, (killer, victim, t) in enumerate(reversed(self.r.kills)):
            age = now - t
            if age > 4.0:
                continue
            a = int(255 * min(1.0, (4.0 - age) / 0.6))
            gfx.text(surf, f"{killer}  >  {victim}", (W - 16, 170 + i * 26), 17, (255, 255, 255), INK, 2,
                     anchor="midright", alpha=a)
        if self.storm_msg and self.t - self.storm_msg[1] < 2.5:
            k = self.t - self.storm_msg[1]
            msg = "THE STORM IS FORMING" if self.storm_msg[0] == 1 else "THE STORM CLOSES IN!"
            gfx.title_text(surf, msg, (W / 2, H * 0.16), 40, scale=1.15 - 0.15 * min(1.0, k / 0.3),
                           color=(230, 170, 255), alpha=int(255 * min(1.0, (2.5 - k) / 0.5)))

    def _draw_counts(self, surf):
        if self.royale:
            self._draw_royale_hud(surf)
            return
        y = H - 26
        if len(self.counts) <= 2:
            for i, (name, c) in enumerate(zip(self.team_names, self.counts)):
                x = W * (0.25 if i == 0 else 0.75)
                gfx.text(surf, f"{name}: {c}", (x, y), 22, gfx.TEAM_COLORS[i] if c else (150, 150, 150))
            return
        # extra teams joined (event bosses): base teams on the bottom row, event bosses above
        for i, (name, c) in enumerate(zip(self.team_names[:2], self.counts[:2])):
            gfx.text(surf, f"{name}: {c}", (W * (0.25 if i == 0 else 0.75), y), 22,
                     gfx.TEAM_COLORS[i] if c else (150, 150, 150))
        extra = list(zip(self.team_names[2:], self.counts[2:]))
        for j, (name, c) in enumerate(extra):
            x = W * (j + 1) / (len(extra) + 1)
            gfx.text(surf, name if c else f"{name} (down)", (x, y - 30), 20,
                     (255, 210, 80) if c else (150, 150, 150))

    def _draw_open_ball(self, surf, cx, cy, size, open_k):
        """Poke Ball drawn in two halves; open_k 0 = closed, 1 = lid flipped open."""
        r = size / 2
        lid = pygame.Surface((size + 4, size // 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(lid, (230, 45, 45), (r + 2, r + 2), r)
        pygame.draw.circle(lid, INK, (r + 2, r + 2), r, max(2, int(size / 12)))
        base = pygame.Surface((size + 4, size // 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(base, (245, 245, 245), (r + 2, 2), r)
        pygame.draw.circle(base, INK, (r + 2, 2), r, max(2, int(size / 12)))
        surf.blit(base, base.get_rect(midtop=(cx, cy)))
        if open_k > 0:  # glow from inside
            pygame.draw.ellipse(surf, (255, 200, 200), (cx - r * 0.8, cy - r * 0.25, r * 1.6, r * 0.5))
        rot = pygame.transform.rotate(lid, open_k * 70)
        surf.blit(rot, rot.get_rect(midbottom=(cx - open_k * r * 0.5, cy - open_k * r * 0.35)))
        pygame.draw.circle(surf, (250, 250, 250), (int(cx - open_k * r * 0.4), int(cy - open_k * r * 0.2)),
                           max(2, int(size / 6)))
        pygame.draw.circle(surf, INK, (int(cx - open_k * r * 0.4), int(cy - open_k * r * 0.2)),
                           max(2, int(size / 6)), 2)

    def _draw_finale(self, surf):
        f = self.finale
        t = f["t"]
        (x0, y0), (x1, y1) = f["start"], f["stop"]
        z = self.r.cam[2]
        # trainer walks in, winds up and throws
        k = min(1.0, t / 2.0)
        x, y = x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
        hop = -abs(math.sin((t - 1.7) / 0.3 * math.pi)) * 10 if 1.7 < t < 2.0 else 0
        frame = int(t * 6) % 2 if k < 1 else (1 if self.THROW <= t < self.THROW + 0.25 else 0)
        tr = gfx.trainer_sprite(max(3, int(1.6 * z)), frame)
        if x1 < x0:
            tr = pygame.transform.flip(tr, True, False)
        sx, sy = self.r.world_to_screen(x, y + hop)
        surf.blit(tr, tr.get_rect(midbottom=(sx, sy)))
        tx, ty = self.target
        size = max(12, int(10 * z))
        u = self.r.units.get(self.mvp.uid)
        # the Pokemon turns into red energy and gets pulled into the ball
        if u and self.ABSORB <= t < self.CLOSE:
            p = (t - self.ABSORB) / (self.CLOSE - self.ABSORB)
            bx, by, _ = self._ball_pos(t)
            mx, my = tx + (bx - tx) * p ** 2, (ty + u.r * 0.6) + (by - (ty + u.r * 0.6)) * p ** 2
            img = SPRITES.get(u.form, max(4, u.r * 2.3 * z * (1 - p * 0.95)), flip=u.face > 0)
            red = gfx.silhouette(img, (255, 70, 70))
            red.set_alpha(int(255 * min(1.0, p * 4)))
            msx, msy = self.r.world_to_screen(mx, my)
            if p < 0.25:
                surf.blit(img, img.get_rect(midbottom=(msx, msy)))
            surf.blit(red, red.get_rect(midbottom=(msx, msy)))
            bsx, bsy = self.r.world_to_screen(bx, by)
            beam = pygame.Surface((W, H), pygame.SRCALPHA)
            for i in range(3):
                pygame.draw.line(beam, (255, 90, 90, 140 - i * 40), (bsx, bsy), (msx, msy - img.get_height() / 2),
                                 int((12 - i * 4) * z / 2) + 2)
            surf.blit(beam, (0, 0))
        # the ball
        if t >= self.THROW:
            bx, by, ang = self._ball_pos(t)
            bsx, bsy = self.r.world_to_screen(bx, by)
            if t < self.HIT:  # motion trail
                for i in range(1, 5):
                    px, py, _ = self._ball_pos(max(self.THROW, t - i * 0.03))
                    tsx, tsy = self.r.world_to_screen(px, py)
                    pygame.draw.circle(surf, (255, 255, 255), (int(tsx), int(tsy)), max(1, size // 2 - i * 2), 1)
            if self.HIT <= t < self.CLOSE:
                open_k = min(1.0, (t - self.HIT) / 0.2) * min(1.0, (self.CLOSE - t) / 0.15)
                self._draw_open_ball(surf, bsx, bsy, size, open_k)
            else:
                ball = pygame.transform.rotate(gfx.ball_sprite(size), ang)
                surf.blit(ball, ball.get_rect(center=(bsx, bsy - size / 2 if t >= self.LAND else bsy)))
                # the button glows while it shakes, then locks with a click
                if t >= self.LAND:
                    lit = any(at <= t < at + 0.55 for at in self.SHAKES) or t >= self.CAUGHT
                    if lit:
                        col = (255, 230, 120) if t >= self.CAUGHT else (255, 120, 120)
                        pygame.draw.circle(surf, col, (int(bsx + ang * 0.1), int(bsy - size / 2)), max(2, size // 6))
            if t >= self.CAUGHT:  # stars burst out
                st = t - self.CAUGHT
                for vx, vy, a in f.get("stars", []):
                    if st > 1.2:
                        break
                    px, py = bsx + vx * st * z * 0.5, bsy - size / 2 + (vy * st + 260 * st * st) * z * 0.5
                    rr = 7 * z * (1 - st / 1.2) + 2
                    pts = [(px + math.cos(a + i * math.pi / 5) * (rr if i % 2 == 0 else rr * 0.45),
                            py + math.sin(a + i * math.pi / 5) * (rr if i % 2 == 0 else rr * 0.45)) for i in range(10)]
                    pygame.draw.polygon(surf, (255, 225, 80), pts)
                    pygame.draw.polygon(surf, INK, pts, 1)
        # GOTCHA card
        if t > self.CAUGHT + 0.5:
            p = min(1.0, (t - self.CAUGHT - 0.5) / 0.35)
            ease = 1 - (1 - p) ** 3
            gfx.title_text(surf, "GOTCHA!", (W / 2, H * 0.20), 80, scale=1.6 - 0.6 * ease)
            cy = H - 230 + (1 - ease) * 300
            ui_rect = pygame.Rect(60, cy - 90, W - 120, 180)
            pygame.draw.rect(surf, INK, ui_rect.move(0, 6), border_radius=18)
            pygame.draw.rect(surf, (248, 246, 236), ui_rect, border_radius=18)
            pygame.draw.rect(surf, (230, 60, 60), (ui_rect.x, ui_rect.y, ui_rect.w, 14), border_top_left_radius=18,
                             border_top_right_radius=18)
            m = self.mvp
            img = SPRITES.get(m.mon.entry["id"], 140)
            surf.blit(img, img.get_rect(center=(ui_rect.x + 100, ui_rect.centery + 6)))
            line = f"{m.mon.name} was caught!"
            fs = 30
            while fs > 16 and gfx.font(fs, True).size(line)[0] > ui_rect.w - 210:
                fs -= 2
            gfx.text(surf, line, (ui_rect.x + 190, ui_rect.y + 52), fs, INK, None, anchor="midleft")
            who = "Battle Royale champion" if self.royale else self.team_names[m.team]
            gfx.text(surf, f"MVP  -  {m.kills} KOs  -  {who}", (ui_rect.x + 190, ui_rect.y + 96),
                     20, (90, 90, 100), None, anchor="midleft", chunky=False)
            for i, typ in enumerate(m.mon.types):
                gfx.pill(surf, typ.upper(), (ui_rect.x + 230 + i * 90, ui_rect.y + 136), gfx.type_color(typ, 0), 14)


# ---------------------------------------------------------------------- headless rendering

def record(dex, cfg, out_path, fps=30, log=print):
    """Render a showcase straight to an MP4 (needs ffmpeg)."""
    from .recorder import Recorder
    disp = gfx.Display(headless=True)

    def prog(done, total):
        if done == total or done % 50 == 0:
            log(f"[showcase] sprites {done}/{total}")

    scene = ShowcaseScene(dex, cfg, prog)
    AUDIO.init(headless=True)
    rec = Recorder(out_path + ".video.mp4", gfx.W, gfx.H, fps)
    frames = 0
    AUDIO.capture, AUDIO.clock = [], (lambda: frames / fps)
    try:
        while not scene.done and frames < fps * 60 * 8:
            scene.update(1 / fps)
            disp.canvas.fill((0, 0, 0))
            scene.draw(disp.canvas)
            rec.write(disp.canvas)
            frames += 1
            if frames % (fps * 10) == 0:
                log(f"[showcase] rendered {frames // fps}s ({scene.phase})")
    finally:
        rec.close()
        events, AUDIO.capture, AUDIO.clock = AUDIO.capture, None, None
    finish_video(out_path, events, frames / fps, log)
    log(f"[showcase] saved {out_path} ({frames / fps:.1f}s, seed {scene.seed})")
    return out_path


def finish_video(out_path, events, duration, log=print):
    """Mix the captured sounds and put them on the silent video."""
    from .audio import mix, mux_track
    video = out_path + ".video.mp4"
    try:
        log("[showcase] mixing audio...")
        wav = out_path + ".wav"
        mix(events, duration, wav)
        mux_track(video, wav, out_path)
        os.remove(wav)
        os.remove(video)
    except Exception as e:  # noqa: BLE001 - keep the silent video rather than nothing
        log(f"[showcase] audio failed ({e}); saving without sound")
        os.replace(video, out_path)
