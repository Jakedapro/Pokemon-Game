"""Tournament showcase: 8 or 16 Pokemon, single elimination. Every match is a 1v1 showcase (so it plays out on
the duel stage), with an animated bracket between rounds and a champion finale. Works like a ShowcaseScene
(update/draw/handle/done/interest), so it can be watched live or recorded and auto-edited."""
import math
import random

import pygame

from . import gfx
from .audio import AUDIO
from .cinematics import _ease, _vignette, draw_plate, eye_strip
from .gfx import H, INK, SPRITES, W, WHITE
from .pokedex import prefetch
from .showcase import ShowcaseScene, load_config


FORM_WORDS = ("Normal", "Plant", "Altered", "Land", "Red Striped", "Standard", "Male", "Incarnate", "Ordinary", "Aria",
              "Shield", "Average", "50", "Baile", "Midday", "Solo", "Red Meteor", "Disguised", "Amped", "Ice",
              "Full Belly", "Single Strike", "Family Of Four", "Green Plumage", "Zero", "Curly", "Two Segment")


def short_name(e):
    """'Giratina Altered' -> 'Giratina': default forms don't need their form name on a bracket."""
    name = e["name"]
    if e.get("default"):
        for w in FORM_WORDS:
            if name.endswith(" " + w):
                return name[: -len(w) - 1]
    return name


def pick_entrants(dex, cfg, rng):
    """The bracket: explicit "pokemon" names, or a random draw from the teams' filters."""
    size = 16 if cfg.get("size", 8) >= 16 else 8
    names = cfg.get("pokemon")
    if names:
        entries = [dex.get(n) for n in names]
        entries = [e for e in entries if e][:size]
    else:
        pool, seen = [], set()
        for t in cfg.get("teams", []):
            for e in dex.filter(t.get("filter", t)):
                if e["species"] not in seen:
                    seen.add(e["species"])
                    pool.append(e)
        entries = rng.sample(pool, min(size, len(pool)))
    while len(entries) & (len(entries) - 1):  # brackets need 2, 4, 8 or 16
        entries.pop()
    return entries


