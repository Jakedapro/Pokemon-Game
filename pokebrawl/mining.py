"""Digging for buried Mega Stones: the Mega Radar leads you to a spot on a route, you break into the hidden cave
under it, and chip away at the wall to uncover what's buried before the wall caves in.

Controls: arrows move, Z hits, X swaps PICK / HAMMER, Esc leaves. The mouse works too (click to hit)."""
import math
import random

import pygame

from . import adventure as A
from . import gbaui as U
from . import pixelfont as F
from .adventure_ui import GBAScene
from .audio import AUDIO
from .gfx import PIXEL

VW, VH = PIXEL
COLS, ROWS, CELL = 15, 10, 24
OX, OY = 12, 64
STABILITY = 64
TOOLS = {"pick": 2, "hammer": 4}   # how much the wall cracks per hit
SOIL = [(56, 40, 32), (156, 120, 80), (132, 100, 66), (110, 82, 56), (88, 68, 48)]
TREASURE = ["rare-candy", "ultra-ball", "max-potion", "great-ball", "max-revive", "super-potion"]
STONE_SHAPES = [[(0, 0), (1, 0), (0, 1), (1, 1)], [(1, 0), (0, 1), (1, 1), (2, 1), (1, 2)],
                [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)]]


class MiningScene(GBAScene):
    def __init__(self, app, game, site, on_done=None):
        """site: (site id, x, y, (kind, stone key)) from riftdex.dig_sites."""
        super().__init__(app)
        self.game = game
        self.site_id, _, _, (self.kind, self.stone) = site
        self.on_done = on_done
        self.t = 0.0
        rng = random.Random()
        self.depth = [[rng.choice((1, 2, 2, 3, 3, 4)) for _ in range(COLS)] for _ in range(ROWS)]
        self.bedrock = set()   # hard rock that never breaks
        self.items = []        # {"kind": "stone"/"item", "key", "cells", "got"}
        taken = set()

        def place(shape):
            for _ in range(200):
                x, y = rng.randrange(COLS - 3), rng.randrange(ROWS - 3)
                cells = [(x + dx, y + dy) for dx, dy in shape]
                if not any(c in taken for c in cells):
                    taken.update(cells)
                    return cells
            return None
        cells = place(rng.choice(STONE_SHAPES))
        self.items.append({"kind": "stone", "key": self.stone, "cells": cells, "got": False})
        for _ in range(rng.randint(1, 3)):
            c = place([(0, 0)] if rng.random() < 0.6 else [(0, 0), (1, 0)])
            if c:
                self.items.append({"kind": "item", "key": rng.choice(TREASURE), "cells": c, "got": False})
        for _ in range(rng.randint(2, 4)):
            c = place([(0, 0), (1, 0), (0, 1), (1, 1)] if rng.random() < 0.5 else [(0, 0), (0, 1)])
            if c:
                self.bedrock.update(c)
        self.cx, self.cy = COLS // 2, ROWS // 2
        self.tool = "pick"
        self.cracks = 0
        self.fx = []           # flying rock bits
        self.shake = 0.0
        self.done = None       # None while digging, then "won" / "collapsed" / "left"
        self.text = None

    # ------------------------------------------------------------------ digging
    def _hit(self, x, y):
        if self.done:
            return
        self.cracks += TOOLS[self.tool]
        self.shake = 0.15
        AUDIO.play("hit" if self.tool == "pick" else "hit_super", 0.6)
        if self.tool == "pick":
            area = [((x, y), 2)] + [((x + dx, y + dy), 1) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        else:
            area = [((x, y), 2)] + [((x + dx, y + dy), 2 if dx == 0 or dy == 0 else 1)
                                    for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
        for (cx, cy), n in area:
            if 0 <= cx < COLS and 0 <= cy < ROWS and (cx, cy) not in self.bedrock:
                if self.depth[cy][cx] > 0:
                    for _ in range(3):
                        self.fx.append([OX + cx * CELL + 12, OY + cy * CELL + 12, random.uniform(-60, 60),
                                        random.uniform(-120, -30), 0.5, SOIL[min(4, self.depth[cy][cx])]])
                self.depth[cy][cx] = max(0, self.depth[cy][cx] - n)
        for it in self.items:
            if not it["got"] and it["cells"] and all(self.depth[cy][cx] == 0 for cx, cy in it["cells"]):
                it["got"] = True
                AUDIO.play("catch", 0.7)
        if all(it["got"] for it in self.items):
            self._finish("won")
        elif self.cracks >= STABILITY:
            self._finish("collapsed")

    def _finish(self, how):
        from . import riftdex as R
        from . import story as S
        self.done = how
        g = self.game
        dex = self.app.dex
        lines = []
        if how == "collapsed":
            AUDIO.play("faint", 0.8)
            lines.append("The wall collapsed!")
        stone = self.items[0]
        if stone["got"]:
            if self.kind == "corrupt":
                lst = g.setdefault("corrupted", [])
                if self.stone not in lst:
                    lst.append(self.stone)
                lines += [f"{g['name']} dug up a {R.corrupted_name(dex, self.stone).upper()}!",
                          "It's pulsing with a sick, black light..."]
            else:
                lst = g.setdefault("megastones", [])
                if self.stone not in lst:
                    lst.append(self.stone)
                lines.append(f"{g['name']} dug up a MEGA STONE: {S.stone_name(dex, self.stone).upper()}!")
                if R.is_custom(dex.get(self.stone)["id"] if dex.get(self.stone) else -1):
                    lines.append("Nobody has ever seen this kind of Mega Evolution before...")
            dug = g.setdefault("dug", [])
            if self.site_id not in dug:
                dug.append(self.site_id)
            AUDIO.play("tera", 0.8)
        elif how != "won":
            lines.append("The stone is still buried in there... Come back and try again!")
        for it in self.items[1:]:
            if it["got"]:
                g["bag"][it["key"]] = g["bag"].get(it["key"], 0) + 1
                lines.append(f"Also found: {A.SHOP.get(it['key'], (it['key'],))[0].upper()}!")
        A.save(g)
        self.text = U.TextBox(lines or ["Nothing more to dig here."], self._leave)

    def _leave(self):
        self.app.pop()
        if self.on_done:
            self.on_done(self.done)

    # ------------------------------------------------------------------ input
    def handle(self, ev, pos):
        if self.text is not None:
            self.text.handle(ev)
            return
        d = U.direction(ev)
        if d:
            dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[d]
            self.cx = max(0, min(COLS - 1, self.cx + dx))
            self.cy = max(0, min(ROWS - 1, self.cy + dy))
        elif ev.type == pygame.KEYDOWN and ev.key in (pygame.K_x, pygame.K_TAB):
            self.tool = "hammer" if self.tool == "pick" else "pick"
            AUDIO.play("select", 0.5)
        elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self._finish("left")
        elif U.is_a(ev):
            self._hit(self.cx, self.cy)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and pos:
            x, y = (pos[0] - OX) // CELL, (pos[1] - OY) // CELL
            if 0 <= x < COLS and 0 <= y < ROWS:
                self.cx, self.cy = x, y
                self._hit(x, y)
            elif pygame.Rect(388, 120, 84, 40).collidepoint(pos):
                self.tool = "pick"
            elif pygame.Rect(388, 170, 84, 40).collidepoint(pos):
                self.tool = "hammer"

    def update(self, dt):
        self.t += dt
        self.shake = max(0.0, self.shake - dt)
        for p in self.fx:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 400 * dt
            p[4] -= dt
        self.fx = [p for p in self.fx if p[4] > 0]
        if self.text is not None:
            self.text.update(dt)

    # ------------------------------------------------------------------ drawing
    def draw(self, surf):
        surf.fill((40, 28, 24))
        for y in range(0, VH, 8):   # the cave around the wall
            k = y / VH
            surf.fill((int(64 - 24 * k), int(44 - 16 * k), int(36 - 12 * k)), (0, y, VW, 8))
        sx = int(math.sin(self.t * 80) * 3) if self.shake else 0
        # the stability bar: the wall cracking along the top
        bar = pygame.Rect(OX, 14, COLS * CELL, 18)
        pygame.draw.rect(surf, (24, 16, 12), bar, border_radius=4)
        k = min(1.0, self.cracks / STABILITY)
        col = (96, 200, 96) if k < 0.5 else (232, 192, 64) if k < 0.8 else (232, 72, 56)
        pygame.draw.rect(surf, col, (bar.x + 2, bar.y + 2, int((bar.w - 4) * (1 - k)), bar.h - 4), border_radius=3)
        F.draw(surf, "WALL", (bar.x + 6, bar.y + 1), (248, 240, 224), None, small=True)
        title = "BURIED MEGA STONE" if self.kind == "stone" else "SOMETHING DARK IS BURIED HERE..."
        F.draw(surf, title, (OX, 36), (248, 224, 160) if self.kind == "stone" else (208, 144, 255), (40, 24, 16),
               small=True)
        # what's buried (drawn first, the soil goes over it)
        for it in self.items:
            if not it["cells"]:
                continue
            xs = [c[0] for c in it["cells"]]
            ys = [c[1] for c in it["cells"]]
            r = pygame.Rect(OX + min(xs) * CELL + sx, OY + min(ys) * CELL, (max(xs) - min(xs) + 1) * CELL,
                            (max(ys) - min(ys) + 1) * CELL)
            for cx, cy in it["cells"]:
                pygame.draw.rect(surf, (44, 32, 26), (OX + cx * CELL + sx, OY + cy * CELL, CELL, CELL))
            if it["kind"] == "stone":
                self._gem(surf, r, self.kind == "corrupt", it["got"])
            else:
                U.ball(surf, r.center, 8)
        for y in range(ROWS):
            for x in range(COLS):
                rect = pygame.Rect(OX + x * CELL + sx, OY + y * CELL, CELL, CELL)
                if (x, y) in self.bedrock:
                    pygame.draw.rect(surf, (72, 76, 88), rect)
                    pygame.draw.rect(surf, (112, 116, 128), rect.inflate(-6, -6), border_radius=3)
                    continue
                dd = self.depth[y][x]
                if dd <= 0:
                    continue
                pygame.draw.rect(surf, SOIL[min(4, dd)], rect)
                pygame.draw.rect(surf, tuple(max(0, c - 18) for c in SOIL[min(4, dd)]), rect, 1)
                for i in range(dd):   # specks: more layers, more rubble
                    px = rect.x + 4 + (x * 7 + y * 3 + i * 9) % 16
                    py = rect.y + 4 + (x * 5 + y * 11 + i * 7) % 16
                    pygame.draw.rect(surf, tuple(max(0, c - 34) for c in SOIL[min(4, dd)]), (px, py, 3, 3))
        cur = pygame.Rect(OX + self.cx * CELL + sx, OY + self.cy * CELL, CELL, CELL)
        pygame.draw.rect(surf, (255, 255, 255), cur.inflate(4, 4), 2, border_radius=3)
        for x, y, _, _, life, col in self.fx:
            pygame.draw.rect(surf, col, (int(x), int(y), 4, 4))
        # tools
        for i, (tool, label) in enumerate((("pick", "PICK"), ("hammer", "HAMMER"))):
            r = pygame.Rect(388, 120 + i * 50, 84, 40)
            on = self.tool == tool
            pygame.draw.rect(surf, (248, 216, 96) if on else (120, 96, 80), r, border_radius=6)
            pygame.draw.rect(surf, (48, 32, 24), r, 2, border_radius=6)
            F.draw(surf, label, r.center, (48, 32, 24), None, anchor="center", small=True)
        for i, line in enumerate(("Z  dig", "X  swap", "Esc  quit")):
            F.draw(surf, line, (392, 222 + i * 18), (232, 216, 200), None, small=True)
        if self.text is not None:
            self.text.draw(surf, self.t)

    def _gem(self, surf, r, corrupt, got):
        c = r.center
        w, h = r.w // 2 - 3, r.h // 2 - 3
        pts = [(c[0], c[1] - h), (c[0] + w, c[1]), (c[0], c[1] + h), (c[0] - w, c[1])]
        body = (64, 24, 80) if corrupt else (96, 200, 240)
        light = (180, 40, 60) if corrupt else (232, 248, 255)
        pygame.draw.polygon(surf, body, pts)
        pygame.draw.polygon(surf, light, [pts[0], pts[1], c])
        pygame.draw.polygon(surf, (24, 16, 32), pts, 2)
        # the Mega symbol: a little helix in the middle
        for i in range(6):
            a = self.t * 3 + i * math.pi / 3
            pygame.draw.circle(surf, (255, 240, 160) if not corrupt else (255, 64, 64),
                               (int(c[0] + math.cos(a) * w * 0.35), int(c[1] + math.sin(a * 2) * h * 0.25)), 2)
        if got:
            k = 0.5 + 0.5 * math.sin(self.t * 6)
            pygame.draw.circle(surf, (255, 255, 255), c, int(4 + 6 * k), 1)
