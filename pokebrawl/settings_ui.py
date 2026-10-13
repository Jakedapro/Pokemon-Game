"""Settings: volumes, name, and your record against friends and bots."""
import pygame

from . import gfx, profile, ui
from .app import Scene, save_settings
from .audio import AUDIO
from .gfx import W

LEVELS = [i / 10 for i in range(11)]


class SettingsScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        s = app.settings
        pct = lambda v: f"{int(round(v * 100))}%"  # noqa: E731
        self.music = ui.Cycle((60, 190, 600, 62), "Music", LEVELS, fmt=pct)
        self.music.set(round(AUDIO.music_vol, 1))
        self.sfx = ui.Cycle((60, 266, 600, 62), "Sound effects", LEVELS, fmt=pct)
        self.sfx.set(round(AUDIO.sfx_vol, 1))
        self.cry = ui.Cycle((60, 342, 600, 62), "Pokemon cries", LEVELS, fmt=pct)
        self.cry.set(round(AUDIO.cry_vol, 1))
        self.auto = ui.Cycle((60, 418, 600, 62), "Auto-update", ["On", "Off"])
        self.auto.set(s.get("auto_update", "On"))
        self.name = ui.TextInput((60, 514, 600, 56), "Your name (shown to friends)", s.get("name", "Trainer"))
        self.buttons = [ui.Button((40, 1160, 200, 70), "BACK", ui.PANEL2, 24)]
        self.record = profile.load()

    def _save(self):
        s = self.app.settings
        s.update(music_vol=self.music.value, sfx_vol=self.sfx.value, cry_vol=self.cry.value,
                 name=self.name.value.strip()[:16] or "Trainer", auto_update=self.auto.value)
        save_settings(s)

    def handle(self, ev, pos):
        if self.name.handle(ev, pos):
            self._save()
            return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self._save()
            self.app.pop()
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        if self.auto.click(pos):
            self._save()
        if self.music.click(pos) or self.sfx.click(pos) or self.cry.click(pos):
            AUDIO.set_volumes(sfx=self.sfx.value, music=self.music.value, cry=self.cry.value)
            AUDIO.play("select")
            self._save()
        if self.buttons[0].hit(pos):
            self._save()
            self.app.pop()

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "SETTINGS")
        for c in (self.music, self.sfx, self.cry, self.auto):
            c.draw(surf)
        self.name.draw(surf)
        ui.panel(surf, (60, 590, 600, 530))
        gfx.text(surf, "YOUR RECORD", (W / 2, 622), 26)
        rows = [("vs " + k, v) for k, v in sorted(self.record.get("vs", {}).items(), key=lambda kv: -sum(kv[1]))]
        rows += [(f"vs {k.upper()} bots", v) for k, v in self.record.get("bots", {}).items()]
        if not rows:
            gfx.text(surf, "No battles yet", (W / 2, 680), 20, ui.MUTED)
        for i, (label, (w, l_)) in enumerate(rows[:12]):
            y = 668 + i * 37
            gfx.text(surf, label, (90, y), 20, anchor="midleft", ow=1)
            pct = int(100 * w / max(1, w + l_))
            gfx.text(surf, f"{w}W - {l_}L   ({pct}%)", (630, y), 20, (255, 240, 150) if w >= l_ else ui.MUTED,
                     anchor="midright", ow=1)
        for b in self.buttons:
            b.draw(surf)
