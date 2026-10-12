"""Real-time arena battle screen (practice vs bot, or online PvP)."""
import pygame

from . import gfx, ui
from .app import Scene
from .audio import AUDIO
from .battle_common import BattleExtras
from .gfx import H, W, WHITE
from .render import FX, ArenaRenderer
from .session import INTRO_HOLD

PANEL_Y = 1090


class RTBattle(Scene):
    def __init__(self, app, session, rematch=None):
        super().__init__(app)
        self.s = session
        self.rematch = rematch
        self.me = session.my_team
        self.r = ArenaRenderer(app.dex, session.roster, mode="team", my_team=self.me, team_names=session.names)
        self.selected = None
        self.last = None
        self.t = 0.0
        self.over = False
        self.winner = None
        self.move_buttons = []
        self.mega_button = None
        self.buttons = []
        self.x = BattleExtras(app, session, PANEL_Y - 44)
        self.end_buttons = self.x.end_buttons(620)
        self.r.smooth = not hasattr(session, "sim")  # online client: glide between network snapshots

    def close(self):
        self.s.close()

    # ------------------------------------------------------------------ helpers
    def my_units(self):
        return [u for u in self.r.units.values() if u.team == self.me]

    def info(self, uid):
        return self.s.roster.get(uid, {})

    def _layout_panel(self):
        self.move_buttons = []
        self.mega_button = None
        u = self.r.units.get(self.selected)
        if not u:
            return
        info = self.info(u.uid)
        for i, (name, mtype) in enumerate(zip(info.get("moves", []), info.get("types", []))):
            x = 20 + (i % 2) * 250
            y = PANEL_Y + 52 + (i // 2) * 62
            self.move_buttons.append(ui.Button((x, y, 236, 54), name, gfx.type_color(mtype, 2), 20, tag=i))
        if u.flags & 4:
            self.mega_button = ui.Button((530, PANEL_Y + 52, 170, 116), "MEGA", (150, 70, 210), 32, "press M",
                                         tag="mega")
        elif u.flags & 64:
            tt = info.get("tera", "normal")
            self.mega_button = ui.Button((530, PANEL_Y + 52, 170, 116), "TERA", gfx.type_color(tt, 2), 32,
                                         f"{tt.upper()} - press T", tag="tera")

    # ------------------------------------------------------------------ input
    def handle(self, ev, pos):
        if self.x.handle(ev, pos):
            return
        if self.over or self.s.error:
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for b in self.end_buttons:
                    if b.hit(pos):
                        self._end_action(b.tag)
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self.app.home()
            return
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                if self.selected:
                    self.selected = None
                else:
                    self.app.home()
            elif ev.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4) and self.selected:
                self.s.command({"cmd": "move", "unit": self.selected, "slot": ev.key - pygame.K_1})
            elif ev.key == pygame.K_m:
                cands = [u for u in self.my_units() if u.flags & 4]
                pick = self.r.units.get(self.selected) if self.selected else None
                if pick and pick.flags & 4:
                    cands = [pick]
                if cands:
                    self.s.command({"cmd": "mega", "unit": cands[0].uid})
            elif ev.key == pygame.K_t and self.selected:
                self.s.command({"cmd": "tera", "unit": self.selected})
            elif ev.key == pygame.K_TAB:
                mine = sorted(u.uid for u in self.my_units())
                if mine:
                    i = mine.index(self.selected) + 1 if self.selected in mine else 0
                    self.selected = mine[i % len(mine)]
            return
        if ev.type != pygame.MOUSEBUTTONDOWN or pos is None:
            return
        if ev.button == 1 and pos[1] > PANEL_Y:
            for b in self.move_buttons:
                if b.hit(pos):
                    self.s.command({"cmd": "move", "unit": self.selected, "slot": b.tag})
                    return
            if self.mega_button and self.mega_button.hit(pos):
                self.s.command({"cmd": self.mega_button.tag, "unit": self.selected})
            return
        u = self.r.unit_at(*pos)
        if ev.button == 1:
            if u and u.team == self.me:
                self.selected = None if self.selected == u.uid else u.uid
            elif u:
                units = [self.selected] if self.selected else None
                self.s.command({"cmd": "focus", "units": units, "target": u.uid})
                self.r.fx.append(FX("pop", 0.6, x=u.x, y=u.y - u.r * 1.8, text="FOCUS!", color=(255, 230, 90)))
            elif self.selected:
                wx, wy = self.r.screen_to_world(*pos)
                self.s.command({"cmd": "goto", "unit": self.selected, "pos": [wx, wy]})
        elif ev.button == 3 and self.selected:
            wx, wy = self.r.screen_to_world(*pos)
            self.s.command({"cmd": "goto", "unit": self.selected, "pos": [wx, wy]})

    def _end_action(self, tag):
        if tag == "menu":
            self.app.home()
        elif tag == "rematch" and self.s.online:
            if not self.s.error:
                self.s.request_rematch()
        elif tag == "rematch" and self.rematch:
            self.app.replace(self.rematch())
        elif tag == "rematch":
            from .session import RTLocal
            mine, theirs = self.s.teams
            self.app.replace(RTBattle(self.app, RTLocal(self.app.dex, mine, theirs, self.s.bot.level)))

    # ------------------------------------------------------------------ loop
    def update(self, dt):
        if self.t == 0:
            AUDIO.music("battle")
        self.t += dt
        for snap in self.s.step(dt):
            self.r.feed(snap)
            self.last = snap
            if snap["over"] and not self.over:
                self.over = True
                self.winner = snap["win"]
                AUDIO.music(None)
                AUDIO.play("win" if self.winner == self.me else "lose")
        if self.over:
            self.x.finish(self.winner)
            self.end_buttons = self.x.end_buttons(620)
            if self.x.check_rematch():
                return
        if self.selected and self.selected not in self.r.units:
            self.selected = None
        self.r.selected = self.selected
        self.r.update(dt)
        self._layout_panel()
        self.buttons = self.move_buttons + ([self.mega_button] if self.mega_button else []) + \
            (self.end_buttons if self.over or self.s.error else [])

    def draw(self, surf):
        self.r.draw(surf)
        self._draw_top(surf)
        self._draw_panel(surf)
        if self.t < INTRO_HOLD and not self.over:
            n = int(INTRO_HOLD - self.t) + 1
            gfx.title_text(surf, "READY..." if n > 1 else "FIGHT!", (W / 2, H * 0.45), 80)
        if self.over or self.s.error:
            shade = pygame.Surface((W, H), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 140))
            surf.blit(shade, (0, 0))
            if self.s.error and not self.over:
                gfx.title_text(surf, "DISCONNECTED", (W / 2, 450), 56)
                gfx.text(surf, self.s.error, (W / 2, 520), 22, chunky=False)
            else:
                won = self.winner == self.me
                gfx.title_text(surf, "VICTORY!" if won else ("DRAW" if self.winner is None else "DEFEAT"),
                               (W / 2, 470), 90, color=(255, 230, 110) if won else WHITE)
                gfx.text(surf, self.x.result_text, (W / 2, 545), 22)
                if self.s.online and self.s.rematch_them and not self.s.rematch_me:
                    gfx.text(surf, f"{self.s.names[1 - self.me]} wants a rematch!", (W / 2, 590), 22,
                             (255, 230, 120))
            for b in self.end_buttons:
                b.draw(surf)
        self.x.draw(surf, lambda i: (130 if i == 0 else W - 130, 130))

    def _draw_top(self, surf):
        bar = pygame.Surface((W, 74), pygame.SRCALPHA)
        bar.fill((20, 18, 28, 190))
        surf.blit(bar, (0, 0))
        for team in (0, 1):
            name = self.s.names[team] if team < len(self.s.names) else f"Team {team + 1}"
            x = 20 if team == 0 else W - 20
            anchor = "midleft" if team == 0 else "midright"
            col = gfx.TEAM_COLORS[team]
            tag = " (you)" if team == self.me else ""
            gfx.text(surf, name + tag, (x, 20), 20, col, anchor=anchor, ow=1)
            members = [(uid, info) for uid, info in sorted(self.s.roster.items()) if info["team"] == team]
            for i, (uid, info) in enumerate(members):
                alive = uid in self.r.units
                ix = (20 + i * 46) if team == 0 else (W - 20 - (len(members) - i) * 46)
                u = self.r.units.get(uid)
                pid = u.form if u else info["species"]
                img = gfx.SPRITES.get(pid, 34)
                if not alive:
                    img = img.copy()
                    img.set_alpha(60)
                surf.blit(img, img.get_rect(midbottom=(ix + 20, 70)))
                if u:
                    pygame.draw.rect(surf, gfx.hp_color(u.hp), (ix + 4, 70, int(34 * u.hp), 3))

    def _draw_panel(self, surf):
        p = pygame.Surface((W, H - PANEL_Y), pygame.SRCALPHA)
        p.fill((20, 18, 28, 215))
        surf.blit(p, (0, PANEL_Y))
        u = self.r.units.get(self.selected)
        if not u:
            gfx.text(surf, "Click one of your Pokemon to control it", (W / 2, PANEL_Y + 50), 22)
            gfx.text(surf, "Click an enemy = whole team focuses it  -  M = Mega  -  T = Tera  -  Tab = cycle",
                     (W / 2, PANEL_Y + 92), 17, ui.MUTED, ow=1, chunky=False)
            gfx.text(surf, "Selected: click enemy to focus, right-click ground to move, 1-4 = use move",
                     (W / 2, PANEL_Y + 124), 17, ui.MUTED, ow=1, chunky=False)
            return
        info = self.info(u.uid)
        e = self.app.dex.all.get(u.form, {})
        gfx.text(surf, e.get("name", info.get("name", "?")), (20, PANEL_Y + 24), 24, anchor="midleft")
        types = " / ".join(t.upper() for t in e.get("types", []))
        gfx.text(surf, f"{types}   {info.get('ability', '')}   {info.get('item', '')}   HP {int(u.hp * 100)}%",
                 (W - 20, PANEL_Y + 24), 15,
                 ui.MUTED, anchor="midright", ow=1, chunky=False)
        for b in self.move_buttons:
            b.draw(surf)
        if self.mega_button:
            self.mega_button.draw(surf)