class TournamentScene:
    BRACKET_T = 3.2      # seconds on the bracket before each match
    AFTER_WIN = 2.6      # seconds of a match's win screen before going back to the bracket
    max_ff = 24.0        # auto-edit may fast-forward early rounds harder than a normal showcase

    def __init__(self, dex, cfg, progress=None, wide=False):
        self.dex = dex
        self.cfg = cfg
        self.size = (W, H)
        self.W, self.H = W, H
        seed = cfg.get("seed")
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.rng = random.Random(self.seed)
        self.entrants = pick_entrants(dex, cfg, self.rng)
        prefetch([e["id"] for e in self.entrants], progress)
        self.rounds = [list(range(len(self.entrants)))]   # indexes into entrants, per round
        self.results = []        # (round, match, winner index)
        self.round = 0
        self.match = 0
        self.match_scene = None
        self.phase = "intro"     # intro -> bracket -> match -> bracket ... -> champion -> done
        self.t = 0.0
        self.phase_t = 0.0
        self.done = False
        self.speed = cfg.get("speed", 1.0)
        self.paused = False
        self.champion = None
        self.confetti = []

    # ------------------------------------------------------------------ flow
    @property
    def pair(self):
        r = self.rounds[self.round]
        return r[self.match * 2], r[self.match * 2 + 1]

    def _start_match(self):
        a, b = self.pair
        ea, eb = self.entrants[a], self.entrants[b]
        final = len(self.rounds[self.round]) == 2
        mcfg = load_config({
            "title": f"{short_name(ea)} vs {short_name(eb)}", "subtitle": "",
            "teams": [{"name": short_name(ea), "pokemon": [ea["key"]]}, {"name": short_name(eb), "pokemon": [eb["key"]]}],
            "megas": self.cfg.get("megas", True), "events": "none", "bosses": "none", "hp_mult": 6, "finale": final, "quick_intro": True,
            "seed": self.seed * 31 + self.round * 7 + self.match, "speed": self.speed,
            "level": self.cfg.get("level", 50)})
        self.match_scene = ShowcaseScene(self.dex, mcfg)
        self.phase = "match"
        self.phase_t = 0.0

    def _finish_match(self):
        sc = self.match_scene
        a, b = self.pair
        winner = (a, b)[sc.sim.winner] if sc.sim.winner in (0, 1) else self.rng.choice((a, b))
        self.results.append((self.round, self.match, winner))
        nxt = self.rounds[self.round + 1] if len(self.rounds) > self.round + 1 else None
        if nxt is None:
            nxt = []
            self.rounds.append(nxt)
        nxt.append(winner)
        self.match += 1
        if self.match * 2 >= len(self.rounds[self.round]):
            self.round += 1
            self.match = 0
        self.match_scene = None
        if len(self.rounds[self.round]) == 1:
            self.champion = self.rounds[self.round][0]
            self.phase = "champion"
            AUDIO.play("win")
            AUDIO.cry(self.entrants[self.champion]["id"], 1.0)
            self.confetti = [[self.rng.uniform(0, W), self.rng.uniform(-H, 0), self.rng.uniform(-40, 40),
                              self.rng.uniform(140, 300), gfx.hsv(self.rng.random()), self.rng.uniform(0, 6)]
                             for _ in range(140)]
        else:
            self.phase = "bracket"
        self.phase_t = 0.0

    def update(self, dt):
        if self.paused:
            return
        self.t += dt
        self.phase_t += dt
        if self.t == dt:
            AUDIO.music("showcase")
        if self.phase == "intro" and self.phase_t > 3.4:
            self.phase, self.phase_t = "bracket", 0.0
        elif self.phase == "bracket":
            if self.phase_t < dt * 1.5:
                AUDIO.play("select")
            if self.phase_t > self.BRACKET_T:
                self._start_match()
        elif self.phase == "match":
            sc = self.match_scene
            sc.update(dt)
            final = len(self.rounds[self.round]) == 2
            if sc.done or (not final and sc.phase in ("won", "outro") and sc.t - sc.end_t > self.AFTER_WIN):
                self._finish_match()
        elif self.phase == "champion":
            for c in self.confetti:
                c[0] += c[2] * dt
                c[1] += c[3] * dt
                c[5] += dt * 4
            if self.phase_t > 7.0:
                self.done = True

    def handle(self, ev, pos=None):
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self.done = True
                return
            if ev.key == pygame.K_SPACE:
                self.paused = not self.paused
                return
            if ev.key in (pygame.K_RIGHT, pygame.K_EQUALS, pygame.K_PLUS):
                self.speed = min(8.0, self.speed * 2)
            elif ev.key in (pygame.K_LEFT, pygame.K_MINUS):
                self.speed = max(0.25, self.speed / 2)
            if self.match_scene is not None:
                self.match_scene.speed = self.speed

    def interest(self):
        """For auto-editing recordings."""
        if self.phase == "match" and self.match_scene is not None:
            final = len(self.rounds[self.round]) == 2
            sc = self.match_scene
            base = sc.interest()
            if final:
                return max(base, 1)
            # early rounds: just the knockout blow and the win - the rest whizzes past
            if sc.phase in ("won", "outro"):
                return 2 if sc.t - sc.end_t < 1.0 else 0
            return 0
        if self.phase in ("intro", "champion"):
            return 2
        last = len(self.rounds[self.round]) == 2
        return 2 if last or 0.6 < self.phase_t < 1.3 else 0

    # ------------------------------------------------------------------ drawing
    def _slot(self, rnd, i):
        """Screen position of slot i in round rnd (rounds go left to right, slots spread top to bottom)."""
        n0 = len(self.entrants)
        rounds = int(math.log2(n0)) + 1
        x = 50 if rnd == 0 else 330 + (rnd - 1) * (W - 390) / max(1, rounds - 2)
        count = n0 >> rnd
        top, bottom = 230, H - 120
        y = top + (i + 0.5) * (bottom - top) / count
        return x, y

    def _draw_bracket(self, surf, highlight=None, reveal=1.0):
        surf.fill((14, 12, 26))
        for i in range(0, H, 6):
            pygame.draw.line(surf, (18, 16, 32), (0, i), (W, i))
        draw_plate(surf, self.cfg.get("title", "TOURNAMENT").upper(), (W / 2, 80), 40, (255, 200, 60), 1.0,
                   angle=-3)
        rnd_names = {1: "FINAL", 2: "SEMIFINALS", 3: "QUARTERFINALS", 4: "ROUND OF 16"}
        total = len(self.rounds[0])
        if self.phase in ("bracket", "match"):
            left = len(self.rounds[self.round])
            gfx.text(surf, rnd_names.get(int(math.log2(left)), ""), (W / 2, 150), 22, (255, 225, 150), INK, 2)
        n_rounds = int(math.log2(total)) + 1
        lost = set()
        for rnd in range(len(self.rounds)):
            members = self.rounds[rnd]
            for i in range(0, len(members) - 1, 2):
                for j in (i, i + 1):
                    nxt = self.rounds[rnd + 1] if rnd + 1 < len(self.rounds) else []
                    if len(nxt) > i // 2 and nxt[i // 2] != members[j]:
                        lost.add((rnd, members[j]))
        for rnd in range(n_rounds):
            count = total >> rnd
            for i in range(count):
                x, y = self._slot(rnd, i)
                if rnd + 1 < n_rounds:  # bracket lines to the next round
                    nx, ny = self._slot(rnd + 1, i // 2)
                    sx = x + (180 if rnd == 0 else 30)
                    mid = (sx + nx) / 2
                    won = rnd + 1 < len(self.rounds) and i < len(self.rounds[rnd]) and \
                        i // 2 < len(self.rounds[rnd + 1]) and self.rounds[rnd + 1][i // 2] == self.rounds[rnd][i]
                    col = (255, 200, 60) if won else (70, 70, 100)
                    pygame.draw.lines(surf, col, False, [(sx, y), (mid, y), (mid, ny), (nx - 30, ny)], 3 if won else 2)
                members = self.rounds[rnd] if rnd < len(self.rounds) else []
                big = count <= 8
                pygame.draw.circle(surf, (34, 32, 52), (int(x), int(y)), 30 if big else 20)
                if i < len(members):
                    idx = members[i]
                    if rnd == 0 and i / max(1, count) > reveal:
                        continue
                    e = self.entrants[idx]
                    is_lost = (rnd, idx) in lost
                    hot = highlight is not None and rnd == self.round and idx in highlight
                    if hot:
                        pulse = 0.5 + 0.5 * math.sin(self.t * 8)
                        pygame.draw.circle(surf, (255, 210, 80), (int(x), int(y)), int((34 if big else 22) + pulse * 4), 4)
                    img = SPRITES.get(e["id"], 64 if big else 40)
                    if is_lost:
                        img = img.copy()
                        img.set_alpha(80)
                    surf.blit(img, img.get_rect(center=(x, y)))
                    if is_lost:
                        pygame.draw.line(surf, (220, 60, 60), (x - 18, y - 18), (x + 18, y + 18), 4)
                        pygame.draw.line(surf, (220, 60, 60), (x + 18, y - 18), (x - 18, y + 18), 4)
                    if rnd == 0:
                        gfx.text(surf, short_name(e)[:13], (x + (34 if big else 26), y), 18 if big else 15,
                                 (230, 230, 245) if not is_lost else (110, 110, 120), INK, 2, anchor="midleft")
        if highlight is not None and self.phase == "bracket":
            a, b = (self.entrants[i] for i in highlight)
            q = self.phase_t
            if q > 0.6:  # the next match, eye to eye
                hgt = 150
                k = _ease((q - 0.6) / 0.25)
                strip = pygame.Surface((W, hgt * 2 + 20), pygame.SRCALPHA)
                eye_strip(strip, a["id"], (0, 0, W, hgt), q, gfx.TEAM_COLORS[0], flip=True)
                eye_strip(strip, b["id"], (0, hgt + 20, W, hgt), q, gfx.TEAM_COLORS[1])
                strip.set_alpha(int(235 * k))
                surf.blit(strip, (0, H / 2 - hgt - 10))
                draw_plate(surf, f"{short_name(a)}  VS  {short_name(b)}".upper(), (W / 2, H / 2), 30, (255, 200, 60),
                           1.4 - 0.4 * k, int(255 * k), angle=-4)

    def draw(self, surf):
        if self.phase == "intro":
            self._draw_bracket(surf, reveal=min(1.0, self.phase_t / 2.2))
            q = self.phase_t
            draw_plate(surf, f"{len(self.entrants)} POKEMON ENTER", (W / 2, H * 0.5), 44, (230, 60, 70),
                       1.5 - 0.5 * _ease(q / 0.3), int(255 * min(1.0, (3.4 - q) / 0.5)), angle=-5)
            gfx.text(surf, "ONE CHAMPION", (W / 2, H * 0.5 + 70), 30, WHITE, INK, 3,
                     alpha=int(255 * min(1.0, max(0.0, (q - 0.8) / 0.4)) * min(1.0, (3.4 - q) / 0.5)))
        elif self.phase == "bracket":
            self._draw_bracket(surf, highlight=self.pair)
        elif self.phase == "match":
            self.match_scene.draw(surf)
            r = len(self.rounds[self.round])
            label = {2: "FINAL", 4: "SEMIFINAL", 8: "QUARTERFINAL", 16: "ROUND OF 16"}.get(r, "")
            gfx.pill(surf, label, (W / 2, H - 40), (40, 30, 60), 16)
        elif self.phase == "champion":
            self._draw_champion(surf)

    def _draw_champion(self, surf):
        e = self.entrants[self.champion]
        q = self.phase_t
        surf.fill((20, 14, 6))
        rays = pygame.Surface((W, H), pygame.SRCALPHA)
        for i in range(14):
            a = i / 14 * math.tau + q * 0.4
            pts = [(W / 2, H * 0.45), (W / 2 + math.cos(a - 0.1) * 1500, H * 0.45 + math.sin(a - 0.1) * 1500),
                   (W / 2 + math.cos(a + 0.1) * 1500, H * 0.45 + math.sin(a + 0.1) * 1500)]
            pygame.draw.polygon(rays, (255, 210, 90, 45), pts)
        surf.blit(rays, (0, 0))
        img = SPRITES.get(e["id"], 360)
        bob = math.sin(q * 2) * 8
        surf.blit(img, img.get_rect(midbottom=(W / 2, H * 0.72 + bob)))
        # trophy
        tx, ty = W / 2, H * 0.74
        pygame.draw.ellipse(surf, (255, 205, 70), (tx - 110, ty - 10, 220, 40))
        pygame.draw.polygon(surf, (255, 205, 70), [(tx - 110, ty + 10), (tx + 110, ty + 10), (tx + 60, ty + 130),
                                                    (tx - 60, ty + 130)])
        for side in (-1, 1):
            pygame.draw.arc(surf, (230, 170, 40), (tx + side * 110 - 40, ty + 10, 80, 90),
                            -math.pi / 2 if side > 0 else math.pi / 2, math.pi / 2 if side > 0 else math.pi * 1.5, 10)
        pygame.draw.rect(surf, (230, 170, 40), (tx - 18, ty + 130, 36, 60))
        pygame.draw.rect(surf, (200, 140, 30), (tx - 80, ty + 186, 160, 36), border_radius=6)
        pygame.draw.polygon(surf, (255, 240, 170), [(tx - 70, ty + 20), (tx - 50, ty + 20), (tx - 20, ty + 120),
                                                    (tx - 34, ty + 120)])
        gfx.text(surf, f"BEAT {len(self.entrants) - 1} POKEMON", (tx, ty + 204), 16, (90, 50, 0), None, 0)
        draw_plate(surf, "CHAMPION!", (W / 2, H * 0.14), 64, (255, 200, 60), 1.6 - 0.6 * _ease(q / 0.3), angle=-6)
        draw_plate(surf, short_name(e).upper(), (W / 2, H * 0.14 + 86), 30, (230, 60, 70), 1.0, angle=-3)
        for x, y, vx, vy, col, spin in self.confetti:
            if 0 <= y <= H:
                w = 10 * abs(math.cos(spin))
                pygame.draw.rect(surf, col, (x, y, max(2, w), 6))
        vig = _vignette((W, H))
        vig.set_alpha(140)
        surf.blit(vig, (0, 0))


def make_scene(dex, cfg, progress=None, wide=False):
    """The right scene for a showcase config: a tournament bracket or a normal arena battle."""
    if cfg.get("mode") == "tournament":
        return TournamentScene(dex, cfg, progress)
    return ShowcaseScene(dex, cfg, progress, wide=wide)
