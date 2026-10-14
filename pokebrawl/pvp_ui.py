"""PvP screens: connection setup, room codes, open-room browser, LAN browser, lobby."""
import os
import threading

import pygame

from . import gfx, net, online, profile, ui
from .app import STYLE_NAMES, PrefetchScene, Scene, pick_team, save_settings, team_options
from .gfx import W
from .session import Lobby
from .team import validate

CONNS = ["room", "lan", "direct", "relay"]
CONN_NAMES = {"room": "Online room code", "lan": "Same Wi-Fi", "direct": "Direct IP", "relay": "Relay server"}
CONN_HELP = {
    "room": ["Works anywhere with internet - no setup.",
             "HOST gets a 5-letter code. Your friend taps JOIN and types it.",
             "Or list your room publicly and they pick it from OPEN ROOMS."],
    "lan": ["Both on the same Wi-Fi / hotspot.",
            "HOST, then your friend's JOIN screen finds you automatically.", ""],
    "direct": ["Host shares their IP (Tailscale IPs work great).",
               "Needs port 7777 open if you're not on the same network.", ""],
    "relay": ["Both enter the same relay server + room code.",
              "Run your own relay on any server with: pokebrawl relay", ""],
}


class PvPSetup(Scene):
    def __init__(self, app):
        super().__init__(app)
        s = app.settings
        opts, self.saved = team_options(app)
        self.team = ui.Cycle((60, 190, 600, 64), "Your team", opts)
        self.team.set(s.get("pvp_team", "Random"))
        self.conn = ui.Cycle((60, 268, 600, 64), "Connection", CONNS, fmt=lambda v: CONN_NAMES[v])
        self.conn.set(s.get("pvp_conn2", "room"))
        self.public = ui.Cycle((60, 346, 600, 64), "List room publicly", ["No", "Yes"])
        self.public.set(s.get("pvp_public", "No"))
        self.ranked = ui.Cycle((60, 424, 600, 64), "Match type", ["Ranked", "Casual"])
        self.ranked.set(s.get("pvp_ranked", "Ranked"))
        self.rating = profile.my_rating()
        self.name = ui.TextInput((60, 530, 290, 56), "Your name", s.get("name", os.environ.get("USER", "Trainer")))
        self.code = ui.TextInput((370, 530, 290, 56), "Room code (to join)", "", "ABCDE")
        self.addr = ui.TextInput((370, 530, 290, 56), "Friend's address", s.get("join_addr", ""), "192.168.1.20")
        self.relay = ui.TextInput((60, 630, 380, 56), "Relay server", s.get("relay", ""), "relay.example.com:7778")
        self.room = ui.TextInput((460, 630, 200, 56), "Relay room", s.get("room", ""), "ABCD")
        self.error = None
        self._layout()

    def _layout(self):
        y = 720
        self.buttons = [ui.Button((60, y, 290, 110), "Host", (34, 140, 88), 38, "start a battle"),
                        ui.Button((370, y, 290, 110), "Join", (38, 104, 188), 38,
                                  {"room": "enter the code", "lan": "find games nearby", "direct": "connect to IP",
                                   "relay": "enter the room"}[self.conn.value]),
                        ui.Button((60, 1150, 200, 70), "Back", ui.PANEL2, 24)]
        if self.conn.value == "room":
            self.buttons.append(ui.Button((60, 850, 290, 70), "Browse open rooms", (150, 80, 200), 22))
            self.buttons.append(ui.Button((370, 850, 290, 70), "Quick Match", (200, 120, 30), 26, "ranked, near you"))
        self.buttons.append(ui.Button((460, 1150, 200, 70), "Ladder", (60, 90, 160), 24))

    def inputs(self):
        c = self.conn.value
        return [self.name] + ({"room": [self.code], "lan": [], "direct": [self.addr],
                               "relay": [self.relay, self.room]}[c])

    def handle(self, ev, pos):
        for i in self.inputs():
            if i.handle(ev, pos):
                return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        for c in (self.team, self.conn, self.ranked) + ((self.public,) if self.conn.value == "room" else ()):
            if c.click(pos):
                self._layout()
        b = self.buttons
        if b[2].hit(pos):
            self.app.pop()
        elif b[0].hit(pos):
            self.go("host")
        elif b[1].hit(pos):
            self.go("join")
        elif b[-1].hit(pos):
            self.app.push(LadderScene(self.app))
        elif len(b) > 4 and b[3].hit(pos):
            self.go("browse")
        elif len(b) > 4 and b[4].hit(pos):
            self.go("quick")

    def _team(self):
        team = pick_team(self.app, self.team.value, self.saved)
        errs = validate(self.app.dex, team)
        if errs:
            self.error = errs[0]
            return None
        return team

    def go(self, role):
        app = self.app
        app.settings.update(pvp_team=self.team.value, pvp_conn2=self.conn.value, pvp_ranked=self.ranked.value,
                            pvp_public=self.public.value, name=self.name.value or "Trainer",
                            join_addr=self.addr.value, relay=self.relay.value, room=self.room.value)
        save_settings(app.settings)
        team = self._team()
        if not team:
            return
        name = (self.name.value or "Trainer")[:16]
        c = self.conn.value
        ranked = self.ranked.value == "Ranked"
        if role == "browse":
            app.push(RoomBrowser(app, team, name, ranked))
            return
        if role == "quick":
            app.push(QuickMatch(app, team, name))
            return
        if c == "lan" and role == "join":
            app.push(LanBrowser(app, team, name, "turn"))
            return
        if c == "room" and role == "join" and len(self.code.value.strip()) < 4:
            self.error = "Type the room code your friend sees"
            return
        if c == "direct" and role == "join" and not self.addr.value:
            self.error = "Enter your friend's address"
            return
        if c == "relay" and (not self.relay.value or not self.room.value):
            self.error = "Enter the relay server and a room code (same as your friend)"
            return
        app.push(LobbyScene(app, role, c, "turn", team, name, code=self.code.value,
                            addr=self.addr.value, relay=self.relay.value, room=self.room.value,
                            public=self.public.value == "Yes", ranked=ranked))

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "PvP", "Battle your friends online")
        rk = profile.mmr_rank(self.rating["mmr"], self.rating["games"])
        ui.rank_badge(surf, (420, 165), 14, rk, self.app.t)
        gfx.text(surf, (f"{rk['label']}  {rk['mmr']}" if not rk.get("placing") else rk["label"]) +
                 f"   {self.rating['w']}W {self.rating['l']}L", (442, 165), 17, rk["color"], gfx.INK, 1,
                 anchor="midleft", chunky=False)
        for c in (self.team, self.conn, self.ranked):
            c.draw(surf)
        if self.conn.value == "room":
            self.public.draw(surf)
        for i in self.inputs():
            i.draw(surf)
        for b in self.buttons:
            b.draw(surf)
        if self.error:
            gfx.text(surf, self.error, (W / 2, 950), 19, (255, 120, 120), chunky=False)
        for i, t in enumerate(CONN_HELP[self.conn.value] +
                              ["", "Turn-based singles. Species + Item Clause, 1 Mega + 1 Tera per team."]):
            gfx.text(surf, t, (W / 2, 990 + i * 28), 17, (190, 190, 205), ow=1, chunky=False)


