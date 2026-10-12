"""The game window: scene stack, main menu, practice setup, PvP lobby."""
import os
import random
import threading

import pygame

from . import gfx, pokedex, ui
from .audio import AUDIO
from .bot import DIFF_INFO, DIFFICULTIES, bot_team
from .gfx import H, W
from .session import RTLocal, TurnLocal
from .team import load_saved, random_team, validate

STYLES = ["realtime", "turn"]
STYLE_NAMES = {"realtime": "Real-time Arena", "turn": "Turn-based (Showdown)"}
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
        self.display = gfx.Display(headless=headless, title="PokeBrawl")
        self.clock = pygame.time.Clock()
        self.stack = []
        self.dex = None
        self.running = True
        self.t = 0.0
        self.settings = load_settings()
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
        gfx.title_text(surf, "POKEBRAWL", (W / 2, H * 0.4), 80)
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
        x, w = 110, 500
        self.buttons = [
            ui.Button((x, 340, w, 120), "PRACTICE", (196, 60, 60), 40, "Battle a bot - easy to insane", tag="practice"),
            ui.Button((x, 480, w, 120), "SHOWCASE", (70, 120, 220), 40, "Mass battles, royales, tournaments + MP4",
                      tag="showcase"),
            ui.Button((x, 620, w, 120), "PVP", (60, 160, 90), 40, "Play your friends online - just a room code",
                      tag="pvp"),
            ui.Button((x, 760, 245, 84), "TEAMS", ui.PANEL2, 28, tag="teams"),
            ui.Button((x + 255, 760, 245, 84), "REPLAYS", ui.PANEL2, 28, tag="replays"),
            ui.Button((x, 860, 245, 70), "SETTINGS", (60, 58, 70), 24, tag="settings"),
            ui.Button((x + 255, 860, 245, 70), "QUIT", (60, 58, 70), 24, tag="quit"),
        ]

    def update(self, dt):
        AUDIO.music("menu")

    def handle(self, ev, pos):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for b in self.buttons:
                if b.hit(pos):
                    self.go(b.tag)
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
        elif tag == "settings":
            from .settings_ui import SettingsScene
            self.app.push(SettingsScene(self.app))
        elif tag == "quit":
            self.app.running = False

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        gfx.title_text(surf, "POKEBRAWL", (W / 2, 170), 96)
        gfx.text(surf, f"{len(self.app.dex.selectable())} Pokemon  -  {len(self.app.dex.moves)} moves",
                 (W / 2, 250), 20, ui.MUTED, ow=1, chunky=False)
        # a few random mascots
        for i, pid in enumerate((6, 150, 384)):
            img = gfx.SPRITES.get(pid, 90, flip=i == 0)
            surf.blit(img, img.get_rect(center=(W / 2 + (i - 1) * 200, 1110)))
        for b in self.buttons:
            b.draw(surf)
        gfx.text(surf, "Fan-made, not affiliated with Nintendo / Game Freak / The Pokemon Company", (W / 2, H - 30),
                 13, (110, 110, 125), ow=1, chunky=False)


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
        self.style = ui.Cycle((60, 240, 600, 70), "Battle style", STYLES, fmt=lambda v: STYLE_NAMES[v])
        self.style.set(s.get("practice_style", "realtime"))
        self.diff = ui.Cycle((60, 340, 600, 70), "Difficulty", DIFFICULTIES, 1, fmt=str.upper)
        self.diff.set(s.get("practice_diff", "normal"))
        self.team = ui.Cycle((60, 440, 600, 70), "Your team", opts)
        self.team.set(s.get("practice_team", "Random"))
        self.buttons = [ui.Button((60, 640, 600, 110), "START BATTLE", (196, 60, 60), 38),
                        ui.Button((60, 1150, 200, 70), "BACK", ui.PANEL2, 24, tag="back")]
        self.error = None

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        for c in (self.style, self.diff, self.team):
            c.click(pos)
        if self.buttons[1].hit(pos):
            self.app.pop()
        elif self.buttons[0].hit(pos):
            self.start()

    def start(self):
        app = self.app
        app.settings.update(practice_style=self.style.value, practice_diff=self.diff.value,
                            practice_team=self.team.value)
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
        if self.style.value == "realtime":
            from .battle_rt import RTBattle
            make = lambda: RTBattle(app, RTLocal(app.dex, mine, theirs, diff, seed))  # noqa: E731
        else:
            from .battle_turn import TurnBattleScene
            make = lambda: TurnBattleScene(app, TurnLocal(app.dex, mine, theirs, diff, seed))  # noqa: E731
        app.push(PrefetchScene(app, ids, make))

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "PRACTICE", "Train against a bot before you fight your friends")
        for c in (self.style, self.diff, self.team):
            c.draw(surf)
        gfx.text(surf, DIFF_INFO[self.diff.value], (W / 2, 535), 20, ui.MUTED, ow=1, chunky=False)
        for b in self.buttons:
            b.draw(surf)
        if self.error:
            gfx.text(surf, self.error, (W / 2, 790), 20, (255, 120, 120), chunky=False)
        tips = ["Real-time: click your Pokemon, then an enemy to focus it.",
                "Right-click the ground to move. Click a move to queue it. M = Mega.",
                "Turn-based: pick a move or switch each turn, Showdown style."]
        for i, t in enumerate(tips):
            gfx.text(surf, t, (W / 2, 870 + i * 34), 18, (190, 190, 205), ow=1, chunky=False)
