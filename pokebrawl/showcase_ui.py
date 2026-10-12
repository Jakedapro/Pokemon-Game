"""Showcase menu: presets, custom matchups (Gen 1 vs Gen 3, Fire vs Water, ...), play live or record an MP4."""
import os
import subprocess
import sys
import threading
import time

import pygame

from . import gfx, ui
from .app import Scene, save_settings
from .gfx import H, W
from .audio import AUDIO
from .showcase import ShowcaseScene, finish_video, list_presets, load_config
from .types import TYPES

GROUPS = [(f"Gen {g}", {"gen": g}) for g in range(1, 10)] + [
    ("All Pokemon", {}), ("Legendaries", {"legendary": True}), ("Non-legendaries", {"legendary": False}),
    ("Fully evolved", {"fully_evolved": True}), ("Strong (BST 500+)", {"min_bst": 500}),
    ("Weak (BST < 350)", {"max_bst": 349}),
] + [(f"{t.title()} types", {"type": t}) for t in TYPES]
SIZES = ["All", "100", "50", "25", "10", "3", "1"]


def video_dir():
    movies = os.path.join(os.path.expanduser("~"), "Movies")
    d = os.path.join(movies, "PokeBrawl") if os.path.isdir(movies) else os.path.join(os.path.expanduser("~"),
                                                                                       "pokebrawl-videos")
    os.makedirs(d, exist_ok=True)
    return d


def open_path(path):
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", path])
    except OSError:
        pass


class ShowcaseMenu(Scene):
    def __init__(self, app):
        super().__init__(app)
        s = app.settings
        self.presets = list_presets()
        self.list = ui.ListView((40, 190, 640, 300), 54)
        self.list.set_rows([(p, self._row(t)) for p, t in self.presets])
        names = [g[0] for g in GROUPS]
        self.a = ui.Cycle((40, 560, 640, 62), "Team A", names)
        self.a.set(s.get("sc_a", "Gen 1"))
        self.b = ui.Cycle((40, 636, 640, 62), "Team B", names)
        self.b.set(s.get("sc_b", "Gen 3"))
        self.size = ui.Cycle((40, 712, 640, 62), "Per team", SIZES)
        self.size.set(s.get("sc_size", "All"))
        self.megas = ui.Cycle((40, 788, 310, 62), "Megas", ["On", "Off"])
        self.bosses = ui.Cycle((370, 788, 310, 62), "Bosses", ["On", "Off"])
        self.finale = ui.Cycle((40, 864, 310, 62), "Catch", ["On", "Off"])
        self.speed = ui.Cycle((370, 864, 310, 62), "Speed", ["1x", "2x", "0.5x"])
        self.cycles = [self.a, self.b, self.size, self.megas, self.bosses, self.finale, self.speed]
        self.custom = s.get("sc_mode", "custom") == "custom"
        self.buttons = [ui.Button((40, 960, 310, 110), "PLAY", (70, 120, 220), 40, "watch it live"),
                        ui.Button((370, 960, 310, 110), "RECORD MP4", (196, 60, 60), 34, "vertical 720x1280"),
                        ui.Button((40, 1160, 200, 70), "BACK", ui.PANEL2, 24)]

    def _row(self, title):
        def draw(surf, r, sel):
            gfx.text(surf, title, (r.x + 16, r.centery), 22, anchor="midleft", ow=1)
        return draw

    def config(self):
        if not self.custom and self.list.selected:
            cfg = load_config(self.list.selected)
        else:
            ga, gb = dict(GROUPS)[self.a.value], dict(GROUPS)[self.b.value]
            ta, tb = {"name": self.a.value, "filter": ga}, {"name": self.b.value, "filter": gb}
            if self.size.value != "All":
                ta["count"] = tb["count"] = int(self.size.value)
            cfg = load_config({"title": f"{self.a.value} vs {self.b.value}!", "teams": [ta, tb]})
            n = int(self.size.value) if self.size.value != "All" else 999
            if n <= 6:
                cfg["hp_mult"] = 6
                cfg["subtitle"] = "WHO WILL WIN???"
        cfg["megas"] = self.megas.value == "On"
        cfg["bosses"] = "legendary" if self.bosses.value == "On" else "none"
        cfg["finale"] = self.finale.value == "On"
        cfg["speed"] = {"1x": 1.0, "2x": 2.0, "0.5x": 0.5}[self.speed.value]
        return cfg

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        if self.list.handle(ev, pos):
            self.custom = False
            return
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        for c in self.cycles:
            if c.click(pos) and c in (self.a, self.b, self.size):
                self.custom = True
        if self.buttons[2].hit(pos):
            self.app.pop()
        elif self.buttons[0].hit(pos) or self.buttons[1].hit(pos):
            self.app.settings.update(sc_a=self.a.value, sc_b=self.b.value, sc_size=self.size.value,
                                     sc_mode="custom" if self.custom else "preset")
            save_settings(self.app.settings)
            cfg = self.config()
            if self.buttons[0].hit(pos):
                self.app.push(ShowcaseLoad(self.app, cfg, record=False))
            else:
                self.app.push(ShowcaseLoad(self.app, cfg, record=True))

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "SHOWCASE", "Mass battles for your content - pick a preset or build a matchup")
        gfx.text(surf, "PRESETS", (40, 170), 18, ui.MUTED if self.custom else (255, 240, 150), anchor="midleft", ow=1)
        if self.custom:
            self.list.selected = None
        self.list.draw(surf)
        gfx.text(surf, "CUSTOM MATCHUP", (40, 535), 18, (255, 240, 150) if self.custom else ui.MUTED,
                 anchor="midleft", ow=1)
        for c in self.cycles:
            c.draw(surf)
        for b in self.buttons:
            b.draw(surf)
        gfx.text(surf, "While watching: Space = pause, +/- = speed, Esc = exit", (W / 2, 1100), 16, ui.MUTED,
                 ow=1, chunky=False)
        gfx.text(surf, f"Videos are saved to {video_dir()}", (W / 2, 1126), 15, ui.MUTED, ow=1, chunky=False)