class RoomBrowser(Scene):
    """Lists public rooms from the online servers."""

    def __init__(self, app, team, name, ranked=True):
        super().__init__(app)
        self.team, self.name, self.ranked = team, name, ranked
        self.list = ui.ListView((40, 170, 640, 860), 84)
        self.rooms = []
        self.loading = True
        self.buttons = [ui.Button((40, 1150, 200, 70), "Back", ui.PANEL2, 24),
                        ui.Button((480, 1150, 200, 70), "Refresh", (38, 104, 188), 24)]
        self.refresh()

    def refresh(self):
        self.loading = True

        def go():
            try:
                self.rooms = online.list_public_rooms()
            except Exception:  # noqa: BLE001
                self.rooms = []
            self.loading = False
            rows = []
            for r in self.rooms:
                def draw(surf, rect, sel, r=r):
                    gfx.text(surf, r.get("name", "?"), (rect.x + 16, rect.y + 26), 24, anchor="midleft", ow=1)
                    rk = profile.mmr_rank(int(r.get("mmr", 1000)), int(r.get("games", 0)))
                    sub = STYLE_NAMES.get(r.get("style"), r.get("style", "")) + \
                        ("   RANKED" if r.get("ranked") else "   casual") + \
                        (f"   {rk['label']} {rk['mmr']}" if "mmr" in r and not rk.get("placing") else "")
                    gfx.text(surf, sub, (rect.x + 16, rect.y + 56), 16, rk["color"] if r.get("ranked") else ui.MUTED,
                             anchor="midleft", ow=1, chunky=False)
                    gfx.text(surf, r["code"], (rect.right - 16, rect.centery), 30, (255, 240, 150), anchor="midright")
                rows.append((r["code"], draw))
            self.list.set_rows(rows)
        threading.Thread(target=go, daemon=True).start()

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        picked = self.list.handle(ev, pos)
        if picked:
            r = next(x for x in self.rooms if x["code"] == picked)
            self.app.replace(LobbyScene(self.app, "join", "room", r.get("style", "turn"), self.team, self.name,
                                        code=r["code"],
                                        broker=r["broker"] if r["broker"] == "https" else tuple(r["broker"]),
                                        ranked=self.ranked))
            return
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.buttons[0].hit(pos):
                self.app.pop()
            elif self.buttons[1].hit(pos) and not self.loading:
                self.refresh()

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "Open rooms", "Public rooms open right now")
        self.list.draw(surf)
        if self.loading:
            gfx.text(surf, "Looking for rooms...", (W / 2, 500), 26)
        elif not self.rooms:
            gfx.text(surf, "No open rooms right now", (W / 2, 480), 26, ui.MUTED)
            gfx.text(surf, "Host one with 'List room publicly: Yes'", (W / 2, 520), 18, ui.MUTED, chunky=False)
        for b in self.buttons:
            b.draw(surf)


