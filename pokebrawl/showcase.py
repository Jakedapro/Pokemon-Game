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
from .cinematics import Cutscene
from .gfx import H, W
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
}
EVENTS = ["arceus", "primal", "rayquaza", "meteor"]
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
    return teams, names


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
        for key in ("arceus", "kyogre-primal", "groudon-primal", "rayquaza-mega", "deoxys"):
            e = dex.get(key)
            if e:
                ids.add(e["id"])
        prefetch(list(ids), progress)
        n = max(len(t) for t in teams)
        radius = 13 if n > 40 else 17 if n > 12 else 24
        self.sim = Sim(dex, teams, seed=seed, hp_mult=cfg["hp_mult"], boss_hp_mult=cfg["boss_hp_mult"],
                       radius=radius, mega={0: "auto", 1: "auto"} if cfg.get("megas", True) else {0: "off", 1: "off"},
                       ai={0: "normal", 1: "normal"}, time_ramp=cfg.get("time_ramp", 80))
        self.r = ArenaRenderer(dex, self.sim.roster(), mode="showcase", team_names=self.team_names)
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

    def _spawn(self, key, team_name, pos, hp_scale=2.0, radius_scale=1.2, signature=None):
        entry = self.dex.get(key)
        m = auto_member(self.dex, entry, self.rng, None, allow_mega=False, level=self.level + 10, comp=False)
        sig = self.dex.move(signature) if signature else None
        if sig and sig["id"] not in m.moves:
            m.moves = [sig["id"]] + m.moves[:3]
        hp_scale *= min(1.0, max(0.3, self.start_units / 180))  # don't steamroll small fights
        u = self.sim.spawn(m, self._new_team(team_name), pos, boss=True, hp_scale=hp_scale,
                           radius_scale=radius_scale)
        self.r.roster[u.uid] = self.sim.roster()[u.uid]
        return u

    def _trigger(self, name):
        cx, cy = (ARENA[0] + ARENA[2]) / 2, (ARENA[1] + ARENA[3]) / 2
        if name == "arceus":
            def act():
                self._spawn("arceus", "Arceus", (cx, cy), hp_scale=2.6, radius_scale=1.35, signature="judgment")
                self.r.god_beam(cx, cy)
            self.cutscenes.append(Cutscene("card", 4.2, (cx, cy), 1.5, "ARCEUS DESCENDS",
                                           "A GOD HAS ENTERED THE BATTLE", (255, 200, 60),
                                           self.dex.get("arceus")["id"], action=act, cry=self.dex.get("arceus")["id"]))
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
                                           portrait=a.mon.entry["id"], portrait2=b.mon.entry["id"],
                                           action_at=0.45, sound="count"))

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
        tx = self.target[0] - 140 if self.target[0] > ARENA[0] + 200 else self.target[0] + 140
        self.finale = {"t": 0.0, "start": (ARENA[0] - 30 if tx < self.target[0] else ARENA[2] + 30, self.target[1] + 10),
                       "stop": (tx, self.target[1] + 10), "stage": "walk"}
        self.r.cam_target = (self.target[0] + (tx - self.target[0]) / 2, self.target[1], 1.6)

    def _update_finale(self, dt):
        f = self.finale
        f["t"] += dt
        t = f["t"]
        uid = self.mvp.uid
        if t > 2.0 and self._once("throw"):
            AUDIO.play("select")
        if t > 2.7 and self._once("capture"):
            AUDIO.play("ball")
        for k in range(3):
            if t > 3.4 + k * 0.93 and self._once(f"wiggle{k}"):
                AUDIO.play("wiggle")
        if t > 6.2 and self._once("caught"):
            AUDIO.play("catch")
        if 2.7 <= t < 3.3:
            k = (t - 2.7) / 0.6
            self.r.white[uid] = min(1.0, k * 2)
            self.r.scale_over[uid] = max(0.02, 1 - k)
        elif t >= 3.3:
            self.r.hidden.add(uid)
        if 6.2 <= t < 6.25:
            self.r._burst(self.target[0], self.target[1], (255, 240, 120), 24, 160, 5, 0.9)
        if t > 7.0:
            sx, sy = f["stop"]
            self.r.cam_target = ((sx + self.target[0]) / 2, sy - 30, 2.4)
        if t > 11.0:
            self.done = True

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

    def _draw_counts(self, surf):
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

    def _draw_finale(self, surf):
        f = self.finale
        t = f["t"]
        (x0, y0), (x1, y1) = f["start"], f["stop"]
        k = min(1.0, t / 2.0)
        x, y = x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
        frame = int(t * 6) % 2 if k < 1 else 0
        z = self.r.cam[2]
        tr = gfx.trainer_sprite(max(3, int(3 * z)), frame)
        if x1 < x0:
            tr = pygame.transform.flip(tr, True, False)
        sx, sy = self.r.world_to_screen(x, y)
        surf.blit(tr, tr.get_rect(midbottom=(sx, sy)))
        tx, ty = self.target
        ball = gfx.ball_sprite(int(18 * z))
        if 2.0 <= t < 2.7:  # throw arc
            p = (t - 2.0) / 0.7
            bx = x + (tx - x) * p
            by = y - 30 + (ty - y) * p - math.sin(p * math.pi) * 90
            bsx, bsy = self.r.world_to_screen(bx, by)
            rot = pygame.transform.rotate(ball, -p * 720)
            surf.blit(rot, rot.get_rect(center=(bsx, bsy)))
        elif t >= 2.7:
            bsx, bsy = self.r.world_to_screen(tx, ty)
            ang = 0
            if 3.4 < t < 6.2:  # three wiggles
                ph = (t - 3.4) % 0.93
                ang = math.sin(ph / 0.45 * math.pi) * 25 if ph < 0.45 else 0
            if 2.7 <= t < 3.3:
                beam = pygame.Surface((W, H), pygame.SRCALPHA)
                pygame.draw.line(beam, (255, 255, 255, 160), (bsx, bsy), (bsx, bsy - 40 * z), int(10 * z))
                surf.blit(beam, (0, 0))
            rot = pygame.transform.rotate(ball, ang)
            surf.blit(rot, rot.get_rect(center=(bsx, bsy)))
        if t > 6.2:
            name = self.mvp.mon.name
            gfx.title_text(surf, "GOTCHA!", (W / 2, H * 0.22), 72)
            gfx.text(surf, f"{name} was caught!", (W / 2, H * 0.22 + 64), 32)


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
