"""The Starter's Journey: your starter carries you to Starter's Haven, the way only it can.

    Blastoise (water)  - you ride its shell across the sea (Route 20), through a storm, firing Hydro Pump
    Venusaur  (grass)  - it leads you through the dark of Viridian Forest, clearing trees with Vine Whip
    Charizard (fire)   - you fly on its back over Mt. Ember, through the clouds, at sunset

Any other starter (the randomizer) takes the route that suits its type. It is all real Pokemon art, drawn the
way the handheld draws a cutscene: real FireRed maps seen from above (frlg.render), the Pokemon's own overworld
sprites (pokeemerald-expansion), your Surf sitting sprite, FireRed's weather (rain, fog, clouds), field effects
(ripples, shadows, Cut) and battle animation sprites (Hydro Pump, Flamethrower, Vine Whip, Thunder, sparkles).
Starter's Haven is Birth Island.
"""
import math
import os
import random
import threading
from collections import deque

import pygame

from . import adventure as A
from . import frlg
from . import gbaart as G
from . import gbaui as U
from . import pixelfont as F
from . import pokedex
from .adventure_ui import GBAScene
from .audio import AUDIO

LW, LH, K = 240, 160, 2      # a GBA screen, scaled 2x to 480x320
MAP_T, TRAVEL_T = 7.0, 34.0
OCEAN = {"water", "ice"}
FOREST = {"grass", "bug", "poison", "fairy"}
ROUTE_NAME = {"ocean": "the SEA", "forest": "the FOREST", "sky": "the MOUNTAINS"}
CAMEOS = {"ocean": ("wingull", "lapras", "mantine", "tentacool"),
          "forest": ("pikachu", "caterpie", "weedle", "butterfree", "metapod"),
          "sky": ("pidgey", "skarmory")}
OW_URL = ("https://raw.githubusercontent.com/rh-hideout/pokeemerald-expansion/"
          "73b3fbeb574327cd9420c89e56bef5aa3c08fead/graphics/pokemon/{}/overworld.png")
BA = "graphics/battle_anims/sprites/"
FX = {  # name: (path, frame w, frame h)
    "fire": (BA + "fire.png", 32, 32), "ember": (BA + "small_ember.png", 32, 32),
    "pump": (BA + "water_column.png", 16, 32), "spray": (BA + "water_droplet_2.png", 32, 32),
    "bolt": (BA + "lightning.png", 32, 32), "vine": (BA + "vine.png", 32, 32),
    "sparkle": (BA + "sparkle_1.png", 32, 32), "star": (BA + "sparkle_4.png", 32, 32),
    "halo": (BA + "round_white_halo.png", 64, 64), "eye": (BA + "small_red_eye.png", 8, 8),
    "ripple": ("graphics/field_effects/pics/ripple.png", 16, 16),
    "bigsplash": ("graphics/field_effects/pics/jump_big_splash.png", 16, 16),
    "glint": ("graphics/field_effects/pics/small_sparkle.png", 16, 16),
    "shadow": ("graphics/field_effects/pics/shadow_large.png", 32, 8),
    "shadow_s": ("graphics/field_effects/pics/shadow_medium.png", 16, 8),
    "cuttree": ("graphics/object_events/pics/misc/cut_tree.png", 16, 16),
    "cutleaf": ("graphics/field_effects/fldeff_cut.png", 8, 8),
    "rain": ("graphics/weather/rain.png", 16, 32), "cloud": ("graphics/weather/cloud.png", 64, 64),
    "fog": ("graphics/weather/fog_horizontal.png", 64, 64),
}


def family(dex, pid):
    """A Pokemon and everything it evolves into."""
    out, todo = set(), [pid]
    while todo:
        p = todo.pop()
        if p in out or p not in dex.all:
            continue
        out.add(p)
        todo += [e[0] for e in dex.all[p].get("evo") or []]
    return out


def partner(game, dex):
    """Your starter (however it has evolved), if it's still in your party."""
    if game.get("starter") is None:
        return None
    fam = family(dex, game["starter"])
    mons = [m for m in game["party"] if m["species"] in fam]
    return max(mons, key=lambda m: m["level"]) if mons else None


def biome_for(dex, pid):
    types = set(dex.all[pid]["types"])
    return "ocean" if types & OCEAN else "forest" if types & FOREST else "sky"