class LanBrowser(Scene):
    """Finds games hosted on the same network."""

    def __init__(self, app, team, name, style):
        super().__init__(app)
        self.team, self.name, self.style = team, name, style
        self.scanner = online.LanScanner()
        self.list = ui.ListView((40, 170, 640, 700), 84)
        self.addr = ui.TextInput((40, 950, 440, 56), "Or type an address", app.settings.get("join_addr", ""),
                                 "192.168.1.20")
        self.buttons = [ui.Button((40, 1150, 200, 70), "Back", ui.PANEL2, 24),
                        ui.Button((500, 950, 180, 56), "Join", (38, 104, 188), 24)]

    def close(self):
        self.scanner.close()

    def update(self, dt):
        rows = []
        for key, g in sorted(self.scanner.current().items()):
            def draw(surf, rect, sel, key=key, g=g):
                gfx.text(surf, g.get("name", "?"), (rect.x + 16, rect.y + 26), 24, anchor="midleft", ow=1)
                gfx.text(surf, f"{STYLE_NAMES.get(g.get('style'), '')}  -  {key}", (rect.x + 16, rect.y + 56), 16,
                         ui.MUTED, anchor="midleft", ow=1, chunky=False)
            rows.append((key, draw))
        sel = self.list.selected
        self.list.set_rows(rows)
        self.list.selected = sel

    def _join(self, addr):
        self.app.replace(LobbyScene(self.app, "join", "direct", self.style, self.team, self.name, addr=addr))

    def handle(self, ev, pos):
        if self.addr.handle(ev, pos):
            return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        picked = self.list.handle(ev, pos)
        if picked:
            self._join(picked)
            return
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.buttons[0].hit(pos):
                self.app.pop()
            elif self.buttons[1].hit(pos) and self.addr.value.strip():
                self._join(self.addr.value.strip())

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "Nearby games", "Games on your Wi-Fi")
        self.list.draw(surf)
        if not self.list.rows:
            gfx.text(surf, "Searching" + "." * (int(self.app.t * 2) % 4), (W / 2, 480), 26, ui.MUTED)
            if self.scanner.error:
                gfx.text(surf, f"(LAN search unavailable: {self.scanner.error})", (W / 2, 520), 16, ui.MUTED,
                         chunky=False)
        self.addr.draw(surf)
        for b in self.buttons:
            b.draw(surf)


