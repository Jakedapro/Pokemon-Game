"""Turn-based (Showdown-style) battle screen."""
import math

import pygame

from . import gfx, ui
from .app import Scene
from .audio import AUDIO
from .battle_common import BattleExtras, draw_rank_change
from .battlecore import STATUS_NAMES
from .cinematics import ARCEUS_JUDGMENT, AttackFX, Finisher, Gigantamax, Judgment, MegaEvolution
from .gfx import H, INK, SPRITES, W, WHITE
from .render import STATUS_COLORS
from .types import effectiveness

CLS_NAMES = {"phys": "PHYSICAL", "spec": "SPECIAL", "status": "STATUS"}
EFF_TEXT = {0.0: ("NO EFFECT", (150, 150, 150)), 0.25: ("RESISTED x1/4", (200, 120, 110)),
            0.5: ("RESISTED", (230, 150, 130)), 2.0: ("SUPER EFFECTIVE", (120, 255, 140)),
            4.0: ("SUPER EFFECTIVE x4", (120, 255, 200))}


def type_pills(surf, types, x, y, size=13, right=False):
    """A row of type badges starting at x (or ending at x when right=True). Returns the row's width."""
    f = gfx.font(size, False)
    widths = [f.size(t.upper())[0] + 12 for t in types]
    total = sum(widths) + 4 * max(0, len(types) - 1)
    cx = x - total if right else x
    for t, w in zip(types, widths):
        gfx.pill(surf, t.upper(), (cx + w / 2, y), gfx.type_color(t, 0), size)
        cx += w + 4
    return total

FOE_POS = (510, 440)
MY_POS = (220, 780)


