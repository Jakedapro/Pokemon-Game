"""The game window: scene stack, main menu, practice setup, PvP lobby."""
import math
import os
import random
import threading

import pygame

from . import gfx, pokedex, profile, ui
from .audio import AUDIO
from .bot import DIFF_INFO, DIFFICULTIES, bot_team
from .gfx import H, W
from .session import TurnLocal
from .team import load_saved, random_team, validate

STYLE_NAMES = {"turn": "Turn-based", "realtime": "Arena"}
SETTINGS_FILE = os.path.join(pokedex.HOME, "settings.txt")


def load_settings():
    out = {}
    try:
        with open(SETTINGS_FILE) as f:
            for line in f:
                if "=" in line:
                    k, v = line.rstrip("\n").split("=", 1)
                    out[k] = v
    except OSError:
        pass
    return out


def save_settings(d):
    os.makedirs(pokedex.HOME, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        for k, v in d.items():
            f.write(f"{k}={v}\n")


class Scene:
    def __init__(self, app):
        self.app = app

    def handle(self, ev, pos):
        pass

    def update(self, dt):
        pass

    def draw(self, surf):
        pass


class App:
    def __init__(self, headless=False):
        self.settings = load_settings()
        self.display = gfx.Display(headless=headless, title="PokeBrawl")
        self.clock = pygame.time.Clock()
        self.stack = []
        self.dex = None
        self.running = True
        self.t = 0.0
        pygame.key.set_repeat(350, 35)
        AUDIO.init(self.settings, headless=headless)

    def push(self, scene):
        self.stack.append(scene)

    def pop(self):
        s = self.stack.pop()
        close = getattr(s, "close", None)
        if close:
            close()

    def replace(self, scene):
        self.pop()
        self.push(scene)

    def home(self):
        while len(self.stack) > 1:
            self.pop()
        gfx.SPRITES.shiny_forms = set()

    def run(self):
        self.push(LoadingScene(self))
        while self.running and self.stack:
            dt = min(0.05, self.clock.tick(60) / 1000)
            self.t += dt
            scene = self.stack[-1]
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    self.running = False
                pos = None
                if hasattr(ev, "pos"):
                    pos = self.display.to_canvas(ev.pos)
                elif ev.type == pygame.MOUSEWHEEL:
                    pos = self.display.to_canvas(pygame.mouse.get_pos())
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and pos and \
                        any(b.rect.collidepoint(pos) and b.enabled for b in getattr(scene, "buttons", [])):
                    AUDIO.play("click", 0.8)
                scene.handle(ev, pos)
            scene = self.stack[-1] if self.stack else None
            if scene is None:
                break
            scene.update(dt)
            scene = self.stack[-1] if self.stack else scene
            # most screens are portrait in a window; big battle royales ask for a wide full-screen canvas
            self.display.set_canvas(getattr(scene, "canvas_size", (gfx.W, gfx.H)))
            mp = self.display.to_canvas(pygame.mouse.get_pos())
            for b in getattr(scene, "buttons", []):
                b.hover = b.rect.collidepoint(mp)
            scene.draw(self.display.canvas)
            self.display.present()
        while self.stack:
            self.pop()
        pygame.quit()


# ---------------------------------------------------------------------------- loading
class LoadingScene(Scene):
    """First launch: downloads the Pokedex. Later launches: instant."""

    def __init__(self, app):
        super().__init__(app)
        self.msg = "Loading Pokedex..."
        self.error = None
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            self.app.dex = pokedex.load_dex(progress=lambda m: setattr(self, "msg", m.replace("[pokebrawl] ", "")))
        except Exception as e:  # noqa: BLE001
            self.error = f"Couldn't download data: {e}"

    def update(self, dt):
        if self.app.dex:
            self.app.replace(MainMenu(self.app))

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "PokeBrawl")
        gfx.text(surf, self.error or self.msg, (W / 2, H * 0.5), 22, (220, 220, 230), chunky=False)
        if self.error:
            gfx.text(surf, "Check your internet connection and restart.", (W / 2, H * 0.54), 18, ui.MUTED,
                     chunky=False)