class LobbyScene(Scene):
    def __init__(self, app, role, conn_type, style, team, name, code="", addr="", relay="", room="",
                 public=False, broker=None, ranked=False, searching=False):
        super().__init__(app)
        self.ranked, self.searching = ranked, searching
        self.role, self.conn_type, self.style, self.team, self.name = role, conn_type, style, team, name
        self.host = None
        self.beacon = None
        self.conn = None
        self.lobby = None
        self.error = None
        self.status = "Starting..."
        self.code = ""
        self.buttons = [ui.Button((260, 1100, 200, 70), "Cancel", ui.PANEL2, 24)]
        self.ips = net.local_ips()
        if role == "host":
            try:
                if conn_type == "room":
                    self.host = online.RoomHost(name, style, public, ranked=ranked)
                    self.code = self.host.code
                elif conn_type == "relay":
                    self.host = net.Host(net.DEFAULT_PORT, relay=relay, room=room)
                else:
                    self.host = net.Host(net.DEFAULT_PORT)
                    self.beacon = online.LanBeacon(name, style)
            except OSError as e:
                self.error = f"Couldn't open port {net.DEFAULT_PORT}: {e}"
        else:
            self.status = "Connecting..."
            target = {"room": lambda: online.join_room(code, name, broker=broker),
                      "relay": lambda: net.relay_connect(relay, room, "join"),
                      "direct": lambda: net.connect(addr), "lan": lambda: net.connect(addr)}[conn_type]
            threading.Thread(target=self._join, args=(target,), daemon=True).start()
            self.code = code.upper()

    def _join(self, target):
        try:
            self.conn = target()
        except Exception as e:  # noqa: BLE001
            self.error = f"Couldn't connect: {e}"

    def close(self):
        if self.host:
            self.host.close()
        if self.beacon:
            self.beacon.close()
        if self.conn and not self.lobby:
            self.conn.close()

    def handle(self, ev, pos):
        if (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.buttons[0].hit(pos)) or \
                (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
            self.app.pop()
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_c and (ev.mod & (pygame.KMOD_META | pygame.KMOD_CTRL)):
            from .clip import copy
            copy(self.code)

    def update(self, dt):
        if self.error:
            return
        if self.host:
            self.status = getattr(self.host, "status", self.status)
            if self.host.error:
                self.error = self.host.error
                return
            if self.conn is None and self.host.conn:
                self.conn = self.host.conn
        if self.conn and not self.lobby:
            self.status = "Connected! Exchanging teams..."
            self.lobby = Lobby(self.app.dex, self.conn, self.role, self.style, self.team, self.name,
                               ranked=self.ranked)
        if self.lobby:
            session = self.lobby.poll()
            if self.lobby.error:
                self.error = self.lobby.error
            elif session:
                start_battle(self.app, session, self.team, replace=True)
                self.lobby = None  # the session owns the connection now
                self.conn = None
                if self.beacon:
                    self.beacon.close()
                if self.host:
                    self.host.close()
                    self.host = None

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "Hosting" if self.role == "host" else "Joining",
                  f"{STYLE_NAMES[self.style]}  -  {CONN_NAMES.get(self.conn_type, '')}" if self.role == "host" else None)
        ui.panel(surf, (60, 240, 600, 520))
        if self.error:
            gfx.text(surf, self.error, (W / 2, 420), 19, (255, 120, 120), chunky=False)
        else:
            gfx.text(surf, self.status, (W / 2, 300), 24)
            gfx.text(surf, "." * (int(self.app.t * 2) % 4), (W / 2, 335), 30)
            if self.searching:
                r = profile.my_rating()
                rk = profile.mmr_rank(r["mmr"], r["games"])
                ui.rank_badge(surf, (W / 2, 470), 44, rk, self.app.t)
                gfx.text(surf, "Searching for a ranked opponent near you...", (W / 2, 560), 22, chunky=False)
                gfx.text(surf, f"{rk['label']}  -  rating {r['mmr']}", (W / 2, 600), 20, rk["color"], chunky=False)
                gfx.text(surf, f"Anyone can also join with code {self.code}", (W / 2, 660), 17, ui.MUTED,
                         chunky=False)
            elif self.code:
                gfx.text(surf, "Room code", (W / 2, 420), 22, ui.MUTED)
                gfx.title_text(surf, " ".join(self.code), (W / 2, 500), 84, color=(255, 240, 150))
                if self.role == "host":
                    gfx.text(surf, "Your friend: PVP > Online room code > type it > JOIN", (W / 2, 590), 17,
                             ui.MUTED, ow=1, chunky=False)
                    gfx.text(surf, "(Cmd+C copies the code)", (W / 2, 620), 15, ui.MUTED, ow=1, chunky=False)
            elif self.role == "host" and self.conn_type in ("direct", "lan"):
                gfx.text(surf, "Friends on your Wi-Fi will see you in JOIN.", (W / 2, 410), 18, ui.MUTED,
                         chunky=False)
                gfx.text(surf, "Or they can type one of:", (W / 2, 445), 18, ui.MUTED, chunky=False)
                for i, ip in enumerate(self.ips[:4]):
                    gfx.text(surf, f"{ip}:{net.DEFAULT_PORT}", (W / 2, 500 + i * 44), 30, (255, 240, 150))
        for b in self.buttons:
            b.draw(surf)


