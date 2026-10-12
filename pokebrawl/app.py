"""The game window: scene stack, main menu, practice setup, PvP lobby."""
import os
import random
import threading

import pygame

from . import gfx, net, pokedex, ui
from .bot import DIFF_INFO, DIFFICULTIES, bot_team
from .gfx import H, W
from .session import Lobby, RTLocal, TurnLocal
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
            ui.Button((x, 360, w, 120), "PRACTICE", (196, 60, 60), 40, "Battle a bot - easy to insane", tag="practice"),
            ui.Button((x, 510, w, 120), "SHOWCASE", (70, 120, 220), 40, "Gen vs Gen mass battles + record MP4",
                      tag="showcase"),
            ui.Button((x, 660, w, 120), "PVP", (60, 160, 90), 40, "Play your friends online", tag="pvp"),
            ui.Button((x, 810, w, 90), "TEAM BUILDER", ui.PANEL2, 30, tag="teams"),
            ui.Button((x, 930, w, 70), "QUIT", (60, 58, 70), 24, tag="quit"),
        ]

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
            self.app.push(PvPSetup(self.app))
        elif tag == "teams":
            from .teambuilder import TeamList
            self.app.push(TeamList(self.app))
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


# ---------------------------------------------------------------------------- pvp
class PvPSetup(Scene):
    def __init__(self, app):
        super().__init__(app)
        s = app.settings
        opts, self.saved = team_options(app)
        self.style = ui.Cycle((60, 200, 600, 66), "Battle style", STYLES, fmt=lambda v: STYLE_NAMES[v])
        self.style.set(s.get("pvp_style", "turn"))
        self.team = ui.Cycle((60, 286, 600, 66), "Your team", opts)
        self.team.set(s.get("pvp_team", "Random"))
        self.conn = ui.Cycle((60, 372, 600, 66), "Connection", ["direct", "relay"],
                             fmt=lambda v: {"direct": "Direct (LAN / IP)", "relay": "Relay server"}[v])
        self.conn.set(s.get("pvp_conn", "direct"))
        self.name = ui.TextInput((60, 490, 600, 56), "Your name", s.get("name", os.environ.get("USER", "Trainer")))
        self.addr = ui.TextInput((60, 590, 600, 56), "Friend's address (to join)", s.get("join_addr", ""),
                                 "e.g. 192.168.1.20 or 100.x.y.z:7777")
        self.relay = ui.TextInput((60, 590, 380, 56), "Relay server", s.get("relay", ""), "relay.example.com:7778")
        self.room = ui.TextInput((460, 590, 200, 56), "Room code", s.get("room", ""), "ABCD")
        self.inputs = [self.name, self.addr, self.relay, self.room]
        self.buttons = [ui.Button((60, 690, 290, 110), "HOST", (60, 160, 90), 38, "you run the battle"),
                        ui.Button((370, 690, 290, 110), "JOIN", (70, 120, 220), 38, "connect to a host"),
                        ui.Button((60, 1150, 200, 70), "BACK", ui.PANEL2, 24)]
        self.error = None

    def visible_inputs(self):
        if self.conn.value == "relay":
            return [self.name, self.relay, self.room]
        return [self.name, self.addr]

    def handle(self, ev, pos):
        for i in self.visible_inputs():
            if i.handle(ev, pos):
                return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        for c in (self.style, self.team, self.conn):
            c.click(pos)
        if self.buttons[2].hit(pos):
            self.app.pop()
        elif self.buttons[0].hit(pos):
            self.go("host")
        elif self.buttons[1].hit(pos):
            self.go("join")

    def go(self, role):
        app = self.app
        app.settings.update(pvp_style=self.style.value, pvp_team=self.team.value, pvp_conn=self.conn.value,
                            name=self.name.value or "Trainer", join_addr=self.addr.value, relay=self.relay.value,
                            room=self.room.value)
        save_settings(app.settings)
        team = pick_team(app, self.team.value, self.saved)
        errs = validate(app.dex, team)
        if errs:
            self.error = errs[0]
            return
        relay = self.conn.value == "relay"
        if relay and (not self.relay.value or not self.room.value):
            self.error = "Enter the relay server and a room code (same code as your friend)"
            return
        if role == "join" and not relay and not self.addr.value:
            self.error = "Enter your friend's address"
            return
        app.push(LobbyScene(app, role, self.style.value, team, self.name.value or "Trainer",
                            addr=self.addr.value, relay=self.relay.value if relay else None, room=self.room.value))

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "PVP", "Battle your friends with your comp teams")
        for c in (self.style, self.team, self.conn):
            c.draw(surf)
        for i in self.visible_inputs():
            i.draw(surf)
        for b in self.buttons:
            b.draw(surf)
        if self.error:
            gfx.text(surf, self.error, (W / 2, 830), 19, (255, 120, 120), chunky=False)
        lines = (["HOST: share your address (shown next) with your friend.",
                  "Same Wi-Fi works right away. Over the internet: use Tailscale",
                  "(free, easiest), forward port 7777, or a relay server."]
                 if self.conn.value == "direct" else
                 ["Relay: both players enter the same relay server + room code.",
                  "Anyone can run one on a cheap VPS with: pokebrawl relay",
                  "One player presses HOST, the other JOIN."])
        lines += ["", "The host picks the battle style. Species + Item Clause, 1 Mega per team."]
        for i, t in enumerate(lines):
            gfx.text(surf, t, (W / 2, 900 + i * 32), 17, (190, 190, 205), ow=1, chunky=False)


