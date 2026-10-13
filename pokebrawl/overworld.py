"""Adventure mode's overworld: walk around the Brawl region on a tile map, with your lead Pokemon following you.
Tall grass hides wild Pokemon, trainers battle you when you walk into their line of sight, Pokemon Centers heal,
Marts sell items, gyms give badges. Everything is drawn in code (no game art is copied)."""
import math
import random

import pygame

from . import adventure as A
from . import gfx, profile, ui
from .app import Scene
from .audio import AUDIO
from .gfx import H, INK, SPRITES, W

T = A.TILE
WALK = set('.,"=')
DOORS = {"C": "center", "M": "mart", "G": "gym", "D": "house", "P": "lab", "L": "league"}
BODY = {"c": "center", "m": "mart", "g": "gym", "h": "house", "p": "lab", "l": "league"}
DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
KEYS = {pygame.K_UP: "up", pygame.K_w: "up", pygame.K_DOWN: "down", pygame.K_s: "down",
        pygame.K_LEFT: "left", pygame.K_a: "left", pygame.K_RIGHT: "right", pygame.K_d: "right"}

# palette (a bright handheld-RPG look, drawn in code)
GRASS = (122, 200, 104)
GRASS_D = (98, 176, 84)
TALL = (58, 150, 70)
TALL_D = (36, 112, 52)
PATH = (226, 204, 150)
PATH_D = (204, 180, 126)
WATER = (78, 150, 232)
WATER_L = (150, 200, 250)
TREE = (40, 120, 64)
TREE_L = (70, 160, 84)
TRUNK = (110, 76, 48)


# ====================================================================== drawing the map
def _tile_rng(x, y, salt=0):
    return random.Random(x * 73856093 ^ y * 19349663 ^ salt)


def draw_ground(s, x, y, px, py):
    pygame.draw.rect(s, GRASS, (px, py, T, T))
    r = _tile_rng(x, y)
    for _ in range(5):
        gx, gy = px + r.randint(4, T - 6), py + r.randint(4, T - 6)
        pygame.draw.line(s, GRASS_D, (gx, gy), (gx + 2, gy - 4), 2)


def draw_flowers(s, x, y, px, py):
    draw_ground(s, x, y, px, py)
    r = _tile_rng(x, y, 1)
    for _ in range(3):
        fx, fy = px + r.randint(8, T - 8), py + r.randint(8, T - 8)
        col = r.choice([(240, 80, 90), (250, 220, 80), (250, 250, 250), (200, 120, 230)])
        for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3)):
            pygame.draw.circle(s, col, (fx + dx, fy + dy), 3)
        pygame.draw.circle(s, (250, 200, 60), (fx, fy), 2)


def draw_path(s, x, y, px, py):
    pygame.draw.rect(s, PATH, (px, py, T, T))
    r = _tile_rng(x, y, 2)
    for _ in range(4):
        pygame.draw.circle(s, PATH_D, (px + r.randint(4, T - 4), py + r.randint(4, T - 4)), r.randint(1, 3))


def draw_tall(s, x, y, px, py, sway=0.0):
    pygame.draw.rect(s, TALL_D, (px, py, T, T))
    for row in range(3):
        for k in range(4):
            bx = px + 6 + k * 11 + (row % 2) * 5
            by = py + 16 + row * 14
            lean = sway * (1 if (k + row) % 2 else -1)
            pygame.draw.polygon(s, TALL, [(bx - 6, by), (bx + lean, by - 16), (bx + 6, by)])
            pygame.draw.line(s, (110, 200, 110), (bx - 1, by - 2), (bx + lean, by - 14), 2)