def lines_for(biome, nm, player):
    """(seconds into the journey, line) - the story told along the way. Each fits the message box."""
    if biome == "ocean":
        return [(0.5, f"{nm} wades into the sea. {player} climbs onto its shell."),
                (5.5, "The coast falls away. It cuts through the waves like a ship."),
                (11.0, "The sky turns black. A storm rolls in over the sea!"),
                (16.5, f"{nm} used HYDRO PUMP! You rocket over the waves!"),
                (23.0, "The storm breaks. Sunlight sparkles on the water."),
                (28.5, "Far out at sea, something is glowing. That's it!")]
    if biome == "forest":
        return [(0.5, f"No light gets through these trees. {nm} leads the way."),
                (5.5, "Eyes blink in the dark. Something is watching..."),
                (11.0, f"A tree blocks the path! {nm} used VINE WHIP!"),
                (16.5, f"{nm} hums softly. The shadows let you pass."),
                (23.0, "Light breaks through the leaves. The trees open up..."),
                (28.5, f"{nm}'s flower is glowing. It knows the way.")]
    return [(0.5, f"{nm} spreads its wings. {player} holds on tight."),
            (5.5, "One beat of its wings and the ground drops away!"),
            (11.0, "You plunge into a cloud. Everything turns white..."),
            (16.5, f"...and burst out above it! {nm} used FLAMETHROWER!"),
            (23.0, "The sun sinks behind the peaks. Everything turns gold."),
            (28.5, "Past the summit, out at sea, a light shines. The Haven!")]


