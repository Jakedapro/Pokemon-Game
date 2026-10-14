"""Pixel art for Adventure mode, drawn in code: 16x16 tiles, buildings, room interiors and trainer sprites.
Everything is painted at 1x and scaled 2x with nearest-neighbour onto the 480x320 canvas (a GBA screen at 2x).
None of it is copied from any game - it's original art in a handheld style."""
import math
import os
import random

import pygame

from . import pokedex

S = 2            # pixel scale
TS = 16          # tile size at 1x
T = TS * S       # tile size on the canvas

OUT = (40, 40, 48)
_cache = {}


def _scaled(surf):
    return pygame.transform.scale(surf, (surf.get_width() * S, surf.get_height() * S))


def _r(seed):
    return random.Random(seed)


def _px(s, x, y, c):
    if 0 <= x < s.get_width() and 0 <= y < s.get_height():
        s.set_at((x, y), c)


def _from_grid(rows, pal):
    h, w = len(rows), max(len(r) for r in rows)
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in pal:
                s.set_at((x, y), pal[ch])
    return s


# ====================================================================== ground tiles
GR = (120, 200, 96)
GR2 = (96, 176, 80)
GR3 = (152, 216, 120)
TALL1 = (64, 152, 72)
TALL2 = (40, 112, 56)
TALL3 = (112, 192, 96)
DIRT = (224, 200, 144)
DIRT2 = (200, 176, 120)
DIRT3 = (240, 224, 176)
WAT = (88, 144, 232)
WAT2 = (64, 112, 208)
WAT3 = (168, 208, 248)


def _grass(seed=0):
    s = pygame.Surface((TS, TS))
    s.fill(GR)
    r = _r(seed)
    for _ in range(4):
        x, y = r.randrange(1, 15), r.randrange(2, 15)
        _px(s, x, y, GR2)
        _px(s, x + 1, y - 1, GR2)
    for _ in range(2):
        _px(s, r.randrange(16), r.randrange(16), GR3)
    return s


def _tall(frame=0):
    s = pygame.Surface((TS, TS))
    s.fill(TALL2)
    for bx in range(0, 16, 4):
        for row, by in enumerate((7, 15)):
            off = (frame if row == 0 else -frame)
            x0 = bx + (2 if row else 0)
            pts = [(x0, by), (x0 + 1 + off, by - 6), (x0 + 3, by)]
            pygame.draw.polygon(s, TALL1, pts)
            _px(s, x0 + 1 + off, by - 5, TALL3)
            _px(s, x0 + 1, by - 3, TALL3)
    return s


def _dirt(seed=0):
    s = pygame.Surface((TS, TS))
    s.fill(DIRT)
    r = _r(seed + 7)
    for _ in range(5):
        x, y = r.randrange(16), r.randrange(16)
        _px(s, x, y, DIRT2)
        if r.random() < 0.5:
            _px(s, x + 1, y, DIRT3)
    return s


def _flowers(frame=0, seed=0):
    s = _grass(seed)
    r = _r(seed + 3)
    col = r.choice([(240, 80, 80), (248, 216, 64), (248, 248, 248), (224, 128, 224)])
    for fx, fy in ((4, 4), (11, 10)):
        fy += frame
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
            _px(s, fx + dx, fy + dy, col)
        _px(s, fx, fy, (248, 200, 48))
        _px(s, fx, fy + 2, GR2)
    return s


def _tree(seed=0):
    s = _grass(seed)
    dark, mid, light = (32, 104, 56), (48, 144, 72), (96, 184, 96)
    pygame.draw.rect(s, (112, 80, 48), (6, 11, 4, 5))
    _px(s, 6, 15, (80, 56, 32))
    _px(s, 9, 15, (80, 56, 32))
    pygame.draw.circle(s, OUT, (8, 7), 8)
    pygame.draw.circle(s, dark, (8, 7), 7)
    pygame.draw.circle(s, mid, (7, 6), 6)
    pygame.draw.circle(s, light, (6, 4), 3)
    for x, y in ((10, 3), (4, 9), (11, 8), (8, 11)):
        _px(s, x, y, dark)
    _px(s, 5, 3, (168, 224, 144))
    return s


def _water(frame=0):
    s = pygame.Surface((TS, TS))
    s.fill(WAT)
    for k, y in enumerate((3, 9, 14)):
        x0 = (frame * 3 + k * 5) % 16
        for dx in range(4):
            _px(s, (x0 + dx) % 16, y, WAT3 if dx in (1, 2) else WAT2)
    return s


def _sign():
    s = _grass(5)
    pygame.draw.rect(s, (96, 64, 40), (7, 9, 2, 7))
    pygame.draw.rect(s, OUT, (2, 2, 12, 9))
    pygame.draw.rect(s, (200, 152, 96), (3, 3, 10, 7))
    for y in (5, 7):
        pygame.draw.line(s, (152, 104, 64), (5, y), (10, y))
    return s


def _ledge():
    s = _grass(9)
    pygame.draw.rect(s, (80, 152, 64), (0, 10, 16, 6))
    pygame.draw.line(s, (48, 104, 48), (0, 10), (15, 10))
    return s


def _ball_item():
    s = _grass(11)
    pygame.draw.circle(s, OUT, (8, 9), 5)
    pygame.draw.circle(s, (248, 248, 248), (8, 9), 4)
    pygame.draw.rect(s, (232, 64, 56), (4, 5, 9, 4))
    pygame.draw.line(s, OUT, (4, 9), (12, 9))
    _px(s, 8, 9, (248, 248, 248))
    _px(s, 6, 6, (255, 200, 200))
    return s


def tile(kind, frame=0, seed=0):
    """A 32x32 (2x) map tile. kind: grass flowers tall dirt tree water sign ledge item."""
    key = ("t", kind, frame, seed % 8)
    if key in _cache:
        return _cache[key]
    f = {"grass": lambda: _grass(seed % 8), "flowers": lambda: _flowers(frame, seed % 8),
         "tall": lambda: _tall(frame), "dirt": lambda: _dirt(seed % 8), "tree": lambda: _tree(seed % 8),
         "water": lambda: _water(frame), "sign": _sign, "ledge": _ledge, "item": _ball_item}[kind]
    out = _scaled(f())
    _cache[key] = out
    return out


def tall_overlay(frame=0):
    """The front blades of tall grass, drawn over a trainer's legs."""
    key = ("tallover", frame)
    if key not in _cache:
        s = pygame.Surface((TS, 8), pygame.SRCALPHA)
        for bx in range(0, 16, 4):
            pts = [(bx + 2, 8), (bx + 3 + frame, 1), (bx + 5, 8)]
            pygame.draw.polygon(s, TALL1, pts)
            _px(s, bx + 3 + frame, 2, TALL3)
        _cache[key] = _scaled(s)
    return _cache[key]


# ====================================================================== buildings (1x painters, then scaled)
ROOF = {"center": ((216, 64, 64), (168, 40, 48)), "mart": ((64, 112, 216), (40, 80, 168)),
        "gym": ((136, 144, 160), (96, 104, 120)), "lab": ((200, 200, 208), (152, 152, 168)),
        "league": ((232, 184, 64), (184, 136, 40))}
HOUSE_ROOFS = [((176, 96, 64), (136, 64, 40)), ((88, 152, 96), (56, 112, 64)), ((136, 96, 176), (96, 64, 136)),
               ((200, 128, 64), (160, 96, 40))]