class PrefetchScene(Scene):
    """Makes sure sprites are on disk before a battle starts, then swaps to the next scene."""

    def __init__(self, app, ids, make_next):
        super().__init__(app)
        self.done = 0
        self.total = 1
        self.make_next = make_next
        self.finished = False
        ids = set(ids)
        for i in list(ids):
            ids.update(app.dex.all.get(i, {}).get("megas", []))
        threading.Thread(target=self._go, args=(list(ids),), daemon=True).start()

    def _go(self, ids):
        def prog(d, t):
            self.done, self.total = d, t
        pokedex.prefetch(ids, prog)
        pokedex.ensure_item("poke-ball")
        for pid in ids:  # back sprites too (your side), so send-outs don't freeze while downloading
            pokedex.ensure_back_sprite(pid)
        from .audio import prefetch_cries
        prefetch_cries(ids)
        self.finished = True

    def update(self, dt):
        if self.finished:
            self.app.replace(self.make_next())

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        gfx.text(surf, "Getting sprites ready...", (W / 2, H * 0.45), 30)
        gfx.hp_bar(surf, (160, int(H * 0.5), 400, 14), self.done / max(1, self.total))


# ---------------------------------------------------------------------------- main menu
class MainMenu(Scene):
    def __init__(self, app):
        super().__init__(app)
        x, w = 60, 600
        self.buttons = [
            ui.Button((x, 236, w, 176), "Practice", ui.SHELL, 46, "Turn-based battles against a bot",
                      tag="practice", icon=6),
            ui.Button((x, 440, w, 176), "Showcase", (38, 104, 188), 46, "Mass battles and royales for your videos",
                      tag="showcase", icon=384),
            ui.Button((x, 644, w, 176), "PvP", (34, 140, 88), 46, "Battle your friends with a room code",
                      tag="pvp", icon=25),
            ui.Button((x, 860, 290, 100), "Teams", ui.SCREEN2, 30, tag="teams"),
            ui.Button((x + 310, 860, 290, 100), "Replays", ui.SCREEN2, 30, tag="replays"),
            ui.Button((x, 984, 190, 84), "Trainer", (130, 60, 200), 24, tag="trainer"),
            ui.Button((x + 205, 984, 190, 84), "Settings", ui.SCREEN2, 24, tag="settings"),
            ui.Button((x + 410, 984, 190, 84), "Quit", ui.SCREEN2, 24, tag="quit"),
        ]
        from .updater import AutoUpdater
        from .version import current
        self.version = current()
        self.updater = AutoUpdater(auto=app.settings.get("auto_update", "On") == "On")
        self.restart_btn = ui.Button((60, 1100, 600, 72), "Restart to update", (34, 140, 88), 26,
                                     "or it installs next time you open the game")

    def update(self, dt):
        AUDIO.music("menu")

    def _rp(self):
        now = self.app.t
        if now - getattr(self, "_rp_t", -9) > 1.0:   # re-read now and then (battles change it)
            self._rp_t, self._rp_v = now, profile.load()["rp"]
        return self._rp_v

    def handle(self, ev, pos):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.updater.state == "ready" and self.restart_btn.hit(pos):
                from .updater import restart
                restart()
            for b in self.buttons:
                if b.hit(pos):
                    self.go(b.tag)
            if math.hypot(pos[0] - 650, pos[1] - 62) < 46:   # the rank badge in the corner
                self.go("trainer")
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.running = False

    def go(self, tag):
        if tag == "practice":
            self.app.push(PracticeSetup(self.app))
        elif tag == "showcase":
            from .showcase_ui import ShowcaseMenu
            self.app.push(ShowcaseMenu(self.app))
        elif tag == "pvp":
            from .pvp_ui import PvPSetup
            self.app.push(PvPSetup(self.app))
        elif tag == "teams":
            from .teambuilder import TeamList
            self.app.push(TeamList(self.app))
        elif tag == "replays":
            from .replays_ui import ReplayList
            self.app.push(ReplayList(self.app))
        elif tag == "trainer":
            from .trainer_ui import TrainerCard
            self.app.push(TrainerCard(self.app))
        elif tag == "settings":
            from .settings_ui import SettingsScene
            self.app.push(SettingsScene(self.app))
        elif tag == "quit":
            self.app.running = False

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "PokeBrawl", f"{len(self.app.dex.selectable())} Pokemon and {len(self.app.dex.moves)} moves")
        rk = profile.rank_of(self._rp())
        ui.rank_badge(surf, (650, 58), 34, rk, self.app.t)
        gfx.text(surf, rk["label"], (650, 118), 13, (255, 230, 235), ui.SHELL_DARK, 2)
        for b in self.buttons:
            b.draw(surf)
        h, d = self.version
        gfx.text(surf, f"Version {h}, {d}" if d else f"Version {h}", (W / 2, H - 52), 14, ui.MUTED, None, 0,
                 chunky=False)
        gfx.text(surf, "Fan-made, not affiliated with Nintendo, Game Freak or The Pokemon Company", (W / 2, H - 30),
                 13, (96, 110, 128), None, 0, chunky=False)
        st = self.updater.state
        if st == "ready":
            self.restart_btn.draw(surf)
        elif st == "downloading":
            gfx.text(surf, "Downloading an update...", (W / 2, 1130), 18, ui.MUTED, None, 0, chunky=False)
        elif st in ("available", "error"):
            ui.panel(surf, (60, 1100, 600, 60), ui.SCREEN2, 12)
            gfx.text(surf, "An update is available. Run pokebrawl update in Terminal.", (W / 2, 1130), 17,
                     ui.SIGNAL, None, 0, chunky=False)


