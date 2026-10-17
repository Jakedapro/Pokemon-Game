"""Adventure mode's overworld, GBA style: a 480x320 pixel screen (15x10 tiles of 32px), smooth grid walking,
running with X held, your lead Pokemon following you, doors into Pokemon Centers / Marts / houses / gyms,
trainers who spot you, wild Pokemon in tall grass and the START menu.

Controls: arrows/WASD move, Z/Enter/Space = A (talk, confirm), X/Esc = B (back, hold to run), Enter = START."""
import math
import random

import pygame

from . import adventure as A
from . import gbaart as G
from . import gbaui as U
from . import pixelfont as F
from . import profile
from . import story as S
from . import fieldmap
from .app import Scene
from .audio import AUDIO
from .gfx import PIXEL

T = G.T
VW, VH = PIXEL
OUT_WALK = set('.,"=_')
DOORS = {"C": "center", "M": "mart", "G": "gym", "D": "house", "P": "lab", "L": "league"}
BODY = {"c": "center", "m": "mart", "g": "gym", "h": "house", "p": "lab", "l": "league"}
DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
OPP = {"up": "down", "down": "up", "left": "right", "right": "left"}
FURN = {"c": "counter", "k": "mcounter", "m": "machine", "p": "pc", "s": "shelf", "t": "table", "f": "plant",
        "x": "mat", "b": "bed", "v": "tv", "o": "statue", "r": "books", "a": "sofa"}


def buildings_of(area):
    """Each connected block of building letters -> (kind, x, y, w, h, door x)."""
    rows = area["rows"]
    h = len(rows)
    seen, out = set(), []
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            low = ch.lower()
            if (x, y) in seen or ch == "S" or not (low in BODY or ch in DOORS):
                continue
            letter = low if low in BODY else "h"
            stack, cells = [(x, y)], []
            while stack:
                cx, cy = stack.pop()
                if (cx, cy) in seen or not (0 <= cy < h and 0 <= cx < A.COLS):
                    continue
                c2 = rows[cy][cx]
                l2 = c2.lower() if c2.lower() in BODY else ("h" if c2 == "D" else None)
                if l2 != letter:
                    continue
                seen.add((cx, cy))
                cells.append((cx, cy))
                stack += [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]
            xs, ys = [c[0] for c in cells], [c[1] for c in cells]
            door = next((cx for cx, cy in cells if rows[cy][cx] in DOORS), xs[0])
            out.append((BODY[letter], min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1,
                        door - min(xs)))
    return out


