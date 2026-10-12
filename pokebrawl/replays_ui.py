"""Replay browser: re-simulates saved battles from their seed + inputs, and exports them as MP4s."""
import os
import time

import pygame

from . import gfx, recorder, replays, ui
from .app import STYLE_NAMES, PrefetchScene, Scene
from .battle_turn import TurnBattleScene
from .gfx import W
from .team import Member
from .turnsim import TurnBattle


class TurnReplaySession:
    online = False
    is_replay = True

    def __init__(self, dex, r):
        self.my_side = self.me_index = 0
        self.names = r["names"]
        self.teams = [[Member.from_dict(d) for d in t] for t in r["teams"]]
        b = TurnBattle(dex, self.teams, r["seed"], names=self.names)
        self.updates = [{"log": [], "state": b.state(0), "req": None}]
        for side, choice in r["log"]:
            b.choose(side, choice)
            if b.ready():
                self.updates.append({"log": b.run(), "state": b.state(0), "req": None})
        self.battle = b
        self.error = None

    def pump(self):
        out, self.updates = self.updates, []
        return out

    def choose(self, choice):
        return False

    def replay(self):
        return None

    def close(self):
        pass


class _ReplayMixin:
    """Turns a battle screen into a viewer: no controls, speed keys, no stats recorded."""

    def _replay_init(self, title):
        self.x.done = True          # don't count replays in your record
        self.x.saved_path = ""      # or save them again
        self.title = title
        self.after = 0.0
        self.done = False
        self.replay_btns = [ui.Button((160, 640, 400, 90), "WATCH AGAIN", (196, 60, 60), 30, tag="again"),
                            ui.Button((160, 750, 400, 90), "BACK", ui.PANEL2, 30, tag="back")]
        self.end_buttons = self.end_btns = self.replay_btns

    def _replay_handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self.app.pop()
            elif ev.key in (pygame.K_RIGHT, pygame.K_EQUALS, pygame.K_PLUS):
                self._set_speed(min(8.0, self._speed() * 2))
            elif ev.key in (pygame.K_LEFT, pygame.K_MINUS):
                self._set_speed(max(0.25, self._speed() / 2))
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and pos and self._ended():
            for b in self.replay_btns:
                if b.hit(pos):
                    if b.tag == "back":
                        self.app.pop()
                    else:
                        self.app.replace(self.restart())

    def _replay_tick(self, dt):
        if self._ended():
            self.after += dt
            self.done = self.after > 3.0
        self.end_buttons = self.end_btns = self.replay_btns
        if self._ended():
            self.buttons = list(self.replay_btns)

    def _banner(self, surf):
        gfx.pill(surf, f"REPLAY  x{self._speed():g}   (+/- speed)", (W / 2, 96), (150, 60, 60), 15)


class TurnReplayScene(_ReplayMixin, TurnBattleScene):
    def __init__(self, app, replay):
        self.replay_data = replay
        super().__init__(app, TurnReplaySession(app.dex, replay))
        self._replay_init(" vs ".join(replay["names"]))
        self.anim_speed = 1.0

    def restart(self):
        return TurnReplayScene(self.app, self.replay_data)

    def _speed(self):
        return self.anim_speed

    def _set_speed(self, v):
        self.anim_speed = v

    def _ended(self):
        return bool(self._finished())

    def handle(self, ev, pos):
        self._replay_handle(ev, pos)

    def update(self, dt):
        super().update(dt)
        if not self._busy() and not self._ended():
            self.msg = ""
        self._replay_tick(dt)

    def draw(self, surf):
        super().draw(surf)
        self._banner(surf)


def make_replay_scene(app, r):
    return TurnReplayScene(app, r)


class ReplayList(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.list = ui.ListView((40, 160, 640, 840), 84)
        self.buttons = [ui.Button((40, 1020, 200, 80), "WATCH", (70, 120, 220), 28),
                        ui.Button((260, 1020, 200, 80), "EXPORT MP4", (196, 60, 60), 24, "share it"),
                        ui.Button((480, 1020, 200, 80), "DELETE", (150, 50, 50), 26),
                        ui.Button((40, 1160, 200, 70), "BACK", ui.PANEL2, 24)]
        if not recorder.available():  # no ffmpeg: no video export, just watch / delete
            self.buttons[1].enabled = False
            self.buttons[0].rect.width = self.buttons[2].rect.width = 310
            self.buttons[2].rect.x = 370
        self.msg = ""
        self.refresh()

    def refresh(self):
        self.items = [(p, r) for p, r in replays.list_replays() if r.get("style") == "turn"]
        rows = []
        for path, r in self.items:
            def draw(surf, rect, sel, r=r):
                names = r.get("names", ["?", "?"])
                w = r.get("winner")
                gfx.text(surf, f"{names[0]}  vs  {names[1]}", (rect.x + 16, rect.y + 24), 22, anchor="midleft", ow=1)
                when = time.strftime("%b %d  %H:%M", time.localtime(r.get("date", 0)))
                win = f"winner: {names[w]}" if w is not None and w < len(names) else "draw"
                gfx.text(surf, f"{STYLE_NAMES.get(r['style'], r['style'])}   -   {when}   -   {win}",
                         (rect.x + 16, rect.y + 56), 15, ui.MUTED, anchor="midleft", ow=1, chunky=False)
            rows.append((path, draw))
        self.list.set_rows(rows)

    def selected(self):
        for path, r in self.items:
            if path == self.list.selected:
                return path, r
        return None, None

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        self.list.handle(ev, pos)
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        path, r = self.selected()
        b = self.buttons
        if b[3].hit(pos):
            self.app.pop()
        elif not r:
            if any(x.hit(pos) for x in b[:3]):
                self.msg = "Pick a replay first"
        elif b[0].hit(pos):
            ids = [d["species"] for t in r["teams"] for d in t]
            self.app.push(PrefetchScene(self.app, ids, lambda: make_replay_scene(self.app, r)))
        elif b[1].hit(pos):
            from .showcase_ui import ShowcaseRecord
            scene = make_replay_scene(self.app, r)
            scene.anim_speed = 1.6
            self.app.push(ShowcaseRecord(self.app, scene))
        elif b[2].hit(pos):
            os.remove(path)
            self.msg = "Deleted"
            self.refresh()

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "REPLAYS", "Every battle is saved automatically - watch it or turn it into a video")
        self.list.draw(surf)
        if not self.items:
            gfx.text(surf, "No replays yet - go battle!", (W / 2, 480), 24, ui.MUTED)
        for b in self.buttons:
            if b.enabled:
                b.draw(surf)
        if self.msg:
            gfx.text(surf, self.msg, (W / 2, 1125), 18, (255, 240, 150), ow=1, chunky=False)