class ShowcaseLoad(Scene):
    def __init__(self, app, cfg, record):
        super().__init__(app)
        self.cfg = cfg
        self.record = record
        self.scene = None
        self.error = None
        self.done = 0
        self.total = 1
        threading.Thread(target=self._build, daemon=True).start()

    def _build(self):
        try:
            self.scene = ShowcaseScene(self.app.dex, self.cfg, self._prog)
        except Exception as e:  # noqa: BLE001
            self.error = str(e)

    def _prog(self, d, t):
        self.done, self.total = d, t

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()

    def update(self, dt):
        if self.scene:
            nxt = ShowcaseRecord(self.app, self.scene) if self.record else ShowcasePlay(self.app, self.scene)
            self.app.replace(nxt)

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        gfx.text(surf, self.error or "Loading Pokemon...", (W / 2, H * 0.45), 28)
        gfx.hp_bar(surf, (160, int(H * 0.5), 400, 14), self.done / max(1, self.total))


class ShowcasePlay(Scene):
    def __init__(self, app, scene):
        super().__init__(app)
        self.sc = scene

    def handle(self, ev, pos):
        self.sc.handle(ev, pos)

    def update(self, dt):
        self.sc.update(dt)
        if self.sc.done:
            self.app.pop()

    def draw(self, surf):
        self.sc.draw(surf)


class ShowcaseRecord(Scene):
    """Renders offscreen as fast as possible into an MP4, showing progress."""

    def __init__(self, app, scene, fps=30):
        super().__init__(app)
        from .recorder import Recorder
        self.sc = scene
        self.fps = fps
        self.frames = 0
        self.canvas = pygame.Surface((W, H)).convert()
        title = scene.cfg.get("title", "showcase") if hasattr(scene, "cfg") else getattr(scene, "title", "battle")
        name = "".join(c if c.isalnum() else "_" for c in title).strip("_")
        self.path = os.path.join(video_dir(), f"{name}_{time.strftime('%Y%m%d_%H%M%S')}.mp4")
        self.error = None
        self.finished = False
        self.mixing = False
        try:
            self.rec = Recorder(self.path + ".video.mp4", W, H, fps)
            AUDIO.capture, AUDIO.clock = [], (lambda: self.frames / self.fps)
        except RuntimeError as e:
            self.rec = None
            self.error = str(e)
        self.buttons = [ui.Button((160, 1000, 400, 90), "CANCEL", ui.PANEL2, 30)]

    def close(self):
        if self.rec and not self.finished and not self.mixing:
            self.rec.close()
        if AUDIO.capture is not None:
            AUDIO.capture, AUDIO.clock = None, None

    def handle(self, ev, pos):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.buttons[0].hit(pos):
            if self.finished:
                open_path(os.path.dirname(self.path))
            self.app.pop()
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()

    def update(self, dt):
        if self.error or self.finished or self.mixing:
            return
        start = time.time()
        while time.time() - start < 0.03 and not self.sc.done:
            self.sc.update(1 / self.fps)
            self.sc.draw(self.canvas)
            self.rec.write(self.canvas)
            self.frames += 1
        if self.sc.done:
            self.rec.close()
            events, AUDIO.capture, AUDIO.clock = AUDIO.capture, None, None
            self.mixing = True

            def mix():
                finish_video(self.path, events, self.frames / self.fps, log=lambda m: None)
                self.mixing = False
                self.finished = True
                self.buttons = [ui.Button((160, 1000, 400, 90), "OPEN FOLDER", (60, 160, 90), 30)]
            threading.Thread(target=mix, daemon=True).start()

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        if self.error:
            gfx.text(surf, self.error, (W / 2, H * 0.4), 24, (255, 120, 120), chunky=False)
        else:
            thumb = pygame.transform.smoothscale(self.canvas, (W // 2, H // 2))
            surf.blit(thumb, thumb.get_rect(center=(W / 2, 470)))
            secs = self.frames / self.fps
            msg = f"Saved! {secs:.0f}s video" if self.finished else "Adding sound..." if self.mixing else \
                f"Recording... {secs:.0f}s  ({getattr(self.sc, 'phase', '')})"
            gfx.text(surf, msg, (W / 2, 840), 28)
            gfx.text(surf, self.path, (W / 2, 890), 15, ui.MUTED, ow=1, chunky=False)
        for b in self.buttons:
            b.draw(surf)
