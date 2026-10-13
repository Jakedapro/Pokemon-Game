"""Adventure battles, GBA style: the foe on its platform top-right with its HP box top-left, your Pokemon's back
on the bottom-left with HP numbers and the EXP bar, the message box along the bottom and the FIGHT / BAG /
POKeMON / RUN menu. Experience is handed out right after each knockout, with level-ups mid-battle.

Driven by AdventureSession (the same battle engine as the rest of the game)."""
import math
import random

import pygame

from . import adventure as A
from . import gbaart as G
from . import gbaui as U
from . import pixelfont as F
from .app import Scene
from .audio import AUDIO
from .gfx import PIXEL, type_color

VW, VH = PIXEL
FOE_AT = (352, 136)     # midbottom of the foe's sprite (FireRed: centre 176,40 at 1x)
ME_AT = (144, 232)      # (FireRed: centre 72,80 at 1x)
STATUS_TAGS = {"brn": ("BRN", (232, 112, 56)), "par": ("PAR", (216, 184, 40)), "psn": ("PSN", (168, 80, 168)),
               "tox": ("PSN", (168, 80, 168)), "slp": ("SLP", (144, 144, 152)), "frz": ("FRZ", (96, 176, 232))}


class GBABattle(Scene):
    canvas_size = PIXEL
    no_transition = True

    def __init__(self, app, session):
        super().__init__(app)
        self.s = session
        self.dex = app.dex
        self.g = session.game
        self.t = 0.0
        self.queue = []            # [text, anim] still to show
        self.text = None           # current TextBox
        self.anim = None           # current animation: {"kind", "t", "dur", ...}
        self.req = None
        self.state = None
        self.mode = "intro"        # intro -> play -> action/fight/bag/party -> play ... -> end
        self.intro_t = 0.0
        self.vis = {0: None, 1: None}      # what's shown on each side: dict(idx, pid, name, level, status, shiny)
        self.frac = {}             # (side, idx) -> HP fraction shown
        self.target = {}           # (side, idx) -> HP fraction to drain toward
        self.exp_shown = None
        self.hidden = {0: True, 1: self.s.kind != "wild"}   # before the send-out
        self.blink = {0: 0.0, 1: 0.0}
        self.faint = {0: 0.0, 1: 0.0}
        self.grow = {0: 1.0, 1: 1.0}       # send-out scale
        self.lunge = {0: 0.0, 1: 0.0}
        self.fx = []               # hit particles
        self.catch = None
        self.menu = None
        self.sub = None            # bag / party overlay menus
        self.bag_item = None
        self.done = False
        self.end_t = None
        self.trainer = session.trainer or {}
        self.buttons = []
        for u in self.s.pump():
            self._absorb(u)

    # ------------------------------------------------------------------ the log
    def _absorb(self, u):
        if self.state is None:
            self.state = u["state"]
            for side in (0, 1):
                for i, m in enumerate(u["state"]["sides"][side]["mons"]):
                    self.frac[(side, i)] = self.target[(side, i)] = m["frac"]
        for e in u["log"]:
            a = e.get("a") or []
            text = e.get("t") or ""
            kind = a[0] if a else None
            if kind == "turn" or text.startswith("---"):
                continue
            if kind == "switch":
                side, idx = a[1], a[2]
                m = self.s.battle.sides[side].mons[idx]
                name = m.name.split(" ")[0] if m.entry["default"] else m.name
                if side == 0:
                    text = f"Go! {name.upper()}!"
                elif self.s.kind == "wild":
                    text = ""
                else:
                    text = f"{self.trainer.get('name', 'The trainer')} sent out {name.upper()}!"
            if kind == "end":
                continue
            self.queue.append([text, a])
        self.pending_state = u
        if u["req"] is None and u["state"]["over"]:
            self._queue_ending(u["state"])

    def _queue_ending(self, st):
        if st["winner"] == 0 and self.s.kind != "wild":
            t = self.trainer
            money = t.get("money", 0)
            self.queue.append([f"{self.g['name']} defeated {t.get('name', 'the trainer')}!", ["win"]])
            if t.get("lose"):
                self.queue.append([t["lose"], None])
            self.queue.append([f"{self.g['name']} got {money} coins for winning!", None])
        self.queue.append(["", ["finish"]])

    # ------------------------------------------------------------------ update
    def update(self, dt):
        self.t += dt
        AUDIO.music("battle")
        for side in (0, 1):
            self.blink[side] = max(0.0, self.blink[side] - dt)
            self.lunge[side] = max(0.0, self.lunge[side] - dt)
            if self.faint[side] > 0:
                self.faint[side] = min(1.0, self.faint[side] + dt * 3)
            if self.grow[side] < 1:
                self.grow[side] = min(1.0, self.grow[side] + dt * 3)
        for key, goal in self.target.items():   # HP bars drain smoothly
            cur = self.frac.get(key, goal)
            step = dt * 0.8
            self.frac[key] = goal if abs(cur - goal) <= step else cur + (step if goal > cur else -step)
        for p in self.fx:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] -= dt
        self.fx = [p for p in self.fx if p[4] > 0]
        if self.catch is not None:
            self.catch["t"] += dt
        if self.exp_shown is not None:
            goal = self._exp_frac(self.exp_shown[0])
            cur = self.exp_shown[1]
            self.exp_shown[1] = goal if goal < cur else min(goal, cur + dt * 0.9)
        if self.mode == "intro":
            self.intro_t += dt
            if self.intro_t >= 1.3:
                self.mode = "play"
                if self.s.kind == "wild":
                    m = self.s.foes[0]
                    AUDIO.cry(self.s.battle.sides[1].mons[0].entry["id"], 0.9)
                    shiny = " shiny" if m.get("shiny") else ""
                    self.queue.insert(0, [f"Wild{shiny} {A.name_of(self.dex, m).upper()} appeared!", None])
                else:
                    self.queue.insert(0, [f"{self.trainer.get('name', 'Trainer')} would like to battle!", None])
            return
        if self.mode != "play":
            return
        if self.text is not None:
            self.text.update(dt)
            if self.text.done:
                self.text = None
        if self.anim is not None:
            self.anim["t"] += dt
            if self.anim["t"] >= self.anim["dur"]:
                self.anim = None
        if self.text is None and self.anim is None:
            if self.queue:
                text, a = self.queue.pop(0)
                self._start(a)
                if text:
                    self.text = U.TextBox([text], auto=0.7)
            elif self.done:
                return
            else:
                self._ready()

    def _ready(self):
        """The log is shown: wait for the next choice (or new log)."""
        for u in self.s.pump():
            self._absorb(u)
            return
        u = getattr(self, "pending_state", None)
        if u is None:
            return
        self.state = u["state"]
        self.req = u["req"]
        self.pending_state = None
        if self.req is None:
            return
        if self.req["kind"] == "switch":
            self._open_party(forced=True)
        else:
            self._open_action()

    # ------------------------------------------------------------------ animations from log entries
    def _start(self, a):
        if not a:
            return
        kind = a[0]
        if kind == "switch":
            side, idx, pid = a[1], a[2], a[3]
            m = self.s.battle.sides[side].mons[idx]
            src = (self.g["party"][idx] if side == 0 else self.s.foes[idx])
            self.vis[side] = {"idx": idx, "pid": pid, "name": (m.name.split(" ")[0] if m.entry["default"] else m.name),
                              "level": m.member.level, "status": m.status, "shiny": src.get("shiny", False)}
            self.hidden[side] = False
            self.faint[side] = 0.0
            if not (side == 1 and self.s.kind == "wild"):
                self.grow[side] = 0.0
                AUDIO.play("ball", 0.6)
                AUDIO.cry(pid, 0.8)
            if side == 0:
                self.exp_shown = [idx, self._exp_frac(idx)]
            self.anim = {"kind": "switch", "t": 0, "dur": 0.5}
        elif kind == "move":
            side = a[1]
            self.lunge[side] = 0.25
            AUDIO.play("beam" if a[4] == "spec" else "melee" if a[4] == "phys" else "select", 0.5)
            if a[4] != "status":
                self._burst(1 - side, type_color(a[3], 0))
            self.anim = {"kind": "move", "t": 0, "dur": 0.45}
        elif kind in ("hit", "hp"):
            side = a[1]
            v = self.vis[side]
            if v:
                self.target[(side, v["idx"])] = a[2]
            if kind == "hit":
                self.blink[side] = 0.5
                AUDIO.play("hit_super" if a[3] > 1 else "hit_weak" if a[3] < 1 else "hit", 0.8)
            self.anim = {"kind": kind, "t": 0, "dur": 0.7}
        elif kind == "faint":
            side = a[1]
            v = self.vis[side]
            if v:
                self.target[(side, v["idx"])] = 0
                AUDIO.cry(v["pid"], 0.7)
            self.faint[side] = 0.01
            AUDIO.play("faint", 0.7)
            self.anim = {"kind": "faint", "t": 0, "dur": 0.6}
            if side == 1 and v:
                self._queue_exp(v["idx"])
        elif kind == "status":
            side = a[1]
            if self.vis[side]:
                self.vis[side]["status"] = a[2]
            if a[2]:
                AUDIO.play("status", 0.6)
        elif kind == "stat":
            AUDIO.play("boost" if len(a) > 2 and a[2] else "drop", 0.6)
        elif kind == "crit":
            AUDIO.play("hit_super", 0.6)
        elif kind == "miss":
            AUDIO.play("miss", 0.6)
        elif kind == "ball":
            self.catch = {"t": 0.0, "shakes": 0, "caught": False, "broke": None, "shake_t": None}
            AUDIO.play("ball", 0.7)
            self.anim = {"kind": "ball", "t": 0, "dur": 1.0}
        elif kind == "shake" and self.catch is not None:
            self.catch.update(shakes=a[2], caught=a[3], shake_t=self.catch["t"])
            self.anim = {"kind": "shake", "t": 0, "dur": 0.4 + 0.8 * a[2]}
        elif kind == "caught":
            AUDIO.play("catch")
            AUDIO.music(None)
            self.anim = {"kind": "caught", "t": 0, "dur": 0.8}
            v = self.vis[1]
            if v:
                self._queue_exp(v["idx"])
        elif kind == "breakfree" and self.catch is not None:
            self.catch["broke"] = self.catch["t"]
            self.blink[1] = 0.3
            AUDIO.play("ball", 0.6)
        elif kind == "mega":
            side, pid = a[1], a[2]
            if self.vis[side]:
                self.vis[side]["pid"] = pid
                self.vis[side]["name"] = self.s.battle.sides[side].mon.name
            AUDIO.play("tera", 0.9)
            for col in ((255, 240, 160), (200, 120, 255), (120, 220, 255)):
                self._burst(side, col)
            self.grow[side] = 0.0
            self.anim = {"kind": "switch", "t": 0, "dur": 0.9}
        elif kind == "item":
            AUDIO.play("heal", 0.6)
        elif kind == "win":
            AUDIO.music(None)
            AUDIO.play("win")
        elif kind == "finish":
            self.done = True
            self.anim = {"kind": "finish", "t": 0, "dur": 0.4}
            self.end_t = self.t
            self.app.pop()
        elif kind == "expbar":
            self.exp_shown = [a[1], self.exp_shown[1] if self.exp_shown and self.exp_shown[0] == a[1] else 0.0]
            AUDIO.play("boost", 0.3)
            self.anim = {"kind": "exp", "t": 0, "dur": 0.9}
        elif kind == "levelup":
            AUDIO.play("tera", 0.6)
            i = a[1]
            v = self.vis[0]
            if v and v["idx"] == i:
                v["level"] = self.g["party"][i]["level"]
                bm = self.s.battle.sides[0].mons[i]
                self.target[(0, i)] = self.frac[(0, i)] = bm.hp / bm.maxhp
                self.exp_shown = [i, 0.0]
            self.anim = {"kind": "level", "t": 0, "dur": 0.5}

    def _queue_exp(self, foe_idx):
        """Right after a knockout / catch: EXP for the team, level-ups and new moves (inserted next in line)."""
        msgs = []
        for i, gain, events in self.s.award(foe_idx):
            nm = A.name_of(self.dex, self.g["party"][i]).upper()
            active = self.vis[0] and self.vis[0]["idx"] == i
            msgs.append([f"{nm} gained {gain} EXP. Points!", ["expbar", i] if active else None])
            for ev in events:
                if ev[0] == "level":
                    msgs.append([f"{nm} grew to LV. {ev[1]}!", ["levelup", i]])
                elif ev[0] == "learn":
                    mv = self.dex.moves[ev[1]]["name"].upper()
                    if ev[2]:
                        old = self.dex.moves[ev[2]]["name"].upper()
                        msgs += [[f"1, 2, and... Poof! {nm} forgot {old}.", None],
                                 [f"And... {nm} learned {mv}!", None]]
                    else:
                        msgs.append([f"{nm} learned {mv}!", None])
        self.queue[0:0] = msgs

    def _exp_frac(self, i):
        p = self.g["party"][i]
        lo, hi = A.xp_for(p["level"]), A.xp_for(p["level"] + 1)
        return max(0.0, min(1.0, (p["xp"] - lo) / max(1, hi - lo)))

    def _burst(self, side, color):
        x, y = FOE_AT if side == 1 else ME_AT
        y -= 50
        rng = random.Random(self.t)
        for _ in range(14):
            a = rng.random() * math.tau
            v = rng.uniform(40, 140)
            self.fx.append([x, y, math.cos(a) * v, math.sin(a) * v, 0.45, color])

    # ------------------------------------------------------------------ menus
    def _open_action(self):
        self.mode = "action"
        self.menu = U.Menu([("fight", "FIGHT"), ("bag", "BAG"), ("party", "POKeMON"),
                            ("run", "RUN", self.s.kind == "wild")], cols=2,
                           index=self.menu.index if self.menu and self.mode == "action" else 0)

    def _open_fight(self):
        self.mega_on = False
        self.mode = "fight"
        moves = self.req["moves"]
        self.menu = U.Menu([(m["slot"], m["name"].upper()[:13], not m["disabled"]) for m in moves], cols=2)

    def _open_bag(self):
        self.mode = "bag"
        items = self.s.bag_items()
        self.sub = U.Menu([((k, kind), f"{name.upper()}  x{n}") for k, name, n, kind in items] +
                          [("cancel", "CANCEL")])

    def _open_party(self, forced=False, item=None):
        self.mode = "party"
        self.forced = forced
        self.bag_item = item
        opts = []
        mons = self.s.battle.sides[0].mons
        allowed = set(self.req.get("switches", [])) if self.req else set()
        for i, m in enumerate(mons):
            if item:
                ok = m.fainted == (item[1] == "revive")
            else:
                ok = i in allowed
            opts.append((i, m.name, ok))
        if not forced:
            opts.append(("cancel", "CANCEL"))
        self.sub = U.Menu(opts)

    def handle(self, ev, pos):
        if self.mode in ("intro",):
            return
        if self.mode == "play":
            if self.text is not None and (U.is_a(ev) or U.is_b(ev)):
                self.text.next()
                if self.text.done:
                    self.text = None
            return
        if self.mode == "action":
            k = self.menu.handle(ev, pos)
            if k == "fight":
                self._open_fight()
            elif k == "bag":
                self._open_bag()
            elif k == "party":
                self._open_party()
            elif k == "run":
                self._send({"type": "run"})
        elif self.mode == "fight":
            k = self.menu.handle(ev, pos)
            if k == "back":
                self._open_action()
            elif k is not None:
                self._send({"type": "move", "slot": k, "mega": bool(getattr(self, "mega_on", False))})
            elif self.req.get("can_mega") and ev.type == pygame.KEYDOWN and ev.key in (pygame.K_m, pygame.K_c):
                self.mega_on = not getattr(self, "mega_on", False)
                AUDIO.play("select")
            elif (self.req.get("can_mega") and ev.type == pygame.MOUSEBUTTONDOWN and pos
                  and pygame.Rect(332, 294, 136, 18).collidepoint(pos)):
                self.mega_on = not getattr(self, "mega_on", False)
                AUDIO.play("select")
        elif self.mode == "bag":
            k = self.sub.handle(ev, pos)
            if k in ("back", "cancel"):
                self.sub = None
                self._open_action()
            elif k is not None:
                key, kind = k
                if kind == "ball":
                    self.sub = None
                    self._send({"type": "ball", "ball": key})
                else:
                    self._open_party(item=(key, kind))
        elif self.mode == "party":
            k = self.sub.handle(ev, pos)
            if k in ("back", "cancel"):
                if not self.forced:
                    self.sub = None
                    if self.bag_item:
                        self._open_bag()
                    else:
                        self._open_action()
            elif k is not None:
                if self.bag_item:
                    self.sub = None
                    self._send({"type": "item", "item": self.bag_item[0], "index": k})
                else:
                    self.sub = None
                    self._send({"type": "switch", "index": k})

    def _send(self, choice):
        if self.s.choose(choice):
            self.req = None
            self.menu = None
            self.sub = None
            self.mode = "play"
            for u in self.s.pump():
                self._absorb(u)
        else:
            AUDIO.play("miss", 0.5)

    # ------------------------------------------------------------------ drawing
    def draw(self, surf):
        self._background(surf)
        k = min(1.0, self.intro_t / 0.9) if self.mode == "intro" else 1.0
        e = 1 - (1 - k) ** 3
        # platforms slide in from opposite sides
        fx = FOE_AT[0] + int((1 - e) * -400)
        mx = ME_AT[0] + int((1 - e) * 400)
        self._platform(surf, fx, FOE_AT[1] - 6, 92, 20)
        self._platform(surf, mx, ME_AT[1] - 8, 110, 24)
        if self.mode == "intro" and self.s.kind != "wild":   # trainers standing on their platforms
            look = self.trainer.get("look") or "Youngster"
            img = pygame.transform.scale_by(G.person(look, "down", 0), 2)
            surf.blit(img, img.get_rect(midbottom=(fx, FOE_AT[1] - 4)))
        if self.mode == "intro" or self.hidden[0]:
            img = pygame.transform.scale_by(G.person("player", "up", 0), 2)
            surf.blit(img, img.get_rect(midbottom=(mx - (0 if self.mode == "intro" else 0), ME_AT[1])))
        self._mon(surf, 1, (fx, FOE_AT[1]), dark=self.mode == "intro" and self.intro_t < 0.9)
        self._mon(surf, 0, (mx, ME_AT[1]))
        if self.catch is not None:
            self._draw_catch(surf)
        for x, y, vx, vy, life, col in self.fx:
            pygame.draw.circle(surf, col, (int(x), int(y)), max(1, int(life * 10)))
        if self.mode != "intro":
            if self.vis[1] and self.faint[1] < 1 and not (self.catch and self.catch.get("caught")):
                self._foe_box(surf)
            if self.vis[0] and self.faint[0] < 1:
                self._my_box(surf)
        self._bottom(surf)

    def _background(self, surf):
        kind = self.trainer.get("arena") or {"gym": "gym", "champion": "league"}.get(self.s.kind, "grass")
        surf.blit(G.battle_bg(kind), (0, 0))

    def _platform(self, surf, x, y, rx, ry):
        kind = self.trainer.get("arena") or {"gym": "gym", "champion": "league"}.get(self.s.kind, "grass")
        img = G.platform(kind, mine=rx > 100)
        surf.blit(img, img.get_rect(center=(x, y + 4)))

    def _mon(self, surf, side, at, dark=False):
        v = self.vis[side] if not self.hidden[side] else None
        if side == 1 and self.s.kind == "wild" and v is None and self.state:   # the wild one is there from the start
            m = self.s.battle.sides[1].mons[0]
            v = {"pid": m.entry["id"], "shiny": self.s.foes[0].get("shiny")}
        if v is None:
            return
        if self.blink[side] > 0 and int(self.blink[side] * 16) % 2:
            return
        if side == 1 and self.catch is not None and self.catch["t"] > 0.5 and not \
                (self.catch["broke"] is not None and self.catch["t"] - self.catch["broke"] > 0.1):
            return
        img = G.battle_sprite(v["pid"], back=side == 0, shiny=v.get("shiny", False), max_h=150 if side == 0 else 128)
        if dark:
            img = img.copy()
            img.fill((40, 40, 56), special_flags=pygame.BLEND_RGB_MIN)
        g = self.grow[side]
        if g < 1:
            img = pygame.transform.scale(img, (max(1, int(img.get_width() * g)), max(1, int(img.get_height() * g))))
        x, y = at
        lunge = math.sin(self.lunge[side] / 0.25 * math.pi) * 14 if self.lunge[side] > 0 else 0
        x += lunge if side == 0 else -lunge
        r = img.get_rect(midbottom=(x, y))
        if self.faint[side] > 0:   # slides down out of view
            drop = int(self.faint[side] * img.get_height())
            clip = surf.get_clip()
            surf.set_clip(pygame.Rect(0, 0, VW, y))
            surf.blit(img, r.move(0, drop))
            surf.set_clip(clip)
            return
        if g < 1:
            flash = pygame.Surface(img.get_size(), pygame.SRCALPHA)
            flash.fill((255, 255, 255, int(255 * (1 - g))))
            img = img.copy()
            img.blit(flash, (0, 0), special_flags=pygame.BLEND_RGBA_MAX)
        surf.blit(img, r)

    def _status_tag(self, surf, x, y, status):
        if status in STATUS_TAGS:
            label, col = STATUS_TAGS[status]
            pygame.draw.rect(surf, col, (x, y, 30, 12), border_radius=3)
            F.draw(surf, label, (x + 4, y), (248, 248, 248), None, scale=1)

    def _foe_box(self, surf):
        v = self.vis[1]
        r = pygame.Rect(10, 30, 214, 52)     # FireRed: opponent box centred near (44,30) at 1x
        pygame.draw.rect(surf, (64, 72, 64), r, border_radius=6)
        pygame.draw.rect(surf, (248, 248, 216), r.inflate(-4, -4), border_radius=5)
        pygame.draw.polygon(surf, (64, 72, 64), [(r.right - 6, r.bottom - 2), (r.right + 10, r.bottom - 2),
                                                  (r.right - 6, r.y + 22)])
        F.draw(surf, v["name"].upper()[:11], (r.x + 10, r.y + 6), U.TEXT, U.SHADOW)
        F.draw(surf, f"Lv{v['level']}", (r.right - 52, r.y + 6), U.TEXT, U.SHADOW)
        if self.s.kind == "wild" and self.s.foes[0]["species"] in self.g["caught"]:
            U.ball(surf, (r.x + 8, r.y + 38), 4)
        U.hp_bar(surf, r.x + 64, r.y + 32, 116, self.frac.get((1, v["idx"]), 1.0))
        self._status_tag(surf, r.x + 22, r.y + 31, v.get("status"))

    def _my_box(self, surf):
        v = self.vis[0]
        r = pygame.Rect(232, 140, 222, 76)   # FireRed: player box centred near (158,88) at 1x
        pygame.draw.rect(surf, (64, 72, 64), r, border_radius=6)
        pygame.draw.rect(surf, (248, 248, 216), r.inflate(-4, -4), border_radius=5)
        F.draw(surf, v["name"].upper()[:11], (r.x + 14, r.y + 6), U.TEXT, U.SHADOW)
        F.draw(surf, f"Lv{v['level']}", (r.right - 52, r.y + 6), U.TEXT, U.SHADOW)
        frac = self.frac.get((0, v["idx"]), 1.0)
        U.hp_bar(surf, r.x + 66, r.y + 30, 120, frac)
        self._status_tag(surf, r.x + 26, r.y + 29, v.get("status"))
        bm = self.s.battle.sides[0].mons[v["idx"]]
        F.draw(surf, f"{max(0, round(bm.maxhp * frac))}/ {bm.maxhp}", (r.right - 14, r.y + 42), U.TEXT, U.SHADOW,
               anchor="topright")
        ef = self.exp_shown[1] if self.exp_shown and self.exp_shown[0] == v["idx"] else self._exp_frac(v["idx"])
        F.draw(surf, "EXP", (r.x + 28, r.y + 62), (96, 104, 120), None, scale=1)
        U.exp_bar(surf, r.x + 52, r.y + 64, 160, ef)

    def _bottom(self, surf):
        r = pygame.Rect(0, 240, VW, 80)
        pygame.draw.rect(surf, (48, 48, 56), r)
        pygame.draw.rect(surf, (200, 168, 88), r.inflate(-6, -6), border_radius=6)
        pygame.draw.rect(surf, U.NAVY, r.inflate(-12, -12), border_radius=5)
        if self.mode == "play" and self.text is not None:
            self.text.draw(surf, self.t, rect=r, dark=True)
        elif self.mode == "action":
            name = self.vis[0]["name"].upper() if self.vis[0] else ""
            F.draw(surf, "What will", (20, 256), U.WHITE, (96, 104, 128))
            F.draw(surf, f"{name} do?", (20, 282), U.WHITE, (96, 104, 128))
            self.menu.draw(surf, (VW - 216, 240, 216, 80), row_h=28, border=(112, 104, 144))
        elif self.mode == "fight":
            self.menu.draw(surf, (0, 240, 320, 80), row_h=28, border=(112, 104, 144))
            m = self.req["moves"][self.menu.index] if self.menu.index < len(self.req["moves"]) else None
            inner = U.box(surf, (320, 240, 160, 80), border=(112, 104, 144))
            if m:
                F.draw(surf, "PP", (inner.x + 8, inner.y + 6), U.TEXT, U.SHADOW)
                col = (232, 72, 64) if m["pp"] == 0 else (224, 160, 48) if m["pp"] <= m["maxpp"] // 4 else U.TEXT
                F.draw(surf, f"{m['pp']}/{m['maxpp']}", (inner.right - 10, inner.y + 6), col, U.SHADOW,
                       anchor="topright")
                ty = inner.y + (24 if self.req.get("can_mega") else 32)
                F.draw(surf, f"TYPE/{m['type'].upper()}", (inner.x + 8, ty), U.TEXT, U.SHADOW)
            if self.req.get("can_mega"):   # the Key Stone glows: M to Mega Evolve with this move
                on = getattr(self, "mega_on", False)
                b = pygame.Rect(332, 294, 136, 18)
                glow = 0.5 + 0.5 * math.sin(self.t * 6)
                pygame.draw.rect(surf, (120 + int(100 * glow), 72, 200) if on else (88, 88, 104), b,
                                 border_radius=6)
                pygame.draw.rect(surf, (255, 232, 140) if on else (160, 160, 176), b, 2, border_radius=6)
                F.draw(surf, "MEGA: ON" if on else "M: MEGA", b.center, U.WHITE, None, scale=1, anchor="center")
        if self.mode in ("bag", "party") and self.sub is not None:
            self._overlay(surf)

    def _overlay(self, surf):
        U.fade(surf, 0.35)
        if self.mode == "bag":
            n = len(self.sub.options)
            self.sub.draw(surf, (VW - 260, 8, 252, min(VH - 16, 20 + 26 * n)))
            F.draw(surf, "Choose an item.", (16, 268), U.WHITE, (96, 104, 128))
            return
        # party: one row per Pokemon with icon, HP bar, level
        mons = self.s.battle.sides[0].mons
        title = "Choose a POKeMON." if not self.bag_item else "Use on which POKeMON?"
        rows = len(self.sub.options)
        inner = U.box(surf, (24, 6, VW - 48, 34 + 36 * rows))
        self.sub.rects = []
        for i, o in enumerate(self.sub.options):
            y = inner.y + 4 + i * 36
            rr = pygame.Rect(inner.x + 4, y, inner.w - 8, 34)
            self.sub.rects.append(rr)
            sel = i == self.sub.index
            if sel:
                pygame.draw.rect(surf, (216, 232, 248), rr, border_radius=4)
                pygame.draw.rect(surf, (224, 96, 88), rr, 2, border_radius=4)
            if o[0] == "cancel":
                F.draw(surf, "CANCEL", (rr.x + 40, rr.y + 10), U.TEXT, U.SHADOW)
                continue
            m = mons[o[0]]
            p = self.g["party"][o[0]]
            icon = G.icon(p["species"], p.get("shiny", False))
            surf.blit(icon, icon.get_rect(midleft=(rr.x + 2, rr.centery)))
            col = U.TEXT if (len(o) < 3 or o[2]) else (168, 168, 168)
            F.draw(surf, A.name_of(self.dex, p).upper()[:11], (rr.x + 48, rr.y + 4), col, U.SHADOW)
            F.draw(surf, f"Lv{m.member.level}", (rr.x + 48, rr.y + 20), col, U.SHADOW, scale=1)
            U.hp_bar(surf, rr.x + 200, rr.y + 8, 120, m.hp / m.maxhp)
            F.draw(surf, f"{m.hp}/{m.maxhp}", (rr.right - 8, rr.y + 6), col, U.SHADOW, anchor="topright")
            if m.fainted:
                F.draw(surf, "FNT", (rr.x + 120, rr.y + 20), (224, 64, 64), None, scale=1)
            elif m.status in STATUS_TAGS:
                self._status_tag(surf, rr.x + 120, rr.y + 20, m.status)
        F.draw(surf, title, (16, 268), U.WHITE, (96, 104, 128))

    def _draw_catch(self, surf):
        c = self.catch
        t = c["t"]
        fx, fy = FOE_AT[0], FOE_AT[1] - 50
        if t < 0.5:                     # the throw
            p = t / 0.5
            x = 60 + (fx - 60) * p
            y = 230 + (fy - 230) * p - math.sin(p * math.pi) * 110
            U.ball(surf, (int(x), int(y)), 7)
            return
        if c["broke"] is not None and t - c["broke"] > 0.25:
            self.catch = None
            return
        if t < 0.8:                     # the beam that pulls it in
            q = (t - 0.5) / 0.3
            pygame.draw.circle(surf, (255, 200, 220), (fx, fy), int(30 * (1 - q)) + 2, 2)
        drop = min(1.0, max(0.0, (t - 0.7) / 0.2))
        y = fy + int(drop * 44) - int(abs(math.sin(drop * math.pi * 2)) * 12 * (1 - drop))
        x = fx
        st = c.get("shake_t")
        if st is not None and c["broke"] is None:
            q = t - st - 0.2
            n = int(q // 0.8) if q > 0 else -1
            if 0 <= n < c["shakes"] and (q % 0.8) < 0.4:
                x += int(math.sin((q % 0.8) / 0.4 * math.tau) * 5)
        if c["broke"] is not None:
            q = (t - c["broke"]) / 0.25
            pygame.draw.circle(surf, (255, 255, 255), (fx, y), int(10 + 40 * q), 3)
            return
        U.ball(surf, (int(x), int(y)), 7)
        if c["caught"] and st is not None and t - st > 0.2 + 0.8 * c["shakes"]:
            for k in range(3):
                a = -math.pi / 2 + (k - 1) * 0.8
                pygame.draw.circle(surf, (248, 216, 64), (int(fx + math.cos(a) * 18), int(y + math.sin(a) * 18)), 2)
            dim = pygame.Surface((14, 14), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 60))
            surf.blit(dim, (fx - 7, y - 7))

    def close(self):
        pass
