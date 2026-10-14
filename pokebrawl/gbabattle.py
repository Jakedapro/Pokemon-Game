"""Adventure battles, GBA style: the foe on its platform top-right with its HP box top-left, your Pokemon's back
on the bottom-left with HP numbers and the EXP bar, the message box along the bottom and the FIGHT / BAG /
POKeMON / RUN menu. Experience is handed out right after each knockout, with level-ups mid-battle.

Driven by AdventureSession (the same battle engine as the rest of the game)."""
import math
import random

import pygame

from . import adventure as A
from . import battlegfx as BG
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
        self.arena = self._arena()
        self.real = BG.terrain(self.arena) is not None and BG.box("message") is not None
        # FireRed: the foe's sprite is centred at (176, 40), yours at (72, 80), at 1x
        self.foe_at, self.me_at = ((352, 144), (144, 224)) if self.real else (FOE_AT, ME_AT)
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
                    if m.get("shiny"):
                        self._shine(1)
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
            if self.anim["kind"] == "mega":
                self._mega_tick()
            if self.anim["t"] >= self.anim["dur"]:
                self.anim = None
        if self.text is None and self.anim is None:
            if self.queue:
                text, a = self.queue.pop(0)
                if a and a[0] == "mega" and text:   # the build-up first, the result after the reveal
                    self.queue.insert(0, [text, None])
                    text = self._mega_line(a)
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
            if src.get("shiny") and not (side == 1 and self.s.kind == "wild"):
                self._shine(side)
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
            self.catch = {"t": 0.0, "shakes": 0, "caught": False, "broke": None, "shake_t": None,
                          "ball": a[2] if len(a) > 2 else "poke-ball"}
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
        elif kind == "mega":   # the full sequence plays out in _mega_tick / _draw_mega
            side, pid = a[1], a[2]
            AUDIO.play("tera", 0.9)
            self.anim = {"kind": "mega", "t": 0, "dur": 2.6, "side": side, "pid": pid,
                         "name": self.s.battle.sides[side].mon.name, "swapped": False}
            if A.OPTS.get("scene") == "OFF":   # BATTLE SCENE: OFF - straight to the result
                self.anim.update(t=1.69, dur=1.9)
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
        x, y = self.foe_at if side == 1 else self.me_at
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

    def _arena(self):
        """Which FireRed battle background this fight gets."""
        tid = str(self.trainer.get("id", ""))
        if self.trainer.get("rift"):
            return "agatha"   # the dark violet arena inside a rift
        if tid.startswith("e4_"):
            return ["lorelei", "bruno", "agatha", "lance"][int(tid[3]) % 4]
        if tid in ("final", "creator") or self.s.kind == "champion":
            return "champion"
        if self.s.kind == "gym":
            return "leader"
        if tid.startswith("gym"):
            return "gym"
        if self.g.get("room"):
            return "building"
        if self.g.get("area", 0) == 17:   # Victory Road
            return "cave"
        return "grass"

    # ------------------------------------------------------------------ drawing
    def draw(self, surf):
        if self.real:
            self._draw_real(surf)
            return
        self._background(surf)
        k = min(1.0, self.intro_t / 0.9) if self.mode == "intro" else 1.0
        e = 1 - (1 - k) ** 3
        # platforms slide in from opposite sides
        fx = self.foe_at[0] + int((1 - e) * -400)
        mx = self.me_at[0] + int((1 - e) * 400)
        self._platform(surf, fx, self.foe_at[1] - 6, 92, 20)
        self._platform(surf, mx, self.me_at[1] - 8, 110, 24)
        if self.mode == "intro" and self.s.kind != "wild":   # trainers standing on their platforms
            look = self.trainer.get("look") or "Youngster"
            img = pygame.transform.scale_by(G.person(look, "down", 0), 2)
            surf.blit(img, img.get_rect(midbottom=(fx, self.foe_at[1] - 4)))
        if self.mode == "intro" or self.hidden[0]:
            img = pygame.transform.scale_by(G.person("player", "up", 0), 2)
            surf.blit(img, img.get_rect(midbottom=(mx - (0 if self.mode == "intro" else 0), self.me_at[1])))
        self._mon(surf, 1, (fx, self.foe_at[1]), dark=self.mode == "intro" and self.intro_t < 0.9)
        self._mon(surf, 0, (mx, self.me_at[1]))
        if self.catch is not None:
            self._draw_catch(surf)
        self._draw_mega(surf)
        self._draw_shine(surf)
        for x, y, vx, vy, life, col in self.fx:
            pygame.draw.circle(surf, col, (int(x), int(y)), max(1, int(life * 10)))
        if self.mode != "intro":
            if self.vis[1] and self.faint[1] < 1 and not (self.catch and self.catch.get("caught")):
                self._foe_box(surf)
            if self.vis[0] and self.faint[0] < 1:
                self._my_box(surf)
        self._bottom(surf)

    def _draw_real(self, surf):
        """The FireRed battle screen: real background (with its bases), boxes and pictures."""
        surf.blit(BG.terrain(self.arena), (0, 0))
        k = min(1.0, self.intro_t / 0.9) if self.mode == "intro" else 1.0
        e = 1 - (1 - k) ** 3
        fx = self.foe_at[0] + int((1 - e) * -400)
        mx = self.me_at[0] + int((1 - e) * 400)
        if self.mode == "intro" and self.s.kind != "wild":   # the trainer, in their battle picture
            look = self.trainer.get("look") or "Youngster"
            img = BG.trainer_pic(look)
            if img is None:
                img = pygame.transform.scale_by(G.person(look, "down", 0), 2)
            surf.blit(img, img.get_rect(midbottom=(fx, self.foe_at[1] + 8)))
        if self.mode == "intro" or self.hidden[0]:
            img = BG.player_back(0) or pygame.transform.scale_by(G.person("player", "up", 0), 2)
            surf.blit(img, img.get_rect(midbottom=(mx, self.me_at[1])))
        self._mon(surf, 1, (fx, self.foe_at[1]), dark=self.mode == "intro" and self.intro_t < 0.9)
        self._mon(surf, 0, (mx, self.me_at[1]))
        if self.catch is not None:
            self._draw_catch(surf)
        self._draw_mega(surf)
        self._draw_shine(surf)
        for x, y, vx, vy, life, col in self.fx:
            pygame.draw.circle(surf, col, (int(x), int(y)), max(1, int(life * 10)))
        if self.mode != "intro":
            if self.vis[1] and self.faint[1] < 1 and not (self.catch and self.catch.get("caught")):
                self._foe_box_real(surf)
            if self.vis[0] and self.faint[0] < 1:
                self._my_box_real(surf)
        self._bottom_real(surf)

    def _foe_box_real(self, surf):
        v = self.vis[1]
        x, y = 26, 32                               # FireRed: the box's corner at (13, 16)
        ink, shade = (64, 64, 64), (216, 208, 176)
        surf.blit(BG.healthbox(1), (x, y))
        self._mega_mark(surf, v, x + 166, y + 19)
        if v.get("shiny"):   # a shiny gets a star on its box
            self._star(surf, x + 8, y + 22)
        F.draw(surf, self._short(v["name"]).upper()[:9], (x + 16, y + 10), ink, shade, small=True)
        F.draw(surf, str(v["level"]), (x + 128, y + 10), ink, shade, small=True)   # right after the box's own "Lv"
        if self.s.kind == "wild" and self.s.foes[0]["species"] in self.g["caught"]:
            U.ball(surf, (x + 14, y + 38), 4)
        U.hp_bar(surf, x + 54, y + 34, 96, self.frac.get((1, v["idx"]), 1.0))
        self._status_tag(surf, x + 22, y + 33, v.get("status"))

    def _my_box_real(self, surf):
        v = self.vis[0]
        x, y = 252, 148                             # FireRed: (126, 74)
        ink, shade = (64, 64, 64), (216, 208, 176)
        surf.blit(BG.healthbox(0), (x, y))
        self._mega_mark(surf, v, x + 182, y + 19)
        if v.get("shiny"):   # a shiny gets a star on its box
            self._star(surf, x + 24, y + 22)
        F.draw(surf, self._short(v["name"]).upper()[:9], (x + 32, y + 10), ink, shade, small=True)
        F.draw(surf, str(v["level"]), (x + 144, y + 10), ink, shade, small=True)
        frac = self.frac.get((0, v["idx"]), 1.0)
        U.hp_bar(surf, x + 70, y + 32, 96, frac)
        self._status_tag(surf, x + 36, y + 31, v.get("status"))
        bm = self.s.battle.sides[0].mons[v["idx"]]
        F.draw(surf, str(max(0, round(bm.maxhp * frac))), (x + 126, y + 46), ink, shade, anchor="topright", small=True)
        F.draw(surf, str(bm.maxhp), (x + 142, y + 46), ink, shade, small=True)   # either side of the box's own "/"
        ef = self.exp_shown[1] if self.exp_shown and self.exp_shown[0] == v["idx"] else self._exp_frac(v["idx"])
        w = int(128 * max(0.0, min(1.0, ef)))
        if w:
            pygame.draw.rect(surf, (64, 200, 248), (x + 64, y + 70, w, 4))

    @staticmethod
    def _short(name):
        return name[5:] if name.startswith("Mega ") else name

    def _mega_mark(self, surf, v, cx, cy):
        """A little rainbow Mega mark on the healthbox of a Mega Evolved Pokemon."""
        if not v["name"].startswith("Mega "):
            return
        cols = [(255, 96, 96), (255, 184, 64), (255, 240, 96), (96, 224, 120), (96, 176, 255), (184, 120, 255)]
        for i, col in enumerate(cols):
            pygame.draw.arc(surf, col, (cx - 8, cy - 8, 16, 16), i * math.tau / 6, (i + 1) * math.tau / 6, 3)
        pygame.draw.polygon(surf, (120, 64, 200), [(cx, cy - 4), (cx + 3, cy), (cx, cy + 4), (cx - 3, cy)])

    def _bottom_real(self, surf):
        top = VH - 96
        if self.mode == "action":
            surf.blit(BG.box("action"), (0, top))
            name = self.vis[0]["name"].upper() if self.vis[0] else ""
            F.draw(surf, "What will", (22, top + 18), U.WHITE, (104, 88, 112))
            F.draw(surf, f"{name} do?", (22, top + 50), U.WHITE, (104, 88, 112))
            self.menu.draw(surf, (256, top + 12, 220, 76), row_h=32, col_w=104, bare=True)
        elif self.mode == "fight":
            surf.blit(BG.box("move"), (0, top))
            self.menu.draw(surf, (4, top + 12, 316, 76), row_h=32, col_w=150, bare=True)
            m = self.req["moves"][self.menu.index] if self.menu.index < len(self.req["moves"]) else None
            if m:
                F.draw(surf, "PP", (338, top + 18), U.TEXT, U.SHADOW)
                col = (232, 72, 64) if m["pp"] == 0 else (224, 160, 48) if m["pp"] <= m["maxpp"] // 4 else U.TEXT
                F.draw(surf, f"{m['pp']}/{m['maxpp']}", (464, top + 18), col, U.SHADOW, anchor="topright")
                F.draw(surf, f"TYPE/{m['type'].upper()}", (338, top + 50), U.TEXT, U.SHADOW)
            if self.req.get("can_mega"):
                on = getattr(self, "mega_on", False)
                F.draw(surf, "MEGA: ON (M)" if on else "M: MEGA", (VW - 8, top - 18),
                       (255, 216, 96) if on else U.WHITE, (48, 40, 72), scale=1, anchor="topright")
        else:
            surf.blit(BG.box("message"), (0, top))
            if self.mode == "play" and self.text is not None:
                self.text.draw(surf, self.t, rect=(12, top + 12, 440, 76), dark=True, bare=True, line_h=32)
        if self.mode in ("bag", "party") and self.sub is not None:
            self._overlay(surf)

    def _background(self, surf):
        kind = self.trainer.get("arena") or {"gym": "gym", "champion": "league"}.get(self.s.kind, "grass")
        surf.blit(G.battle_bg(kind), (0, 0))

    def _platform(self, surf, x, y, rx, ry):
        kind = self.trainer.get("arena") or {"gym": "gym", "champion": "league"}.get(self.s.kind, "grass")
        img = G.platform(kind, mine=rx > 100)
        surf.blit(img, img.get_rect(center=(x, y + 4)))

    # ------------------------------------------------------------------ shinies
    def _shine(self, side):
        """The shiny sparkle: stars burst around it, with the chime."""
        if A.OPTS.get("scene") == "OFF":
            return
        self.__dict__.setdefault("shines", {})[side] = self.t
        AUDIO.play("tera", 0.5)

    def _draw_shine(self, surf):
        for side, t0 in list(self.__dict__.get("shines", {}).items()):
            k = self.t - t0 - 0.35
            if k < 0:
                continue
            if k > 1.3:
                del self.shines[side]
                continue
            x, y = self.foe_at if side == 1 else self.me_at
            cy = y - 64
            for i in range(8):
                ang = i * math.tau / 8 + k * 2
                r = 20 + k * 60
                px, py = int(x + math.cos(ang) * r), int(cy + math.sin(ang) * r * 0.8)
                size = max(1, int(7 * (1 - k / 1.3)))
                col = (255, 248, 168) if i % 2 else (255, 255, 255)
                pygame.draw.line(surf, col, (px - size, py), (px + size, py), 2)
                pygame.draw.line(surf, col, (px, py - size), (px, py + size), 2)

    @staticmethod
    def _star(surf, cx, cy):
        pts = [(cx + math.cos(a) * (6 if i % 2 == 0 else 3), cy + math.sin(a) * (6 if i % 2 == 0 else 3))
               for i, a in enumerate(-math.pi / 2 + k * math.pi / 5 for k in range(10))]
        pygame.draw.polygon(surf, (248, 200, 48), pts)
        pygame.draw.polygon(surf, (152, 96, 16), pts, 1)

    # ------------------------------------------------------------------ Mega Evolution
    def _mega_line(self, a):
        from . import story as S
        side, pid = a[1], a[2]
        v = self.vis[side]
        mon = v["name"] if v else "It"
        stone = S.stone_name(self.dex, self.dex.all[pid]["key"]) if pid in self.dex.all else "Mega Stone"
        who = self.g["name"] if side == 0 else self.trainer.get("name", "the trainer")
        return f"{mon}'s {stone} is reacting to {who}'s Key Stone!"

    def _mega_tick(self):
        a = self.anim
        if a["t"] >= 1.7 and not a["swapped"]:   # the flash: it comes out Mega Evolved
            a["swapped"] = True
            v = self.vis[a["side"]]
            if v:
                v["pid"] = a["pid"]
                v["name"] = a["name"]
            AUDIO.play("hit_super", 0.8)
            AUDIO.cry(a["pid"], 1.0)
            for col in ((255, 240, 160), (200, 120, 255), (120, 220, 255), (255, 255, 255)):
                self._burst(a["side"], col)

    def _mega_phase(self, side):
        """'orb' while it's wrapped in light (drawn as a white silhouette), else None."""
        a = self.anim
        if a and a.get("kind") == "mega" and a["side"] == side and 0.7 <= a["t"] < 1.7:
            return "orb"
        return None

    def _draw_mega(self, surf):
        a = self.anim
        if not a or a.get("kind") != "mega":
            return
        t, side = a["t"], a["side"]
        x, y = self.foe_at if side == 1 else self.me_at
        cy = y - 60
        rainbow = [(255, 96, 96), (255, 184, 64), (255, 240, 96), (96, 224, 120), (96, 176, 255), (184, 120, 255)]
        if t < 1.7:   # the world goes dark around it
            shade = pygame.Surface((VW, VH), pygame.SRCALPHA)
            shade.fill((16, 8, 40, int(150 * min(1.0, t / 0.4))))
            surf.blit(shade, (0, 0))
        if t < 0.8:   # rainbow light pours in from the Key Stone / Mega Stone
            k = t / 0.8
            for i, col in enumerate(rainbow):
                ang = self.t * 4 + i * math.tau / 6
                r = int(220 * (1 - k)) + 18
                pygame.draw.circle(surf, col, (int(x + math.cos(ang) * r), int(cy + math.sin(ang) * r * 0.7)), 6)
            if side == 0:   # your Key Stone glints on your wrist (by the healthbox)
                pygame.draw.circle(surf, (255, 255, 255), (300, 200), int(4 + 4 * math.sin(self.t * 20)))
        elif t < 1.7:   # wrapped in a pulsing orb, a helix of light spinning around it
            k = (t - 0.8) / 0.9
            rad = int(54 + 10 * math.sin(t * 14))
            glow = pygame.Surface((rad * 2 + 8, rad * 2 + 8), pygame.SRCALPHA)
            pygame.draw.circle(glow, (255, 255, 255, 70), (rad + 4, rad + 4), rad)
            pygame.draw.circle(glow, (220, 200, 255, 200), (rad + 4, rad + 4), rad, 3)
            surf.blit(glow, (x - rad - 4, cy - rad - 4))
            for i in range(12):
                ang = self.t * 6 + i * math.tau / 12
                hx = x + math.cos(ang) * (rad + 6)
                hy = cy + math.sin(ang * 2) * 30 * (1 - k * 0.5)
                pygame.draw.circle(surf, rainbow[i % 6], (int(hx), int(hy)), 4)
        else:   # the flash, then the Mega symbol over its head
            k = (t - 1.7) / 0.9
            if k < 0.25:
                flash = pygame.Surface((VW, VH), pygame.SRCALPHA)
                flash.fill((255, 255, 255, int(255 * (1 - k / 0.25))))
                surf.blit(flash, (0, 0))
            sy = cy - 80 - int(10 * k)
            alpha = 255 if k < 0.7 else int(255 * (1 - (k - 0.7) / 0.3))
            sym = pygame.Surface((60, 60), pygame.SRCALPHA)
            pygame.draw.circle(sym, (255, 255, 255, alpha), (30, 30), 26)
            for i, col in enumerate(rainbow):   # the Mega mark: a rainbow ring around a white core
                pygame.draw.arc(sym, col + (alpha,), (4, 4, 52, 52), i * math.tau / 6, (i + 1) * math.tau / 6, 6)
            pygame.draw.polygon(sym, (120, 64, 200, alpha), [(30, 12), (42, 30), (30, 48), (18, 30)])
            pygame.draw.polygon(sym, (255, 255, 255, alpha), [(30, 20), (36, 30), (30, 40), (24, 30)])
            surf.blit(sym, (x - 30, sy))

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
        if self._mega_phase(side) == "orb":
            img = img.copy()
            img.fill((255, 255, 255), special_flags=pygame.BLEND_RGB_MAX)
            at = (at[0], at[1] - int(abs(math.sin(self.t * 10)) * 6))
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
        fx, fy = self.foe_at[0], self.foe_at[1] - 50
        if t < 0.5:                     # the throw
            p = t / 0.5
            x = 60 + (fx - 60) * p
            y = 230 + (fy - 230) * p - math.sin(p * math.pi) * 110
            self._ball(surf, int(x), int(y), int(t * 12) % 2 + (1 if self.real else 0))
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
        self._ball(surf, int(x), int(y), 0)
        if c["caught"] and st is not None and t - st > 0.2 + 0.8 * c["shakes"]:
            for k in range(3):
                a = -math.pi / 2 + (k - 1) * 0.8
                pygame.draw.circle(surf, (248, 216, 64), (int(fx + math.cos(a) * 18), int(y + math.sin(a) * 18)), 2)
            dim = pygame.Surface((14, 14), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 60))
            surf.blit(dim, (fx - 7, y - 7))

    def _ball(self, surf, x, y, frame):
        img = BG.ball(self.catch.get("ball", "poke-ball") if self.catch else "poke-ball", 0) if self.real else None
        if img is None:
            U.ball(surf, (x, y), 7)
            return
        if frame:
            img = pygame.transform.rotate(img, -90 * frame)
        surf.blit(img, img.get_rect(center=(x, y)))

    def close(self):
        pass