class OverworldScene(Scene):
    canvas_size = PIXEL

    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        A.migrate(game)       # older saves move onto the 18-gym map
        A.use_options(game)   # difficulty, text speed, sound, the player's look, the randomizer
        self.world = A.World(app.dex)
        self.rng = random.Random()
        self.t = 0.0
        self.text = None          # gbaui.TextBox
        self.move = None          # (from x, y, to x, y, progress)
        self.step = 0
        self.trail = []
        self.battle = None
        self.trans = None
        self.fade = 1.0           # fade-in from black
        self.warp = None          # door fade: {"t", "go": callable}
        self.cool = 3
        self.banner = 0.0
        self.emote = None
        self.walking_npc = None
        self.menu = None
        self.choice = None        # yes/no prompts
        self.healing = None
        self.buttons = []
        from . import frlg
        frlg.start(fieldmap.warm)
        self.cur = None           # the area or room being shown
        self.field = None         # FireRed-tile layers (under, over) for it, when available
        self.field_missing = []
        g = game
        if g.get("room"):
            r = g["room"]
            self._load_room(r["kind"], r["area"], tuple(r["door"]), g["x"], g["y"])
        else:
            self._load_area(g["area"], g["x"], g["y"], first=True)
            ch = self.tile(g["x"], g["y"])
            if ch not in OUT_WALK and ch not in DOORS:   # an old save on a map that has changed since
                area, x, y = g["center"]
                self._load_area(area, x, y, first=True)

    # ------------------------------------------------------------------ places
    def _load_area(self, index, x, y, first=False):
        g = self.game
        self.move = None   # a step that was under way belongs to the map we just left
        g["room"] = None
        g["area"], g["x"], g["y"] = index, x, y
        self.cur = self.world.areas[index]
        self._roll_echo(index)
        self.blds = buildings_of(self.cur)
        self._set_field(("area", index), lambda: fieldmap.render_area(self.cur, self.blds))
        self._refresh()
        self.trail = [(x, y + 1)]
        self.banner = 0.0
        AUDIO.music(self.cur["music"])
        if not first:
            A.save(g)

    # ------------------------------------------------------------------ the Mega Radar and digging
    def _dig_sites(self):
        from . import riftdex
        r = self.cur.get("route")
        if self.inside or not r:
            return []
        dug = self.game.get("dug", [])
        return [s for s in riftdex.dig_sites(self.app.dex, self.cur, r) if s[0] not in dug]

    def _use_radar(self):
        if self.inside or not self.cur.get("route"):
            self.say(["The MEGA RADAR only picks up signals out on the routes."])
            return
        sites = self._dig_sites()
        if not sites:
            self.say(["The MEGA RADAR is quiet. There's nothing left buried on this route."])
            return
        self.radar = 30.0
        self.radar_ping = 0.0
        AUDIO.play("select")
        self.say([f"The MEGA RADAR switched on! {len(sites)} signal{'s' if len(sites) > 1 else ''} on this route.",
                  "Follow the arrow. When it's going wild, stand on the spot and press Z to dig!"])

    def _nearest_site(self):
        g = self.game
        sites = self._dig_sites()
        if not sites:
            return None, None
        s = min(sites, key=lambda s: abs(s[1] - g["x"]) + abs(s[2] - g["y"]))
        return s, abs(s[1] - g["x"]) + abs(s[2] - g["y"])

    def _radar_beep(self, dt):
        s, d = self._nearest_site()
        if s is None:
            return
        self.radar_ping = getattr(self, "radar_ping", 0.0) - dt
        if self.radar_ping <= 0 and self.text is None:
            AUDIO.play("click", 0.25 if d > 6 else 0.5)
            self.radar_ping = max(0.15, min(1.6, d * 0.1))

    def _dig(self, site):
        from .mining import MiningScene
        self.radar = 0
        self.app.push(MiningScene(self.app, self.game, site, on_done=lambda how: self._refresh()))

    def _roll_echo(self, index):
        """Sealed rifts flicker open again now and then: each visit to a route whose rift you sealed has a chance
        of an echo rift with a wild Mega inside (caught ones are Rift-Born)."""
        g = self.game
        r = self.cur.get("route")
        if (g.get("echo") or {}).get("area") == index:
            return
        g.pop("echo", None)
        if not (r and g.get("keystone") and S.has(g, f"rift_{r}")) or self.rng.random() > 0.35:
            return
        pool = S.echo_species(self.app.dex)
        if not pool:
            return
        x, y = S._rift_spot(self.cur, r + 5000 + self.rng.randrange(1000))
        g["echo"] = {"area": index, "pid": self.rng.choice(pool), "lv": A.World.route_levels(r)[1] + 3, "x": x, "y": y}

    def _set_field(self, key, make):
        """The FireRed-tile drawing of this place (cached), or None to use the drawn art."""
        cache = self.__dict__.setdefault("_fields", {})
        if key not in cache:
            try:
                cache[key] = make() if fieldmap.available() else None
            except Exception:
                cache[key] = None
        f = cache[key]
        self.field = (f[0], f[1]) if f else None
        self.field_missing = f[2] if f and len(f) > 2 else []

    def _load_room(self, kind, area_index, door, x=None, y=None):
        g = self.game
        self.move = None
        self.cur = A.room(self.world, kind, area_index, door)
        self.blds = []
        self.field, self.field_missing = None, []
        real = None
        if fieldmap.available():
            try:
                real = fieldmap.room(kind, area_index, self.world, door)
            except Exception:
                real = None
        if real:
            self._realize(real, kind, area_index)
            self.field = real["field"]
            if x is None:
                x, y = real["entry"]
        if x is None:
            x = 7
        if y is None:
            y = len(self.cur["rows"]) - 1
        g["room"] = {"kind": kind, "area": area_index, "door": list(door)}
        self._refresh()
        g["area"] = area_index
        g["x"], g["y"], g["face"] = x, y, "up"
        self.trail = [(x, y)]
        AUDIO.music(self.cur["music"])

    def _realize(self, real, kind, area_index):
        """Moves this room's people to where they stand in the real interior."""
        cur = dict(self.cur)
        cur["rows"] = real["rows"]
        spots = real["spots"]
        npcs = [dict(n) for n in cur["npcs"]]
        people = list(spots.get("people", []))
        trainer_spots = list(spots.get("trainers", []))
        out = []
        for n in npcs:
            k = n["kind"]
            if k in ("nurse", "clerk") and spots.get(k):
                n["x"], n["y"], n["face"] = spots[k][0][:3]
            elif k in ("leader", "prof", "champion") and spots.get("leader"):
                n["x"], n["y"], n["face"] = spots["leader"][0][:3]
                if k == "leader":
                    n["look"] = f"leader{n.get('gym', 0)}"   # our own leaders (cast.py)
            elif k == "trainer":
                if not trainer_spots:
                    continue
                sx, sy, face, gfx = trainer_spots.pop(0)
                n["x"], n["y"], n["face"] = sx, sy, face
                n["look"] = n.get("look") or gfx
            elif people:
                sx, sy, face, gfx = people.pop(0)
                n["x"], n["y"], n["face"] = sx, sy, face
                n["look"] = gfx
            out.append(n)
        if kind == "gym" and trainer_spots:   # the real gym has more trainers: fill their spots too
            k = self.world.areas[area_index].get("town", 1) - 1
            town, leader, typ, ace, *_ = A.GYMS[k]
            rng = random.Random(900 + k)
            have = sum(1 for n in out if n["kind"] == "trainer")
            taken = {n["name"].split()[-1] for n in out if n["kind"] == "trainer"}
            names = [nm for nm in rng.sample(A.TRAINER_NAMES, 8) if nm not in taken]
            classes = A.GYM_CLASSES.get(typ, ["Ace Trainer"])
            extra = max(0, A.gym_trainer_count(k) - have)   # later Gyms have more trainers before the leader
            for j, (sx, sy, face, gfx) in enumerate(trainer_spots[:extra]):
                team = self.world.team_for([typ], ace - 7 + j, 1 + (k > 2) + (k > 5), rng)
                cls = classes[(j + have) % len(classes)]
                out.append({"id": f"gym{k}-x{j}", "kind": "trainer", "x": sx, "y": sy, "face": face,
                            "name": f"{cls} {names[j]}", "cls": cls, "look": cls,
                            "team": team, "sight": 4, "intro": f"{leader} won't have to lift a finger against you!",
                            "lose": f"Fine... go on and face {leader}.", "money": 40 * ace})
        cur["npcs"] = out
        self.cur = cur

    def _exit_room(self):
        r = self.game["room"]
        dx, dy = r["door"]
        self._load_area(r["area"], dx, dy + 1)
        self.game["face"] = "down"

    @property
    def inside(self):
        return self.cur.get("kind") == "room"

    def rows(self):
        return self.cur["rows"]

    def tile(self, x, y):
        rows = self.rows()
        if 0 <= y < len(rows) and 0 <= x < len(rows[y]):
            return rows[y][x]
        return "#"

    def _mask(self, x, y, same):
        """Which neighbours (N, E, S, W) are the same kind of tile - for edges that blend."""
        def ok(xx, yy):
            if not (0 <= yy < len(self.rows())):
                return True     # map edges continue off-screen
            if not (0 <= xx < len(self.rows()[0])):
                return True
            return self.rows()[yy][xx] in same
        return (ok(x, y - 1), ok(x + 1, y), ok(x, y + 1), ok(x - 1, y))

    def _refresh(self):
        """The people and items here: the map's own plus the story's (they change as flags change)."""
        g = self.game
        if self.inside:
            r = g["room"]
            extra = S.npcs_for(self.world, ("room", r["kind"], r["area"], tuple(r["door"])), g)
            base = [n for n in self.cur["npcs"] if n["kind"] not in ("champion",) or not extra]
            self.items, self.hidden = [], []
        else:
            extra = S.npcs_for(self.world, g["area"], g)
            base = self.cur["npcs"]
            self.items = list(self.cur.get("items", [])) + S.route_extras(self.world, g["area"], g)
            self.hidden = S.hidden_items(self.world, g["area"])
        spots = {(n["x"], n["y"]) for n in extra if not isinstance(n.get("x"), tuple)}
        self.npcs = [n for n in base if (n["x"], n["y"]) not in spots]   # the story's people take their place
        for n in extra:
            if isinstance(n.get("x"), tuple):
                n["x"], n["y"] = n["x"]
            if not n.get("fixed"):
                n["x"], n["y"] = self._free_spot(n["x"], n["y"])
            self.npcs.append(n)

    def _free_spot(self, x, y):
        """The nearest open ground to (x, y): story people never stand inside a wall, tree or each other."""
        walk = "_" if self.inside else OUT_WALK
        taken = ({(n["x"], n["y"]) for n in self.npcs} | {(i["x"], i["y"]) for i in self.items} |
                 {(self.game["x"], self.game["y"])})
        rows = self.rows()
        best = None
        for yy in range(len(rows)):
            for xx in range(len(rows[yy])):
                if rows[yy][xx] in walk and (xx, yy) not in taken:
                    d = abs(xx - x) * 1.01 + abs(yy - y)
                    if best is None or d < best[0]:
                        best = (d, xx, yy)
        return (best[1], best[2]) if best else (x, y)

    def npc_at(self, x, y):
        for n in self.npcs:
            if (n["x"], n["y"]) == (x, y):
                return n
        return None

    def item_at(self, x, y):
        for it in self.items:
            if (it["x"], it["y"]) == (x, y) and it["id"] not in self.game["picked"]:
                return it
        return None

    def walkable(self, x, y):
        ch = self.tile(x, y)
        ok = ch in A.ROOM_WALK if self.inside else (ch in OUT_WALK or ch in DOORS)
        return ok and not self.npc_at(x, y) and not self.item_at(x, y)

    # ------------------------------------------------------------------ messages
    def say(self, lines, then=None, speaker=""):
        self.text = U.TextBox(lines if isinstance(lines, list) else [lines], then, speaker=speaker)

    # ------------------------------------------------------------------ update
    def update(self, dt):
        if self.app.stack[-1] is not self:
            return
        self.t += dt
        if not self.__dict__.get("_had_field") and fieldmap.available():   # the graphics just finished downloading
            self._had_field = True
            self.__dict__["_fields"] = {}
            if not self.inside:
                self._set_field(("area", self.game["area"]), lambda: fieldmap.render_area(self.cur, self.blds))
        g = self.game
        g["playtime"] = g.get("playtime", 0.0) + dt
        if g.pop("_radar", None):
            self._use_radar()
        if getattr(self, "radar", 0) > 0:
            self.radar -= dt
            self._radar_beep(dt)
        self.banner += dt
        self.fade = max(0.0, self.fade - dt * 3)
        AUDIO.music(self.cur["music"])
        if self.battle is not None:
            s, self.battle = self.battle, None
            self._after_battle(s)
            return
        if self.warp is not None:
            self.warp["t"] += dt
            if self.warp["t"] >= 0.25 and not self.warp.get("done"):
                self.warp["done"] = True
                self.warp["go"]()
                self.fade = 1.0
            if self.warp["t"] >= 0.3:
                self.warp = None
            return
        if self.trans is not None:
            self.trans["t"] += dt
            if self.trans["t"] >= 1.2:
                start, self.trans = self.trans["start"], None
                start()
            return
        if self.healing is not None:
            self.healing -= dt
            if self.healing <= 0:
                self.healing = None
                self._heal_done()
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
        if self.text is not None:
            self.text.update(dt)
            if self.text.done:
                self.text = None
            return
        if self.choice is not None:
            self.choice["q"].update(dt)
            return
        if self.menu is not None:
            return
        if self._look_around(dt):
            return
        if self.move is not None:
            fx, fy, tx, ty, p = self.move
            keys = pygame.key.get_pressed()
            run = keys[pygame.K_x] or keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
            p += dt * (2.2 if getattr(self, "jumping", False) else 8.0 if run and not self.inside else 4.0)
            if p >= 1:
                self.move = None
                self.jumping = False
                g["x"], g["y"] = tx, ty
                self._carry = min(p - 1, 0.5)   # keep walking without losing the leftover bit of this frame
                self._arrived(tx, ty)
                if self.move is None and self.text is None and self.trans is None:
                    self._held_move()
                self._carry = 0.0
            else:
                self.move = (fx, fy, tx, ty, p)
            return
        self._held_move()

    def _held_move(self):
        keys = pygame.key.get_pressed()
        for k, d in U.DIR_KEYS.items():
            if keys[k]:
                self._try_move(d)
                return

    def _try_move(self, d):
        if self.warp is not None:   # a door / map change / blackout is already taking you somewhere
            return
        g = self.game
        g["face"] = d
        dx, dy = DIRS[d]
        x, y = g["x"], g["y"]
        nx, ny = x + dx, y + dy
        rows = self.rows()
        if self.inside and self.tile(x, y) == "x" and d == "down":
            if not g["party"]:   # FireRed: Oak won't let you leave without a Pokemon
                self.say(["Wait! Don't go out without a Pokemon of your own!",
                          "Wild Pokemon live in the tall grass. Choose one from the table first."],
                         speaker="Prof. Oak")
                return
            AUDIO.play("ball", 0.3)
            self.warp = {"t": 0.0, "go": self._exit_room}
            return
        if ny < 0 or ny >= len(rows):
            if not self.inside:
                self._edge(nx, ny)
            return
        if d == "down" and not self.inside and self.tile(nx, ny) == "v":   # hop down a ledge
            if self.walkable(nx, ny + 1):
                AUDIO.play("click", 0.5)
                self.move = (x, y, nx, ny + 1, getattr(self, "_carry", 0.0))
                self.jumping = True
            return
        if not self.walkable(nx, ny):
            return
        self.jumping = False
        self.move = (x, y, nx, ny, getattr(self, "_carry", 0.0))
        self.step = 1 - self.step
        self.trail.append((x, y))
        self.trail = self.trail[-3:]

    def _edge(self, nx, ny):
        i = self.game["area"]
        area = self.cur
        if ny < 0:
            if area["kind"] == "town" and area.get("town", 0) >= 1:
                need = area["town"]
                if len(self.game["badges"]) < need and need <= len(A.GYMS):
                    badge = A.GYMS[need - 1][6]
                    self.say([f"Sorry! Only trainers with the {badge} may go this way.",
                              f"The Gym is right here in {area['name']}."], speaker="Guard")
                    return
            if i + 1 < len(self.world.areas):
                nxt = self.world.areas[i + 1]
                y = len(nxt["rows"]) - 1
                x = self._landing(nxt, nx, y)
                self.warp = {"t": 0.0, "go": lambda: self._load_area(i + 1, x, y)}
        elif i > 0:
            x = self._landing(self.world.areas[i - 1], nx, 0)
            self.warp = {"t": 0.0, "go": lambda: self._load_area(i - 1, x, 0)}

    @staticmethod
    def _landing(area, x, y):
        """Where you come out on the next map's edge: the same column if you can stand there, otherwise the
        nearest spot you can (towns are open all along their edges, routes only along the road - walking off a
        town's corner used to drop you inside the trees, stuck for good)."""
        row = area["rows"][y]
        if 0 <= x < len(row) and row[x] in OUT_WALK:
            return x
        cands = [c for c, ch in enumerate(row) if ch in OUT_WALK]
        return min(cands, key=lambda c: abs(c - x)) if cands else x

    def _arrived(self, x, y):
        ch = self.tile(x, y)
        self.game["steps"] = self.game.get("steps", 0) + 1
        if not self.inside and ch in DOORS:
            kind = DOORS[ch]
            area = self.game["area"]
            AUDIO.play("ball", 0.3)
            self.warp = {"t": 0.0, "go": lambda: self._load_room(kind, area, (x, y))}
            return
        if self._trainer_spots():
            return
        self.cool -= 1
        if ch == '"' and self.cur.get("kind") == "route" and self.cool <= 0 and self.rng.random() < 0.1:
            self._wild()

    # ------------------------------------------------------------------ talking
    def interact(self):
        if not self.inside and "mega-radar" in self.game.get("bag", {}):
            here = next((s for s in self._dig_sites() if (s[1], s[2]) == (self.game["x"], self.game["y"])), None)
            if here:
                self.say(["The MEGA RADAR is going wild! Something's buried right under your feet!",
                          "You dug down and broke into a hidden cave..."], lambda: self._dig(here))
                return
        dx, dy = DIRS[self.game["face"]]
        x, y = self.game["x"] + dx, self.game["y"] + dy
        n = self.npc_at(x, y)
        if n is None and self.tile(x, y) in "ck":   # talk across a counter
            n = self.npc_at(x + dx, y + dy)
        if n:
            n["face"] = OPP[self.game["face"]]
            self._talk(n)
            return
        it = self.item_at(x, y)
        if it:
            self._pick(it)
            return
        for h in self.hidden:   # the hidden items you only find by checking the right spot
            if (h["x"], h["y"]) == (x, y) and h["id"] not in self.game["picked"]:
                self.game["picked"].append(h["id"])
                self.game["bag"][h["item"]] = self.game["bag"].get(h["item"], 0) + 1
                AUDIO.play("catch", 0.6)
                self.say(["There's something hidden here...", f"{self.game['name']} found a "
                          f"{A.SHOP.get(h['item'], (h['item'],))[0]}!"])
                return
        ch = self.tile(x, y)
        if ch == "S" and not self.inside:
            self._sign()
        elif self.inside and ch == "p":
            from .adventure_ui import BoxScene
            self.say([f"{self.game['name']} booted up the PC.", "Accessed the POKeMON STORAGE SYSTEM."],
                     lambda: self.app.push(BoxScene(self.app, self.game)))
        elif self.inside and ch in "sr":
            self.say(["It's crammed full of stuff."])
        elif self.inside and ch == "v":
            self.say(["There's a movie on TV. Four kids are walking along a railroad track..."])

    def _sign(self):
        a = self.cur
        t = a.get("town")
        if t:
            if t <= len(A.GYMS):
                _, leader, typ, *_ = A.GYMS[t - 1]
                self.say([f"{a['name'].upper()}", f"Gym Leader: {leader.upper()} - the {typ.title()} type expert!"])
            else:
                self.say(["POKeMON LEAGUE", "Only the strongest trainers may enter."])
            return
        self.say(["ROOTLEAF TOWN", "Where every journey begins."])

    def _talk(self, n):
        g = self.game
        k = n["kind"]
        if k == "nurse":
            self.say(["Welcome to our Pokemon Center!", "We restore your tired Pokemon to full health.",
                      "We'll take your Pokemon for a few seconds."], self._start_heal)
        elif k == "clerk":
            from .adventure_ui import MartScene
            self.say(["Hi there! May I help you?"], lambda: self.app.push(MartScene(self.app, g)))
        elif k == "prof" and not g["party"]:
            self.say(["Those three Poke Balls on the table each hold a Pokemon.",
                      "Go on - check them and choose your partner!"], speaker="Prof. Oak")
        elif k == "ball":
            self._starter_ask(n)
        elif k == "prof":
            c = len(g["caught"])
            self.say(["Oak: Ah, you're back!", f"Your Pokedex has {c} Pokemon caught.",
                      "Amazing work!" if c > 40 else "There are many more out there. Keep it up!"],
                     speaker="Prof. Oak")
        elif k == "trainer":
            if n["id"] in g["beaten"]:
                self.say([n["lose"]], speaker=n["name"])
            else:
                self._challenge(n)
        elif k == "leader":
            gi = n["gym"]
            town, leader, typ, ace, intro, lose, badge = A.GYMS[gi]
            if badge in g["badges"]:
                self.say([f"{leader}: You earned that {badge}. Go on - the League is waiting!"])
                return
            team = self.world.gym_team(gi)
            trainer = {"name": f"Leader {leader}", "leader": leader, "id": n["id"], "lose": lose,
                       "money": 100 * ace, "badge": badge, "gym": gi, "look": f"leader{gi}"}
            self.say([f"I'm {leader}, the {town} Gym Leader!", intro],
                     lambda: self._battle(team, "gym", trainer), speaker=leader)
        elif k == "champion":
            if len(g["badges"]) < len(A.GYMS):
                self.say(["Come back when you have all 18 badges."], speaker=CHAMP_NAME)
                return
            name, lvl, intro, lose = A.CHAMPION
            trainer = {"name": f"Champion {name}", "leader": name, "id": "champion", "lose": lose,
                       "money": 200 * lvl, "champion": True, "look": "rival"}
            self.say([intro], lambda: self._battle(self.world.champion_team(), "champion", trainer), speaker=name)
        elif k in ("story", "static", "rift"):
            self.run_script(n.get("script", []), n)
        elif k == "quest":
            self.run_script(S.quest_script(g, self.app.dex, n["quest"]), n)
        else:
            if n.get("heal"):
                self.say(n["lines"] + ["You and your Pokemon took a good rest."], self._heal_all, speaker=n["name"])
                return
            talks = g.setdefault("talks", {})   # easter egg: keep talking to people...
            talks[n["id"]] = talks.get(n["id"], 0) + 1
            if talks[n["id"]] == 6 and not S.has(g, "chatterbox"):
                S.set_flag(g, "chatterbox")
                self.run_script([("say", n.get("name", ""), ["...You REALLY like talking to me, huh?",
                                                              "Fine, fine. Take this and go train!"]),
                                 ("give", "rare-candy", 1)], n)
                return
            self.say(n["lines"], speaker=n.get("name", ""))

    # ------------------------------------------------------------------ the first Pokemon
    def _starter_ask(self, n):
        g = self.game
        e = self.app.dex.all[n["pokemon"]]
        if g["party"]:
            self.say(["That's Prof. Oak's last Pokemon. It's staying here in the lab."])
            return
        AUDIO.cry(e["id"], 0.7)
        self.choice = {"menu": U.Menu([("yes", "YES"), ("no", "NO")]), "pid": e["id"],
                       "q": U.TextBox([f"So, {g['name'].upper()}, you want the {e['types'][0].upper()} Pokemon, "
                                       f"{e['name'].upper()}?"])}

    def _choice_handle(self, ev, pos):
        c = self.choice
        q = c["q"]
        if q.shown < q._len():
            if U.is_a(ev) or U.is_b(ev):
                q.shown = q._len()
            return
        k = c["menu"].handle(ev, pos)
        if k == "yes":
            self.choice = None
            self._take_starter(c["pid"])
        elif k in ("no", "back"):
            self.choice = None

    def _take_starter(self, pid):
        g = self.game
        dex = self.app.dex
        trio = A.starters(dex)
        mon = A.make_mon(dex, dex.all[pid], 5, self.rng, origin="Rootleaf Town",
                         shiny=self.rng.randrange(A.SHINY_ODDS) == 0)
        g["party"] = [mon]
        g["starter"] = pid
        for lst in (g["seen"], g["caught"]):
            if pid not in lst:
                lst.append(pid)
        rival = dex.all[A.rival_starter(dex, pid)] if pid in trio else None
        nm = A.name_of(dex, mon).upper()
        AUDIO.play("win")
        AUDIO.cry(pid, 1.0)
        got = [f"{g['name'].upper()} received the {nm} from PROF. OAK!"]
        if mon.get("shiny"):
            got.insert(0, f"...Wait, it's sparkling! It's a SHINY {nm}!")
        steps = [("say", "Prof. Oak", ["This Pokemon is really energetic!"]), ("say", "", got)]
        if rival:
            steps += [("say", S.RIVAL, ["I'll take this one, then!"]),
                      ("say", "", [f"{S.RIVAL.upper()} received the {rival['name'].upper()} from PROF. OAK!"])]
        steps += [("say", S.RIVAL, [f"Wait, {g['name']}! Let's check out our Pokemon!", "Come on, I'll take you on!"]),
                  ("battle", "rival1"),
                  ("ifwon", [("say", S.RIVAL, ["WHAT? Unbelievable! I picked the wrong Pokemon!"])],
                   [("say", S.RIVAL, ["Yeah! Am I great or what?"])]),
                  ("say", S.RIVAL, ["Okay! I'll make my Pokemon fight to toughen it up!",
                                    f"{g['name']}! Gramps! Smell you later! See you at the World Tournament!"]),
                  ("flag", "rival1"), ("heal",),
                  ("say", "Prof. Oak", ["...That boy. He's so much like his father it hurts sometimes."]),
                  ("say", "Prof. Oak", [f"{g['name']}, take these for your journey.",
                                          "Poke Balls catch wild Pokemon, and Potions heal them."]),
                  ("give", "poke-ball", 5), ("give", "potion", 3),
                  ("say", "Prof. Oak", ["Catch Pokemon in the tall grass on ROUTE 1, north of town.",
                                          "The first Gym is in PEBBLECREST CITY. Off you go!"])]
        A.save(g)
        self._refresh()   # both balls leave the table
        self.run_script(steps)

    # ------------------------------------------------------------------ story scripts
    def run_script(self, steps, npc=None):
        self.script = list(steps)
        self.script_npc = npc
        self._step()

    def _step(self):
        g = self.game
        dex = self.app.dex
        if not getattr(self, "script", None):
            self.script = None
            self._refresh()
            A.save(g)
            return
        st = self.script.pop(0)
        op = st[0]
        if op == "say":
            speaker, lines = st[1], st[2]
            self.say(lines, self._step, speaker=speaker)
        elif op == "battle":
            team, trainer = S.battle_team(self.world, g, st[1])
            trainer = dict(trainer, id=st[1])
            if st[1].startswith(("e4_", "final", "creator")):
                trainer["arena"] = "league"
            if st[1] == "rival1":
                trainer["practice"] = True   # the first battle goes on win or lose
            self._battle(team, "story", trainer, then=self._step)
        elif op == "ifcaught":
            caught = bool((getattr(self, "last_battle", None) or {}).get("caught"))
            self.script[0:0] = list(st[1] if caught else st[2])
            self._step()
        elif op == "ifwon":   # ("ifwon", steps if you won the last battle, steps if you lost)
            won = bool((getattr(self, "last_battle", None) or {}).get("won"))
            self.script[0:0] = list(st[1] if won else st[2])
            self._step()
        elif op == "gift":   # a Pokemon that joins you
            _, species, level = st
            mon = A.make_mon(dex, dex.all[species], level, self.rng, shiny=self.rng.randrange(32) == 0)
            where = A.add_caught(g, dex, mon)
            AUDIO.play("win")
            AUDIO.cry(species, 0.9)
            nm = A.name_of(dex, mon)
            lines = [f"{nm} joined your team!" if where != "box" else f"{nm} was sent to the Box!"]
            if mon.get("shiny"):
                lines.insert(0, f"...Wait, its fur is shimmering! It's a SHINY {nm.upper()}!")
            self.say(lines, self._step)
        elif op == "rift":   # a raging Mega Pokemon inside a rift
            _, fid, level = st
            form = dex.all[fid]
            foe = A.make_mon(dex, dex.all[form["species"]], level, self.rng, shiny=False)
            foe["species"] = fid
            from .riftdex import ANOMALIES
            npc = getattr(self, "script_npc", None) or {}
            self._battle([foe], "wild", {"rift": True, "ai": "insane", "name": f"Wild {form['name']}",
                                         "anomaly": self.rng.choice(sorted(ANOMALIES)), "echo": npc.get("echo"),
                                         "route": self.cur.get("route")}, then=self._step)
        elif op == "riftboss":   # a raging legendary inside a rift that won't collapse (the finale)
            _, key, level, anomaly = st
            e = dex.get(key)
            foe = A.make_mon(dex, dex.all[e["species"]] if e.get("species") else e, level, self.rng, shiny=False)
            foe["species"] = e["id"]
            self._battle([foe], "wild", {"rift": True, "ai": "insane", "name": e["name"], "anomaly": anomaly,
                                         "turns": 99, "boss": True}, then=self._step)
        elif op == "tower":
            self._tower()
        elif op == "journey":   # the Starter's Journey cutscene; the script goes on once it's over
            from .journey import JourneyScene, partner
            mon = partner(g, dex)
            A.save(g)
            if mon:
                self.app.push(JourneyScene(self.app, g, mon))
            self._step()
        elif op == "credits":
            from .adventure_ui import Credits
            A.save(g)
            self.app.push(Credits(self.app, g))
            self._step()
        elif op == "pay":
            if g["money"] < st[1]:
                self.script = None
                self.say([f"You need {st[1]} coins. You have {g['money']}."])
                return
            g["money"] -= st[1]
            AUDIO.play("buy", 0.6)
            self._step()
        elif op == "purify":
            bad = g.get("corrupted", [])
            if not bad:
                self._step()
                return
            key = bad.pop(0)
            stones = g.setdefault("megastones", [])
            if key not in stones:
                stones.append(key)
            if key in g.get("corrupt_on", []):
                g["corrupt_on"].remove(key)
            AUDIO.play("heal")
            self.say([f"The {S.stone_name(dex, key).upper()} is clean again!", "Its light is calm and warm."],
                     self._step)
        elif op == "wild":
            _, species, level, shiny, *how = st
            e = dex.get(species)
            foe = A.make_mon(dex, e, level, self.rng, shiny=shiny)

            def after():   # a one-off Pokemon only leaves for good once it's caught
                if (getattr(self, "last_battle", None) or {}).get("caught") or "leaves" in how:
                    self._step()
                else:
                    self.script = None
                    self.say([f"The {e['name'].upper()} got away...", "It might be back if you look again."])
            self._battle([foe], "wild", None, then=after)
        elif op == "flag":
            S.set_flag(g, st[1])
            self._step()
        elif op == "give":
            _, item, n = st
            g["bag"][item] = g["bag"].get(item, 0) + n
            AUDIO.play("catch", 0.6)
            name = A.SHOP.get(item, S.KEY_ITEMS.get(item, (item,)))[0]
            self.say([f"{g['name']} received {n} x {name}!" if n > 1 else
                      f"{g['name']} received {'an' if name[0] in 'AEIOU' else 'a'} {name}!"],
                     self._step)
        elif op == "take":
            g["bag"].pop(st[1], None)
            self._step()
        elif op == "mega":
            self._get_stone(st[1], self._step)
        elif op == "keystone":
            g["keystone"] = True
            AUDIO.play("win")
            self.say([f"{g['name']} received the KEY STONE!", "Pokemon holding their Mega Stone can now Mega Evolve!"],
                     self._step)
        elif op == "money":
            g["money"] += st[1]
            self.say([f"{g['name']} received {st[1]} coins!"], self._step)
        elif op == "heal":
            self._heal_all()
            self._step()
        elif op == "quest_done":
            g.setdefault("quests", {})[st[1]] = "done"
            AUDIO.play("win")
            self.say([f"Quest complete: {S.QUESTS[st[1]]['name']}!"], self._step)
        elif op == "tournament":
            self.script = self._tournament_steps() + self.script
            self._step()
        elif op == "crowned":
            from .adventure_ui import HallOfFame
            g["champion"] = True
            S.set_flag(g, "world_champion")
            data = profile.load()
            if not data.get("adventure_champion"):
                data["adventure_champion"] = True
                profile.save(data)
                self.script[0:0] = [("say", "", ["RANDOMIZER MODE UNLOCKED!",
                                                 "Start a NEW GAME and turn it on in the OPTION screen."])]
            A.save(g)
            self.app.push(HallOfFame(self.app, g))
            self._step()
        else:
            self._step()

    TOWER_PRIZES = {7: [("rare-candy", 3)], 14: [("ultra-ball", 10), ("rare-candy", 5)], 21: [("master-ball", 1)],
                    35: [("rare-candy", 10)], 50: [("master-ball", 3)]}

    def _tower(self):
        """One Battle Tower battle: your team is healed, the opponent scales with your streak, a loss only ends
        the streak."""
        g = self.game
        streak = g.get("tower_streak", 0)
        self._heal_all()
        team, trainer = S.battle_team(self.world, g, "tower")
        trainer = dict(trainer, id=None, practice=True)
        boss = streak % 7 == 6

        def after():
            r = getattr(self, "last_battle", None) or {}
            self._heal_all()
            lines = []
            if r.get("won"):
                n = g["tower_streak"] = streak + 1
                g["tower_best"] = max(g.get("tower_best", 0), n)
                prize = 500 * (1 + n // 7)
                g["money"] += prize
                lines += [f"Win number {n}! You earned {prize} coins."]
                for item, k in self.TOWER_PRIZES.get(n, []):
                    g["bag"][item] = g["bag"].get(item, 0) + k
                    name = A.SHOP.get(item, (item,))[0]
                    lines.append(f"A {n}-win streak! Here's {k} x {name.upper()}!")
                if n >= 50:
                    S.set_flag(g, "tower_legend")
                lines.append("Talk to me again for your next battle!" if (n + 1) % 7 else
                             "Next up... the TOWER TYCOON. Talk to me when you're ready.")
            else:
                lines += [f"Your streak ended at {streak} win{'s' if streak != 1 else ''}.",
                          f"Your best is {g.get('tower_best', 0)}. Come back any time!"]
                g["tower_streak"] = 0
            A.save(g)
            self.say(lines, self._step, speaker="Tower Clerk")
        intro = ([f"Welcome to the BATTLE TOWER! Your streak: {streak}. Best: {g.get('tower_best', 0)}.",
                  "Your team will be healed before every battle. Lose, and the streak is over."] +
                 (["This is battle 7... the TOWER TYCOON is waiting for you!"] if boss else
                  [f"Battle {streak + 1}: {trainer['name']} is ready!"]))
        self.say(intro, lambda: self._battle(team, "trainer", trainer, then=after), speaker="Tower Clerk")

    def _tournament_steps(self):
        steps = []
        for k, (name, typ, title, intro, lose, lv) in enumerate(S.E4):
            steps += [("say", "Host", [f"ROUND {k + 1}! {title.upper()} {name.upper()}, master of {typ.upper()} "
                                       f"Pokemon, enters the arena!"]),
                      ("say", name, [intro]), ("battle", f"e4_{k}"), ("say", name, [lose])]
        steps += [("say", "Host", ["The Elite Four has fallen! The crowd is on its feet!",
                                   f"Ladies and gentlemen... the GRAND FINAL! The {S.CHAMP[1].upper()},",
                                   f"{S.CHAMP[0].upper()}!"]),
                  ("say", S.CHAMP[0], ["So you're the one everyone's talking about. The one who beat Team Rocket.",
                                       "I've held this title for ten years - ever since my greatest rival vanished.",
                                       "His name was Elias. You battle the way he did. Like the world depends on it.",
                                       "Show me everything you have!"]),
                  ("battle", "final"),
                  ("say", "Host", [f"IT'S OVER! {self.game['name'].upper()} IS THE NEW WORLD CHAMPION!",
                                   "The best Pokemon trainer in the world!"]),
                  ("say", S.CHAMP[0], ["Elias would have loved this battle.",
                                       "...They say the pond in Rootleaf is glowing again. Go. Bring him home."]),
                  ("crowned",)]
        return steps

    def _get_stone(self, key, then=None):
        g = self.game
        stones = g.setdefault("megastones", [])
        name = S.stone_name(self.app.dex, key)
        if key not in stones:
            stones.append(key)
        AUDIO.play("tera", 0.7)
        lines = [f"{g['name']} found a MEGA STONE: {name.upper()}!"]
        if not g.get("keystone"):
            lines.append("...It's warm to the touch. Maybe someone knows what it's for?")
        lines.append(f"Mega Stones collected: {len(stones)}.")
        self.say(lines, then)

    def _start_heal(self):
        self.healing = 2.4
        AUDIO.music(None)
        AUDIO.play("heal")

    def _heal_done(self):
        self._heal_all()
        g = self.game
        g["center"] = [g["room"]["area"], g["room"]["door"][0], g["room"]["door"][1] + 1]
        A.save(g)
        self.say(["Thank you for waiting.", "We've restored your Pokemon to full health.",
                  "We hope to see you again!"])

    def _heal_all(self):
        A.heal_party(self.game)

    def _pick(self, it):
        g = self.game
        g["picked"].append(it["id"])
        if it.get("mega"):
            self._get_stone(it["item"])
            return
        g["bag"][it["item"]] = g["bag"].get(it["item"], 0) + it["count"]
        AUDIO.play("catch", 0.6)
        name = A.SHOP.get(it["item"], S.KEY_ITEMS.get(it["item"], (it["item"],)))[0]
        found = f"{it['count']} x {name}" if it["count"] > 1 else (f"an {name}" if name[0] in "AEIOU" else f"a {name}")
        self.say([f"{g['name']} found {found}!", f"{g['name']} put {'them' if it['count'] > 1 else 'it'} in the BAG."])

    # ------------------------------------------------------------------ trainers
    def _trainer_spots(self):
        x, y = self.game["x"], self.game["y"]
        for n in self.npcs:
            if n["kind"] == "story" and n.get("auto"):
                ddx, ddy = DIRS[n["face"]]
                ahead = (y - n["y"]) * ddy + (x - n["x"]) * ddx
                side = abs(x - n["x"]) if ddy else abs(y - n["y"])
                if 0 < ahead <= n.get("sight", 4) and side <= 1:
                    AUDIO.play("select")
                    self.emote = ["!", n, 0.8, lambda n=n: self._talk(n)]
                    return True
                continue
            if self._sees(n):
                return True
        return False

    def _sees(self, n):
        """An unbeaten trainer who can see you down their line of sight walks over to battle."""
        if n["kind"] != "trainer" or n["id"] in self.game["beaten"]:
            return False
        x, y = self.game["x"], self.game["y"]
        dx, dy = DIRS[n["face"]]
        for k in range(1, n.get("sight", 4) + 1):
            tx, ty = n["x"] + dx * k, n["y"] + dy * k
            if (tx, ty) == (x, y):
                AUDIO.play("select")
                AUDIO.music("battle")
                self.emote = ["!", n, 0.8, lambda n=n: self._approach(n)]
                return True
            if not self.walkable(tx, ty):
                return False
        return False

    def _look_around(self, dt):
        """Trainers don't just stare one way: every few seconds they turn to look for someone to battle."""
        for n in self.npcs:
            if n["kind"] != "trainer" or n["id"] in self.game["beaten"] or n.get("still"):
                continue
            n["_look"] = n.get("_look", self.rng.uniform(0.5, 3.0)) - dt
            if n["_look"] > 0:
                continue
            n["_look"] = self.rng.uniform(1.2, 3.5)
            n["face"] = self.rng.choice([d for d in DIRS if d != n["face"]])
            if self.move is None and self._sees(n):
                return True
        return False

    def _approach(self, n):
        self.walking_npc = [n, 0.0]

    def _walk_npc(self, dt):
        n, p = self.walking_npc
        dx, dy = DIRS[n["face"]]
        nx, ny = n["x"] + dx, n["y"] + dy
        if (nx, ny) == (self.game["x"], self.game["y"]):
            self.walking_npc = None
            self.game["face"] = OPP[n["face"]]
            self._challenge(n)
            return
        p += dt * 4.0
        if p >= 1:
            n["x"], n["y"] = nx, ny
            p = 0.0
        self.walking_npc[1] = p

    def _challenge(self, n):
        if getattr(self, "_challenging", None) == n["id"] or n["id"] in self.game["beaten"]:
            return   # already on its way to a battle (spotted you and you pressed A at the same moment)
        self._challenging = n["id"]
        trainer = {"name": n["name"], "id": n["id"], "lose": n["lose"], "money": n["money"],
                   "look": n.get("cls", "Youngster")}
        team = [dict(m) for m in n["team"]]
        self.say([n["intro"]], lambda: self._battle(team, "trainer", trainer), speaker=n["name"])

    # ------------------------------------------------------------------ battles
    def _wild(self):
        area = self.cur
        lo, hi = area["levels"]
        rng = self.rng
        dex = self.app.dex
        legend = None
        if area["route"] >= 5 and rng.random() < (1 / 60 if self.game.get("champion") else 1 / 300):
            pool = [e for e in profile.legendary_pool(dex) if e["id"] not in self.game["caught"]]
            legend = rng.choice(pool) if pool else None
        if legend:
            foe = A.make_mon(dex, legend, hi + 6, rng)
        else:
            lv = rng.randint(lo, hi)
            met = self.game.get("wilds_met", 0)
            if met < 4 and area["route"] <= 2:   # your first few wild Pokemon: level 1, 2, 3, 4 - then it picks up
                lv = met + 1
            self.game["wilds_met"] = met + 1
            charm = S.has(self.game, "shiny_charm")
            foe = A.make_mon(dex, A.grown_species(dex, dex.all[self.world.wild_species(area, rng)], lv - 4), lv, rng,
                             shiny=rng.randrange(50 if charm else A.SHINY_ODDS) == 0)
        self.cool = 3
        self._battle([foe], "wild", None)

    def _battle(self, foes, kind, trainer, then=None):
        if self.trans is not None or self.battle is not None:
            return
        self.battle_then = then
        if A.lead_alive(self.game, self.app.dex) is None:
            self._challenging = None
            self.say(["Your Pokemon are too tired to battle! Heal them at a Pokemon Center."])
            return

        def start():
            from .adventure_battle import AdventureSession
            from .gbabattle import GBABattle
            s = AdventureSession(self.game, self.app.dex, foes, kind, trainer)
            self.battle = s
            self.app.push(GBABattle(self.app, s))
        AUDIO.music("battle")
        self.trans = {"t": 0.0, "start": start, "kind": kind}

    def _after_battle(self, s):
        from .adventure_ui import EvolutionScene, HallOfFame
        dex = self.app.dex
        g = self.game
        r = s.results()
        self.last_battle = r
        self._challenging = None
        then, self.battle_then = getattr(self, "battle_then", None), None
        rt = r.get("trainer") or {}
        if rt.get("echo"):
            g.pop("echo", None)   # an echo rift only opens once
        if r.get("collapsed"):
            self.script = None
            if not rt.get("echo") and rt.get("route"):   # the rift tears open again somewhere else on the route
                moved = g.setdefault("rift_moved", {})
                moved[str(rt["route"])] = moved.get(str(rt["route"]), 0) + 1
            self._refresh()
            self.say(["The rift collapsed around you!", "...You landed back on the route. The Mega Pokemon is gone.",
                      "The rift re-formed somewhere else on this route..." if not rt.get("echo") else
                      "The echo rift has faded away."])
            A.save(g)
            return
        if r["lost"] and (r.get("trainer") or {}).get("practice") and then:
            self._heal_all()
            then()
            return
        if r["lost"]:
            self.script = None
            # FireRed: you drop (your best Pokemon's level x a badge-based amount), never more than half your money
            mult = [8, 16, 24, 36, 48, 64, 80, 100, 120][min(8, len(g["badges"]) // 2)]
            top = max((m["level"] for m in g["party"]), default=5)
            lost = min(g["money"] // 2, top * mult)
            g["money"] -= lost
            area, x, y = g["center"]

            def wake():
                self.warp = {"t": 0.0, "go": lambda: (self._load_area(area, x, y), self._heal_all(), A.save(g))}
            self.say([f"{g['name']} is out of usable Pokemon!", f"{g['name']} panicked and dropped {lost} coins...",
                      "...", f"{g['name']} scurried home, protecting the exhausted Pokemon." if area == 0 else
                      f"{g['name']} scurried to a Pokemon Center, protecting the exhausted Pokemon."], wake)
            return
        lines = []
        if r["caught"]:
            mon = r["caught"]
            base = dex.all[mon["species"]]
            if not base["default"] and "-mega" in base["key"]:   # caught from a rift: it calms down
                mon["species"] = base["species"]
                lines.append(f"The Mega Evolution faded. {A.name_of(dex, mon)} looks calm now.")
            rift_born = bool((r.get("trainer") or {}).get("rift"))
            if rift_born:   # caught inside a rift: it keeps a spark of it forever
                from .riftdex import RIFT_ABILITY
                mon["rift_born"] = True
                mon["ability"] = RIFT_ABILITY
            where = A.add_caught(g, dex, mon)
            nm = A.name_of(dex, mon)
            if rift_born:
                lines.append(f"{nm} is RIFT-BORN! It has the rare ability RIFT HEART,")
                lines.append("and a fifth move no other Pokemon can learn: RIFT BREAKER!")
            if where == "box":
                lines.append(f"{nm} was transferred to the Box.")
            e = dex.all[mon["species"]]
            if e["legendary"] or e["mythical"]:
                profile.add_legend(e, mon.get("shiny", False))
                lines.append(f"{nm} also joined your Legend collection!")
        t = r.get("trainer") or {}
        if r["won"] and r["kind"] != "wild":
            g["money"] += t.get("money", 0)
            if t.get("id") and t["id"] not in g["beaten"]:
                g["beaten"].append(t["id"])
            if t.get("badge") and t["badge"] not in g["badges"]:
                g["badges"].append(t["badge"])
                lines += [f"{g['name']} received the {t['badge']} from {t.get('leader', '')}!"]
                AUDIO.play("win")
                stone = S.gym_stone(dex, t["gym"])
                if stone and stone not in g.setdefault("megastones", []):
                    g["megastones"].append(stone)
                    lines.append(f"{t.get('leader', '')} also gave you a MEGA STONE: "
                                 f"{S.stone_name(dex, stone).upper()}!")
                if t.get("gym") == len(A.GYMS) - 1:
                    g["bag"]["master-ball"] = g["bag"].get("master-ball", 0) + 1
                    lines.append(f"{t.get('leader', '')} also gave you a Master Ball! It never fails.")
            if self.cur.get("route") == A.LEGACY[4] and all(n["id"] in g["beaten"] for n in self.cur["npcs"]
                                                  if n["kind"] == "trainer"):
                S.set_flag(g, "route4_clear")
        evolutions = list(s.evolutions)

        go_on = then if (r["won"] or r["caught"]) and then else None
        if then and not go_on:
            self.script = None   # ran away from a story encounter: try again later

        def finish():
            if go_on:
                go_on()
            for mon, to in reversed(evolutions):
                self.app.push(EvolutionScene(self.app, g, mon, to))
            if t.get("champion") and r["won"]:
                g["champion"] = True
                self.app.push(HallOfFame(self.app, g))
            A.save(g)
        if lines:
            self.say(lines, finish)
        else:
            finish()

    # ------------------------------------------------------------------ input
    def handle(self, ev, pos):
        if self.trans or self.emote or self.walking_npc or self.warp or self.healing:
            return
        if self.text is not None:
            if self.text.handle(ev):
                if self.text and self.text.done:
                    self.text = None
            return
        if self.menu is not None:
            self._menu_handle(ev, pos)
            return
        if self.choice is not None:
            self._choice_handle(ev, pos)
            return
        if ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_TAB) and self.move is None:
                self._open_menu()
            elif ev.key in (pygame.K_z, pygame.K_SPACE) and self.move is None:
                self.interact()
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and pos and pos[0] > VW - 60 and pos[1] < 40:
            self._open_menu()

    def _open_menu(self):
        AUDIO.play("select", 0.5)
        self.menu = U.Menu([("dex", "POKeDEX"), ("party", "POKeMON"), ("bag", "BAG"), ("quests", "QUESTS"),
                            ("card", self.game["name"].upper()), ("save", "SAVE"), ("options", "OPTION"),
                            ("quit", "QUIT"), ("close", "EXIT")])

    def _menu_handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_RETURN, pygame.K_TAB) and \
                self.menu.options[self.menu.index][0] == "close":
            self.menu = None
            return
        k = self.menu.handle(ev, pos)
        if k is None:
            return
        from . import adventure_ui as UI
        if k in ("back", "close"):
            self.menu = None
        elif k == "dex":
            self.app.push(UI.DexScene(self.app, self.game))
        elif k == "party" and not self.game["party"]:
            self.menu = None
            self.say(["You don't have any Pokemon yet!"])
        elif k == "party":
            self.app.push(UI.PartyScene(self.app, self.game))
        elif k == "bag":
            self.app.push(UI.BagScene(self.app, self.game))
        elif k == "card":
            self.app.push(UI.CardScene(self.app, self.game))
        elif k == "quests":
            self.app.push(UI.QuestScene(self.app, self.game))
        elif k == "options":
            self.app.push(UI.OptionsScene(self.app, self.game))
        elif k == "save":
            self.menu = None
            A.save(self.game)
            AUDIO.play("heal", 0.4)
            self.say([f"{self.game['name']} saved the game."])
        elif k == "quit":
            A.save(self.game)
            self.app.pop()

    # ------------------------------------------------------------------ drawing
    def _player_px(self):
        """Where you are, snapped to whole GBA pixels (2 canvas px) so you and the camera always move together -
        no 1-pixel shimmer between you and the map while walking."""
        g = self.game
        if self.move is not None:
            fx, fy, tx, ty, p = self.move
            return (round((fx + (tx - fx) * p) * T / 2) * 2, round((fy + (ty - fy) * p) * T / 2) * 2, p)
        return g["x"] * T, g["y"] * T, 0.0

    def draw(self, surf):
        rows = self.rows()
        mh = len(rows) * T
        px, py, p = self._player_px()
        cam = int(min(max(0, py + T / 2 - VH / 2), max(0, mh - VH)))
        oy = -cam if mh > VH else (VH - mh) // 2
        mw = len(rows[0]) * T
        camx = int(min(max(0, px + T / 2 - VW / 2), max(0, mw - VW)))
        ox = -camx if mw > VW else (VW - mw) // 2
        surf.fill((0, 0, 0) if self.field else (16, 16, 24))
        y0, y1 = max(0, cam // T - 1), min(len(rows), (cam + VH) // T + 2)
        wf = int(self.t * 3) % 3
        gf = int(self.t * 2) % 2
        inside = self.inside
        kind = self.cur.get("room")
        field = self.field
        if field:
            surf.blit(field[0], (ox, oy))
        for y in range(y0, y1) if not field else ():
            for x, ch in enumerate(rows[y]):
                dx, dy = x * T + ox, y * T + oy
                if inside:
                    if ch == "W":
                        surf.blit(G.hwall(kind, self.tile(x, y + 1) != "W"), (dx, dy))
                    else:
                        surf.blit(G.hfloor(kind, x, y), (dx, dy))
                        if ch in FURN:
                            surf.blit(G.hfurn(FURN[ch], kind), (dx, dy))
                    continue
                if ch in "=_":
                    surf.blit(G.hsand(self._mask(x, y, "=_" + "".join(DOORS)), x * 3 + y), (dx, dy))
                elif ch in "rvf":   # without the FireRed tiles: simple stand-ins
                    surf.blit(G.hgrass(x, y), (dx, dy))
                    if ch == "r":
                        pygame.draw.ellipse(surf, (120, 104, 96), (dx + 4, dy + 6, T - 8, T - 10))
                    elif ch == "v":
                        pygame.draw.rect(surf, (128, 96, 72), (dx, dy + T - 10, T, 6))
                    else:
                        pygame.draw.rect(surf, (200, 200, 208), (dx, dy + 10, T, 4))
                        pygame.draw.rect(surf, (200, 200, 208), (dx + 4, dy + 4, 4, T - 8))
                elif ch == '"':
                    surf.blit(G.htall(0), (dx, dy))
                elif ch == ",":
                    surf.blit(G.hflowers(gf, x + y * 5), (dx, dy))
                elif ch == "~":
                    surf.blit(G.hwater(self._mask(x, y, "~"), wf), (dx, dy))
                else:
                    surf.blit(G.hgrass(x, y), (dx, dy))
                    if ch == "S":
                        surf.blit(G.hsign(), (dx, dy))
        if not inside and not field:   # forests: crowns overlap upward, drawn top row first so lower trees sit in front
            for y in range(y0, min(len(rows), y1 + 1)):
                for x, ch in enumerate(rows[y]):
                    if ch in "#t":
                        img = G.htree(self.tile(x, y + 1) in "#t", self.tile(x, y - 1) in "#t", x * 7 + y)
                        surf.blit(img, (x * T + ox, y * T + oy - 16))
        if inside and kind == "center" and self.healing is not None:   # balls on the healing machine
            nurse = next((n for n in self.npcs if n["kind"] == "nurse"), None)
            hx, hy = (nurse["x"] - 2, nurse["y"]) if field and nurse else (5, 2)
            mx, my = hx * T + ox, hy * T + oy
            n = len(self.game["party"])
            for i in range(n):
                if (2.4 - self.healing) > i * 0.15:
                    on = int(self.t * 8) % 2 if self.healing < 1.4 else 1
                    U.ball(surf, (mx + 10 + (i % 3) * 7, my + 12 + (i // 3) * 7), 3)
                    if on and self.healing < 1.4:
                        pygame.draw.circle(surf, (255, 255, 200), (mx + 10 + (i % 3) * 7, my + 12 + (i // 3) * 7), 2)
        for kind_b, bx, by, bw, bh, door in (self.field_missing if field else self.blds):
            accent = None
            if kind_b == "gym" and self.cur.get("town"):
                from .gfx import type_color
                accent = type_color(A.GYMS[self.cur["town"] - 1][2], 0)
            surf.blit(G.hbuilding(kind_b, bw, bh, door, accent, seed=bx * 3 + by), (bx * T + ox, by * T + oy))
        for it in self.items:
            if it["id"] not in self.game["picked"]:
                if it.get("mega"):   # a Mega Stone glinting on the ground
                    cx, cy = it["x"] * T + T // 2 + ox, it["y"] * T + oy + T // 2
                    k = 0.5 + 0.5 * math.sin(self.t * 5 + it["x"])
                    pygame.draw.circle(surf, (255, 255, 255), (cx, cy), 2 + int(3 * k))
                    for a in range(4):
                        ang = a * math.pi / 2 + self.t
                        ex = cx + int(math.cos(ang) * (4 + 6 * k))
                        ey = cy + int(math.sin(ang) * (4 + 6 * k))
                        pygame.draw.line(surf, (255, 236, 150), (cx, cy), (ex, ey), 2)
                    continue
                if not field:
                    surf.blit(G.hgrass(it["x"], it["y"]), (it["x"] * T + ox, it["y"] * T + oy))
                surf.blit(G.hitem(), (it["x"] * T + ox, it["y"] * T + oy))
        actors = []
        for n in self.npcs:
            nx, ny = n["x"] * T + ox, n["y"] * T
            walking = self.walking_npc and self.walking_npc[0] is n
            if walking:
                ddx, ddy = DIRS[n["face"]]
                nx += ddx * self.walking_npc[1] * T
                ny += ddy * self.walking_npc[1] * T
            actors.append((ny, "npc", (n, nx, ny, walking)))
        lead = A.lead_alive(self.game, self.app.dex)
        if lead is not None and not inside:
            fx, fy = self._follower_px(p)
            actors.append((fy - 1, "follow", (lead, fx + ox, fy)))
        actors.append((py, "player", (px + ox, py, p)))
        actors.sort(key=lambda a: a[0])
        for _, kind_a, data in actors:
            if kind_a == "npc":
                n, nx, ny, walking = data
                frame = (1 + int(self.t * 6) % 2) if walking else 0
                if n["kind"] == "rift":   # a tear in the world, crackling with Mega energy
                    cx, cy = nx + T // 2, ny + oy + T // 2
                    for k in range(5):
                        ang = self.t * (2.5 + k * 0.4) + k * 1.3
                        rr = 6 + k * 3 + int(2 * math.sin(self.t * 5 + k))
                        col = [(40, 8, 72), (96, 32, 160), (160, 72, 232), (208, 144, 255), (255, 232, 255)][k]
                        pygame.draw.arc(surf, col, (cx - rr, cy - rr, rr * 2, rr * 2), ang, ang + 2.4, 3)
                    pygame.draw.circle(surf, (24, 0, 40), (cx, cy), 5)
                    for k in range(3):
                        a = self.t * 3 + k * 2.1
                        pygame.draw.circle(surf, (255, 240, 160), (int(cx + math.cos(a) * 18), int(cy + math.sin(a) * 14)), 2)
                    continue
                if n["kind"] == "ball":   # a starter's Poke Ball on Oak's table
                    surf.blit(G.hitem(), (nx, ny + oy))
                    continue
                if n["kind"] == "static":   # a Pokemon standing in the world
                    e = self.app.dex.get(n["pokemon"])
                    img = G.icon(e["id"] if e else 25, n.get("shiny", False), int(self.t * 2))
                    bob = int(2 * math.sin(self.t * 3))
                    surf.blit(img, img.get_rect(midbottom=(nx + T / 2, ny + oy + T - 2 + bob)))
                    continue
                img = G.person(n.get("look") or n.get("cls") or "villager", n["face"], frame)
                surf.blit(img, (nx, ny + oy + T - img.get_height() - 2))
            elif kind_a == "follow":
                mon, fx, fy = data
                img = G.icon(mon["species"], mon.get("shiny", False), int(self.t * (6 if self.move else 2)))
                if self.game["x"] * T + ox > fx:
                    img = pygame.transform.flip(img, True, False)
                hop = 0   # the icon's own two frames do the bounce
                surf.blit(img, img.get_rect(midbottom=(fx + T / 2, fy + T - 2 - hop + oy)))
            else:
                x, y, pp = data
                if getattr(self, "jumping", False):   # an arc over the ledge, with a shadow
                    pygame.draw.ellipse(surf, (40, 56, 48), (x + 6, y + oy + T - 10, T - 12, 8))
                    y -= int(math.sin(pp * math.pi) * 22)
                frame = (1 + self.step) if self.move is not None and pp < 0.5 else 0
                img = G.person("player", self.game["face"], frame)
                surf.blit(img, (x, y + oy + T - img.get_height() - 2))
                if not field and not inside and self.tile(self.game["x"], self.game["y"]) == '"' and self.move is None:
                    surf.blit(G.htall_over(gf), (x, y + oy + T - 16))
        if field:
            surf.blit(field[1], (ox, oy))   # tree tops, roofs and grass tips go over everyone
        if getattr(self, "radar", 0) > 0 and not inside:
            self._draw_radar(surf, ox, oy)
        if self.emote is not None:
            n = self.emote[1]
            bx, by = n["x"] * T + T // 2 + ox, n["y"] * T + oy - 28
            pygame.draw.rect(surf, (48, 48, 56), (bx - 8, by - 10, 16, 20), border_radius=4)
            pygame.draw.rect(surf, (248, 248, 248), (bx - 6, by - 8, 12, 16), border_radius=3)
            F.draw(surf, "!", (bx - 1, by - 6), (224, 56, 56), None)
        self._draw_hud(surf)
        if self.text is not None:
            self.text.draw(surf, self.t)
        if self.choice is not None:   # FireRed: the Pokemon in a window, the question and YES/NO
            win = pygame.Rect(VW // 2 - 76, 40, 152, 152)
            U.std_frame(surf, win) or U.box(surf, win)
            img = G.battle_sprite(self.choice["pid"], max_h=128)
            surf.blit(img, img.get_rect(center=win.center))
            q = self.choice["q"]
            q.draw(surf, self.t)
            if q.shown >= q._len():
                self.choice["menu"].draw(surf, (VW - 110, 160, 100, 70))
        if self.menu is not None:
            self.menu.draw(surf, (VW - 140, 6, 134, 20 + 26 * len(self.menu.options)))   # FireRed: right side, tiles (22,1)
        if self.trans is not None:
            self._draw_transition(surf, self.trans["t"])
        if self.warp is not None:
            U.fade(surf, min(1.0, self.warp["t"] / 0.25))
        U.fade(surf, self.fade)

    def _follower_px(self, p):
        if self.move is not None and len(self.trail) >= 2:
            (fx, fy), (tx, ty) = self.trail[-2], self.trail[-1]
            return round((fx + (tx - fx) * p) * T / 2) * 2, round((fy + (ty - fy) * p) * T / 2) * 2
        tx, ty = self.trail[-1] if self.trail else (self.game["x"], self.game["y"] + 1)
        return tx * T, ty * T

    def _draw_radar(self, surf, ox, oy):
        """The radar's signal: bars, an arrow toward the nearest buried stone and a glow once you're close."""
        s, d = self._nearest_site()
        if s is None:
            return
        g = self.game
        r = pygame.Rect(VW - 120, VH - 58, 114, 52)
        pygame.draw.rect(surf, (24, 32, 48), r, border_radius=6)
        pygame.draw.rect(surf, (96, 200, 255), r, 2, border_radius=6)
        F.draw(surf, "MEGA RADAR", (r.x + 8, r.y + 4), (200, 232, 255), None, small=True)
        bars = 5 if d <= 1 else 4 if d <= 3 else 3 if d <= 7 else 2 if d <= 14 else 1
        for i in range(5):
            h = 4 + i * 4
            col = (96, 255, 160) if i < bars else (56, 72, 88)
            pygame.draw.rect(surf, col, (r.x + 10 + i * 9, r.bottom - 8 - h, 6, h))
        ang = math.atan2(s[2] - g["y"], s[1] - g["x"])
        cx, cy = r.right - 26, r.y + 30
        if d == 0:
            k = 0.5 + 0.5 * math.sin(self.t * 12)
            pygame.draw.circle(surf, (255, 240, 128), (cx, cy), int(6 + 5 * k), 2)
        else:
            tip = (cx + math.cos(ang) * 12, cy + math.sin(ang) * 12)
            left = (cx + math.cos(ang + 2.5) * 9, cy + math.sin(ang + 2.5) * 9)
            right = (cx + math.cos(ang - 2.5) * 9, cy + math.sin(ang - 2.5) * 9)
            pygame.draw.polygon(surf, (255, 216, 96), [tip, left, right])
        if d <= 2:   # the spot itself shimmers when you're right next to it
            k = 0.5 + 0.5 * math.sin(self.t * 8)
            px, py = s[1] * T + T // 2 + ox, s[2] * T + T // 2 + oy
            pygame.draw.circle(surf, (160, 240, 255), (px, py), int(5 + 7 * k), 2)

    def _draw_hud(self, surf):
        q = self.banner
        if q < 2.6 and not self.inside:   # area name sign in the top-left corner
            k = min(1.0, q / 0.25, (2.6 - q) / 0.25)
            y = int(-40 + 44 * k)
            r = pygame.Rect(4, y, max(140, F.width(self.cur["name"]) + 30), 34)
            pygame.draw.rect(surf, (48, 48, 56), r, border_radius=4)
            pygame.draw.rect(surf, (216, 184, 120), r.inflate(-4, -4), border_radius=3)
            pygame.draw.rect(surf, (248, 240, 216), r.inflate(-8, -8), border_radius=2)
            F.draw(surf, self.cur["name"], (r.x + 14, r.y + 9), U.TEXT, U.SHADOW)

    def _draw_transition(self, surf, t):
        """Into battle: the screen flashes, then black bars close in from both sides."""
        if t < 0.5:
            if int(t / 0.08) % 2 == 0:
                U.fade(surf, 0.75, (248, 248, 248) if self.trans["kind"] == "wild" else (16, 16, 24))
            return
        k = min(1.0, (t - 0.5) / 0.6)
        n = 10
        bh = VH / n
        for i in range(n):
            w = int(VW * min(1.0, max(0.0, k * 1.5 - i * 0.04)))
            x = 0 if i % 2 == 0 else VW - w
            pygame.draw.rect(surf, (8, 8, 16), (x, int(i * bh), w, int(bh) + 1))


CHAMP_NAME = A.CHAMPION[0]