# ---------------------------------------------------------------------- sprites
def mon_frames(pid):
    """The Pokemon's overworld frames {"down"/"up"/"left"/"right": [a, b]} (32x32). Falls back to its party icon."""
    path = os.path.join(pokedex.SPRITE_DIR, f"ow-{pid}.png")
    if not os.path.exists(path):
        for folder in G._icon_folders(pid):
            try:
                data = pokedex.fetch(OW_URL.format(folder), timeout=10)
            except Exception:  # noqa: BLE001
                continue
            os.makedirs(pokedex.SPRITE_DIR, exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
            break
    try:
        sheet = pygame.image.load(path)
        if sheet.get_bitsize() <= 8:
            sheet.set_colorkey(sheet.get_palette_at(0))
        sheet = G._rgba(sheet)
        h = sheet.get_height()
        fr = [sheet.subsurface((x, 0, h, h)).copy() for x in range(0, sheet.get_width() - h + 1, h)]
        if len(fr) >= 6:
            left = fr[4:6]
            return {"down": fr[0:2], "up": fr[2:4], "left": left,
                    "right": [pygame.transform.flip(f, True, False) for f in left]}
    except Exception:  # noqa: BLE001
        pass
    icons = [pygame.transform.scale_by(G.icon(pid, frame=i), 0.5) for i in (0, 1)]
    return {"down": icons, "up": icons, "left": icons, "right": [pygame.transform.flip(f, True, False) for f in icons]}


def player_frames():
    """{"walk": {face: [3 frames]}, "sit": {face: frame}} - you, at GBA size (sitting = FireRed's Surf pose)."""
    from . import cast
    walk = {face: [pygame.transform.scale_by(G.person("player", face, f), 0.5) for f in (0, 1, 2)]
            for face in ("up", "down", "left", "right")}
    look = cast.player_look()
    rules = cast.CAST.get(look, (None, None, ()))[2]
    surf = "green_surf" if look == "player_f" else "red_surf"
    fr = frlg.frames(f"graphics/object_events/pics/people/{surf}.png", 32, 32, rules)
    if fr and len(fr) > 8:
        sit = {"down": fr[6], "up": fr[7], "left": fr[8], "right": pygame.transform.flip(fr[8], True, False)}
    else:
        sit = {face: walk[face][0] for face in walk}
    return {"walk": walk, "sit": sit}


def fx_frames(name):
    path, w, h = FX[name]
    return frlg.frames(path, w, h) or []


# ---------------------------------------------------------------------- the maps
def _route(blocked, start_cells, goal, prefer=((1, 0), (0, -1), (0, 1), (-1, 0))):
    """Cells from one of start_cells to a goal cell over open ground (BFS). goal(x, y) -> bool."""
    h, w = len(blocked), len(blocked[0])
    q = deque(start_cells)
    prev = {c: None for c in start_cells}
    while q:
        x, y = q.popleft()
        if goal(x, y):
            out, c = [], (x, y)
            while c is not None:
                out.append(c)
                c = prev[c]
            return out[::-1]
        for dx, dy in prefer:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in prev and not blocked[ny][nx]:
                prev[(nx, ny)] = (x, y)
                q.append((nx, ny))
    return None


class Path:
    """A route through cells as a smooth walk: point(d) -> (x, y, facing) at d pixels along it."""

    def __init__(self, cells):
        self.pts = [(x * 16 + 8, y * 16 + 14) for x, y in cells]
        self.seg = [0.0]
        for (x0, y0), (x1, y1) in zip(self.pts, self.pts[1:]):
            self.seg.append(self.seg[-1] + math.hypot(x1 - x0, y1 - y0))
        self.length = self.seg[-1]

    def point(self, d):
        d = max(0.0, min(self.length, d))
        i = 1
        while i < len(self.seg) - 1 and self.seg[i] < d:
            i += 1
        (x0, y0), (x1, y1) = self.pts[i - 1], self.pts[i]
        f = (d - self.seg[i - 1]) / max(1e-6, self.seg[i] - self.seg[i - 1])
        dx, dy = x1 - x0, y1 - y0
        face = ("right" if dx > 0 else "left") if abs(dx) >= abs(dy) else ("down" if dy > 0 else "up")
        return x0 + dx * f, y0 + dy * f, face


def _splice(name, spans):
    """Column ranges of a real map laid side by side: (under, over, blocked), like frlg.render."""
    lay = frlg.layout(name)
    if not lay:
        return None
    parts = [frlg.render(name, x0, 0, x1 - x0, lay["h"], scale=1) for x0, x1 in spans]
    if not all(parts):
        return None
    w = sum(p[0].get_width() for p in parts)
    under = pygame.Surface((w, lay["h"] * 16), pygame.SRCALPHA)
    over = pygame.Surface((w, lay["h"] * 16), pygame.SRCALPHA)
    blocked = [[] for _ in range(lay["h"])]
    x = 0
    for u, o, b in parts:
        under.blit(u, (x, 0))
        over.blit(o, (x, 0))
        for y, row in enumerate(b):
            blocked[y] += row
        x += u.get_width()
    return under, over, blocked


def region_map():
    """The overview, built from real towns and routes: Birth Island up north, then Viridian Forest, the open sea
    and Mt. Ember side by side, and a Pallet-style home town in the south. (surface, {zone: rect}) or None."""
    birth = frlg.layout("BirthIsland_Exterior_Layout")
    if not birth:
        return None
    sea = birth["blocks"][0] & 0x3FF
    w, h = 30, 58
    out = pygame.Surface((w * 16, h * 16))
    over = pygame.Surface((w * 16, h * 16), pygame.SRCALPHA)
    tile = birth["tiles"].metatile(sea, "under")
    for y in range(h):
        for x in range(w):
            out.blit(tile, (x * 16, y * 16))
    for name, x, y, cw, ch, cx, cy in (("BirthIsland_Exterior_Layout", 3, 2, 24, 19, 3, 0),
                                       ("ViridianForest_Layout", 2, 16, 10, 19, 0, 19),
                                       ("Route20_Layout", 2, 1, 10, 19, 10, 19),
                                       ("MtEmber_Exterior_Layout", 0, 0, 10, 19, 20, 19),
                                       ("PalletTown_Layout", 0, 0, 24, 20, 3, 38)):
        r = frlg.render(name, x, y, cw, ch, scale=1)
        if not r:
            return None
        out.blit(r[0], (cx * 16, cy * 16))
        over.blit(r[1], (cx * 16, cy * 16))
    out.blit(over, (0, 0))
    return out, {"forest": pygame.Rect(0, 304, 160, 304), "ocean": pygame.Rect(160, 304, 160, 304),
                 "sky": pygame.Rect(320, 304, 160, 304)}


# ---------------------------------------------------------------------- the scene
class JourneyScene(GBAScene):
    """The cutscene. Press A to move the words along; it ends at Starter's Haven."""

    def __init__(self, app, game, mon):
        super().__init__(app)
        self.game = game
        self.dex = app.dex
        self.mon = mon
        self.pid = mon["species"]
        self.biome = biome_for(self.dex, self.pid)
        self.nm = A.name_of(self.dex, mon).upper()
        self.t = 0.0
        self.text = None
        self.told = 0
        self.lines = lines_for(self.biome, self.nm, game["name"].upper())
        self.finished = False
        self.arrived = 0.0
        self.low = pygame.Surface((LW, LH))
        self.flash = 0.0
        self.bolt_x = 0
        self.anims = []
        self.rng = random.Random(3)
        self.mf = mon_frames(self.pid)
        self.pf = player_frames()
        self.fx = {k: fx_frames(k) for k in FX}
        self.fx["cloud"] = [self._whiten(c) for c in self.fx["cloud"]]
        self.cameo = {}
        threading.Thread(target=self._load_cameos, daemon=True).start()
        self.overview = region_map()
        self._setup()
        AUDIO.cry(self.pid, 1.0)

    @staticmethod
    def _whiten(img):
        """The weather cloud, in white (its sheet's palette is the blue placeholder one)."""
        out = img.copy()
        for y in range(out.get_height()):
            for x in range(out.get_width()):
                r, g, b, a = out.get_at((x, y))
                if a:
                    v = min(255, (r + g + b) // 3 + 60)
                    out.set_at((x, y), (v, v, min(255, v + 6), a))
        return out

    def _load_cameos(self):
        for name in CAMEOS[self.biome]:
            e = self.dex.get(name)
            if e:
                try:
                    self.cameo[name] = mon_frames(e["id"])
                except Exception:  # noqa: BLE001
                    pass

    def _setup(self):
        """The map for the journey, and the way across it."""
        self.field = None
        self.path = None
        self.cut = []
        if self.biome == "ocean":
            r = _splice("Route20_Layout", ((0, 50), (83, 120)))   # the open sea either side of Seafoam
            if r:
                blocked = r[2]
                row = min(range(len(blocked)), key=lambda y: (sum(blocked[y]), abs(y - 15)))
                cells = _route(blocked, [(0, row)], lambda x, y: x == len(blocked[0]) - 1)
                self.field, self.path = r, Path(cells) if cells else None
        elif self.biome == "forest":
            r = frlg.render("ViridianForest_Layout", scale=1)
            if r:
                blocked = r[2]
                starts = [(x, y) for y in range(62, 50, -1) for x in range(25, 34) if not blocked[y][x]][:1]
                cells = _route(blocked, starts, lambda x, y: y <= 8 and x <= 12,
                               prefer=((0, -1), (-1, 0), (1, 0), (0, 1))) if starts else None
                self.field, self.path = r, Path(cells) if cells else None
                if self.path:   # two trees in the way, for Vine Whip to clear
                    for when in (12.6, 19.5):
                        self.cut.append([self._walk_d(when) + 34, when, False])
        else:
            r = frlg.render("MtEmber_Exterior_Layout", scale=1)
            if r:
                self.field = r
                self.path = Path([(4, 60), (14, 44), (22, 30), (36, 14), (40, -6)])
        self.haven = frlg.render("BirthIsland_Exterior_Layout", scale=1)

    # ------------------------------------------------------------------ timing
    def _walk_d(self, tt):
        """How far along the path you are, tt seconds into the journey."""
        if not self.path:
            return 0.0
        return self.path.length * max(0.0, min(1.0, tt / (TRAVEL_T - 1.5)))

    def update(self, dt):
        self.t += dt
        AUDIO.music("showcase" if self.t > MAP_T else "town")
        self.flash = max(0.0, self.flash - dt * 2.5)
        if self.text is not None:
            self.text.update(dt)
            if self.text.done:
                self.text = None
        tt = self.t - MAP_T
        if 0 <= tt and self.told < len(self.lines) and tt >= self.lines[self.told][0] and self.text is None:
            self.text = U.TextBox([self.lines[self.told][1]], auto=3.6)
            self.told += 1
        if self.biome == "ocean" and 12.5 < tt < 22 and self.rng.random() < dt * 0.45:
            self.flash = 1.0   # Thunder
            self.bolt_x = self.rng.randint(20, LW - 40)
            AUDIO.play("hit_super", 0.4)
        if self.t > MAP_T + TRAVEL_T and not self.finished and self.text is None:
            self.finished = True
            self.arrived = self.t
            self.anims = []
            AUDIO.play("win", 0.8)
            AUDIO.cry(self.pid, 1.0)
            self.text = U.TextBox(["You've arrived at STARTER'S HAVEN.",
                                   f"{self.nm} walks up to the old shrine. It has always known the way.",
                                   "Something on the shrine is glowing..."], self.app.pop)
        for a in self.anims:
            a["x"] += a["vx"] * dt
            a["y"] += a["vy"] * dt
            a["vy"] += a["g"] * dt
            a["age"] += dt
        self.anims = [a for a in self.anims if a["age"] < a["life"]]

    def handle(self, ev, pos):
        if self.text is not None and (U.is_a(ev) or U.is_b(ev)):
            self.text.handle(ev)
            if self.text and self.text.done:
                self.text = None
        elif U.is_a(ev) and self.t < MAP_T:
            self.t = MAP_T   # skip the map

    # ------------------------------------------------------------------ effects (battle anim / field effect sprites)
    def _anim(self, name, x, y, fps=12, life=None, vx=0.0, vy=0.0, g=0.0, flip=False):
        """A one-off animation at a map position (frames play once over its life)."""
        fr = self.fx.get(name)
        if fr:
            self.anims.append({"f": name, "x": x, "y": y, "fps": fps, "life": life or len(fr) / fps, "vx": vx,
                               "vy": vy, "g": g, "age": 0.0, "flip": flip})

    def _draw_anims(self, s, cam, names=None):
        for a in self.anims:
            if names and a["f"] not in names:
                continue
            fr = self.fx[a["f"]]
            img = fr[min(len(fr) - 1, int(a["age"] * a["fps"]))]
            if a["flip"]:
                img = pygame.transform.flip(img, True, False)
            s.blit(img, img.get_rect(center=(int(a["x"] - cam[0]), int(a["y"] - cam[1]))))

    def _sprite(self, s, name, i, pos, alpha=255, anchor="center", rot=0):
        fr = self.fx.get(name)
        if not fr:
            return
        img = fr[i % len(fr)]
        if rot:
            img = pygame.transform.rotate(img, rot)
        if alpha < 255:
            img = img.copy()
            img.set_alpha(alpha)
        s.blit(img, img.get_rect(**{anchor: (int(pos[0]), int(pos[1]))}))

    def _halo(self, s, pos, t, size=0.6, strength=1.0):
        """A pulsing glow (the battle animations' white halo) with a twinkle in it."""
        p = 0.5 + 0.5 * math.sin(t * 3)
        halo = self.fx.get("halo")
        if halo:
            g = pygame.transform.scale_by(halo[0], size + 0.25 * size * p)
            g.set_alpha(int(strength * (110 + 90 * p)))
            s.blit(g, g.get_rect(center=(int(pos[0]), int(pos[1]))))
        self._sprite(s, "glint", int(t * 6), pos)

    def _rain(self, s, k, tt):
        fr = self.fx.get("rain")
        if fr:
            for i in range(int(36 * k)):
                x = (i * 53 - tt * 180) % (LW + 40) - 20
                y = (i * 37 + tt * 300) % (LH + 40) - 30
                s.blit(fr[(i + int(tt * 10)) % len(fr)], (int(x), int(y)))

    def _fog(self, s, alpha, tt, speed=20):
        fr = self.fx.get("fog")
        if not fr or alpha <= 1:
            return
        img = fr[0].copy()
        img.set_alpha(int(alpha))
        ox = int(tt * speed) % 64
        for y in range(0, LH, 64):
            for x in range(-64, LW, 64):
                s.blit(img, (x + ox, y))

    def _cameo(self, s, name, face, pos, speed=4, shadow=False, lift=0):
        fr = self.cameo.get(name)
        if not fr:
            return
        x, y = int(pos[0]), int(pos[1])
        if shadow:
            self._sprite(s, "shadow_s", 0, (x, y), alpha=140)
        img = fr[face][int(self.t * speed) % 2]
        s.blit(img, img.get_rect(midbottom=(x, y + 2 - lift)))

    def _field(self, s, cam, layer):
        s.blit(self.field[layer], (-int(cam[0]), -int(cam[1])))

    @staticmethod
    def _cam(x, y, size, ox=120, oy=78):
        w, h = size
        return (int(max(0, min(w - LW, x - ox))), int(max(0, min(h - LH, y - oy))))

    # ------------------------------------------------------------------ drawing
    def draw(self, surf):
        if self.t < MAP_T and self.overview:
            self._draw_map(surf, self.t)
        else:
            s = self.low
            s.fill((0, 0, 0))
            if self.finished:
                self._draw_haven(s, self.t - self.arrived)
            elif self.t >= MAP_T and self.field and self.path:
                tt = self.t - MAP_T
                {"ocean": self._draw_ocean, "forest": self._draw_forest, "sky": self._draw_sky}[self.biome](s, tt)
            surf.blit(pygame.transform.scale(s, (LW * K, LH * K)), (0, 0))
            if self.finished:
                fade = 1 - (self.t - self.arrived) / 0.8
            else:
                fade = max(1 - (self.t - MAP_T) / 0.6, (self.t - (MAP_T + TRAVEL_T - 0.8)) / 0.8)
            if fade > 0:   # fade in and out of each place
                f = pygame.Surface(surf.get_size())
                f.fill((0, 0, 0) if self.biome == "forest" and not self.finished else (255, 255, 255))
                f.set_alpha(int(255 * min(1.0, fade)))
                surf.blit(f, (0, 0))
        if self.flash > 0:
            fl = pygame.Surface(surf.get_size())
            fl.fill((248, 248, 255))
            fl.set_alpha(int(170 * self.flash))
            surf.blit(fl, (0, 0))
        if self.text is not None:
            self.text.draw(surf, self.t)

    # --- the overview: the camera pans up from home, over the three ways, to the Haven
    def _draw_map(self, surf, t):
        img, zones = self.overview
        mh = img.get_height()
        stops = ((0.0, mh - 320), (1.2, mh - 320), (3.0, 330), (5.0, 330), (6.6, 0), (99.0, 0))
        cam = 0
        for (t0, y0), (t1, y1) in zip(stops, stops[1:]):
            if t0 <= t < t1:
                f = (t - t0) / (t1 - t0)
                f = f * f * (3 - 2 * f)
                cam = int(y0 + (y1 - y0) * f)
                break
        surf.blit(img, (0, -cam))
        you, mon = self.pf["walk"]["up"][0], self.mf["up"][0]   # you and your starter at home, looking north
        surf.blit(you, you.get_rect(midbottom=(150, 752 - cam)))
        surf.blit(mon, mon.get_rect(midbottom=(174, 752 - cam)))
        if t > 2.6:
            dim = pygame.Surface((480, 320), pygame.SRCALPHA)
            for key, rect in zones.items():
                if key != self.biome:
                    dim.fill((8, 16, 40, 120), rect.move(0, -cam))
            pulse = int(150 + 100 * math.sin(t * 6))
            pygame.draw.rect(dim, (255, 255, 255, pulse), zones[self.biome].move(0, -cam).inflate(-4, -4), 2)
            surf.blit(dim, (0, 0))
            for key, label in (("forest", "FOREST"), ("ocean", "SEA"), ("sky", "MOUNTAINS")):
                c = zones[key].move(0, -cam).center
                F.draw(surf, label, (c[0], c[1] - 40), (248, 232, 96) if key == self.biome else U.WHITE,
                       (24, 32, 56), anchor="center")
        self._halo(surf, (248, 170 - cam), t, 0.7)   # the Haven's stone, glowing
        if cam < 120:
            F.draw(surf, "STARTER'S HAVEN", (240, max(8, 100 - cam)), (255, 240, 180), (80, 48, 16), anchor="center")
        if t > 3.2:
            box = U.box(surf, (24, 236, 432, 80))
            F.draw(surf, f"{self.nm} looks toward {ROUTE_NAME[self.biome]}.", (box.x + 8, box.y + 6), U.TEXT,
                   U.SHADOW)
            F.draw(surf, "It knows the way.", (box.x + 8, box.y + 34), U.TEXT, U.SHADOW)

    # --- the sea: surfing on its shell along Route 20
    def _draw_ocean(self, s, tt):
        storm = max(0.0, min(1.0, (tt - 10.5) / 2.5)) * max(0.0, min(1.0, (23.5 - tt) / 2.5))
        pump = 16.5 < tt < 21
        x, y, face = self.path.point(self._walk_d(tt))
        bob = int(round(math.sin(tt * 3) * (1 + storm * 2)))
        cam = self._cam(x, y, self.field[0].get_size(), 100, 70)
        self._field(s, cam, 0)
        sx, sy = x - cam[0], y - cam[1] + bob
        back = {"right": (-1, 0), "left": (1, 0), "up": (0, 1), "down": (0, -1)}[face]
        if self.rng.random() < (0.2 if not pump else 0.7):   # ripples in its wake
            self._anim("ripple", x + back[0] * 12, y + back[1] * 8 - 2, fps=10)
        if tt < 10:
            self._cameo(s, "lapras", "left", (LW + 40 - tt * 26, 44), 2)
        if 1.5 < tt < 9:
            self._cameo(s, "tentacool", "down", (210 - (tt - 1.5) * 14, 112), 2)
        self._draw_anims(s, cam, ("ripple",))
        mon = self.mf[face][int(tt * 4) % 2]
        sit = self.pf["sit"][face]
        if pump:
            self._pump(s, sx, sy, face, back, tt, cam)
        if face == "up":
            s.blit(mon, mon.get_rect(midbottom=(sx, sy + 4)))
            s.blit(sit, sit.get_rect(midbottom=(sx, sy - 2)))
        elif face == "down":
            s.blit(sit, sit.get_rect(midbottom=(sx, sy - 6)))
            s.blit(mon, mon.get_rect(midbottom=(sx, sy + 4)))
        else:
            s.blit(mon, mon.get_rect(midbottom=(sx, sy + 4)))
            s.blit(sit, sit.get_rect(midbottom=(sx - 8 * (1 if face == "right" else -1), sy - 9)))
        self._draw_anims(s, cam, ("spray", "bigsplash", "glint"))
        self._field(s, cam, 1)
        if tt < 10 or tt > 24:   # Wingull riding the wind, their shadows on the water
            for k in range(3):
                wx = (tt * (40 + k * 6) + k * 80) % (LW + 60) - 30
                wy = 48 + k * 14 + math.sin(tt * 2 + k) * 3
                self._cameo(s, "wingull", "right", (wx, wy), 6, shadow=True, lift=24)
        if 24 < tt < 26.4:   # a Mantine leaps
            f = (tt - 24) / 2.4
            mx, my = 150 + f * 50, 108
            self._cameo(s, "mantine", "right", (mx, my - math.sin(f * math.pi) * 30), 6)
            if f > 0.9 and self.rng.random() < 0.5:
                self._anim("bigsplash", mx + cam[0], my + cam[1] - 4, fps=10)
        if 23 < tt < 31 and self.rng.random() < 0.3:   # sunlight sparkling on the sea
            self._anim("glint", cam[0] + self.rng.uniform(0, LW), cam[1] + self.rng.uniform(10, 110), fps=8)
        if storm > 0:
            s.fill(tuple(int(255 - (255 - c) * storm) for c in (96, 104, 136)), special_flags=pygame.BLEND_MULT)
            self._fog(s, 80 * storm, tt, 30)
            self._rain(s, storm, tt)
        if self.flash > 0.4:   # Thunder
            for k in range(5):
                self._sprite(s, "bolt", k, (self.bolt_x, k * 24), anchor="midtop")
        if tt > 27:   # far off, a glow on the horizon
            self._halo(s, (214, 30), tt, 0.5, min(1.0, (tt - 27) / 2))

    def _pump(self, s, sx, sy, face, back, tt, cam):
        """Hydro Pump out of both cannons: the battle animation's spinning water column, laid end to end and
        blasting back the way you came, bursting into spray at the end."""
        fr = self.fx.get("pump")
        if not fr:
            return
        rot = {"right": 90, "left": -90, "up": 180, "down": 0}[face]
        grow = min(1.0, (tt - 16.5) / 0.25)
        for side in (-3, 3):
            if back[1] == 0:
                ox, oy = sx + back[0] * 6, sy - 20 + side
            else:
                ox, oy = sx + side * 2, sy - 16
            n = int(5 * grow)
            for k in range(n):
                img = pygame.transform.rotate(fr[(int(tt * 16) + k) % len(fr)], rot)
                px = ox + back[0] * (12 + k * 15)
                py = oy + back[1] * (12 + k * 15) + (k * k * 0.5 if back[1] == 0 else 0)
                s.blit(img, img.get_rect(center=(int(px), int(py))))
            if n and self.rng.random() < 0.6:
                ex = ox + back[0] * (12 + n * 15)
                ey = oy + back[1] * (12 + n * 15) + (n * n * 0.5 if back[1] == 0 else 0)
                self._anim("spray", ex + cam[0], ey + cam[1], fps=14, flip=back[0] > 0)

    # --- the forest: following it through the dark of Viridian Forest
    def _draw_forest(self, s, tt):
        glow = max(0.0, min(1.0, (tt - 22) / 5))
        mx, my, mface = self.path.point(self._walk_d(tt) + 22)   # it walks just ahead of you
        px, py, pface = self.path.point(self._walk_d(tt))
        cam = self._cam(px, py, self.field[0].get_size(), 120, 84)
        self._field(s, cam, 0)
        for c in self.cut:   # trees in the way: Vine Whip, then they're cut down
            tx, ty, _ = self.path.point(c[0])
            age = tt - c[1]
            pos = (tx - cam[0], ty - cam[1] + 2)
            if age < 0.5:
                self._sprite(s, "cuttree", 0, pos, anchor="midbottom")
                if age >= 0 and not c[2]:
                    c[2] = True
                    self._anim("vine", tx, ty - 10, fps=12, flip=mface == "left")
                    AUDIO.play("hit", 0.5)
            elif age < 0.9:
                self._sprite(s, "cuttree", 1 + int((age - 0.5) * 8), pos, anchor="midbottom")
                if self.rng.random() < 0.6:
                    self._anim("cutleaf", tx + self.rng.uniform(-6, 6), ty - 8, fps=4, life=0.6,
                               vx=self.rng.uniform(-30, 30), vy=self.rng.uniform(-40, -10), g=60)
        for name, at, side in (("caterpie", 4.0, 1), ("weedle", 9.0, -1), ("pikachu", 14.5, 1),
                               ("metapod", 20.0, -1), ("butterfree", 25.0, 1)):
            cx, cy, _ = self.path.point(self._walk_d(at) + 70)
            pos = (cx + 26 * side - cam[0], cy - cam[1])
            if name == "pikachu" and tt > 14.5:   # it scampers off into the trees
                pos = (pos[0] + min(3.0, tt - 14.5) * 30, pos[1])
            lift = int(10 + 4 * math.sin(tt * 3)) if name == "butterfree" else 0
            self._cameo(s, name, "left" if side > 0 else "right", pos, 4, shadow=bool(lift), lift=lift)
        mon = self.mf[mface][int(tt * 4) % 2]
        you = self.pf["walk"][pface][(1 + int(tt * 4) % 2) if int(tt * 8) % 2 else 0]
        for img, (x, y) in sorted(((mon, (mx, my)), (you, (px, py))), key=lambda e: e[1][1]):
            s.blit(img, img.get_rect(midbottom=(int(x - cam[0]), int(y - cam[1]) + 2)))
        self._draw_anims(s, cam, ("vine", "cutleaf"))
        self._field(s, cam, 1)
        # the dark: like a cave before Flash, only a small circle of light around you
        r = int(36 + glow * 130 + (10 if 15.5 < tt < 19 else 0))
        dark = pygame.Surface((LW, LH), pygame.SRCALPHA)
        dark.fill((8, 16, 24, int(235 * (1 - glow * 0.9))))
        c = (int((px + mx) / 2 - cam[0]), int((py + my) / 2 - cam[1]) - 8)
        pygame.draw.circle(dark, (8, 16, 24, int(120 * (1 - glow))), c, r + 10)
        pygame.draw.circle(dark, (0, 0, 0, 0), c, r)
        s.blit(dark, (0, 0))
        if 4.5 < tt < 20:   # eyes in the dark
            for i in range(6):
                if (int(tt * 1.7) + i) % 4:
                    ex, ey = (i * 41 + 20) % LW, 16 + (i * 29) % 90
                    if math.hypot(ex - c[0], ey - c[1]) > r + 14:
                        self._sprite(s, "eye", 0, (ex, ey))
                        self._sprite(s, "eye", 0, (ex + 9, ey))
        if 15.5 < tt < 19 and self.rng.random() < 0.3:   # its hum: a sparkle of light
            self._anim("sparkle", mx, my - 20, fps=12)
        if tt > 22 and self.rng.random() < 0.25:
            self._anim("glint", cam[0] + self.rng.uniform(0, LW), cam[1] + self.rng.uniform(10, 110), fps=6)
        if tt > 26:   # the flower glows
            self._halo(s, (mx - cam[0], my - cam[1] - 22), tt, 0.4)
        self._draw_anims(s, cam, ("sparkle", "glint"))

    # --- the mountains: flying on its back over Mt. Ember
    def _draw_sky(self, s, tt):
        sun = max(0.0, min(1.0, (tt - 21) / 6))
        gx, gy, _ = self.path.point(self._walk_d(tt))
        alt = 34
        cam = self._cam(gx, gy - alt, self.field[0].get_size(), 120, 70)
        self._field(s, cam, 0)
        self._field(s, cam, 1)
        sx, sy = gx - cam[0], gy - cam[1]
        cloud = self.fx.get("cloud")
        if cloud:   # cloud shadows sliding over the slopes
            sh = pygame.transform.scale_by(cloud[0], 2)
            sh.fill((40, 40, 60, 255), special_flags=pygame.BLEND_RGBA_MULT)
            sh.set_alpha(60)
            for k in range(3):
                s.blit(sh, (int((k * 110 - tt * 22) % (LW + 140) - 70), int((k * 70 + tt * 30) % (LH + 120) - 60)))
        self._sprite(s, "shadow", 0, (sx, sy), alpha=150)   # its shadow far below
        if 3 < tt < 11 or tt > 21:   # a flock of Pidgey keeping pace
            for k in range(3):
                bx = sx - 36 - k * 18 + math.sin(tt + k) * 4
                by = sy - alt + 14 + k * 10 + math.sin(tt * 3 + k) * 2
                self._sprite(s, "shadow_s", 0, (bx + 10, by + alt), alpha=110)
                self._cameo(s, "pidgey", "up", (bx, by), 8)
        if 5 < tt < 10:
            self._cameo(s, "skarmory", "down", (LW - 40 - (tt - 5) * 20, (tt - 5) * 40 - 10), 6)
        cy = sy - alt + int(round(math.sin(tt * 2.5) * 2))
        mon = self.mf["up"][int(tt * 6) % 2]
        s.blit(mon, mon.get_rect(midbottom=(sx, cy)))
        sit = self.pf["sit"]["up"]
        s.blit(sit, sit.get_rect(midbottom=(sx, cy - 4)))
        if 16.5 < tt < 20.5:   # Flamethrower, roaring out ahead
            if self.rng.random() < 0.7:
                self._anim("ember", gx + self.rng.uniform(-3, 3), gy - alt - 30, fps=14,
                           vy=-150 + self.rng.uniform(-20, 20), vx=self.rng.uniform(-14, 14))
            self._sprite(s, "fire", int(tt * 14), (sx, cy - 34))
        self._draw_anims(s, cam)
        cl = max(0.0, 1 - abs(tt - 13.5) / 2.3)   # flying through a cloud
        self._fog(s, 250 * cl, tt, 90)
        if cloud and not 11 < tt < 16:   # clouds drifting past below you
            img = pygame.transform.scale_by(cloud[0], 2)
            img.set_alpha(150)
            for k in range(4):
                s.blit(img, (int((k * 90 - tt * 34) % (LW + 160) - 80), int((k * 57 + tt * 46) % (LH + 160) - 80)))
        if sun:
            s.fill(tuple(int(255 - (255 - c) * sun) for c in (255, 184, 136)), special_flags=pygame.BLEND_MULT)
        if tt > 27:
            self._halo(s, (150, 18), tt, 0.5, min(1.0, (tt - 27) / 2))

    # --- Starter's Haven: Birth Island
    def _draw_haven(self, s, t):
        if not self.haven:
            return
        under, over, _ = self.haven
        walk = min(1.0, t / 3.0)
        py = 330 - 90 * walk
        cam = (128, int(max(0, min(under.get_height() - LH, py - 100))))
        s.blit(under, (-cam[0], -cam[1]))
        self._halo(s, (248 - cam[0], 166 - cam[1]), t, 0.9)
        if self.rng.random() < 0.3:
            self._anim("sparkle", 248 + self.rng.uniform(-40, 40), 176 + self.rng.uniform(-10, 20), fps=10, vy=-12)
        self._draw_anims(s, cam)
        step = int(t * 4) % 2 if walk < 1 else 0
        mon = self.mf["up"][step]
        you = self.pf["walk"]["up"][(1 + step) if walk < 1 and int(t * 8) % 2 else 0]
        s.blit(mon, mon.get_rect(midbottom=(258 - cam[0], int(py - 8 - cam[1]))))
        s.blit(you, you.get_rect(midbottom=(240 - cam[0], int(py - cam[1]))))
        s.blit(over, (-cam[0], -cam[1]))
