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


# Showcase mode is only for the game's owner: it unlocks on a computer once the secret code is typed on the
# main menu (or `pokebrawl unlock CODE`). Only the code's hash lives here.
CREATOR_HASH = "a9fd4f63c5e7bb920cb0be1d72831ea1ca584575b218f98cdb04bbfba125e50a"


def creator_unlocked(settings):
    import hashlib
    key = settings.get("creator_key", "")
    return bool(key) and hashlib.sha256(key.strip().upper().encode()).hexdigest() == CREATOR_HASH


def try_unlock(settings, code):
    """Returns True (and remembers it) if code is the owner's code."""
    import hashlib
    code = code.strip().upper()
    if hashlib.sha256(code.encode()).hexdigest() != CREATOR_HASH:
        return False
    settings["creator_key"] = code
    save_settings(settings)
    return True


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
        gfx.SPRITES.async_load = not headless   # downloads never freeze the screen
        self._shown = None        # the scene drawn last frame (to notice screen changes)
        self._trans = None        # [old frame, time, direction] while a screen transition plays

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

    TRANSITION = 0.32

    def _start_transition(self, scene, canvas):
        """The screen just changed: keep the old picture and slide it away over the new one."""
        old = self._shown
        self._shown = scene
        if old is None or getattr(scene, "no_transition", False) or getattr(old, "no_transition", False):
            self._trans = None
            return
        if canvas.get_size() != (gfx.W, gfx.H):
            self._trans = None
            return
        back = old not in self.stack   # popped: slide right, pushed: slide left
        self._trans = [canvas.copy(), 0.0, 1 if back else -1]

    def _draw_transition(self, canvas, dt):
        if not self._trans or canvas.get_size() != self._trans[0].get_size():
            self._trans = None
            return
        old, t, d = self._trans
        t += dt
        self._trans[1] = t
        k = min(1.0, t / self.TRANSITION)
        e = 1 - (1 - k) ** 3
        w = canvas.get_width()
        # the new screen slides in like a card over the old one, which drifts back and dims
        if k < 1:
            new = canvas.copy()
            canvas.blit(old, (int(d * w * 0.2 * e), 0))
            dim = pygame.Surface(canvas.get_size(), pygame.SRCALPHA)
            dim.fill((0, 0, 0, int(170 * e)))
            canvas.blit(dim, (0, 0))
            x = int(-d * w * (1 - e))
            canvas.blit(new, (x, 0))
            # soft shadow cast by the sliding card onto the old screen
            hgt = canvas.get_height()
            shade = pygame.Surface((16, hgt), pygame.SRCALPHA)
            for i in range(16):  # darkest right next to the card's edge
                col = 15 - i if d < 0 else i
                pygame.draw.line(shade, (0, 0, 0, 130 - i * 8), (col, 0), (col, hgt))
            canvas.blit(shade, (x - 16, 0) if d < 0 else (x + w, 0))
        else:
            self._trans = None

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
            canvas = self.display.canvas
            if scene is not self._shown:
                self._start_transition(scene, canvas)
            scene.draw(canvas)
            self._draw_transition(canvas, dt)
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
        self.typed = ""
        self.unlock_t = -9.0
        self._build()
        from .updater import AutoUpdater
        from .version import current
        self.version = current()
        self.updater = AutoUpdater(auto=app.settings.get("auto_update", "On") == "On")
        self.restart_btn = ui.Button((60, 1100, 600, 72), "Restart to update", (34, 140, 88), 26,
                                     "or it installs next time you open the game")

    def _build(self):
        x, w = 60, 600
        big = [("Adventure", (232, 150, 40), "Catch Pokemon, beat 8 gyms, become Champion", "adventure", 25),
               ("Practice", ui.SHELL, "Turn-based battles against a bot", "practice", 6)]
        if creator_unlocked(self.app.settings):
            big.append(("Showcase", (38, 104, 188), "Mass battles and royales for your videos", "showcase", 384))
        big.append(("PvP", (34, 140, 88), "Battle your friends with a room code", "pvp", 448))
        h = 140 if len(big) == 4 else 182
        gap = (608 - h * len(big)) // max(1, len(big) - 1)
        self.buttons = [ui.Button((x, 236 + i * (h + gap), w, h), label, col, 44, sub, tag=tag, icon=icon)
                        for i, (label, col, sub, tag, icon) in enumerate(big)] + [
            ui.Button((x, 860, 190, 100), "Teams", ui.SCREEN2, 28, tag="teams"),
            ui.Button((x + 205, 860, 190, 100), "Pokedex", ui.SCREEN2, 28, tag="dex"),
            ui.Button((x + 410, 860, 190, 100), "Replays", ui.SCREEN2, 28, tag="replays"),
            ui.Button((x, 984, 190, 84), "Trainer", (130, 60, 200), 24, tag="trainer"),
            ui.Button((x + 205, 984, 190, 84), "Settings", ui.SCREEN2, 24, tag="settings"),
            ui.Button((x + 410, 984, 190, 84), "Quit", ui.SCREEN2, 24, tag="quit"),
        ]

    TIPS = ["Win battles for a chance to meet a legendary",
            "Shiny Pokemon are 1 in 512 in Adventure",
            "Tournament mode: 8 or 16 Pokemon, one champion",
            "Hold a Choice item and you're locked into one move",
            "Press G in a 1v1 to Gigantamax (if your Pokemon can)",
            "Hold X to run in Adventure",
            "Rank up for a guaranteed legendary encounter",
            "Tap a sprite in the Pokedex to see its shiny",
            "Only one legendary per team in PvP",
            "Talk to the nurse in any Pokemon Center to heal"]

    def update(self, dt):
        AUDIO.music("menu")
        self._parade_update(dt)

    def _parade_update(self, dt):
        """Pokemon running across the strip under the header."""
        if not hasattr(self, "parade"):
            self.parade, self.parade_rng, self.parade_gap = [], random.Random(), 0.0
        self.parade_gap -= dt
        if self.parade_gap <= 0 and self.app.dex:
            rng = self.parade_rng
            e = rng.choice(self.app.dex.selectable())
            # only Pokemon already on disk (never stall the menu on a download)
            if not os.path.exists(pokedex.sprite_path(e["id"])):
                return
            shiny = rng.randrange(64) == 0 and os.path.exists(os.path.join(pokedex.SPRITE_DIR,
                                                                           f"shiny-{e['id']}.png"))
            self.parade.append([W + 60, e["id"], rng.uniform(70, 130), rng.uniform(0, 6), shiny])
            self.parade_gap = rng.uniform(0.7, 1.6)
        for p in self.parade:
            p[0] -= p[2] * dt
        self.parade = [p for p in self.parade if p[0] > -80]

    def _draw_parade(self, surf):
        t = self.app.t
        for x, pid, speed, ph, shiny in getattr(self, "parade", []):
            hop = abs(math.sin(t * speed / 14 + ph)) * 10
            img = gfx.SPRITES.get(pid, 62, flip=True, shiny=shiny)
            if img.get_width() > 90:
                img = gfx.SPRITES.get(pid, int(62 * 90 / img.get_width()), flip=True, shiny=shiny)
            pygame.draw.ellipse(surf, (16, 22, 32), (x - 22, 218, 44, 10))
            surf.blit(img, img.get_rect(midbottom=(x, 224 - hop)))
            if shiny:
                gfx.sparkles(surf, (x, 190), 40, t, pid, 4)

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
        if ev.type == pygame.TEXTINPUT:   # the owner's secret code, typed anywhere on this screen
            self.typed = (self.typed + ev.text.upper())[-16:]
            for n in range(8, 13):
                if len(self.typed) >= n and try_unlock(self.app.settings, self.typed[-n:]):
                    self.typed = ""
                    self.unlock_t = self.app.t
                    AUDIO.play("win")
                    self._build()
                    break
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.running = False

    def go(self, tag):
        if tag == "adventure":
            from .adventure_ui import AdventureTitle
            self.app.push(AdventureTitle(self.app))
        elif tag == "practice":
            self.app.push(PracticeSetup(self.app))
        elif tag == "showcase" and creator_unlocked(self.app.settings):
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
        elif tag == "dex":
            from .pokedex_ui import PokedexScene
            self.app.push(PokedexScene(self.app))
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
        self._draw_parade(surf)
        if self.app.t - self.unlock_t < 3:
            gfx.text(surf, "Showcase unlocked on this computer", (W / 2, 1050 + 85), 20, ui.SIGNAL, None, 0)
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
        if st not in ("ready", "downloading", "available", "error"):
            tip = self.TIPS[int(self.app.t / 6) % len(self.TIPS)]
            k = (self.app.t / 6) % 1.0
            a = int(255 * min(1.0, k / 0.08, (1 - k) / 0.08))
            ui.panel(surf, (60, 1100, 600, 60), ui.SCREEN2, 12)
            gfx.text(surf, "TIP", (90, 1130), 15, ui.SIGNAL, None, 0, anchor="midleft")
            gfx.text(surf, tip, (134, 1130), 16, ui.TEXT, None, 0, anchor="midleft", chunky=False, alpha=a)
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