def building(kind, wt, ht, door_col, accent=None, seed=0):
    """A building wt x ht tiles, door at column door_col (bottom row)."""
    key = ("b", kind, wt, ht, door_col, accent, seed % 4)
    if key in _cache:
        return _cache[key]
    w, h = wt * TS, ht * TS
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    roof, roof_d = ROOF.get(kind) or HOUSE_ROOFS[seed % len(HOUSE_ROOFS)]
    wall, wall_d = ((240, 232, 216), (208, 192, 168)) if kind != "gym" else ((200, 204, 216), (160, 164, 180))
    if kind == "league":
        wall, wall_d = (248, 240, 208), (216, 200, 160)
    roof_h = max(10, int(h * 0.5))
    # walls
    pygame.draw.rect(s, OUT, (1, roof_h - 2, w - 2, h - roof_h + 2))
    pygame.draw.rect(s, wall, (2, roof_h - 1, w - 4, h - roof_h - 1))
    pygame.draw.line(s, wall_d, (2, h - 2), (w - 3, h - 2))
    for x in range(4, w - 4, 8):   # wall boards
        pygame.draw.line(s, wall_d, (x, roof_h), (x, h - 3))
    # roof: overhang + shingle rows + ridge highlight
    pygame.draw.rect(s, OUT, (0, 0, w, roof_h + 1), border_radius=2)
    pygame.draw.rect(s, roof, (1, 1, w - 2, roof_h - 1), border_radius=2)
    for y in range(4, roof_h - 1, 4):
        pygame.draw.line(s, roof_d, (2, y), (w - 3, y))
        for x in range(2 + (y // 4 % 2) * 4, w - 2, 8):
            _px(s, x, y - 1, roof_d)
    pygame.draw.line(s, tuple(min(255, c + 40) for c in roof), (2, 1), (w - 3, 1))
    pygame.draw.line(s, roof_d, (1, roof_h - 1), (w - 2, roof_h - 1))
    # windows
    dx = door_col * TS
    for x in range(4, w - 12, 16):
        if abs(x + 4 - (dx + 8)) < 10:
            continue
        wy = roof_h + 3
        if wy + 7 > h - 2:
            break
        pygame.draw.rect(s, OUT, (x, wy, 10, 8))
        pygame.draw.rect(s, (136, 192, 240), (x + 1, wy + 1, 8, 6))
        pygame.draw.line(s, (216, 240, 255), (x + 1, wy + 1), (x + 4, wy + 1))
        pygame.draw.line(s, OUT, (x + 5, wy + 1), (x + 5, wy + 6))
    # door
    dy = h - 13
    pygame.draw.rect(s, OUT, (dx + 3, dy, 10, 13))
    if kind in ("center", "mart", "gym", "league"):   # sliding glass doors
        pygame.draw.rect(s, (152, 208, 240), (dx + 4, dy + 1, 8, 12))
        pygame.draw.line(s, OUT, (dx + 8, dy + 1), (dx + 8, dy + 12))
        pygame.draw.line(s, (232, 248, 255), (dx + 5, dy + 2), (dx + 5, dy + 6))
    else:
        pygame.draw.rect(s, (152, 96, 56), (dx + 4, dy + 1, 8, 12))
        _px(s, dx + 10, dy + 7, (248, 216, 96))
    # signs
    cx = w // 2
    sy = max(3, roof_h // 2 - 4)
    if kind == "center":
        pygame.draw.rect(s, OUT, (cx - 7, sy - 1, 14, 10), border_radius=2)
        pygame.draw.rect(s, (248, 248, 248), (cx - 6, sy, 12, 8), border_radius=2)
        pygame.draw.rect(s, (216, 56, 56), (cx - 1, sy + 1, 2, 6))
        pygame.draw.rect(s, (216, 56, 56), (cx - 4, sy + 3, 8, 2))
    elif kind == "mart":
        pygame.draw.rect(s, OUT, (cx - 10, sy - 1, 20, 10), border_radius=2)
        pygame.draw.rect(s, (248, 248, 248), (cx - 9, sy, 18, 8), border_radius=2)
        for k in range(3):   # a tiny "shop" mark: three stripes
            pygame.draw.line(s, (64, 112, 216), (cx - 6 + k * 5, sy + 2), (cx - 4 + k * 5, sy + 5), 2)
    elif kind == "gym":
        col = accent or (200, 200, 216)
        pygame.draw.rect(s, col, (2, roof_h - 4, w - 4, 3))
        pygame.draw.rect(s, OUT, (cx - 12, sy - 1, 24, 10), border_radius=2)
        pygame.draw.rect(s, (56, 60, 72), (cx - 11, sy, 22, 8), border_radius=2)
        pygame.draw.circle(s, col, (cx, sy + 4), 3)
    elif kind == "league":
        for k in range(-2, 3):
            pygame.draw.polygon(s, (248, 224, 120), [(cx + k * 10 - 3, sy + 8), (cx + k * 10, sy), (cx + k * 10 + 3,
                                                                                                    sy + 8)])
    out = _scaled(s)
    _cache[key] = out
    return out


# ====================================================================== interiors
FLOOR = {"center": ((232, 224, 208), (216, 204, 184)), "mart": ((224, 232, 216), (200, 212, 192)),
         "house": ((208, 168, 120), (184, 144, 96)), "lab": ((232, 232, 240), (208, 208, 224)),
         "gym": ((176, 184, 200), (152, 160, 176)), "league": ((200, 64, 64), (168, 40, 48))}


def floor_tile(kind, x, y):
    key = ("f", kind, (x + y) % 2)
    if key not in _cache:
        a, b = FLOOR.get(kind, FLOOR["house"])
        s = pygame.Surface((TS, TS))
        s.fill(a if (x + y) % 2 == 0 else b)
        pygame.draw.line(s, tuple(max(0, c - 16) for c in a), (0, 15), (15, 15))
        pygame.draw.line(s, tuple(max(0, c - 16) for c in a), (15, 0), (15, 15))
        _cache[key] = _scaled(s)
    return _cache[key]


def wall_tile(kind):
    key = ("w", kind)
    if key not in _cache:
        s = pygame.Surface((TS, TS))
        base = {"center": (248, 232, 232), "mart": (232, 240, 248), "house": (232, 216, 184),
                "lab": (240, 240, 248), "gym": (120, 128, 144), "league": (72, 56, 96)}.get(kind, (232, 216, 184))
        s.fill(base)
        pygame.draw.rect(s, tuple(max(0, c - 40) for c in base), (0, 12, 16, 4))
        pygame.draw.line(s, tuple(max(0, c - 24) for c in base), (0, 4), (15, 4))
        _cache[key] = _scaled(s)
    return _cache[key]


def furniture(kind):
    """Interior objects, each one tile: counter, pc, shelf, table, plant, mat, machine, bed, tv, books, statue."""
    key = ("o", kind)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((TS, TS), pygame.SRCALPHA)
    if kind == "counter":
        pygame.draw.rect(s, OUT, (0, 4, 16, 12))
        pygame.draw.rect(s, (232, 104, 104), (0, 5, 16, 4))
        pygame.draw.rect(s, (240, 232, 216), (0, 9, 16, 6))
    elif kind == "mcounter":
        pygame.draw.rect(s, OUT, (0, 4, 16, 12))
        pygame.draw.rect(s, (104, 144, 232), (0, 5, 16, 4))
        pygame.draw.rect(s, (240, 232, 216), (0, 9, 16, 6))
    elif kind == "machine":
        pygame.draw.rect(s, OUT, (1, 2, 14, 13), border_radius=2)
        pygame.draw.rect(s, (200, 208, 224), (2, 3, 12, 11), border_radius=2)
        for k in range(3):
            pygame.draw.circle(s, (232, 64, 56), (4 + k * 4, 7), 1)
        pygame.draw.rect(s, (104, 200, 152), (3, 10, 10, 2))
    elif kind == "pc":
        pygame.draw.rect(s, OUT, (2, 1, 12, 14))
        pygame.draw.rect(s, (216, 216, 224), (3, 2, 10, 12))
        pygame.draw.rect(s, (72, 160, 216), (4, 3, 8, 6))
        pygame.draw.line(s, (168, 224, 248), (5, 4), (8, 4))
    elif kind == "shelf":
        pygame.draw.rect(s, OUT, (0, 0, 16, 16))
        pygame.draw.rect(s, (176, 128, 80), (1, 1, 14, 14))
        r = _r(3)
        for row in (2, 7, 12):
            pygame.draw.line(s, (128, 88, 48), (1, row + 3), (14, row + 3))
            for x in range(2, 14, 3):
                c = r.choice([(232, 80, 80), (80, 136, 232), (248, 216, 80), (104, 200, 120)])
                pygame.draw.rect(s, c, (x, row, 2, 3))
    elif kind == "table":
        pygame.draw.rect(s, OUT, (1, 3, 14, 10), border_radius=2)
        pygame.draw.rect(s, (200, 144, 88), (2, 4, 12, 7), border_radius=2)
        pygame.draw.rect(s, (160, 104, 56), (3, 11, 2, 4))
        pygame.draw.rect(s, (160, 104, 56), (11, 11, 2, 4))
    elif kind == "plant":
        pygame.draw.rect(s, OUT, (4, 10, 8, 6))
        pygame.draw.rect(s, (184, 104, 64), (5, 11, 6, 4))
        pygame.draw.circle(s, (48, 136, 72), (8, 7), 5)
        pygame.draw.circle(s, (96, 184, 96), (7, 5), 2)
    elif kind == "mat":
        pygame.draw.rect(s, (200, 64, 64), (1, 4, 14, 9), border_radius=2)
        pygame.draw.rect(s, (232, 120, 104), (3, 6, 10, 5), border_radius=1)
    elif kind == "bed":
        pygame.draw.rect(s, OUT, (1, 0, 14, 16))
        pygame.draw.rect(s, (80, 120, 200), (2, 5, 12, 10))
        pygame.draw.rect(s, (248, 248, 248), (3, 1, 10, 4))
    elif kind == "tv":
        pygame.draw.rect(s, OUT, (1, 3, 14, 11))
        pygame.draw.rect(s, (72, 72, 88), (2, 4, 12, 9))
        pygame.draw.rect(s, (120, 184, 232), (3, 5, 10, 7))
    elif kind == "statue":
        pygame.draw.rect(s, OUT, (3, 10, 10, 6))
        pygame.draw.rect(s, (168, 168, 184), (4, 11, 8, 4))
        pygame.draw.circle(s, OUT, (8, 6), 5)
        pygame.draw.circle(s, (200, 200, 216), (8, 6), 4)
    elif kind == "books":
        pygame.draw.rect(s, OUT, (0, 0, 16, 16))
        pygame.draw.rect(s, (136, 96, 64), (1, 1, 14, 14))
        for x in range(2, 14, 2):
            pygame.draw.rect(s, (200 - x * 6, 120, 80 + x * 8), (x, 2, 2, 12))
    out = _scaled(s)
    _cache[key] = out
    return out


# ====================================================================== trainers
# trainers are 16x32 like the handheld games (a big head, ~25 px of art standing on the tile's bottom edge)
_TOP = ["................"] * 7
_LEGS = ["...KPPPPPPPPK...", "...KPPPKKPPPK...", "...KPPK..KPPK...", "...KpGK..KGpK...", "...KGGK..KGGK...",
         "...KKK....KKK..."]
_LEGS_WALK = ["...KPPPPPPPPK...", "...KPPPKKPPPK...", "...KPPK..KPPK...", "...KGGK..KpGK...", "...KKK...KGGK...",
              "..........KKK..."]
PLAYER_DOWN = _TOP + [
    ".....KKKKKK.....",
    "...KKRRRRRRKK...",
    "..KRRRRWWRRRRK..",
    ".KRRRRWWWWRRRRK.",
    ".KRRRRRRRRRRRRK.",
    ".KrrrrrrrrrrrrK.",
    ".KKKKKKKKKKKKKK.",
    ".KHHSSSSSSSSHHK.",
    ".KHSSESSSSESSHK.",
    ".KHSSESSSSESSHK.",
    "..KSSSSSSSSSSK..",
    "...KSSSssSSSK...",
    "....KKSSSSKK....",
    "...KBBKSSKBBK...",
    "..KBBBBYBBBBBK..",
    ".KSKBBBYBBBBKSK.",
    ".KSKBBBBYBBBKSK.",
    ".KSKbBBBBYBbKSK.",
    "..KKbbbbbbbbKK..",
] + _LEGS
PLAYER_DOWN_WALK = PLAYER_DOWN[:-6] + _LEGS_WALK
PLAYER_UP = _TOP + [
    ".....KKKKKK.....",
    "...KKRRRRRRKK...",
    "..KRRRRRRRRRRK..",
    ".KRRRRRRRRRRRRK.",
    ".KRRRRRRRRRRRRK.",
    ".KrrrrrrrrrrrrK.",
    ".KKrrrrrrrrrrKK.",
    ".KHHHHHHHHHHHHK.",
    ".KHHHHHHHHHHHHK.",
    ".KHHHHHHHHHHHHK.",
    "..KHHHHHHHHHHK..",
    "...KHHHHHHHHK...",
    "....KKSSSSKK....",
    "...KBBBBBBBBK...",
    "..KBBYYYYYYBBK..",
    ".KSKBYyyyyYBKSK.",
    ".KSKBYyyyyYBKSK.",
    ".KSKbYYYYYYbKSK.",
    "..KKbbbbbbbbKK..",
] + _LEGS
PLAYER_UP_WALK = PLAYER_UP[:-6] + _LEGS_WALK
PLAYER_LEFT = _TOP + [
    "....KKKKKK......",
    "..KKRRRRRRKK....",
    ".KRRRRRRRWWRK...",
    ".KRRRRRRRWWRRK..",
    "KRRRRRRRRRRRRK..",
    "KrrrrrrrrrrrrK..",
    "KKKKKKKKKKKKKK..",
    "..KSSSSHHHHHHK..",
    "..KESSSSHHHHHK..",
    "..KESSSSSHHHHK..",
    "..KSSSSSSHHHK...",
    "...KsSSSSSSK....",
    "....KKSSSKK.....",
    "....KBBBBBK.....",
    "...KBBBBBYYK....",
    "...KBSSBBYYK....",
    "...KBSSBByyK....",
    "...KbBBBbYYK....",
    "...KKbbbbbKK....",
    "....KPPPPPK.....",
    "....KPPPPPK.....",
    "....KPPKPPK.....",
    "....KPPKPPK.....",
    "....KGGKGGK.....",
    "....KKKKKKK.....",
]
PLAYER_LEFT_WALK = PLAYER_LEFT[:-6] + [
    "....KPPPPPK.....",
    "...KPPPKPPPK....",
    "..KPPK...KPPK...",
    "..KpGK...KGpK...",
    "..KGGK...KGGK...",
    "..KKK.....KKK...",
]

LOOKS = {   # cap, shirt, pants, hair; cap None = no cap (hair shown)
    "player": ((224, 56, 56), (64, 120, 216), (56, 64, 96), (88, 56, 40)),
    "rival": ((56, 56, 64), (232, 120, 48), (64, 64, 72), (40, 40, 48)),
    "Youngster": ((248, 200, 64), (88, 144, 232), (72, 88, 136), (120, 72, 40)),
    "Lass": (None, (240, 128, 168), (96, 64, 136), (168, 96, 48)),
    "Bug Catcher": ((232, 224, 120), (120, 184, 96), (96, 104, 64), (88, 56, 40)),
    "Hiker": ((120, 80, 48), (176, 120, 72), (88, 72, 56), (56, 40, 32)),
    "Swimmer": (None, (64, 168, 224), (64, 168, 224), (40, 40, 48)),
    "Ace Trainer": ((48, 48, 64), (224, 64, 72), (48, 48, 64), (200, 160, 64)),
    "Psychic": (None, (152, 88, 200), (96, 56, 136), (72, 40, 104)),
    "Black Belt": (None, (240, 240, 240), (240, 240, 240), (40, 40, 40)),
    "Picnicker": ((216, 88, 80), (248, 176, 72), (64, 112, 176), (176, 104, 56)),
    "Fisher": ((96, 144, 96), (88, 128, 168), (80, 88, 112), (88, 64, 48)),
    "Biker": ((64, 64, 72), (48, 48, 56), (48, 48, 56), (200, 72, 40)),
    "Beauty": (None, (232, 96, 144), (232, 96, 144), (232, 200, 104)),
    "nurse": ((248, 168, 192), (248, 200, 216), (248, 248, 248), (240, 128, 160)),
    "clerk": ((64, 112, 216), (104, 160, 232), (56, 64, 96), (104, 72, 48)),
    "mom": (None, (232, 120, 104), (120, 88, 160), (176, 88, 56)),
    "prof": (None, (248, 248, 248), (120, 104, 88), (176, 176, 184)),
    "leader": ((40, 40, 48), (208, 168, 64), (40, 40, 48), (40, 40, 48)),
    "guard": ((64, 80, 136), (64, 80, 136), (48, 56, 96), (72, 48, 32)),
    "villager": (None, (120, 168, 120), (104, 88, 72), (120, 80, 48)),
    # Team Rocket (drawn-art fallback)
    "grunt": ((48, 40, 64), (64, 56, 88), (40, 36, 52), (40, 36, 52)),
    "admin": (None, (120, 56, 152), (48, 40, 64), (200, 64, 96)),
    "boss": (None, (32, 28, 40), (32, 28, 40), (232, 232, 240)),
    "ace": ((240, 240, 248), (56, 96, 184), (40, 48, 80), (64, 48, 40)),
    # the Elite Four
    "frost": (None, (168, 216, 248), (88, 120, 184), (232, 240, 255)),
    "brutus": (None, (248, 248, 248), (40, 40, 48), (32, 32, 32)),
    "morrow": (None, (88, 56, 128), (48, 32, 72), (200, 200, 224)),
    "drakon": ((176, 48, 48), (64, 72, 152), (40, 40, 64), (200, 48, 48)),
    "champ": (None, (248, 216, 96), (240, 240, 248), (248, 232, 160)),
    "creator": ((40, 200, 160), (40, 40, 48), (40, 40, 48), (32, 32, 40)),
}


# the FireRed overworld sprite each look uses (graphics/object_events/pics/people/<name>.png)
FRLG_PEOPLE = {
    "player": "red_normal", "rival": "blue", "Youngster": "youngster", "Lass": "lass", "Bug Catcher": "bug_catcher",
    "Hiker": "hiker", "Swimmer": "swimmer_m_land", "Ace Trainer": "cooltrainer_m", "Psychic": "channeler",
    "Black Belt": "black_belt", "Picnicker": "picnicker", "Fisher": "fisher", "Biker": "biker", "Beauty": "beauty",
    "nurse": "nurse", "clerk": "clerk", "mom": "mom", "prof": "prof_oak", "leader": "cooltrainer_m",
    "guard": "policeman", "villager": "man", "grunt": "rocket_m", "admin": "rocket_f", "boss": "giovanni",
    "ace": "cooltrainer_m", "champ": "cooltrainer_f", "creator": "gba_kid", "frost": "lorelei", "brutus": "bruno",
    "morrow": "agatha", "drakon": "lance",
}
# frames in a FireRed people sheet: stand down/up/left, then two steps each for down, up, left
FRLG_FRAMES = {"down": (0, 3, 4), "up": (1, 5, 6), "left": (2, 7, 8), "right": (2, 7, 8)}


def _frlg_person(look, face, frame):
    from . import cast, frlg
    mine = cast.overworld(look)
    rules = None
    if mine:
        name, rules = mine
    else:
        name = FRLG_PEOPLE.get(look, look if isinstance(look, str) and look.islower() else None)
    if not name:
        return None
    fr = frlg.frames(f"graphics/object_events/pics/people/{name}.png", 16, 32, rules)
    if not fr:
        return None
    i = FRLG_FRAMES[face][frame]
    if i >= len(fr):
        i = FRLG_FRAMES[face][0]
    img = fr[i]
    if face == "right":
        img = pygame.transform.flip(img, True, False)
    return pygame.transform.scale_by(img, 2)


def person(look, face, frame=0, shirt=None):
    """A trainer sprite (32x64 on the canvas: 16x32 like the handhelds). face: up/down/left/right,
    frame 0 = standing, 1/2 = steps."""
    key = ("p", look, face, frame, shirt)
    if key in _cache:
        return _cache[key]
    if not shirt:
        real = _frlg_person(look, face, frame)
        if real is not None:
            _cache[key] = real
            return real
    cap, sh, pants, hair = LOOKS.get(look, LOOKS["villager"])
    if shirt:
        sh = shirt
    grids = {"down": (PLAYER_DOWN, PLAYER_DOWN_WALK), "up": (PLAYER_UP, PLAYER_UP_WALK),
             "left": (PLAYER_LEFT, PLAYER_LEFT_WALK), "right": (PLAYER_LEFT, PLAYER_LEFT_WALK)}[face]
    rows = grids[0] if frame == 0 else grids[1]
    if not cap:   # no cap: the brim line becomes hair
        rows = list(rows)
        r = rows[13]
        a, b = r.find("K"), r.rfind("K")
        rows[13] = r[:a + 1] + r[a + 1:b].replace("K", "H") + r[b:]
    capc = cap or hair
    pal = {"K": OUT, "R": capc, "r": tuple(max(0, c - 48) for c in capc), "W": (248, 248, 248) if cap else capc,
           "H": hair, "S": (248, 208, 168), "s": (224, 176, 136), "E": OUT, "B": sh,
           "b": tuple(max(0, c - 40) for c in sh), "P": pants, "p": tuple(max(0, c - 32) for c in pants),
           "G": (72, 64, 64), "Y": (232, 184, 72), "y": (200, 144, 48)}
    img = _from_grid(rows, pal)
    flip = face == "right" or (face in ("down", "up") and frame == 2)
    if flip:
        img = pygame.transform.flip(img, True, False)
    out = _scaled(img)
    _cache[key] = out
    return out


# ====================================================================== Pokemon icons (followers / party)
ICON_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/generation-viii/icons/{}.png"


def icon(pid, shiny=False):
    """A small Pokemon icon for the party screen and the walking follower. Falls back to a shrunk sprite."""
    key = ("i", pid, shiny)
    if key in _cache:
        return _cache[key]
    path = os.path.join(pokedex.SPRITE_DIR, f"icon-{pid}.png")
    img = None
    if not os.path.exists(path):
        try:
            data = pokedex.fetch(ICON_URL.format(pid), timeout=8)
            os.makedirs(pokedex.SPRITE_DIR, exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        except Exception:  # noqa: BLE001
            path = None
    if path:
        try:
            img = pygame.image.load(path).convert_alpha() if pygame.display.get_surface() else \
                pygame.image.load(path)
            r = img.get_bounding_rect()
            if r.w:
                img = img.subsurface(r).copy()
        except Exception:  # noqa: BLE001
            img = None
    if img is None or shiny:
        from .gfx import SPRITES
        base = SPRITES.base(pid, False, shiny)
        k = 30 / max(1, base.get_height())
        img = pygame.transform.scale(base, (max(1, int(base.get_width() * k)), 30))
    _cache[key] = img
    return img


def battle_sprite(pid, back=False, shiny=False, max_h=150):
    """A battle sprite scaled 2x (nearest) like the handhelds, capped to fit the screen."""
    key = ("bs", pid, back, shiny, max_h)
    if key in _cache:
        return _cache[key]
    from . import battlegfx
    real = battlegfx.mon(pid, back, shiny) if battlegfx.frlg.is_ready() else None
    if real is not None:   # the FireRed sprite itself
        _cache[key] = real
        return real
    from .gfx import SPRITES
    base = SPRITES.base(pid, back and not shiny, shiny)
    if back and shiny:
        base = SPRITES.base(pid, True, False)
    if pid >= 10000 and battlegfx.frlg.is_ready() and base.get_width() > 8:   # Megas etc. redrawn GBA-style
        dk = ("demake", pid, back, shiny)
        if dk not in _cache:
            _cache[dk] = pygame.transform.scale_by(battlegfx.demake(base), 2)
        _cache[key] = _cache[dk]
        return _cache[dk]
    k = 2.0
    if base.get_height() * k > max_h:
        k = max_h / base.get_height()
    out = pygame.transform.scale(base, (max(1, int(base.get_width() * k)), max(1, int(base.get_height() * k))))
    if not (1 <= pid <= 386 and battlegfx.frlg.is_ready()):   # the FireRed one may still be on its way
        _cache[key] = out
    return out


# ====================================================================== nicer terrain (edges that blend)
GR_DARK = (80, 160, 72)
EDGE = (176, 152, 104)


def grass2(x, y):
    """Grass with a regular little tuft pattern (like the handhelds), not random noise."""
    key = ("g2", (x * 7 + y * 3) % 4)
    if key not in _cache:
        s = pygame.Surface((TS, TS))
        s.fill(GR)
        v = key[1]
        for tx, ty in ((3 + v, 4), (11 - v, 10), (6, 13 - v % 2)):
            _px(s, tx, ty, GR2)
            _px(s, tx + 1, ty - 1, GR2)
            _px(s, tx + 2, ty, GR2)
        _px(s, (v * 5) % 16, (v * 3 + 7) % 16, GR3)
        _cache[key] = _scaled(s)
    return _cache[key]


def dirt_edged(mask, seed=0):
    """A path tile; mask = which neighbours are path too (N, E, S, W). Grass curls over the other sides."""
    key = ("de", mask, seed % 4)
    if key in _cache:
        return _cache[key]
    s = _dirt(seed % 4)
    n, e, so, w = mask
    lip = 3
    if not n:
        pygame.draw.rect(s, GR, (0, 0, 16, lip))
        for x in range(0, 16, 4):
            _px(s, x + 1, lip, GR)
            _px(s, x + 2, lip, GR)
        pygame.draw.line(s, EDGE, (0, lip + 1), (15, lip + 1))
    if not so:
        pygame.draw.rect(s, GR, (0, 16 - lip, 16, lip))
        pygame.draw.line(s, GR_DARK, (0, 16 - lip), (15, 16 - lip))
    if not w:
        pygame.draw.rect(s, GR, (0, 0, lip, 16))
        for y in range(0, 16, 4):
            _px(s, lip, y + 1, GR)
        pygame.draw.line(s, EDGE, (lip + 1, 0 if n else lip + 2), (lip + 1, 15 if so else 16 - lip - 1))
    if not e:
        pygame.draw.rect(s, GR, (16 - lip, 0, lip, 16))
        for y in range(2, 16, 4):
            _px(s, 15 - lip, y, GR)
        pygame.draw.line(s, EDGE, (15 - lip - 1, 0 if n else lip + 2), (15 - lip - 1, 15 if so else 16 - lip - 1))
    for (cx, cy, on) in ((0, 0, not n and not w), (15, 0, not n and not e), (0, 15, not so and not w),
                         (15, 15, not so and not e)):
        if on:
            pygame.draw.circle(s, GR, (cx, cy), lip + 2)
    out = _scaled(s)
    _cache[key] = out
    return out


def canopy(below_tree, above_tree, seed=0):
    """Forest: each tree's crown overlaps its neighbours so a block of trees reads as one dense canopy.
    The trunk only shows on the bottom row of a forest. Drawn 32x48 (spills 16px up into the tile above)."""
    key = ("cn", below_tree, above_tree, seed % 3)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((TS, TS + 8), pygame.SRCALPHA)
    dark, mid, light, hi = (24, 88, 48), (40, 128, 64), (72, 168, 88), (136, 208, 120)
    oy = 8
    if not below_tree:
        pygame.draw.rect(s, (96, 64, 40), (6, oy + 10, 4, 6))
        _px(s, 5, oy + 15, (72, 48, 32))
        _px(s, 10, oy + 15, (72, 48, 32))
        pygame.draw.ellipse(s, (40, 96, 48, 120), (2, oy + 13, 12, 4))
    top = oy - 6 if not above_tree else oy - 8
    pygame.draw.ellipse(s, OUT, (-1, top, 18, 20 if not below_tree else 22))
    pygame.draw.ellipse(s, dark, (0, top + 1, 16, 18 if not below_tree else 20))
    pygame.draw.ellipse(s, mid, (1, top + 1, 13, 14))
    pygame.draw.ellipse(s, light, (3, top + 2, 7, 6))
    r = _r(seed)
    for _ in range(5):
        _px(s, r.randrange(2, 14), r.randrange(top + 4, top + 15), dark)
    _px(s, 5, top + 3, hi)
    _px(s, 6, top + 3, hi)
    out = _scaled(s)
    _cache[key] = out
    return out


def water_shore(mask, frame=0):
    key = ("ws", mask, frame)
    if key in _cache:
        return _cache[key]
    s = _water(frame)
    n, e, so, w = mask
    foam = (216, 240, 248)
    if not n:
        pygame.draw.rect(s, (200, 184, 136), (0, 0, 16, 2))
        pygame.draw.line(s, foam, (0, 2), (15, 2))
    if not so:
        pygame.draw.line(s, WAT2, (0, 15), (15, 15))
    if not w:
        pygame.draw.rect(s, (200, 184, 136), (0, 0, 2, 16))
        pygame.draw.line(s, foam, (2, 0), (2, 15))
    if not e:
        pygame.draw.rect(s, (200, 184, 136), (14, 0, 2, 16))
        pygame.draw.line(s, foam, (13, 0), (13, 15))
    out = _scaled(s)
    _cache[key] = out
    return out


def tall2(frame=0, edge_top=True):
    """Tall grass: rows of pointed blades with light tips, and a dark band where it meets normal grass."""
    key = ("t2", frame, edge_top)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((TS, TS))
    s.fill(TALL2)
    for row, by in enumerate((6, 11, 16)):
        for bx in range(-2, 16, 4):
            x0 = bx + (2 if row % 2 else 0)
            sway = frame if row == 0 else 0
            pygame.draw.polygon(s, TALL1, [(x0, by), (x0 + 2 + sway, by - 7), (x0 + 4, by)])
            _px(s, x0 + 2 + sway, by - 6, TALL3)
            _px(s, x0 + 1, by - 2, (48, 128, 64))
    if edge_top:
        pygame.draw.line(s, (40, 96, 48), (0, 0), (15, 0))
    out = _scaled(s)
    _cache[key] = out
    return out


def fence():
    key = ("fence",)
    if key not in _cache:
        s = _grass(2)
        for x in (2, 13):
            pygame.draw.rect(s, OUT, (x - 1, 3, 3, 12))
            pygame.draw.rect(s, (232, 224, 208), (x, 4, 1, 10))
        for y in (5, 10):
            pygame.draw.rect(s, OUT, (0, y - 1, 16, 3))
            pygame.draw.line(s, (240, 232, 216), (0, y), (15, y))
        _cache[key] = _scaled(s)
    return _cache[key]


# ====================================================================== battle backgrounds (painted at GBA size)
def battle_bg(kind="grass"):
    """A 480x320 battle backdrop painted at 240x160 and scaled 2x: sky, clouds, far trees, field, platforms."""
    key = ("bbg", kind)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((240, 160))
    if kind in ("gym", "league"):
        wall = (152, 160, 184) if kind == "gym" else (112, 72, 120)
        s.fill(wall)
        for y in range(0, 80, 8):
            pygame.draw.line(s, tuple(c - 16 for c in wall), (0, y), (239, y))
        for x in range(0, 240, 24):
            pygame.draw.rect(s, tuple(c + 16 for c in wall), (x + 4, 10, 14, 44))
            pygame.draw.rect(s, tuple(c - 30 for c in wall), (x + 4, 54, 14, 4))
        floor = (200, 192, 168) if kind == "gym" else (184, 72, 72)
        for y in range(80, 160):
            k = (y - 80) / 80
            pygame.draw.line(s, tuple(int(c * (0.85 + 0.15 * k)) for c in floor), (0, y), (239, y))
        for y in range(84, 160, 10):
            pygame.draw.line(s, tuple(c - 20 for c in floor), (0, y), (239, y))
        plat_top, plat_side = ((216, 208, 184), (160, 152, 128)) if kind == "gym" else ((224, 200, 112),
                                                                                         (168, 136, 56))
    else:
        sky_top, sky_bot = (120, 184, 240), (216, 240, 248)
        for y in range(0, 70):
            k = y / 70
            c = tuple(int(a * (1 - k) + b * k) for a, b in zip(sky_top, sky_bot))
            pygame.draw.line(s, c, (0, y), (239, y))
        r = _r(5)
        for cx, cy, w in ((40, 16, 34), (150, 10, 44), (210, 26, 28)):   # pixel clouds
            for k in range(4):
                pygame.draw.ellipse(s, (248, 248, 248), (cx + k * w // 5 - w // 2, cy - (4 if k % 3 else 0),
                                                         w // 2, 10))
            pygame.draw.line(s, (216, 232, 248), (cx - w // 2, cy + 8), (cx + w // 2, cy + 8))
        # far hills and a tree line
        pts = [(x, 58 + int(6 * math.sin(x / 23.0))) for x in range(0, 241, 4)]
        pygame.draw.polygon(s, (128, 184, 136), pts + [(240, 80), (0, 80)])
        for x in range(-6, 246, 9):
            h = 10 + r.randrange(6)
            pygame.draw.ellipse(s, (64, 136, 80), (x, 66 - h, 12, h + 6))
            pygame.draw.ellipse(s, (88, 160, 96), (x + 2, 67 - h, 6, 4))
        # the field
        for y in range(72, 160):
            k = (y - 72) / 88
            c = (int(152 - 40 * k), int(208 - 32 * k), int(112 - 40 * k))
            pygame.draw.line(s, c, (0, y), (239, y))
        for y in range(76, 160, 7):   # mown stripes
            pygame.draw.line(s, (int(140 - (y - 72) * 0.4), int(196 - (y - 72) * 0.3), int(100 - (y - 72) * 0.4)),
                             (0, y), (239, y))
        for _ in range(60):          # tufts
            x, y = r.randrange(240), r.randrange(80, 160)
            _px(s, x, y, (96, 160, 72))
            _px(s, x + 1, y - 1, (96, 160, 72))
        plat_top, plat_side = (144, 200, 104), (104, 152, 72)
    s_plats = (plat_top, plat_side)
    _cache[("plat_cols", kind)] = s_plats
    out = _scaled(s)
    _cache[key] = out
    return out


def platform(kind="grass", mine=False):
    """The oval a Pokemon stands on in battle (yours is bigger, nearer the camera)."""
    key = ("plat", kind, mine)
    if key in _cache:
        return _cache[key]
    battle_bg(kind)
    top, side = _cache[("plat_cols", kind)]
    rx, ry = (60, 12) if mine else (48, 10)
    s = pygame.Surface((rx * 2 + 4, ry * 2 + 8), pygame.SRCALPHA)
    cx, cy = rx + 2, ry + 1
    pygame.draw.ellipse(s, OUT, (cx - rx - 1, cy - ry + 1, rx * 2 + 2, ry * 2 + 4))
    pygame.draw.ellipse(s, side, (cx - rx, cy - ry + 2, rx * 2, ry * 2 + 2))
    pygame.draw.ellipse(s, top, (cx - rx, cy - ry, rx * 2, ry * 2))
    pygame.draw.ellipse(s, tuple(min(255, c + 24) for c in top), (cx - rx + 8, cy - ry + 3, rx, ry - 2))
    r2 = _r(rx)
    for _ in range(16 if kind == "grass" else 0):
        a = r2.random() * math.tau
        px = int(cx + math.cos(a) * rx * 0.7 * r2.random())
        py = int(cy + math.sin(a) * ry * 0.6 * r2.random())
        _px(s, px, py, side)
        _px(s, px, py - 1, side)
    out = _scaled(s)
    _cache[key] = out
    return out


# ====================================================================== handheld palette (soft pastel greens)
# tones like the GBA games: minty grass, deep green foliage with yellow-green highlights, sandy paths
HG = (115, 205, 164)        # grass
HG_L = (139, 222, 189)      # grass highlight
HG_D = (65, 180, 139)       # grass tufts
LEAF_D = (57, 90, 16)       # foliage outline / darkest
LEAF = (57, 148, 49)        # foliage
LEAF_M = (131, 213, 98)     # foliage light
LEAF_L = (189, 255, 139)    # foliage highlight
SAND = (213, 197, 131)
SAND_L = (238, 230, 139)
SAND_D = (197, 172, 106)
SAND_EDGE = (172, 222, 164)  # where sand meets grass
TRUNK2 = (115, 98, 98)


def hgrass(x, y):
    """Plain grass: flat mint with a few paired tufts in a fixed rhythm."""
    key = ("hg", (x + y * 2) % 4)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((TS, TS))
    s.fill(HG)
    v = key[1]
    spots = [((2, 4), (10, 11)), ((6, 2), (12, 9)), ((3, 11), (9, 5)), ((13, 3), (5, 13))][v]
    for tx, ty in spots:
        _px(s, tx, ty, HG_D)
        _px(s, tx + 2, ty, HG_D)
        _px(s, tx + 1, ty + 1, HG_D)
        _px(s, tx, ty - 1, HG_L)
    out = _scaled(s)
    _cache[key] = out
    return out


def htall(frame=0):
    """Tall grass: leafy clumps (two rows of rounded blades) in deep and yellow greens."""
    key = ("ht", frame)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((TS, TS))
    s.fill(HG)
    for row, (by, off) in enumerate(((8, 0), (16, 4))):
        for bx in range(-4, 16, 8):
            x0 = bx + off + (frame if row == 0 else 0)
            # a clump: dark outline, mid fill, light tips
            pygame.draw.polygon(s, LEAF_D, [(x0, by), (x0 + 1, by - 6), (x0 + 3, by - 8), (x0 + 4, by - 5),
                                            (x0 + 5, by - 8), (x0 + 7, by - 6), (x0 + 8, by)])
            pygame.draw.polygon(s, LEAF, [(x0 + 1, by - 1), (x0 + 2, by - 6), (x0 + 3, by - 7), (x0 + 4, by - 4),
                                          (x0 + 5, by - 7), (x0 + 6, by - 5), (x0 + 7, by - 1)])
            _px(s, x0 + 3, by - 6, LEAF_L)
            _px(s, x0 + 5, by - 6, LEAF_M)
            _px(s, x0 + 2, by - 4, LEAF_M)
    out = _scaled(s)
    _cache[key] = out
    return out


def htall_over(frame=0):
    key = ("hto", frame)
    if key not in _cache:
        s = pygame.Surface((TS, 8), pygame.SRCALPHA)
        for bx in range(0, 16, 8):
            x0 = bx + frame
            pygame.draw.polygon(s, LEAF_D, [(x0, 8), (x0 + 1, 2), (x0 + 3, 0), (x0 + 4, 3), (x0 + 5, 0),
                                            (x0 + 7, 2), (x0 + 8, 8)])
            pygame.draw.polygon(s, LEAF, [(x0 + 1, 7), (x0 + 2, 2), (x0 + 3, 1), (x0 + 4, 4), (x0 + 5, 1),
                                          (x0 + 6, 3), (x0 + 7, 7)])
            _px(s, x0 + 3, 2, LEAF_L)
        _cache[key] = _scaled(s)
    return _cache[key]


def htree(below_tree, above_tree, seed=0):
    """A round bushy tree (16x24, spills up into the tile above): scalloped crown, light upper-left,
    dark lower-right, short trunk when nothing is below it."""
    key = ("htr", below_tree, above_tree, seed % 2)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((TS, TS + 8), pygame.SRCALPHA)
    oy = 8
    if not below_tree:
        pygame.draw.rect(s, LEAF_D, (5, oy + 10, 6, 6))
        pygame.draw.rect(s, TRUNK2, (6, oy + 10, 4, 5))
        _px(s, 7, oy + 11, (148, 131, 131))
    top = oy - 7
    h = 17 if not below_tree else 20
    # crown silhouette with bumps
    pygame.draw.ellipse(s, LEAF_D, (0, top, 16, h))
    for bx, by in ((2, top - 1), (7, top - 2), (11, top - 1)):
        pygame.draw.circle(s, LEAF_D, (bx + 2, by + 3), 3)
    pygame.draw.ellipse(s, LEAF, (1, top + 1, 14, h - 3))
    for bx, by in ((2, top), (7, top - 1), (11, top)):
        pygame.draw.circle(s, LEAF, (bx + 2, by + 3), 2)
    # light on the upper left, scallops of highlight
    pygame.draw.ellipse(s, LEAF_M, (2, top + 1, 8, 6))
    for hx, hy in ((3, top + 2), (8, top + 1), (4, top + 6)):
        _px(s, hx, hy, LEAF_L)
        _px(s, hx + 1, hy, LEAF_L)
    # shading arcs lower down
    for ax in (3, 9):
        pygame.draw.arc(s, LEAF_D, (ax, top + 6, 6, 6), 3.6, 5.8, 1)
    out = _scaled(s)
    _cache[key] = out
    return out


def hsand(mask, seed=0):
    """Sandy path; sides that touch grass get a soft two-step edge (sand -> pale green -> grass)."""
    key = ("hs", mask, seed % 3)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((TS, TS))
    s.fill(SAND)
    r = _r(seed % 3 + 40)
    for _ in range(4):
        x, y = r.randrange(2, 14), r.randrange(2, 14)
        _px(s, x, y, SAND_D)
        _px(s, x + 1, y, SAND_L)
    n, e, so, w = mask
    for on, rects in ((not n, [(0, 0, 16, 1), (0, 1, 16, 1)]), (not so, [(0, 15, 16, 1), (0, 14, 16, 1)]),
                      (not w, [(0, 0, 1, 16), (1, 0, 1, 16)]), (not e, [(15, 0, 1, 16), (14, 0, 1, 16)])):
        if on:
            pygame.draw.rect(s, HG, rects[0])
            pygame.draw.rect(s, SAND_EDGE, rects[1])
    # bumpy edge: a few grass pixels poking in
    if not n:
        for x in range(1, 16, 5):
            _px(s, x, 2, SAND_EDGE)
    if not so:
        for x in range(3, 16, 5):
            _px(s, x, 13, SAND_EDGE)
    if not w:
        for y in range(2, 16, 5):
            _px(s, 2, y, SAND_EDGE)
    if not e:
        for y in range(4, 16, 5):
            _px(s, 13, y, SAND_EDGE)
    out = _scaled(s)
    _cache[key] = out
    return out


def hflowers(frame=0, seed=0):
    key = ("hf", frame, seed % 2)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((TS, TS))
    s.fill(HG)
    petals = (248, 112, 112) if seed % 2 == 0 else (248, 248, 248)
    for fx, fy in ((4, 4), (11, 11)):
        fx += frame
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
            _px(s, fx + dx, fy + dy, petals)
        _px(s, fx, fy, (248, 216, 64))
        _px(s, fx, fy + 2, LEAF)
        _px(s, fx - 1, fy + 2, LEAF)
    out = _scaled(s)
    _cache[key] = out
    return out


def hwater(mask, frame=0):
    key = ("hw", mask, frame)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((TS, TS))
    s.fill((106, 172, 238))
    for k, y in enumerate((4, 10)):
        x0 = (frame * 2 + k * 6) % 16
        for dx in range(5):
            _px(s, (x0 + dx) % 16, y, (180, 222, 255) if 0 < dx < 4 else (90, 148, 222))
    n, e, so, w = mask
    if not n:
        pygame.draw.rect(s, SAND, (0, 0, 16, 2))
        pygame.draw.line(s, (230, 246, 255), (0, 2), (15, 2))
    if not w:
        pygame.draw.rect(s, SAND, (0, 0, 2, 16))
    if not e:
        pygame.draw.rect(s, SAND, (14, 0, 2, 16))
    if not so:
        pygame.draw.line(s, (90, 148, 222), (0, 15), (15, 15))
    out = _scaled(s)
    _cache[key] = out
    return out


def hsign():
    key = ("hsign",)
    if key not in _cache:
        s = pygame.Surface((TS, TS), pygame.SRCALPHA)
        pygame.draw.rect(s, (96, 64, 40), (7, 9, 2, 7))
        pygame.draw.rect(s, (90, 57, 65), (2, 2, 12, 9))
        pygame.draw.rect(s, (222, 172, 106), (3, 3, 10, 7))
        for y in (5, 7):
            pygame.draw.line(s, (172, 123, 74), (5, y), (10, y))
        _cache[key] = _scaled(s)
    return _cache[key]


def hitem():
    key = ("hitem",)
    if key not in _cache:
        from . import frlg
        real = frlg.sprite("graphics/object_events/pics/misc/item_ball.png")
        if real is not None:
            _cache[key] = pygame.transform.scale_by(real, 2)
            return _cache[key]
        s = pygame.Surface((TS, TS), pygame.SRCALPHA)
        pygame.draw.circle(s, (57, 57, 74), (8, 9), 5)
        pygame.draw.circle(s, (248, 248, 248), (8, 9), 4)
        pygame.draw.rect(s, (230, 82, 74), (4, 5, 9, 4))
        pygame.draw.line(s, (57, 57, 74), (4, 9), (12, 9))
        _px(s, 8, 9, (248, 248, 248))
        _px(s, 6, 6, (255, 200, 190))
        _cache[key] = _scaled(s)
    return _cache[key]


# ====================================================================== buildings, handheld style
OL = (65, 74, 106)          # navy outline (the handhelds don't use black)
GREY = (123, 123, 131)
SIDING = (205, 222, 238)
SIDING_D = (172, 189, 205)
BASE = (148, 164, 180)
GLASS = (115, 189, 246)
GLASS_L = (156, 213, 255)
GLASS_D = (98, 164, 222)
FRAME = (246, 246, 255)
DOOR = (139, 65, 82)
DOOR_L = (205, 139, 148)
ROOF_SETS = {   # (main, dark eave, mid lines, highlight)
    "coral": ((238, 148, 115), (205, 82, 74), (222, 106, 98), (255, 205, 139)),
    "center": ((230, 98, 90), (172, 57, 57), (205, 74, 74), (255, 172, 148)),
    "mart": ((98, 164, 222), (57, 98, 172), (82, 131, 197), (172, 222, 255)),
    "green": ((131, 197, 106), (57, 131, 65), (98, 172, 82), (197, 238, 156)),
    "purple": ((172, 139, 213), (106, 82, 156), (148, 115, 197), (222, 205, 246)),
    "gym": ((148, 156, 172), (82, 90, 115), (123, 131, 148), (205, 213, 222)),
    "lab": ((172, 189, 205), (106, 123, 148), (148, 164, 180), (222, 230, 238)),
    "league": ((238, 197, 90), (180, 131, 41), (222, 172, 65), (255, 238, 164)),
}


def _window(s, x, y, w=10, h=8):
    pygame.draw.rect(s, OL, (x, y, w, h))
    pygame.draw.rect(s, FRAME, (x + 1, y + 1, w - 2, h - 2))
    pygame.draw.rect(s, GLASS, (x + 2, y + 2, w - 4, h - 4))
    pygame.draw.line(s, GLASS_L, (x + 2, y + 2), (x + w - 4, y + 2))
    pygame.draw.line(s, GLASS_D, (x + 2, y + h - 3), (x + w - 3, y + h - 3))
    pygame.draw.line(s, FRAME, (x + w // 2, y + 1), (x + w // 2, y + h - 2))


def hbuilding(kind, wt, ht, door_col, accent=None, seed=0):
    key = ("hb", kind, wt, ht, door_col, accent, seed % 4)
    if key in _cache:
        return _cache[key]
    w, h = wt * TS, ht * TS
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    roof_kind = kind if kind in ROOF_SETS else ["coral", "green", "purple", "coral"][seed % 4]
    main, dark, mid, hi = ROOF_SETS[roof_kind]
    roof_h = max(12, int(h * 0.52))
    wall_top = roof_h - 1
    brick = kind == "lab"
    # walls: horizontal siding (or yellow brick for the lab), grey base strip
    pygame.draw.rect(s, OL, (1, wall_top, w - 2, h - wall_top))
    wall_c, wall_d = ((246, 238, 197), (222, 205, 123)) if brick else (SIDING, SIDING_D)
    if kind == "gym":
        wall_c, wall_d = (189, 197, 213), (148, 156, 172)
    pygame.draw.rect(s, wall_c, (2, wall_top, w - 4, h - wall_top - 1))
    for y in range(wall_top + 3, h - 3, 3):
        pygame.draw.line(s, wall_d, (2, y), (w - 3, y))
        if brick:
            for x in range(2 + (y // 3 % 2) * 4, w - 3, 8):
                _px(s, x, y - 1, wall_d)
    pygame.draw.rect(s, BASE, (2, h - 3, w - 4, 2))
    pygame.draw.line(s, OL, (1, h - 1), (w - 2, h - 1))
    # roof: outline, body with shingle rows, eave strip, ridge highlight
    pygame.draw.rect(s, OL, (0, 0, w, roof_h + 1), border_radius=3)
    pygame.draw.rect(s, main, (1, 1, w - 2, roof_h - 3), border_radius=2)
    for y in range(4, roof_h - 4, 3):
        pygame.draw.line(s, mid, (2, y), (w - 3, y))
        for x in range(3 + (y // 3 % 2) * 3, w - 3, 6):
            _px(s, x, y - 1, mid)
    pygame.draw.line(s, hi, (3, 2), (w - 4, 2))
    pygame.draw.rect(s, dark, (1, roof_h - 3, w - 2, 3))
    pygame.draw.line(s, OL, (0, roof_h), (w - 1, roof_h))
    # windows (skip where the door is)
    dx = door_col * TS
    wy = wall_top + (14 if kind in ("center", "mart") and ht >= 4 else 3)
    if wy + 8 < h - 3:
        for x in range(4, w - 12, 16):
            if abs(x + 5 - (dx + 8)) < 10:
                continue
            _window(s, x, wy)
    # the door
    dy = h - 13
    glass_door = kind in ("center", "mart", "gym", "league")
    pygame.draw.rect(s, OL, (dx + 3, dy, 10, 13))
    if glass_door:
        pygame.draw.rect(s, GLASS_L, (dx + 4, dy + 1, 8, 11))
        pygame.draw.rect(s, GLASS, (dx + 4, dy + 6, 8, 6))
        pygame.draw.line(s, OL, (dx + 8, dy + 1), (dx + 8, dy + 12))
        pygame.draw.line(s, FRAME, (dx + 5, dy + 2), (dx + 5, dy + 4))
    else:
        pygame.draw.rect(s, DOOR, (dx + 4, dy + 1, 8, 12))
        pygame.draw.line(s, DOOR_L, (dx + 5, dy + 2), (dx + 5, dy + 11))
        _px(s, dx + 10, dy + 7, (255, 205, 139))
    pygame.draw.rect(s, BASE, (dx + 2, h - 2, 12, 2))   # door step
    # signs and emblems
    cx = w // 2
    sy = max(3, roof_h // 2 - 4)
    if kind in ("center", "mart") and ht >= 4:   # the shop sign over the doors
        from . import pixelfont
        label = "POKeMON CENTER" if kind == "center" else "POKe MART"
        tw = pixelfont.width(label, 1)
        plate = pygame.Rect(dx + 8 - tw // 2 - 4, wall_top + 2, tw + 8, 10)
        pygame.draw.rect(s, OL, plate, border_radius=2)
        pygame.draw.rect(s, FRAME, plate.inflate(-2, -2), border_radius=2)
        pixelfont.draw(s, label, (plate.x + 4, plate.y + 1), (205, 74, 74) if kind == "center" else (57, 98, 172),
                       None, scale=1)
    if kind == "center":   # a ball emblem on the roof
        pygame.draw.circle(s, OL, (cx, sy + 4), 6)
        pygame.draw.circle(s, FRAME, (cx, sy + 4), 5)
        pygame.draw.rect(s, (230, 82, 74), (cx - 5, sy - 1, 11, 5))
        pygame.draw.line(s, OL, (cx - 5, sy + 4), (cx + 5, sy + 4))
        pygame.draw.circle(s, OL, (cx, sy + 4), 2)
        _px(s, cx, sy + 4, FRAME)
    elif kind == "mart" and ht < 4:
        pygame.draw.rect(s, OL, (cx - 14, sy - 2, 28, 12), border_radius=2)
        pygame.draw.rect(s, FRAME, (cx - 13, sy - 1, 26, 10), border_radius=2)
        from . import pixelfont
        pixelfont.draw(s, "MART", (cx - pixelfont.width("MART", 1) // 2, sy), (57, 98, 172), None, scale=1)
    elif kind == "gym":
        col = accent or (205, 213, 222)
        pygame.draw.rect(s, col, (2, roof_h - 6, w - 4, 3))
        pygame.draw.rect(s, OL, (cx - 10, sy - 2, 20, 11), border_radius=2)
        pygame.draw.rect(s, (82, 90, 115), (cx - 9, sy - 1, 18, 9), border_radius=2)
        pygame.draw.polygon(s, col, [(cx, sy), (cx + 4, sy + 4), (cx, sy + 7), (cx - 4, sy + 4)])
    elif kind == "league":
        for k in range(-2, 3):
            pygame.draw.polygon(s, (255, 238, 164), [(cx + k * 10 - 3, sy + 8), (cx + k * 10, sy),
                                                      (cx + k * 10 + 3, sy + 8)])
    out = _scaled(s)
    _cache[key] = out
    return out


# ====================================================================== interiors, handheld style
IN_FLOOR = {"center": ((246, 246, 205), (238, 238, 172), (230, 222, 156)),
            "mart": ((238, 246, 230), (222, 238, 213), (205, 222, 197)),
            "house": ((230, 205, 156), (222, 189, 139), (197, 164, 115)),
            "lab": ((238, 238, 246), (222, 222, 238), (205, 205, 222)),
            "gym": ((197, 205, 222), (180, 189, 205), (156, 164, 189)),
            "league": ((222, 82, 82), (205, 65, 65), (172, 49, 57))}
IN_WALL = {"center": ((246, 238, 164), (230, 139, 98)), "mart": ((230, 238, 246), (98, 164, 222)),
           "house": ((246, 230, 197), (189, 139, 98)), "lab": ((238, 238, 246), (148, 164, 180)),
           "gym": ((148, 156, 180), (90, 98, 131)), "league": ((106, 74, 131), (238, 197, 90))}
IN_OL = (82, 82, 106)


def hfloor(kind, x, y):
    key = ("hfl", kind, (x + y) % 2)
    if key not in _cache:
        a, b, line = IN_FLOOR.get(kind, IN_FLOOR["house"])
        s = pygame.Surface((TS, TS))
        s.fill(a if (x + y) % 2 == 0 else b)
        pygame.draw.line(s, line, (0, 15), (15, 15))
        pygame.draw.line(s, line, (15, 0), (15, 15))
        _px(s, 2, 2, tuple(min(255, c + 8) for c in a))
        _cache[key] = _scaled(s)
    return _cache[key]


def hwall(kind, lower):
    """Interior wall: the upper row is plain wall, the lower row has a coloured stripe and a skirting board."""
    key = ("hwl", kind, lower)
    if key not in _cache:
        c, stripe = IN_WALL.get(kind, IN_WALL["house"])
        s = pygame.Surface((TS, TS))
        s.fill(c)
        if lower:
            pygame.draw.rect(s, stripe, (0, 3, 16, 3))
            pygame.draw.rect(s, IN_OL, (0, 13, 16, 3))
            pygame.draw.line(s, tuple(max(0, v - 30) for v in c), (0, 12), (15, 12))
        else:
            pygame.draw.line(s, tuple(max(0, v - 20) for v in c), (0, 15), (15, 15))
            pygame.draw.line(s, tuple(min(255, v + 10) for v in c), (0, 0), (15, 0))
        _cache[key] = _scaled(s)
    return _cache[key]


def hfurn(kind, room="house"):
    key = ("hfu", kind, room)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((TS, TS), pygame.SRCALPHA)
    if kind in ("counter", "mcounter"):
        front = (255, 131, 115) if kind == "counter" else (98, 164, 222)
        pygame.draw.rect(s, IN_OL, (0, 2, 16, 14))
        pygame.draw.rect(s, (246, 238, 164), (0, 3, 16, 5))
        pygame.draw.rect(s, front, (0, 8, 16, 7))
        pygame.draw.line(s, (255, 255, 255), (0, 3), (15, 3))
        pygame.draw.line(s, tuple(max(0, c - 40) for c in front), (0, 14), (15, 14))
    elif kind == "machine":   # healing machine: six ball slots
        pygame.draw.rect(s, IN_OL, (1, 2, 14, 13), border_radius=2)
        pygame.draw.rect(s, (222, 230, 230), (2, 3, 12, 11), border_radius=2)
        for i in range(6):
            pygame.draw.circle(s, (180, 180, 164), (5 + (i % 3) * 3, 6 + (i // 3) * 4), 1)
        pygame.draw.rect(s, (98, 164, 222), (3, 12, 10, 1))
    elif kind == "pc":
        pygame.draw.rect(s, IN_OL, (2, 1, 12, 14), border_radius=1)
        pygame.draw.rect(s, (222, 230, 230), (3, 2, 10, 12))
        pygame.draw.rect(s, (82, 82, 106), (4, 3, 8, 6))
        pygame.draw.rect(s, (115, 189, 246), (5, 4, 6, 4))
        for x in range(4, 12, 2):
            _px(s, x, 11, (123, 123, 123))
    elif kind == "shelf":
        pygame.draw.rect(s, IN_OL, (0, 0, 16, 16))
        pygame.draw.rect(s, (189, 205, 222), (1, 1, 14, 14))
        r = _r(9)
        for row in (2, 7, 12):
            pygame.draw.line(s, (148, 164, 180), (1, row + 3), (14, row + 3))
            for x in range(2, 14, 3):
                c = r.choice([(255, 131, 115), (98, 164, 222), (255, 222, 106), (131, 213, 98), (246, 246, 255)])
                pygame.draw.rect(s, c, (x, row, 2, 3))
    elif kind == "table":
        pygame.draw.rect(s, IN_OL, (1, 3, 14, 10), border_radius=2)
        pygame.draw.rect(s, (222, 164, 98), (2, 4, 12, 6), border_radius=2)
        pygame.draw.line(s, (246, 205, 139), (3, 5), (12, 5))
        pygame.draw.rect(s, (172, 115, 65), (2, 10, 12, 2))
        pygame.draw.rect(s, IN_OL, (3, 12, 2, 3))
        pygame.draw.rect(s, IN_OL, (11, 12, 2, 3))
    elif kind == "plant":
        pygame.draw.rect(s, IN_OL, (4, 10, 8, 6), border_radius=1)
        pygame.draw.rect(s, (230, 139, 98), (5, 11, 6, 4))
        pygame.draw.circle(s, LEAF_D, (8, 6), 6)
        pygame.draw.circle(s, LEAF, (8, 6), 5)
        pygame.draw.circle(s, LEAF_M, (6, 4), 2)
        _px(s, 6, 3, LEAF_L)
    elif kind == "mat":
        pygame.draw.rect(s, IN_OL, (1, 4, 14, 10), border_radius=2)
        pygame.draw.rect(s, (205, 82, 74), (2, 5, 12, 8), border_radius=1)
        pygame.draw.rect(s, (238, 148, 115), (4, 7, 8, 4))
    elif kind == "bed":
        pygame.draw.rect(s, IN_OL, (1, 0, 14, 16), border_radius=2)
        pygame.draw.rect(s, (90, 131, 180), (2, 5, 12, 10))
        pygame.draw.rect(s, (189, 230, 255), (2, 5, 12, 2))
        pygame.draw.rect(s, (246, 246, 255), (3, 1, 10, 4), border_radius=1)
    elif kind == "tv":
        pygame.draw.rect(s, IN_OL, (1, 3, 14, 11), border_radius=1)
        pygame.draw.rect(s, (123, 123, 131), (2, 4, 12, 9))
        pygame.draw.rect(s, (115, 189, 246), (3, 5, 10, 7))
        pygame.draw.line(s, (156, 213, 255), (4, 6), (8, 6))
        pygame.draw.rect(s, IN_OL, (6, 14, 4, 2))
    elif kind == "statue":
        pygame.draw.rect(s, IN_OL, (3, 10, 10, 6))
        pygame.draw.rect(s, (189, 189, 205), (4, 11, 8, 4))
        pygame.draw.circle(s, IN_OL, (8, 6), 5)
        pygame.draw.circle(s, (222, 222, 238), (8, 6), 4)
        pygame.draw.rect(s, (230, 82, 74), (4, 3, 9, 3))
    elif kind == "books":
        pygame.draw.rect(s, IN_OL, (0, 0, 16, 16))
        pygame.draw.rect(s, (189, 139, 98), (1, 1, 14, 14))
        for row in (1, 8):
            for x in range(2, 14, 2):
                c = [(205, 82, 74), (98, 164, 222), (131, 197, 106), (238, 197, 90)][(x // 2 + row) % 4]
                pygame.draw.rect(s, c, (x, row + 1, 2, 6))
    elif kind == "sofa":
        pygame.draw.rect(s, IN_OL, (0, 3, 16, 12), border_radius=3)
        pygame.draw.rect(s, (90, 131, 180), (1, 4, 14, 10), border_radius=3)
        pygame.draw.rect(s, (189, 230, 255), (2, 5, 12, 4), border_radius=2)
    out = _scaled(s)
    _cache[key] = out
    return out