class LobbyScene(Scene):
    def __init__(self, app, role, style, team, name, addr="", relay=None, room=""):
        super().__init__(app)
        self.role, self.style, self.team, self.name = role, style, team, name
        self.host = None
        self.conn = None
        self.lobby = None
        self.error = None
        self.status = "Starting..."
        self.buttons = [ui.Button((260, 1100, 200, 70), "CANCEL", ui.PANEL2, 24)]
        self.ips = net.local_ips()
        if role == "host":
            try:
                self.host = net.Host(net.DEFAULT_PORT, relay=relay, room=room)
                self.status = "Waiting for your friend to join..." if not relay else f"Waiting in room {room.upper()}..."
            except OSError as e:
                self.error = f"Couldn't open port {net.DEFAULT_PORT}: {e}"
        else:
            self.status = "Connecting..."
            threading.Thread(target=self._join, args=(addr, relay, room), daemon=True).start()
        self.relay = relay

    def _join(self, addr, relay, room):
        try:
            self.conn = net.relay_connect(relay, room, "join") if relay else net.connect(addr)
        except Exception as e:  # noqa: BLE001
            self.error = f"Couldn't connect: {e}"

    def close(self):
        if self.host:
            self.host.close()
        if self.conn and not self.lobby:
            self.conn.close()

    def handle(self, ev, pos):
        if (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.buttons[0].hit(pos)) or \
                (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
            self.app.pop()

    def update(self, dt):
        if self.error:
            return
        if self.host and self.host.error:
            self.error = self.host.error
        if self.conn is None and self.host and self.host.conn:
            self.conn = self.host.conn
        if self.conn and not self.lobby:
            self.status = "Connected! Exchanging teams..."
            self.lobby = Lobby(self.app.dex, self.conn, self.role, self.style, self.team, self.name)
        if self.lobby:
            session = self.lobby.poll()
            if self.lobby.error:
                self.error = self.lobby.error
            elif session:
                app = self.app
                if self.lobby.style == "realtime":
                    from .battle_rt import RTBattle
                    scene = RTBattle(app, session)
                    ids = [r["species"] for r in session.roster.values()]
                else:
                    from .battle_turn import TurnBattleScene
                    scene = TurnBattleScene(app, session)
                    ids = [m.species for m in self.team]
                self.lobby = None  # the session owns the connection now
                self.conn = None
                if self.host:
                    self.host.close()
                    self.host = None
                app.replace(PrefetchScene(app, ids, lambda: scene))

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "HOSTING" if self.role == "host" else "JOINING", STYLE_NAMES[self.style]
                  if self.role == "host" else None)
        ui.panel(surf, (60, 260, 600, 420))
        if self.error:
            gfx.text(surf, self.error, (W / 2, 420), 20, (255, 120, 120), chunky=False)
        else:
            gfx.text(surf, self.status, (W / 2, 320), 26)
            dots = "." * (int(self.app.t * 2) % 4)
            gfx.text(surf, dots, (W / 2, 360), 30)
            if self.role == "host" and not self.relay:
                gfx.text(surf, "Tell your friend to JOIN one of:", (W / 2, 430), 20, ui.MUTED, chunky=False)
                for i, ip in enumerate(self.ips[:4]):
                    gfx.text(surf, f"{ip}:{net.DEFAULT_PORT}", (W / 2, 480 + i * 44), 30, (255, 240, 150))
        for b in self.buttons:
            b.draw(surf)
