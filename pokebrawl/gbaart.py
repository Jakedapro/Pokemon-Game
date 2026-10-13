"""Pixel art for Adventure mode, drawn in code: 16x16 tiles, buildings, room interiors and trainer sprites.
Everything is painted at 1x and scaled 2x with nearest-neighbour onto the 480x320 canvas (a GBA screen at 2x).
None of it is copied from any game - it's original art in a handheld style."""
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
}


def person(look, face, frame=0, shirt=None):
    """A trainer sprite (32x64 on the canvas: 16x32 like the handhelds). face: up/down/left/right,
    frame 0 = standing, 1/2 = steps."""
    key = ("p", look, face, frame, shirt)
    if key in _cache:
        return _cache[key]
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
    from .gfx import SPRITES
    base = SPRITES.base(pid, back and not shiny, shiny)
    if back and shiny:
        base = SPRITES.base(pid, True, False)
    k = 2.0
    if base.get_height() * k > max_h:
        k = max_h / base.get_height()
    out = pygame.transform.scale(base, (max(1, int(base.get_width() * k)), max(1, int(base.get_height() * k))))
    _cache[key] = out
    return out