def start_battle(app, session, team=None, replace=False):
    """Swap to the right battle screen for a session (after sprites are on disk)."""
    from .battle_turn import TurnBattleScene
    scene = TurnBattleScene(app, session)
    ids = [m.species for m in team] if team else []
    nxt = PrefetchScene(app, ids, lambda: scene)
    if replace:
        app.replace(nxt)
    else:
        app.push(nxt)


class QuickMatch(Scene):
    """Ranked matchmaking: join the open ranked room closest to your rating, or open one and wait."""

    def __init__(self, app, team, name):
        super().__init__(app)
        self.team, self.name = team, name
        self.rating = profile.my_rating()
        self.done = False
        self.buttons = [ui.Button((260, 1100, 200, 70), "Cancel", ui.PANEL2, 24)]
        threading.Thread(target=self._find, daemon=True).start()

    def _find(self):
        try:
            rooms = online.list_public_rooms()
        except Exception:  # noqa: BLE001
            rooms = []
        self.match = online.best_match(rooms, self.rating["mmr"]) or online.best_match(rooms, self.rating["mmr"], 600)
        self.done = True

    def update(self, dt):
        if not self.done or self.app.stack[-1] is not self:
            return
        m = self.match
        if m:
            self.app.replace(LobbyScene(self.app, "join", "room", "turn", self.team, self.name, code=m["code"],
                                        broker=m["broker"] if m["broker"] == "https" else tuple(m["broker"]),
                                        ranked=True))
        else:
            self.app.replace(LobbyScene(self.app, "host", "room", "turn", self.team, self.name, public=True,
                                        ranked=True, searching=True))

    def handle(self, ev, pos):
        if (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.buttons[0].hit(pos)) or \
                (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
            self.app.pop()

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "Quick Match", "Ranked 1v1")
        rk = profile.mmr_rank(self.rating["mmr"], self.rating["games"])
        ui.rank_badge(surf, (W / 2, 470), 50, rk, self.app.t)
        gfx.text(surf, "Looking for an opponent" + "." * (int(self.app.t * 2) % 4), (W / 2, 580), 26)
        gfx.text(surf, f"{rk['label']}  -  rating {self.rating['mmr']}", (W / 2, 625), 20, rk["color"],
                 chunky=False)
        for b in self.buttons:
            b.draw(surf)