class TurnBattleScene(Scene):
    def __init__(self, app, session):
        super().__init__(app)
        self.s = session
        self.me = session.my_side
        self.foe = 1 - self.me
        self.bg = gfx.turn_background()
        self.state = None
        self.req = None
        self.queue = []          # log entries waiting to be shown
        self.cur = None
        self.cur_t = 0.0
        self.msg = ""
        self.history = []
        self.vis = {0: {}, 1: {}}  # displayed id/frac/status per side
        self.shake = {0: 0.0, 1: 0.0}
        self.flash = {0: 0.0, 1: 0.0}
        self.faint = {0: 0.0, 1: 0.0}
        self.mega_on = False      # a gimmick is selected for the next move
        self.gimmick = "mega"     # which one: mega / gmax / tera (the button cycles through what's available)
        self.ability_pop = None
        self.finisher = None     # knockout cutscene playing right now
        self.last_move = None
        self.attack = None       # (AttackFX, start time) for the move being shown
        self.sendout = {}        # side -> seconds since its Poke Ball was thrown
        self.hp_shown = {}       # side -> HP fraction the bar shows (drains smoothly)
        self.waiting = False
        self.t = 0.0
        self.buttons = []
        self.move_btns = []
        self.party_btns = []
        self.mega_btn = None
        self.x = BattleExtras(app, session, 798)
        self.end_btns = self.x.end_buttons(640)
        self.timer = None  # online: seconds left to choose
        self.pending_updates = []

    def close(self):
        self.s.close()

    # ------------------------------------------------------------------ state flow
    def _sync_vis(self):
        if not self.state:
            return
        for side in (0, 1):
            sd = self.state["sides"][side]
            if sd["active"] is None:
                continue
            m = sd["mons"][sd["active"]]
            self.vis[side] = {"id": m["id"], "frac": m["frac"], "status": m["status"], "name": m["name"],
                              "idx": sd["active"], "fainted": m["fainted"],
                              "tera": m.get("tera") if m.get("terastallized") else None}
            if not m["fainted"]:
                self.faint[side] = 0.0

    def update(self, dt):
        if self.t == 0:
            AUDIO.music("battle")
        self.t += dt
        if self._finished() and self.state and self.state["over"]:
            self.x.finish(self.state["winner"])
            self.end_btns = self.x.end_buttons(640)
            if self.x.check_rematch():
                return
        if self.s.online and self.req and not self._busy():
            if self.timer is None:
                self.timer = 60.0
            self.timer -= dt
            if self.timer <= 0:
                self._send(self._auto_choice())
        else:
            self.timer = None
        if self.ability_pop:
            self.ability_pop[2] -= dt
            if self.ability_pop[2] <= 0:
                self.ability_pop = None
        for side in (0, 1):
            self.shake[side] = max(0.0, self.shake[side] - dt)
            self.flash[side] = max(0.0, self.flash[side] - dt)
            if 0 < self.faint[side] <= 0.6:  # time-based so it always finishes before the next Pokemon comes out
                self.faint[side] += dt * 1.5
            if side in self.sendout:
                self.sendout[side] += dt
            v = self.vis.get(side)
            if v and "frac" in v:  # HP bars drain instead of jumping
                cur = self.hp_shown.get(side, v["frac"])
                step = dt * 0.9
                self.hp_shown[side] = v["frac"] if abs(cur - v["frac"]) <= step else \
                    cur + step * (1 if v["frac"] > cur else -1)
        for u in self.s.pump():
            self.pending_updates.append(u)
        if self.finisher is not None:  # the knockout cutscene holds the battle log until it's done
            self.finisher.update(dt)
            if self.finisher.done:
                self.finisher = None
            self._layout()
            return
        # play log entries one by one
        if self.cur is None and not self.queue and self.pending_updates:
            u = self.pending_updates.pop(0)
            self.queue = list(u["log"])
            self._next_state = u
            if self.state is None:
                self.state = u["state"]
                self._sync_vis()
        if self.cur is None and self.queue:
            self.cur = self.queue.pop(0)
            self.cur_t = 0.0
            self._apply_anim(self.cur.get("a"))
            if self.cur["t"]:
                self.msg = self.cur["t"]
                self.history.append(self.cur["t"])
        if self.attack is not None:
            self.attack[1] += dt * getattr(self, "anim_speed", 1.0)
            if self.attack[1] > 0.7:
                self.attack = None
        if self.cur is not None:
            self.cur_t += dt
            a = self.cur.get("a") or [None]
            dur = 0.95 if self.cur["t"] else 0.45
            if a[0] == "turn":
                dur = 0.3
            dur /= getattr(self, "anim_speed", 1.0)
            if self.cur_t >= dur:
                self.cur = None
        elif not self.queue and getattr(self, "_next_state", None):
            u = self._next_state
            self._next_state = None
            self.state = u["state"]
            self.req = u["req"]
            self.waiting = False
            self._sync_vis()
            self.mega_on = False
            if self.req and self.req["kind"] in ("lead", "switch"):
                self.msg = "Choose your lead Pokemon!" if self.req["kind"] == "lead" else "Choose a Pokemon to send out!"
            elif self.req:
                name = self.vis[self.me].get("name", "")
                self.msg = f"What will {name} do?"
            elif not self.state["over"]:
                self.msg = "Waiting for your opponent..."
        self._layout()

    def _apply_anim(self, a):
        if not a:
            return
        kind = a[0]
        snd = {"miss": "miss", "stat": "boost" if len(a) > 2 and a[2] else "drop", "hazard": "status",
               "protect": "select", "screen": "heal", "crit": "hit_super"}.get(kind)
        if snd:
            AUDIO.play(snd, 0.7)
        if kind == "hit" and a[2] <= 0 and self.last_move and self.app.settings.get("finishers", "On") == "On":
            self._start_finisher(a[1])
        elif kind == "hit":
            AUDIO.play("hit_super" if a[3] > 1 else "hit_weak" if a[3] < 1 else "hit", 0.9)
        if kind == "move" and a[2] == "Judgment" and not getattr(self, "judged", False):
            pid = self.vis.get(a[1], {}).get("id")
            e = self.app.dex.all.get(pid or -1, {})
            if e and e.get("key", "").startswith("arceus"):  # Arceus's first Judgment gets its cutscene
                self.judged = True
                self.finisher = Judgment(pid, ARCEUS_JUDGMENT[self.s.seed % len(ARCEUS_JUDGMENT)]
                                         if hasattr(self.s, "seed") else ARCEUS_JUDGMENT[0], None)
        if kind == "move":
            self.last_move = a
            if a[4] != "status" and self.vis.get(1 - a[1], {}).get("id"):
                me = a[1] == self.me
                start = (MY_POS[0] + 30, MY_POS[1] - 100) if me else (FOE_POS[0] - 20, FOE_POS[1] - 70)
                end = (FOE_POS[0], FOE_POS[1] - 70) if me else (MY_POS[0] + 20, MY_POS[1] - 100)
                self.attack = [AttackFX(a[3], a[4], start, end), 0.0]
            AUDIO.play("beam" if a[4] == "spec" else "melee" if a[4] == "phys" else "select", 0.5)
        elif kind == "faint":
            v = self.vis.get(a[1], {})
            if "id" in v:
                AUDIO.cry(v["id"], 0.9)
            AUDIO.play("faint", 0.8)
        elif kind == "switch":
            AUDIO.play("ball", 0.6)
            AUDIO.cry(a[3], 0.8)
        elif kind == "mega":
            AUDIO.play("mega")
            AUDIO.cry(a[2], 1.0)
        elif kind == "tera":
            AUDIO.play("tera")
        elif kind == "status" and a[2]:
            AUDIO.play("status", 0.7)
        elif kind == "hp" and len(a) > 2 and self.vis.get(a[1], {}).get("frac", 0) < a[2] - 0.01:
            AUDIO.play("heal", 0.5)
        elif kind == "end":
            AUDIO.music(None)
            AUDIO.play("win" if a[1] == self.me else "lose")
        if kind in ("hp", "hit"):
            side = a[1]
            self.vis[side]["frac"] = a[2]
            if kind == "hit":
                self.shake[side] = 0.4
                self.flash[side] = 0.3
        elif kind == "faint":
            self.faint[a[1]] = 0.001
            self.vis[a[1]]["frac"] = 0
        elif kind == "switch":
            side, idx, pid = a[1], a[2], a[3]
            self.sendout[side] = 0.0
            self.hp_shown.pop(side, None)
            m = self.state["sides"][side]["mons"][idx] if self.state else {}
            self.vis[side] = {"id": pid, "frac": m.get("frac", 1.0), "status": m.get("status"),
                              "name": m.get("name", "?"), "idx": idx, "fainted": False}
            self.faint[side] = 0.0
        elif kind == "gmax":
            v = self.vis[a[1]]
            base = v.get("id")
            e = self.app.dex.all.get(a[2])
            mv = (self.req or {}).get("gmax_move") if a[1] == self.me else None
            self.finisher = Gigantamax(base, a[2], e["name"] if e else "", mv or self._gmax_move_name(a[2]),
                                       quick=True)
            v["id"], v["gmax"] = a[2], True
            if e:
                v["name"] = e["name"]
        elif kind == "ungmax":
            v = self.vis[a[1]]
            v["id"], v["gmax"] = a[2], False
            e = self.app.dex.all.get(a[2])
            if e:
                v["name"] = e["name"]
            self.flash[a[1]] = 0.5
        elif kind == "mega":
            old = self.vis[a[1]].get("id")
            e2 = self.app.dex.all.get(a[2])
            if old and e2:
                self.finisher = MegaEvolution(old, a[2], e2["name"],
                                              "PRIMAL REVERSION" if "primal" in e2["key"] else "MEGA EVOLUTION",
                                              quick=True)
            self.vis[a[1]]["id"] = a[2]
            e = self.app.dex.all.get(a[2])
            if e:
                self.vis[a[1]]["name"] = e["name"]
            self.flash[a[1]] = 0.8
        elif kind == "tera":
            self.vis[a[1]]["tera"] = a[2]
            self.flash[a[1]] = 0.8
        elif kind == "ability":
            self.ability_pop = [a[1], str(a[2]).replace("-", " ").title(), 1.4]
        elif kind == "status":
            self.vis[a[1]]["status"] = a[2]
        elif kind == "move":
            self.shake[a[1]] = 0.15

    # ------------------------------------------------------------------ layout + input
    def _gmax_move_name(self, form_id):
        from .pokedex import GMAX_MOVES
        e = self.app.dex.all.get(form_id, {})
        return GMAX_MOVES.get(e.get("key", "").split("-")[0], ("Max Strike", ""))[0]

    def _start_finisher(self, side):
        """The hit that knocks out `side`'s Pokemon becomes a cutscene."""
        mv = self.last_move
        att, dfn = self.vis.get(1 - side, {}), self.vis.get(side, {})
        if "id" not in att or "id" not in dfn or mv[1] == side:
            return
        mons = self.state["sides"][side]["mons"] if self.state else []
        others_left = sum(1 for i, m in enumerate(mons) if not m["fainted"] and i != dfn.get("idx"))
        self.finisher = Finisher(att["id"], dfn["id"], mv[2], mv[3], mv[4], mine=(1 - side) == self.me,
                                 final=others_left == 0)

    def _busy(self):
        return self.cur is not None or bool(self.queue) or bool(self.pending_updates) or self.finisher is not None

    def _layout(self):
        self.move_btns, self.party_btns, self.mega_btn = [], [], None
        req = self.req if not self._busy() else None
        if req and req["kind"] == "move":
            for i, m in enumerate(req["moves"]):
                x = 20 + (i % 2) * 345
                y = 960 + (i // 2) * 88
                sub = f"{CLS_NAMES.get(m['cls'], m['cls'].upper())}   {m['power'] or '-'} POW   " \
                      f"{m['pp']}/{m['maxpp']} PP"
                b = ui.Button((x, y, 335, 80), m["name"], gfx.type_color(m["type"], 2), 24, sub,
                              enabled=not m["disabled"], tag=m["slot"])
                self.move_btns.append(b)
            opts = self._gimmicks(req)
            if opts:
                if self.gimmick not in opts:
                    self.gimmick = opts[0]
                g = self.gimmick
                on = self.mega_on
                tt = req.get("tera_type", "normal")
                label, col, sub = {"mega": ("Mega", (150, 70, 210), "evolve"),
                                   "gmax": ("G-Max", (200, 30, 60), (req.get("gmax_move") or "")[:12]),
                                   "tera": ("Tera", gfx.type_color(tt, 2), tt.upper())}[g]
                self.mega_btn = ui.Button((20, 1150, 160, 100), label if on else (label if len(opts) == 1 else
                                                                                  "Gimmick"),
                                          col if on else ui.PANEL2, 26, sub if on else "off")
        if self.state and req:
            sd = self.state["sides"][self.me]
            allowed = set(req.get("switches", []))
            x0 = 200 if self.mega_btn or (req["kind"] == "move") else 20
            for i, m in enumerate(sd["mons"]):
                x = x0 + i * ((W - 20 - x0) // 6)
                self.party_btns.append((pygame.Rect(x, 1150, (W - 20 - x0) // 6 - 8, 100), i, i in allowed, m))
        self.buttons = self.move_btns + ([self.mega_btn] if self.mega_btn else []) + \
            (self.end_btns if self._finished() else [])

    def _finished(self):
        return (self.state and self.state["over"] and not self._busy()) or (self.s.error and not self._busy())

    def handle(self, ev, pos):
        if self.finisher is not None:
            if (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1) or (
                    ev.type == pygame.KEYDOWN and ev.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_ESCAPE)):
                self.finisher.skip()
            return
        if self.x.handle(ev, pos):
            return
        if self._finished():
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for b in self.end_btns:
                    if b.hit(pos):
                        self._end_action(b.tag)
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self.app.home()
            return
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self.app.home()
            elif ev.key in (pygame.K_m, pygame.K_t, pygame.K_g) and self.mega_btn:
                want = {pygame.K_m: "mega", pygame.K_t: "tera", pygame.K_g: "gmax"}[ev.key]
                if want in self._gimmicks(self.req or {}):
                    self.mega_on = not (self.mega_on and self.gimmick == want)
                    self.gimmick = want
            elif ev.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                i = ev.key - pygame.K_1
                if i < len(self.move_btns) and self.move_btns[i].enabled:
                    self._send(self._move_choice(self.move_btns[i].tag))
            elif ev.key == pygame.K_SPACE and self._busy():
                self.cur_t = 99  # skip ahead
            return
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1 or pos is None:
            return
        if self._busy():
            self.cur_t = 99
            return
        for b in self.move_btns:
            if b.hit(pos):
                self._send(self._move_choice(b.tag))
                return
        if self.mega_btn and self.mega_btn.hit(pos):
            self._cycle_gimmick()
            return
        for rect, i, ok, m in self.party_btns:
            if ok and rect.collidepoint(pos):
                self._send({"type": "switch", "index": i})
                return

    @staticmethod
    def _gimmicks(req):
        return [g for g, flag in (("mega", "can_mega"), ("gmax", "can_gmax"), ("tera", "can_tera")) if req.get(flag)]

    def _cycle_gimmick(self):
        """Off -> first available gimmick -> next -> ... -> off."""
        opts = self._gimmicks(self.req or {})
        if not opts:
            return
        if not self.mega_on:
            self.mega_on, self.gimmick = True, opts[0]
            return
        i = opts.index(self.gimmick) if self.gimmick in opts else len(opts)
        if i + 1 < len(opts):
            self.gimmick = opts[i + 1]
        else:
            self.mega_on = False

    def _move_choice(self, slot):
        c = {"type": "move", "slot": slot}
        if self.mega_on and self.mega_btn:
            c[self.gimmick] = True
        return c

    def _end_action(self, tag):
        if tag == "catch":
            from .trainer_ui import LegendEncounter
            self.x.caught = True
            pid, shiny = self.x.outcome["encounter"]
            self.app.push(LegendEncounter(self.app, pid, shiny))
            return
        if tag == "menu":
            self.app.home()
        elif self.s.online:
            if not self.s.error:
                self.s.request_rematch()
        else:
            from .session import TurnLocal
            mine, theirs = self.s.teams
            self.app.replace(TurnBattleScene(self.app, TurnLocal(self.app.dex, mine, theirs, self.s.bot.level)))

    def _auto_choice(self):
        """Turn timer ran out: pick something legal."""
        req = self.req
        if req["kind"] in ("lead", "switch"):
            return {"type": "switch", "index": req["switches"][0]}
        ok = [m for m in req["moves"] if not m["disabled"]]
        return {"type": "move", "slot": ok[0]["slot"]}

    def _send(self, choice):
        if not self.req:
            return
        if self.s.choose(choice):
            self.req = None
            self.waiting = True
            self.msg = "Waiting for your opponent..." if self.s.online else "..."

    # ------------------------------------------------------------------ drawing
    def draw(self, surf):
        surf.blit(self.bg, (0, 0))
        if self.state:
            self._draw_field_info(surf)
            for side in (self.foe, self.me):
                self._draw_mon(surf, side)
            if self.attack is not None:
                self.attack[0].draw(surf, self.attack[1] / 0.55)
            self._draw_hp_box(surf, self.foe, (30, 120))
            self._draw_hp_box(surf, self.me, (330, 580))
        if self.req and self.req["kind"] == "lead" and not self._busy():
            self._draw_preview(surf)
        # message box
        ui.panel(surf, (20, 840, 680, 100), (36, 34, 50), 12)
        gfx.text(surf, self.msg, (40, 880), 23, anchor="midleft", chunky=False, ow=1)
        if self.timer is not None:
            col = (255, 110, 100) if self.timer < 10 else (220, 220, 230)
            gfx.text(surf, f"{int(self.timer) + 1}s", (686, 880), 24, col, anchor="midright")
        self._draw_move_buttons(surf)
        if self.mega_btn:
            self.mega_btn.draw(surf)
        for rect, i, ok, m in self.party_btns:
            col = (60, 56, 80) if ok else (36, 34, 44)
            pygame.draw.rect(surf, INK, rect.inflate(4, 4), border_radius=10)
            pygame.draw.rect(surf, col, rect, border_radius=8)
            img = SPRITES.get(m["id"], 60)
            if m["fainted"]:
                img = img.copy()
                img.set_alpha(70)
            surf.blit(img, img.get_rect(center=(rect.centerx, rect.centery - 8)))
            gfx.hp_bar(surf, (rect.x + 8, rect.bottom - 14, rect.w - 16, 6), m["frac"])
        if self.req and self.req["kind"] == "move" and not self._busy() and self.req.get("lock"):
            gfx.text(surf, self.req["lock"], (40, 922), 15, (255, 210, 120), anchor="midleft", ow=1, chunky=False)
        elif self.req and self.req["kind"] == "move" and not self._busy():
            gfx.text(surf, "Pick a move (1-4)  -  tap a Pokemon below to switch  -  M = Mega, T = Tera", (40, 922), 14,
                     ui.MUTED, anchor="midleft", ow=1, chunky=False)
        if self._finished():
            shade = pygame.Surface((W, H), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 150))
            surf.blit(shade, (0, 0))
            if self.s.error and not (self.state and self.state["over"]):
                gfx.title_text(surf, "DISCONNECTED", (W / 2, 450), 56)
                gfx.text(surf, self.s.error, (W / 2, 520), 22, chunky=False)
            else:
                won = self.state["winner"] == self.me
                gfx.title_text(surf, "VICTORY!" if won else "DEFEAT", (W / 2, 290), 90,
                               color=(255, 230, 110) if won else WHITE)
                gfx.text(surf, self.x.result_text, (W / 2, 360), 22)
                if self.s.online and self.s.rematch_them and not self.s.rematch_me:
                    gfx.text(surf, f"{self.s.names[self.foe]} wants a rematch!", (W / 2, 396), 22, (255, 230, 120))
                draw_rank_change(surf, self.x.outcome, (W / 2, 466), self.x.outcome_t)
            for b in self.end_btns:
                b.draw(surf)
        self.x.draw(surf, lambda i: (200, 640) if i == self.me else (520, 300))
        if self.finisher is not None:
            self.finisher.draw(surf)
            gfx.text(surf, "click to skip", (W - 16, H - 16), 14, (200, 200, 210), anchor="midright", ow=1,
                     chunky=False)

    def _foe_types(self):
        v = self.vis.get(self.foe)
        if not v or v.get("idx") is None or not self.state:
            return None
        return [v["tera"]] if v.get("tera") else self.state["sides"][self.foe]["mons"][v["idx"]]["types"]

    def _draw_move_buttons(self, surf):
        moves = {m["slot"]: m for m in (self.req or {}).get("moves", [])}
        foe_types = self._foe_types()
        for b in self.move_btns:
            b.draw(surf)
            m = moves.get(b.tag)
            if not m:
                continue
            r = b.rect
            type_pills(surf, [m["type"]], r.x + 8, r.y + 12, 12)
            if foe_types and m["cls"] != "status" and b.enabled:
                eff = effectiveness(m["type"], foe_types)
                if eff in EFF_TEXT:
                    label, col = EFF_TEXT[eff]
                    gfx.text(surf, label, (r.right - 8, r.y + 12), 12, col, anchor="midright", ow=1, chunky=False)

    def _draw_field_info(self, surf):
        st = self.state
        bits = []
        if st["weather"]:
            bits.append({"rain": "Rain", "sun": "Harsh sun", "sand": "Sandstorm", "snow": "Snow"}[st["weather"]])
        if st["trick_room"]:
            bits.append("Trick Room")
        for side, label in ((self.foe, "Foe"), (self.me, "You")):
            sd = st["sides"][side]
            hz = (["Stealth Rock"] if sd["rocks"] else []) + ([f"Spikes x{sd['spikes']}"] if sd["spikes"] else []) + \
                 ([f"Toxic Spikes x{sd['tspikes']}"] if sd["tspikes"] else []) + sd["screens"]
            if hz:
                bits.append(f"{label}: " + ", ".join(hz))
        gfx.text(surf, f"Turn {st['turn']}" + ("   " + "   |   ".join(bits) if bits else ""), (W / 2, 30), 17,
                 ow=1, chunky=False)
        names = self.s.names
        gfx.text(surf, f"{names[self.foe]}", (W - 20, 70), 20, gfx.TEAM_COLORS[1], anchor="midright", ow=1)

    def _draw_mon(self, surf, side):
        v = self.vis.get(side)
        if not v or "id" not in v:
            return
        if self.faint[side] > 0:
            if self.faint[side] > 0.6:
                return
        mine = side == self.me
        x, y = MY_POS if mine else FOE_POS
        hgt = 250 if mine else 190
        if v.get("gmax"):
            hgt = int(hgt * 1.35)
        white = 0.8 if self.flash[side] > 0 and int(self.flash[side] * 20) % 2 else 0.0
        img = SPRITES.get(v["id"], hgt, back=mine, white=white)
        dx = math.sin(self.shake[side] * 60) * 10 * (self.shake[side] > 0)
        dy = self.faint[side] * 300
        so = self.sendout.get(side)
        if so is not None and so < 0.7:  # Poke Ball send-out: arc in, pop, grow out of the light
            self._draw_sendout(surf, side, v, (x, y), hgt, so)
            return
        clip = surf.get_clip()
        if self.faint[side] > 0:
            surf.set_clip(pygame.Rect(0, 0, W, y + 10))
        surf.blit(img, img.get_rect(midbottom=(x + dx, y + 30 + dy)))
        surf.set_clip(clip)

    def _draw_sendout(self, surf, side, v, pos, hgt, t):
        x, y = pos
        mine = side == self.me
        cy = y + 30 - hgt * 0.45
        if t < 0.3:
            p = t / 0.3
            sx, sy = (-40, H * 0.7) if mine else (W + 40, 120)
            bx = sx + (x - sx) * p
            by = sy + (cy - sy) * p - math.sin(p * math.pi) * 160
            ball = pygame.transform.rotate(gfx.ball_sprite(34), -p * 900 * (1 if mine else -1))
            surf.blit(ball, ball.get_rect(center=(bx, by)))
            return
        q = (t - 0.3) / 0.4
        glow = pygame.Surface((W, H), pygame.SRCALPHA)
        r = int(30 + 140 * q)
        pygame.draw.circle(glow, (255, 255, 255, int(200 * (1 - q))), (int(x), int(cy)), r)
        surf.blit(glow, (0, 0))
        scale = 0.15 + 0.85 * (1 - (1 - q) ** 3)
        full = SPRITES.get(v["id"], hgt, back=mine)
        img = gfx.rescale(full, (max(2, full.get_width() * scale), max(2, full.get_height() * scale)))
        surf.blit(img, img.get_rect(midbottom=(x, y + 30)))
        whiten = max(0.0, 1 - q * 1.6)
        if whiten > 0:  # it comes out of the light: a white cut-out fading away on top
            sil = gfx.silhouette(img, (255, 255, 255))
            sil.set_alpha(int(255 * whiten))
            surf.blit(sil, sil.get_rect(midbottom=(x, y + 30)))

    def _draw_hp_box(self, surf, side, pos):
        v = self.vis.get(side)
        if not v or "id" not in v:
            return
        x, y = pos
        ui.panel(surf, (x, y, 360, 96), (248, 246, 236), 12)
        sd = self.state["sides"][side]
        info = sd["mons"][v["idx"]] if v.get("idx") is not None else {}
        types = [v["tera"]] if v.get("tera") else info.get("types", [])
        tw = type_pills(surf, types, x + 344, y + 22, 13, right=True)
        name, size = v["name"], 24
        while size > 15 and gfx.font(size, True).size(name)[0] > 320 - tw:
            size -= 2
        gfx.text(surf, name, (x + 16, y + 24), size, INK, None, anchor="midleft")
        if v.get("tera"):
            gfx.pill(surf, "TERA", (x + 344 - tw - 26, y + 22), (40, 40, 60), 11)
        if v.get("status"):
            gfx.pill(surf, STATUS_NAMES.get(v["status"], ""), (x + 190, y + 78), STATUS_COLORS.get(v["status"],
                                                                                              (90, 90, 90)), 13)
        gfx.hp_bar(surf, (x + 16, y + 48, 328, 12), self.hp_shown.get(side, v["frac"]))
        if side == self.me and info.get("ability"):
            gfx.text(surf, f"{info['ability']}" + (f"  -  {info['item']}" if info.get("item") else ""),
                     (x + 180, y + 108), 14, (220, 220, 235), ow=1, chunky=False)
        if self.ability_pop and self.ability_pop[0] == side:
            ui.panel(surf, (x + 30, y - 46, 300, 38), (60, 50, 90), 8)
            gfx.text(surf, self.ability_pop[1], (x + 180, y - 27), 20, (255, 230, 150))
        if side == self.me and v.get("idx") is not None:
            m = sd["mons"][v["idx"]]
            hp = round(m["maxhp"] * v["frac"])
            gfx.text(surf, f"{hp} / {m['maxhp']}", (x + 344, y + 78), 18, INK, None, anchor="midright", chunky=False)
        else:
            gfx.text(surf, f"{int(math.ceil(v['frac'] * 100))}%", (x + 344, y + 78), 18, INK, None,
                     anchor="midright", chunky=False)
        for i, m in enumerate(sd["mons"]):  # party balls
            col = (90, 90, 90) if m["fainted"] else (230, 60, 60)
            pygame.draw.circle(surf, col, (x + 22 + i * 20, y + 78), 7)
            pygame.draw.circle(surf, INK, (x + 22 + i * 20, y + 78), 7, 2)
        stages = sd["stages"]
        if stages:
            txt = " ".join(f"{k.upper()}{'+' if v_ > 0 else ''}{v_}" for k, v_ in stages.items())
            gfx.text(surf, txt, (x + 180, y + (128 if side == self.me else 108)), 15, (255, 240, 160), ow=1,
                     chunky=False)

    def _draw_preview(self, surf):
        shade = pygame.Surface((W, 820), pygame.SRCALPHA)
        shade.fill((10, 10, 20, 200))
        surf.blit(shade, (0, 0))
        gfx.title_text(surf, "TEAM PREVIEW", (W / 2, 80), 46)
        foe = self.state["sides"][self.foe]["mons"]
        gfx.text(surf, f"{self.s.names[self.foe]}'s team", (W / 2, 150), 22, gfx.TEAM_COLORS[1])
        for i, m in enumerate(foe):
            img = SPRITES.get(m["id"], 80)
            cx = 75 + i * 114
            surf.blit(img, img.get_rect(center=(cx, 240)))
            gfx.text(surf, m["name"][:11], (cx, 300), 14, ow=1, chunky=False)
            for j, t in enumerate(m["types"]):
                gfx.pill(surf, t.upper(), (cx, 324 + j * 22), gfx.type_color(t, 0), 11)
        gfx.text(surf, "Tap your lead below", (W / 2, 420), 26, (255, 240, 150))
        mine = self.state["sides"][self.me]["mons"]
        for i, m in enumerate(mine):
            img = SPRITES.get(m["id"], 90)
            cx = 75 + i * 114
            surf.blit(img, img.get_rect(center=(cx, 540)))
            gfx.text(surf, m["name"][:11], (cx, 606), 14, ow=1, chunky=False)
            gfx.text(surf, m["item"][:14], (cx, 628), 12, ui.MUTED, ow=1, chunky=False)
            for j, t in enumerate(m["types"]):
                gfx.pill(surf, t.upper(), (cx, 652 + j * 22), gfx.type_color(t, 0), 11)