def team_options(app):
    saved = load_saved()
    return ["Random"] + sorted(saved), saved


def pick_team(app, choice, saved, rng=None):
    if choice in saved:
        return saved[choice]
    return random_team(app.dex, rng or random.Random())


# ---------------------------------------------------------------------------- practice
class PracticeSetup(Scene):
    def __init__(self, app):
        super().__init__(app)
        opts, self.saved = team_options(app)
        s = app.settings
        self.diff = ui.Cycle((60, 300, 600, 70), "Difficulty", DIFFICULTIES, 1, fmt=str.upper)
        self.diff.set(s.get("practice_diff", "normal"))
        self.team = ui.Cycle((60, 400, 600, 70), "Your team", opts)
        self.team.set(s.get("practice_team", "Random"))
        self.buttons = [ui.Button((60, 640, 600, 110), "Start battle", ui.SHELL, 38),
                        ui.Button((60, 1150, 200, 70), "Back", ui.PANEL2, 24, tag="back")]
        self.error = None

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        for c in (self.diff, self.team):
            c.click(pos)
        if self.buttons[1].hit(pos):
            self.app.pop()
        elif self.buttons[0].hit(pos):
            self.start()

    def start(self):
        app = self.app
        app.settings.update(practice_diff=self.diff.value, practice_team=self.team.value)
        save_settings(app.settings)
        mine = pick_team(app, self.team.value, self.saved)
        errs = validate(app.dex, mine)
        if errs:
            self.error = errs[0]
            return
        diff = self.diff.value
        theirs = bot_team(app.dex, diff)
        seed = random.randrange(1 << 30)
        ids = [m.species for m in mine + theirs]
        from .battle_turn import TurnBattleScene
        make = lambda: TurnBattleScene(app, TurnLocal(app.dex, mine, theirs, diff, seed))  # noqa: E731
        app.push(PrefetchScene(app, ids, make))

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "Practice", "Train against a bot")
        for c in (self.diff, self.team):
            c.draw(surf)
        gfx.text(surf, DIFF_INFO[self.diff.value], (W / 2, 500), 20, ui.MUTED, ow=1, chunky=False)
        for b in self.buttons:
            b.draw(surf)
        if self.error:
            gfx.text(surf, self.error, (W / 2, 790), 20, (255, 120, 120), chunky=False)
        tips = ["Pick a move or switch each turn, Showdown style.",
                "1-4 = moves, M = Mega Evolve, T = Terastallize.",
                "Insane bots get legendary teams and never misplay."]
        for i, t in enumerate(tips):
            gfx.text(surf, t, (W / 2, 870 + i * 34), 18, (190, 190, 205), ow=1, chunky=False)