def draw_tree(s, x, y, px, py):
    draw_ground(s, x, y, px, py)
    pygame.draw.rect(s, TRUNK, (px + T // 2 - 5, py + T - 18, 10, 16))
    pygame.draw.circle(s, (24, 80, 44), (px + T // 2, py + T // 2 - 2), T // 2 - 1)
    pygame.draw.circle(s, TREE, (px + T // 2, py + T // 2 - 4), T // 2 - 4)
    pygame.draw.circle(s, TREE_L, (px + T // 2 - 7, py + T // 2 - 11), 9)
    pygame.draw.circle(s, (100, 190, 104), (px + T // 2 - 9, py + T // 2 - 13), 4)


def draw_water(s, x, y, px, py, t=0.0):
    pygame.draw.rect(s, WATER, (px, py, T, T))
    for k in range(3):
        wy = py + 10 + k * 14
        off = int((t * 20 + k * 11 + x * 7) % T)
        pygame.draw.line(s, WATER_L, (px + off - 10, wy), (px + off, wy), 2)


def draw_sign(s, x, y, px, py):
    draw_ground(s, x, y, px, py)
    pygame.draw.rect(s, TRUNK, (px + T // 2 - 3, py + 24, 6, 20))
    pygame.draw.rect(s, (60, 40, 24), (px + 7, py + 7, T - 14, 22), border_radius=3)
    pygame.draw.rect(s, (170, 124, 76), (px + 9, py + 9, T - 18, 18), border_radius=2)
    for k in range(3):
        pygame.draw.line(s, (120, 84, 50), (px + 13, py + 13 + k * 5), (px + T - 13, py + 13 + k * 5), 1)


ROOFS = {"center": (220, 60, 70), "mart": (60, 120, 220), "gym": (120, 128, 140), "lab": (230, 230, 236),
         "league": (230, 180, 60)}
HOUSE_ROOFS = [(170, 90, 60), (90, 140, 90), (130, 90, 160), (190, 120, 60)]


def draw_building(s, kind, rect, door, accent=None, seed=0):
    """A building on the map: walls, a big roof, windows, the door and a sign for Centers / Marts / gyms."""
    x, y, w, h = rect
    roof = ROOFS.get(kind) or HOUSE_ROOFS[seed % len(HOUSE_ROOFS)]
    wall = (244, 238, 222) if kind != "gym" else (196, 200, 210)
    if kind == "league":
        wall = (250, 240, 210)
    roof_h = int(h * 0.48)
    pygame.draw.rect(s, (40, 34, 30), (x + 2, y + 6, w - 4, h - 4), border_radius=6)       # shadow / outline
    pygame.draw.rect(s, wall, (x + 4, y + roof_h - 6, w - 8, h - roof_h + 2))
    # roof with overhang and stripes
    pygame.draw.polygon(s, tuple(int(c * 0.6) for c in roof), [(x, y + roof_h + 2), (x + w, y + roof_h + 2),
                                                                (x + w - 6, y + 6), (x + 6, y + 6)])
    pygame.draw.polygon(s, roof, [(x + 2, y + roof_h - 2), (x + w - 2, y + roof_h - 2), (x + w - 8, y + 8),
                                  (x + 8, y + 8)])
    for k in range(4, roof_h - 6, 10):
        pygame.draw.line(s, tuple(int(c * 0.82) for c in roof), (x + 8, y + 8 + k), (x + w - 8, y + 8 + k), 2)
    # windows
    wy = y + roof_h + 8
    for wx in range(x + 14, x + w - 30, 40):
        if abs(wx + 9 - (door[0] + T / 2)) < 30:
            continue
        pygame.draw.rect(s, (60, 70, 90), (wx, wy, 20, 16), border_radius=2)
        pygame.draw.rect(s, (150, 200, 240), (wx + 2, wy + 2, 16, 12), border_radius=2)
    # the door
    dx, dy = door
    pygame.draw.rect(s, (60, 50, 40), (dx + 8, dy + 4, T - 16, T - 4), border_radius=4)
    pygame.draw.rect(s, (110, 90, 70) if kind not in ("center", "mart") else (140, 210, 240),
                     (dx + 11, dy + 7, T - 22, T - 8), border_radius=3)
    if kind in ("center", "mart"):
        pygame.draw.line(s, (60, 50, 40), (dx + T // 2, dy + 7), (dx + T // 2, dy + T - 2), 2)
    # signs
    cx = x + w // 2
    if kind == "center":
        pygame.draw.circle(s, (255, 255, 255), (cx, y + roof_h // 2 + 4), 15)
        pygame.draw.rect(s, (220, 60, 70), (cx - 3, y + roof_h // 2 - 6, 6, 20))
        pygame.draw.rect(s, (220, 60, 70), (cx - 10, y + roof_h // 2 + 1, 20, 6))
    elif kind == "mart":
        pygame.draw.rect(s, (255, 255, 255), (cx - 30, y + roof_h // 2 - 6, 60, 22), border_radius=4)
        gfx.text(s, "MART", (cx, y + roof_h // 2 + 5), 14, (60, 120, 220), None, 0)
    elif kind == "gym":
        col = accent or (200, 200, 210)
        pygame.draw.rect(s, col, (x + 6, y + roof_h - 10, w - 12, 8))
        pygame.draw.rect(s, (40, 44, 56), (cx - 40, y + roof_h // 2 - 10, 80, 26), border_radius=5)
        gfx.text(s, "GYM", (cx, y + roof_h // 2 + 3), 18, col, None, 0)
    elif kind == "league":
        gfx.text(s, "POKEMON LEAGUE", (cx, y + roof_h // 2 + 4), 18, (120, 70, 20), None, 0)
    elif kind == "lab":
        gfx.text(s, "LAB", (cx, y + roof_h // 2 + 4), 16, (90, 90, 110), None, 0)


def render_area(area, world):
    """The static part of an area's map, drawn once."""
    rows = area["rows"]
    h = len(rows)
    s = pygame.Surface((A.COLS * T, h * T))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            px, py = x * T, y * T
            if ch == ",":
                draw_flowers(s, x, y, px, py)
            elif ch == "=":
                draw_path(s, x, y, px, py)
            elif ch == '"':
                draw_tall(s, x, y, px, py)
            elif ch == "~":
                draw_water(s, x, y, px, py)
            elif ch == "S":
                draw_sign(s, x, y, px, py)
            elif ch in "#t":
                draw_ground(s, x, y, px, py)
            else:
                draw_ground(s, x, y, px, py)
    # trees after the ground so their canopies overlap a little
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in "#t":
                draw_tree(s, x, y, x * T, y * T)
    # buildings: each connected block of the same letter
    seen = set()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            low = ch.lower()
            if (x, y) in seen or not (low in BODY or ch in DOORS) or ch in "S":
                continue
            letter = low if low in BODY else {"D": "h"}.get(ch, ch.lower())
            stack, cells = [(x, y)], []
            while stack:
                cx, cy = stack.pop()
                if (cx, cy) in seen or not (0 <= cy < h and 0 <= cx < A.COLS):
                    continue
                c2 = rows[cy][cx]
                l2 = c2.lower() if c2.lower() in BODY else {"D": "h"}.get(c2)
                if l2 != letter:
                    continue
                seen.add((cx, cy))
                cells.append((cx, cy))
                stack += [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]
            xs, ys = [c[0] for c in cells], [c[1] for c in cells]
            door = next(((cx, cy) for cx, cy in cells if rows[cy][cx] in DOORS), (xs[0], max(ys)))
            accent = None
            if BODY[letter] == "gym" and area.get("town"):
                accent = gfx.type_color(A.GYMS[area["town"] - 1][2], 0)
            draw_building(s, BODY[letter], (min(xs) * T, min(ys) * T, (max(xs) - min(xs) + 1) * T,
                                            (max(ys) - min(ys) + 1) * T), (door[0] * T, door[1] * T), accent,
                          seed=min(xs) * 3 + min(ys))
    return s


# ====================================================================== people
SKIN = (250, 214, 176)


def draw_person(surf, cx, bottom, face, step, shirt, hat=None, hair=(70, 46, 30), scale=1.0):
    """A little trainer drawn in code: 4 directions, 2 walk frames."""
    k = scale
    sh = pygame.Surface((int(26 * k), int(10 * k)), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (0, 0, 0, 70), sh.get_rect())
    surf.blit(sh, sh.get_rect(center=(cx, bottom - 2)))
    leg = int(4 * k) if step else 0
    # legs
    pants = (50, 60, 90)
    if face in ("left", "right"):
        pygame.draw.rect(surf, pants, (cx - 5 * k + (leg if step == 1 else -leg) * 0.5, bottom - 14 * k, 6 * k,
                                       12 * k), border_radius=2)
        pygame.draw.rect(surf, pants, (cx - 1 * k - (leg if step == 1 else -leg) * 0.5, bottom - 14 * k, 6 * k,
                                       12 * k), border_radius=2)
    else:
        pygame.draw.rect(surf, pants, (cx - 8 * k, bottom - 14 * k - (leg if step == 1 else 0), 7 * k, 12 * k),
                         border_radius=2)
        pygame.draw.rect(surf, pants, (cx + 1 * k, bottom - 14 * k - (leg if step == 2 else 0), 7 * k, 12 * k),
                         border_radius=2)
    # body
    pygame.draw.rect(surf, INK, (cx - 11 * k, bottom - 30 * k, 22 * k, 18 * k), border_radius=int(6 * k))
    pygame.draw.rect(surf, shirt, (cx - 10 * k, bottom - 29 * k, 20 * k, 16 * k), border_radius=int(5 * k))
    if face == "down":
        pygame.draw.rect(surf, (250, 250, 250), (cx - 2 * k, bottom - 28 * k, 4 * k, 14 * k))
    # arms
    swing = (3 * k if step == 1 else -3 * k if step == 2 else 0)
    if face in ("down", "up"):
        pygame.draw.rect(surf, SKIN, (cx - 14 * k, bottom - 27 * k + swing, 4 * k, 11 * k), border_radius=2)
        pygame.draw.rect(surf, SKIN, (cx + 10 * k, bottom - 27 * k - swing, 4 * k, 11 * k), border_radius=2)
    # head
    hy = bottom - 40 * k
    pygame.draw.circle(surf, INK, (cx, hy), int(12 * k))
    pygame.draw.circle(surf, SKIN, (cx, hy), int(11 * k))
    if face == "up":
        pygame.draw.circle(surf, hair, (cx, hy), int(11 * k))
    else:
        pygame.draw.arc(surf, hair, (cx - 11 * k, hy - 11 * k, 22 * k, 22 * k), 0.2, math.pi - 0.2, int(6 * k))
        if face == "down":
            for ex in (-4, 4):
                pygame.draw.rect(surf, INK, (cx + ex * k - 1, hy, 3 * k, 4 * k))
        else:
            d = 1 if face == "right" else -1
            pygame.draw.rect(surf, INK, (cx + d * 5 * k - 1, hy, 3 * k, 4 * k))
    if hat:   # a cap with a brim pointing where they look
        pygame.draw.arc(surf, hat, (cx - 12 * k, hy - 13 * k, 24 * k, 22 * k), 0.0, math.pi, int(8 * k))
        pygame.draw.rect(surf, (250, 250, 250), (cx - 3 * k, hy - 11 * k, 6 * k, 4 * k))
        if face == "down":
            pygame.draw.rect(surf, hat, (cx - 10 * k, hy - 4 * k, 20 * k, 3 * k))
        elif face in ("left", "right"):
            d = 1 if face == "right" else -1
            pygame.draw.rect(surf, hat, (cx + (d * 6 - (12 if d < 0 else 0)) * k, hy - 5 * k, 12 * k, 3 * k))


NPC_LOOKS = {"Youngster": ((70, 140, 230), (240, 200, 60)), "Lass": ((240, 120, 160), None),
             "Bug Catcher": ((120, 180, 90), (230, 230, 120)), "Hiker": ((160, 110, 70), (120, 80, 40)),
             "Swimmer": ((60, 160, 220), None), "Ace Trainer": ((220, 60, 70), (40, 40, 60)),
             "Psychic": ((150, 80, 200), None), "Black Belt": ((240, 240, 240), (30, 30, 30)),
             "Picnicker": ((240, 170, 60), (200, 80, 80)), "Fisher": ((80, 120, 160), (90, 140, 90)),
             "Biker": ((40, 40, 50), (90, 90, 100)), "Beauty": ((230, 90, 140), None)}


# ====================================================================== dialogue
class Dialogue:
    """The classic text box: types out, Space / Enter / click to continue."""

    def __init__(self, lines, speaker="", on_done=None):
        self.lines = [ln for ln in lines if ln]
        self.speaker = speaker
        self.on_done = on_done
        self.i = 0
        self.shown = 0.0

    @property
    def text(self):
        return self.lines[self.i] if self.i < len(self.lines) else ""

    def update(self, dt):
        self.shown = min(len(self.text), self.shown + dt * 55)

    def advance(self):
        """Returns True when the dialogue is over."""
        if self.shown < len(self.text):
            self.shown = len(self.text)
            return False
        self.i += 1
        self.shown = 0
        AUDIO.play("click", 0.4)
        return self.i >= len(self.lines)

    def draw(self, surf, t):
        r = pygame.Rect(16, H - 236, W - 32, 210)
        pygame.draw.rect(surf, (30, 34, 44), r.inflate(8, 8), border_radius=18)
        pygame.draw.rect(surf, (250, 250, 248), r, border_radius=14)
        pygame.draw.rect(surf, (90, 160, 220), r.inflate(-10, -10), 3, border_radius=10)
        if self.speaker:
            tag = pygame.Rect(r.x + 20, r.y - 26, gfx.font(20).size(self.speaker)[0] + 32, 40)
            pygame.draw.rect(surf, (30, 34, 44), tag.inflate(6, 6), border_radius=12)
            pygame.draw.rect(surf, (220, 60, 70), tag, border_radius=10)
            gfx.text(surf, self.speaker, tag.center, 20, (255, 255, 255), None, 0)
        words = self.text[:int(self.shown)]
        _wrap(surf, words, (r.x + 30, r.y + 40), r.w - 60, 26, INK)
        if self.shown >= len(self.text) and int(t * 3) % 2:
            x, y = r.right - 40, r.bottom - 30
            pygame.draw.polygon(surf, (220, 60, 70), [(x - 10, y - 6), (x + 10, y - 6), (x, y + 6)])


def _wrap(surf, text, pos, width, size, color):
    f = gfx.font(size, False)
    x, y = pos
    line = ""
    for word in text.split(" "):
        test = (line + " " + word).strip()
        if f.size(test)[0] > width and line:
            gfx.text(surf, line, (x, y), size, color, None, 0, anchor="midleft", chunky=False)
            y += size + 14
            line = word
        else:
            line = test
    if line:
        gfx.text(surf, line, (x, y), size, color, None, 0, anchor="midleft", chunky=False)


# ====================================================================== the overworld
class OverworldScene(Scene):
    no_transition = False

    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.world = A.World(app.dex)
        self.rng = random.Random()
        self.t = 0.0
        self.dialogue = None
        self.queue = []          # things to do after the current dialogue: callables
        self.move = None         # (from x, y, to x, y, progress)
        self.step_frame = 0
        self.trail = []          # where the player was (the follower walks it)
        self.follow = None
        self.battle = None       # the AdventureSession while a battle is on
        self.trans = None        # battle intro: {"t", "start": callable}
        self.fade_in = 0.6
        self.cool = 3            # steps before the next wild encounter can happen
        self.banner = 0.0
        self.emote = None        # ("!", npc, time)
        self.menu = None
        self.buttons = []
        self.menu_btn = ui.Button((W - 130, 16, 114, 56), "Menu", (40, 44, 56), 22)
        self.hint = 8.0
        self.walking_npc = None
        self.play_t = 0.0
        self._enter(game["area"], game["x"], game["y"], first=True)

    # ------------------------------------------------------------------ areas
    @property
    def area(self):
        return self.world.areas[self.game["area"]]

    def _enter(self, index, x, y, first=False):
        self.game["area"], self.game["x"], self.game["y"] = index, x, y
        self.map_surf = render_area(self.area, self.world)
        self.banner = 0.0
        self.trail = [(x, y + 1)]
        self.follow = (x, y + 1)
        AUDIO.music(self.area["music"])
        if not first:
            A.save(self.game)

    def rows(self):
        return self.area["rows"]

    def tile(self, x, y):
        rows = self.rows()
        if 0 <= y < len(rows) and 0 <= x < A.COLS:
            return rows[y][x]
        return "#"

    def npc_at(self, x, y):
        for n in self.area["npcs"]:
            if (n["x"], n["y"]) == (x, y):
                return n
        return None

    def item_at(self, x, y):
        for it in self.area.get("items", []):
            if (it["x"], it["y"]) == (x, y) and it["id"] not in self.game["picked"]:
                return it
        return None

    def walkable(self, x, y):
        ch = self.tile(x, y)
        return (ch in WALK or ch in DOORS) and not self.npc_at(x, y) and not self.item_at(x, y)

    # ------------------------------------------------------------------ talking
    def say(self, lines, speaker="", then=None):
        self.dialogue = Dialogue(lines if isinstance(lines, list) else [lines], speaker, then)

    def _finish_dialogue(self):
        d = self.dialogue
        self.dialogue = None
        if d and d.on_done:
            d.on_done()

    # ------------------------------------------------------------------ update
    def update(self, dt):
        if self.app.stack[-1] is not self:
            return
        self.t += dt
        self.game["playtime"] = self.game.get("playtime", 0.0) + dt
        self.banner += dt
        self.hint = max(0.0, self.hint - dt)
        self.fade_in = max(0.0, self.fade_in - dt)
        AUDIO.music(self.area["music"])
        if self.battle is not None:       # back from a battle
            s, self.battle = self.battle, None
            self._after_battle(s)
            return
        if self.trans is not None:
            self.trans["t"] += dt
            if self.trans["t"] >= 1.1:
                start, self.trans = self.trans["start"], None
                start()
            return
        if self.emote is not None:
            self.emote[2] -= dt
            if self.emote[2] <= 0:
                cb, self.emote = self.emote[3], None
                cb()
            return
        if self.walking_npc is not None:
            self._walk_npc(dt)
            return
        if self.dialogue is not None:
            self.dialogue.update(dt)
            return
        if self.menu is not None:
            return
        if self.move is not None:
            fx, fy, tx, ty, p = self.move
            run = pygame.key.get_mods() & pygame.KMOD_SHIFT
            p += dt * (8.5 if run else 4.6)
            if p >= 1:
                self.move = None
                self.game["x"], self.game["y"] = tx, ty
                self._arrived(tx, ty)
            else:
                self.move = (fx, fy, tx, ty, p)
            return
        keys = pygame.key.get_pressed()
        for k, d in KEYS.items():
            if keys[k]:
                self._try_move(d)
                break

    def _try_move(self, d):
        self.game["face"] = d
        dx, dy = DIRS[d]
        x, y = self.game["x"], self.game["y"]
        nx, ny = x + dx, y + dy
        rows = self.rows()
        if ny < 0 or ny >= len(rows):
            self._edge(nx, ny)
            return
        it = self.item_at(nx, ny)
        if it is not None:
            self._pick(it)
            return
        if not self.walkable(nx, ny):
            return
        self.move = (x, y, nx, ny, 0.0)
        self.step_frame = 1 - self.step_frame
        self.trail.append((x, y))
        self.trail = self.trail[-4:]

    def _edge(self, nx, ny):
        i = self.game["area"]
        if ny < 0:
            area = self.area
            if area["kind"] == "town" and area["town"] >= 1:
                need = area["town"]
                if len(self.game["badges"]) < need:
                    badge = A.GYMS[area["town"] - 1][6]
                    self.say([f"Only trainers with the {badge} may go further.",
                              f"Beat the gym leader in {area['name']} first!"], "Guard")
                    return
            if i + 1 < len(self.world.areas):
                nxt = self.world.areas[i + 1]
                self._enter(i + 1, nx, len(nxt["rows"]) - 1)
        elif i > 0:
            self._enter(i - 1, nx, 0)

    def _arrived(self, x, y):
        ch = self.tile(x, y)
        self.game["steps"] = self.game.get("steps", 0) + 1
        if ch in DOORS:
            self._door(DOORS[ch], x, y)
            return
        if self._trainer_spots():
            return
        self.cool -= 1
        if ch == '"' and self.area["kind"] == "route" and self.cool <= 0 and self.rng.random() < 0.11:
            self._wild()

    # ------------------------------------------------------------------ interacting
    def interact(self):
        dx, dy = DIRS[self.game["face"]]
        x, y = self.game["x"] + dx, self.game["y"] + dy
        n = self.npc_at(x, y)
        if n:
            self._talk(n)
            return
        it = self.item_at(x, y)
        if it:
            self._pick(it)
            return
        ch = self.tile(x, y)
        if ch == "S":
            self._sign()

    def _sign(self):
        a = self.area
        if a.get("town"):
            k = a["town"] - 1
            if k < len(A.GYMS):
                _, leader, typ, *_ = A.GYMS[k]
                self.say([f"{a['name']}", f"Gym Leader: {leader} - the {typ.title()} type expert!"])
                return
        self.say(["Rootleaf Town - where every journey begins.", "Route 1 is north. Tall grass ahead!"])

    def _talk(self, n):
        opp = {"up": "down", "down": "up", "left": "right", "right": "left"}
        n["face"] = opp[self.game["face"]]
        if n["kind"] == "trainer":
            if n["id"] in self.game["beaten"]:
                self.say([n["lose"]], n["name"])
            else:
                self._challenge(n)
            return
        if n.get("heal"):
            self.say(n["lines"] + ["Your Pokemon look rested!"], n["name"], then=self._heal_all)
            return
        self.say(n["lines"], n["name"])

    def _pick(self, it):
        self.game["picked"].append(it["id"])
        self.game["bag"][it["item"]] = self.game["bag"].get(it["item"], 0) + it["count"]
        name = A.SHOP[it["item"]][0]
        AUDIO.play("catch", 0.6)
        self.say([f"You found {it['count']} x {name}!"])

    def _heal_all(self):
        A.heal_party(self.game)
        AUDIO.play("heal")

    def _door(self, kind, x, y):
        g = self.game
        back = lambda: self._step_out(x, y)  # noqa: E731
        if kind == "center":
            g["center"] = [g["area"], x, y + 1]

            def healed():
                self._heal_all()
                A.save(g)
                self.say(["Thank you for waiting! Your Pokemon are fully healed.", "We hope to see you again!"],
                         "Nurse", back)
            self.say(["Welcome to the Pokemon Center!", "We'll restore your Pokemon to full health..."], "Nurse",
                     healed)
        elif kind == "mart":
            from .adventure_ui import MartScene
            self.app.push(MartScene(self.app, g))
            back()
        elif kind == "gym":
            k = self.area["town"] - 1
            town, leader, typ, ace, intro, lose, badge = A.GYMS[k]
            if badge in g["badges"]:
                self.say([f"{leader}: You already beat me! Keep going - the League is waiting."], leader, back)
                return
            AUDIO.music("gym")
            team = self.world.gym_team(k)
            trainer = {"name": f"Leader {leader}", "leader": leader, "id": f"gym{k}", "lose": lose,
                       "money": 100 * ace, "badge": badge, "gym": k}
            self.say([f"Welcome to the {town} Gym!", intro], leader,
                     lambda: self._battle(team, "gym", trainer, after=back))
        elif kind == "league":
            if len(g["badges"]) < 8:
                self.say(["You need all 8 badges to challenge the League."], "Guard", back)
                return
            team = self.world.champion_team()
            name, lvl, intro, lose = A.CHAMPION
            trainer = {"name": f"Champion {name}", "leader": name, "id": "champion", "lose": lose, "money": 200 * lvl,
                       "champion": True}
            AUDIO.music("gym")
            self.say(["The Pokemon League. The strongest trainer in the region waits inside...", intro], name,
                     lambda: self._battle(team, "champion", trainer, after=back))
        elif kind == "lab":
            n = len(g["caught"])
            self.say(["Professor Hazel: Hello again!",
                      f"You've caught {n} kinds of Pokemon so far. " +
                      ("Amazing work!" if n > 30 else "Keep exploring - the tall grass is full of them!")],
                     "Prof. Hazel", back)
        else:
            self.say([self.rng.choice(["Nobody's home... but there's a nice smell of cooking.",
                                       "A family lives here. They wave and wish you luck!",
                                       "\"My kid wants to be a Pokemon trainer just like you!\"",
                                       "\"Have you seen a shiny Pokemon? I saw one once... I think.\""])], "", back)

    def _step_out(self, x, y):
        """Leave a building: back onto the tile in front of its door."""
        self.game["x"], self.game["y"] = x, y + 1
        self.game["face"] = "down"

    # ------------------------------------------------------------------ trainers
    def _trainer_spots(self):
        x, y = self.game["x"], self.game["y"]
        for n in self.area["npcs"]:
            if n["kind"] != "trainer" or n["id"] in self.game["beaten"]:
                continue
            dx, dy = DIRS[n["face"]]
            for k in range(1, n.get("sight", 4) + 1):
                tx, ty = n["x"] + dx * k, n["y"] + dy * k
                if (tx, ty) == (x, y):
                    AUDIO.play("select")
                    self.emote = ["!", n, 0.7, lambda n=n: self._approach(n)]
                    return True
                if self.tile(tx, ty) not in WALK or self.npc_at(tx, ty):
                    break
        return False

    def _approach(self, n):
        self.walking_npc = [n, 0.0]

    def _walk_npc(self, dt):
        n, p = self.walking_npc
        dx, dy = DIRS[n["face"]]
        nx, ny = n["x"] + dx, n["y"] + dy
        if (nx, ny) == (self.game["x"], self.game["y"]):
            self.walking_npc = None
            opp = {"up": "down", "down": "up", "left": "right", "right": "left"}
            self.game["face"] = opp[n["face"]]
            self._challenge(n)
            return
        p += dt * 4.6
        if p >= 1:
            n["x"], n["y"] = nx, ny
            p = 0.0
        self.walking_npc[1] = p

    def _challenge(self, n):
        trainer = {"name": n["name"], "id": n["id"], "lose": n["lose"], "money": n["money"]}
        team = [dict(m) for m in n["team"]]
        self.say([n["intro"]], n["name"], lambda: self._battle(team, "trainer", trainer))

    # ------------------------------------------------------------------ battles
    def _wild(self):
        area = self.area
        lo, hi = area["levels"]
        rng = self.rng
        legend = None
        if area["route"] >= 5 and rng.random() < (1 / 60 if self.game.get("champion") else 1 / 300):
            pool = [e for e in profile.legendary_pool(self.app.dex) if e["id"] not in self.game["caught"]]
            legend = rng.choice(pool) if pool else None
        if legend:
            foe = A.make_mon(self.app.dex, legend, hi + 6, rng)
        else:
            sid = self.world.wild_species(area, rng)
            lv = rng.randint(lo, hi)
            foe = A.make_mon(self.app.dex, A.grown_species(self.app.dex, self.app.dex.all[sid], lv - 4), lv, rng)
        self.cool = 3
        self._battle([foe], "wild", None)

    def _battle(self, foes, kind, trainer, after=None):
        if self.trans is not None or self.battle is not None:
            return
        if A.lead_alive(self.game, self.app.dex) is None:
            self.say(["Your Pokemon are all too tired to battle! Go to a Pokemon Center."], "", after)
            return

        def start():
            from .adventure_battle import AdventureSession
            from .battle_turn import TurnBattleScene
            s = AdventureSession(self.game, self.app.dex, foes, kind, trainer)
            s.after = after
            self.battle = s
            if any(f.get("shiny") for f in foes):
                SPRITES.shiny_forms = {f["species"] for f in foes if f.get("shiny")}
            self.app.push(TurnBattleScene(self.app, s))
        AUDIO.music("battle")
        self.trans = {"t": 0.0, "start": start, "kind": kind}

    def _after_battle(self, s):
        from .adventure_ui import EvolutionScene
        dex = self.app.dex
        g = self.game
        SPRITES.shiny_forms = set()
        r = s.results()
        lines = []
        if r["lost"]:
            lost = g["money"] // 2
            g["money"] -= lost
            lines += ["You're out of usable Pokemon!", f"You dropped {lost} coins in the panic...",
                      "...and hurried back to a Pokemon Center."]
            area, x, y = g["center"]

            def wake():
                self._enter(area, x, y)
                self._heal_all()
                A.save(g)
            self.say(lines, "", wake)
            return
        if r["caught"]:
            mon = r["caught"]
            where = A.add_caught(g, dex, mon)
            nm = A.name_of(dex, mon)
            lines.append(f"{nm} was added to your {'party' if where == 'party' else 'Box'}!")
            e = dex.all[mon["species"]]
            if e["legendary"] or e["mythical"]:
                profile.add_legend(e, mon.get("shiny", False))
                lines.append(f"{nm} also joined your Legend collection!")
        evolutions = []
        for i, gain in sorted(r["xp"].items()):
            mon = g["party"][i]
            lines.append(f"{A.name_of(dex, mon)} gained {gain} Exp. Points!")
            for ev in A.gain_xp(dex, mon, gain):
                if ev[0] == "level":
                    lines.append(f"{A.name_of(dex, mon)} grew to Lv. {ev[1]}!")
                    AUDIO.play("boost", 0.5)
                elif ev[0] == "learn":
                    mv = dex.moves[ev[1]]["name"]
                    if ev[2]:
                        lines.append(f"{A.name_of(dex, mon)} forgot {dex.moves[ev[2]]['name']} and learned {mv}!")
                    else:
                        lines.append(f"{A.name_of(dex, mon)} learned {mv}!")
                elif ev[0] == "evolve":
                    evolutions.append((mon, ev[1]))
        t = r.get("trainer") or {}
        if r["won"] and r["kind"] != "wild":
            g["money"] += t.get("money", 0)
            if t.get("id") and t["id"] not in g["beaten"]:
                g["beaten"].append(t["id"])
            lines = [t.get("lose", "")] + lines + [f"You got {t.get('money', 0)} coins for winning!"]
            if t.get("badge") and t["badge"] not in g["badges"]:
                g["badges"].append(t["badge"])
                lines.append(f"You received the {t['badge']}!")
                AUDIO.play("win")
                if t.get("gym") == 7:
                    g["bag"]["master-ball"] = g["bag"].get("master-ball", 0) + 1
                    lines.append("Terra also gave you a Master Ball! It never fails.")
        if r["ran"]:
            lines = ["Got away safely!"] + lines

        def finish():
            for mon, to in evolutions:
                self.app.push(EvolutionScene(self.app, g, mon, to))
            if t.get("champion") and r["won"]:
                from .adventure_ui import HallOfFame
                g["champion"] = True
                self.app.push(HallOfFame(self.app, g))
            A.save(g)
            if s.after:
                s.after()
        if lines:
            self.say(lines, "", finish)
        else:
            finish()

    # ------------------------------------------------------------------ input
    def handle(self, ev, pos):
        if self.trans is not None or self.emote is not None or self.walking_npc is not None:
            return
        if self.dialogue is not None:
            if (ev.type == pygame.KEYDOWN and ev.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_z,
                                                          pygame.K_ESCAPE)) or \
                    (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1):
                if self.dialogue.advance():
                    self._finish_dialogue()
            return
        if self.menu is not None:
            self._menu_handle(ev, pos)
            return
        if ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_ESCAPE, pygame.K_TAB, pygame.K_x):
                self._open_menu()
            elif ev.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_z) and self.move is None:
                self.interact()
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and pos:
            if self.menu_btn.hit(pos):
                self._open_menu()

    # ------------------------------------------------------------------ the start menu
    def _open_menu(self):
        AUDIO.play("select")
        items = [("party", "Pokemon"), ("bag", "Bag"), ("dex", "Pokedex"), ("card", "Trainer"), ("save", "Save"),
                 ("quit", "Save & quit"), ("close", "Close")]
        self.menu = [ui.Button((W - 300, 110 + i * 92, 280, 80), label, ui.SCREEN2 if k != "close" else ui.PANEL2,
                               26, tag=k) for i, (k, label) in enumerate(items)]
        self.buttons = self.menu

    def _menu_handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_ESCAPE, pygame.K_TAB, pygame.K_x):
            self.menu = None
            self.buttons = []
            return
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1 or not pos:
            return
        for b in self.menu:
            if not b.hit(pos):
                continue
            from . import adventure_ui as U
            tag = b.tag
            if tag == "party":
                self.app.push(U.PartyScene(self.app, self.game))
            elif tag == "bag":
                self.app.push(U.BagScene(self.app, self.game))
            elif tag == "dex":
                from .pokedex_ui import PokedexScene
                self.app.push(PokedexScene(self.app))
            elif tag == "card":
                self.app.push(U.AdventureCard(self.app, self.game))
            elif tag == "save":
                A.save(self.game)
                self.menu = None
                self.buttons = []
                self.say(["Your progress was saved!"])
                AUDIO.play("heal", 0.5)
                return
            elif tag == "quit":
                A.save(self.game)
                self.app.pop()
                return
            self.menu = None
            self.buttons = []
            return

    # ------------------------------------------------------------------ drawing
    def _player_px(self):
        if self.move is not None:
            fx, fy, tx, ty, p = self.move
            return (fx + (tx - fx) * p) * T, (fy + (ty - fy) * p) * T, p
        return self.game["x"] * T, self.game["y"] * T, 0.0

    def draw(self, surf):
        rows = self.rows()
        map_h = len(rows) * T
        px, py, p = self._player_px()
        cam = int(min(max(0, py + T / 2 - H * 0.55), max(0, map_h - H)))
        oy = -cam if map_h >= H else (H - map_h) // 2
        surf.fill((20, 30, 24))
        surf.blit(self.map_surf, (0, oy))
        # animated tiles on screen: water ripples, grass the player is in
        y0, y1 = max(0, cam // T - 1), min(len(rows), (cam + H) // T + 2)
        for y in range(y0, y1):
            for x, ch in enumerate(rows[y]):
                if ch == "~":
                    draw_water(surf, x, y, x * T, y * T + oy, self.t)
        # items, npcs, follower and player, sorted by row
        actors = []
        for it in self.area.get("items", []):
            if it["id"] not in self.game["picked"]:
                actors.append((it["y"] * T, "item", it))
        for n in self.area["npcs"]:
            nx, ny = n["x"] * T, n["y"] * T
            if self.walking_npc and self.walking_npc[0] is n:
                dx, dy = DIRS[n["face"]]
                nx += dx * self.walking_npc[1] * T
                ny += dy * self.walking_npc[1] * T
            actors.append((ny, "npc", (n, nx, ny)))
        lead = A.lead_alive(self.game, self.app.dex)
        if lead is not None:
            fx, fy = self._follower_px(px, py, p)
            actors.append((fy - 1, "follow", (lead, fx, fy)))
        actors.append((py, "player", (px, py)))
        actors.sort(key=lambda a: a[0])
        for _, kind, data in actors:
            if kind == "item":
                ball = gfx.ball_sprite(26)
                surf.blit(ball, ball.get_rect(center=(data["x"] * T + T / 2, data["y"] * T + T / 2 + oy)))
            elif kind == "npc":
                n, nx, ny = data
                shirt, hat = NPC_LOOKS.get(n.get("cls"), ((120, 160, 120), None))
                if n.get("name") == "Mom":
                    shirt, hat = (240, 140, 120), None
                walk = 1 + int(self.t * 6) % 2 if self.walking_npc and self.walking_npc[0] is n else 0
                draw_person(surf, nx + T / 2, ny + T - 2 + oy, n["face"], walk, shirt, hat)
            elif kind == "follow":
                mon, fx, fy = data
                img = SPRITES.get(mon["species"], 46, flip=self._follow_face() == "right",
                                  shiny=mon.get("shiny", False))
                hop = abs(math.sin(self.t * 9)) * 4 if self.move else 0
                surf.blit(img, img.get_rect(midbottom=(fx + T / 2, fy + T - 4 - hop + oy)))
            else:
                x, y = data
                walk = (1 + self.step_frame) if self.move is not None and p < 0.6 else 0
                draw_person(surf, x + T / 2, y + T - 2 + oy, self.game["face"], walk, (220, 60, 70),
                            hat=(220, 60, 70), hair=(50, 34, 24))
                if self.tile(self.game["x"], self.game["y"]) == '"' and self.move is None:
                    draw_tall(surf, 0, 0, x, y + oy + 24, math.sin(self.t * 5) * 2)  # grass over your legs
        # "!" over a trainer who spotted you
        if self.emote is not None:
            n = self.emote[1]
            bx, by = n["x"] * T + T / 2, n["y"] * T + oy - 30
            pygame.draw.rect(surf, INK, (bx - 16, by - 22, 32, 40), border_radius=8)
            pygame.draw.rect(surf, (255, 255, 255), (bx - 14, by - 20, 28, 36), border_radius=7)
            gfx.text(surf, "!", (bx, by - 2), 28, (220, 50, 60), None, 0)
        self._draw_hud(surf)
        if self.menu is not None:
            self._draw_menu(surf)
        if self.dialogue is not None:
            self.dialogue.draw(surf, self.t)
        if self.trans is not None:
            self._draw_transition(surf, self.trans["t"])
        if self.fade_in > 0:
            sh = pygame.Surface((W, H))
            sh.set_alpha(int(255 * self.fade_in / 0.6))
            surf.blit(sh, (0, 0))

    def _follow_face(self):
        fx, fy = self.follow if self.follow else (0, 0)
        return "right" if self.game["x"] > fx else "left"

    def _follower_px(self, px, py, p):
        if self.move is not None and self.trail:
            fx, fy = self.trail[-2] if len(self.trail) >= 2 else self.trail[-1]
            tx, ty = self.trail[-1]
            self.follow = (tx, ty)
            return (fx + (tx - fx) * p) * T, (fy + (ty - fy) * p) * T
        if self.trail:
            self.follow = self.trail[-1]
            return self.trail[-1][0] * T, self.trail[-1][1] * T
        return px, py + T

    def _draw_hud(self, surf):
        self.menu_btn.draw(surf)
        q = self.banner
        if q < 3.0:   # the area name slides in like a signpost
            k = min(1.0, q / 0.3, (3.0 - q) / 0.3)
            x = -320 + int(336 * k)
            pygame.draw.rect(surf, INK, (x - 4, 20, 330, 66), border_radius=12)
            pygame.draw.rect(surf, (250, 246, 232), (x, 24, 322, 58), border_radius=10)
            pygame.draw.rect(surf, (170, 124, 76), (x + 6, 30, 310, 46), 3, border_radius=8)
            gfx.text(surf, self.area["name"], (x + 161, 53), 24, INK, None, 0)
        if self.hint > 0 and self.dialogue is None:
            a = int(255 * min(1.0, self.hint / 0.8))
            ui.panel(surf, (40, H - 92, W - 80, 60), (30, 34, 44), 12)
            gfx.text(surf, "Arrows/WASD walk  -  Shift run  -  Space talk  -  Esc menu", (W / 2, H - 62), 17,
                     (240, 240, 245), None, 0, chunky=False, alpha=a)

    def _draw_menu(self, surf):
        g = self.game
        panel = pygame.Rect(W - 320, 30, 304, 110 + len(self.menu) * 92)
        pygame.draw.rect(surf, INK, panel.inflate(8, 8), border_radius=18)
        pygame.draw.rect(surf, (250, 250, 248), panel, border_radius=14)
        gfx.text(surf, g["name"], (panel.x + 20, panel.y + 30), 24, INK, None, 0, anchor="midleft")
        gfx.text(surf, f"{g['money']} coins  -  {len(g['badges'])} badges", (panel.x + 20, panel.y + 60), 16,
                 (90, 90, 100), None, 0, anchor="midleft", chunky=False)
        for b in self.menu:
            b.draw(surf)

    def _draw_transition(self, surf, t):
        """Into battle: the screen flashes, then black bars sweep in."""
        if t < 0.45:
            if int(t / 0.075) % 2 == 0:
                fl = pygame.Surface((W, H))
                fl.fill((255, 255, 255) if self.trans["kind"] == "wild" else (20, 20, 30))
                fl.set_alpha(170)
                surf.blit(fl, (0, 0))
            return
        k = min(1.0, (t - 0.45) / 0.55)
        n = 12
        for i in range(n):
            bh = H / n
            w = int(W * min(1.0, k * 1.6 - (i % 2) * 0.3 - i * 0.02))
            if w <= 0:
                continue
            x = 0 if i % 2 == 0 else W - w
            pygame.draw.rect(surf, (10, 10, 16), (x, int(i * bh), w, int(bh) + 1))