class LadderScene(Scene):
    """The global ranked ladder: every PokeBrawl trainer's skill rating, best first."""

    def __init__(self, app):
        super().__init__(app)
        self.me = profile.my_rating()
        self.rows = []
        self.loading = True
        self.list = ui.ListView((40, 250, 640, 860), 70)
        self.buttons = [ui.Button((40, 1150, 200, 70), "Back", ui.PANEL2, 24),
                        ui.Button((480, 1150, 200, 70), "Refresh", (38, 104, 188), 24)]
        self.refresh()

    def refresh(self):
        self.loading = True

        def go():
            if self.me["games"]:
                online.publish_ladder(self.app.settings.get("name", "Trainer"))
            try:
                self.rows = online.fetch_ladder()
            except Exception:  # noqa: BLE001
                self.rows = []
            rows = []
            for i, r in enumerate(self.rows):
                def draw(surf, rect, sel, r=r, i=i):
                    mine = r["id"] == self.me["id"]
                    rk = profile.mmr_rank(r["mmr"], r["w"] + r["l"])
                    if mine:
                        pygame.draw.rect(surf, (90, 70, 20), rect.inflate(-4, -4), border_radius=10)
                    gfx.text(surf, f"#{i + 1}", (rect.x + 14, rect.centery), 24,
                             (255, 215, 90) if i < 3 else (220, 220, 230), anchor="midleft", ow=1)
                    ui.rank_badge(surf, (rect.x + 100, rect.centery), 16, rk)
                    gfx.text(surf, r["name"] + ("  (you)" if mine else ""), (rect.x + 128, rect.y + 24), 22,
                             anchor="midleft", ow=1)
                    gfx.text(surf, f"{rk['label']}   {r['w']}W {r['l']}L", (rect.x + 128, rect.y + 50), 15, rk["color"],
                             anchor="midleft", ow=1, chunky=False)
                    gfx.text(surf, str(r["mmr"]), (rect.right - 16, rect.centery), 28, (255, 240, 150),
                             anchor="midright")
                rows.append((r["id"], draw))
            self.list.set_rows(rows)
            self.loading = False
        threading.Thread(target=go, daemon=True).start()

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        self.list.handle(ev, pos)
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.buttons[0].hit(pos):
                self.app.pop()
            elif self.buttons[1].hit(pos) and not self.loading:
                self.refresh()

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "Ladder", "Ranked 1v1 - every trainer, best first")
        rk = profile.mmr_rank(self.me["mmr"], self.me["games"])
        place = next((i + 1 for i, r in enumerate(self.rows) if r["id"] == self.me["id"]), None)
        ui.rank_badge(surf, (80, 200), 26, rk, self.app.t)
        gfx.text(surf, rk["label"] + (f"  -  rating {self.me['mmr']}" if not rk.get("placing") else ""),
                 (120, 188), 24, rk["color"], gfx.INK, 2, anchor="midleft")
        gfx.text(surf, (f"You're #{place} of {len(self.rows)}" if place else
                        "Play a ranked match to join the ladder") + f"   ({self.me['w']}W {self.me['l']}L)",
                 (120, 218), 17, (220, 220, 235), gfx.INK, 1, anchor="midleft", chunky=False)
        self.list.draw(surf)
        if self.loading:
            gfx.text(surf, "Loading the ladder...", (W / 2, 520), 26)
        elif not self.rows:
            gfx.text(surf, "Nobody on the ladder yet - be the first!", (W / 2, 520), 24, ui.MUTED)
        for b in self.buttons:
            b.draw(surf)
