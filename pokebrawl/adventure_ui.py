"""Adventure mode screens around the overworld: title (continue / new game), the professor's intro and the
starter pick, party, bag, Poke Mart, evolution and the Hall of Fame."""
import math

import pygame

from . import adventure as A
from . import gfx, ui
from .app import Scene
from .audio import AUDIO
from .gfx import H, INK, SPRITES, W
from .trainer_ui import STAT_NAMES, fit, type_row

STAT_KEYS = [k for k, _ in STAT_NAMES]


def mon_card(surf, dex, mon, rect, selected=False, t=0.0):
    """One party slot: sprite, name, level, HP bar, status."""
    r = pygame.Rect(rect)
    hp, mx = A.hp_of(dex, mon)
    col = (40, 70, 100) if selected else (36, 46, 62)
    if hp <= 0:
        col = (70, 40, 46)
    ui.panel(surf, r, col, 14, border=ui.LENS if selected else None)
    img = fit(mon["species"], r.h + 10, r.h - 16, mon.get("shiny", False))
    bob = math.sin(t * 4) * 3 if selected else 0
    surf.blit(img, img.get_rect(center=(r.x + r.h * 0.6, r.centery + bob)))
    x = r.x + r.h * 1.25
    gfx.text(surf, A.name_of(dex, mon), (x, r.y + 24), 24, ui.TEXT, None, 0, anchor="midleft")
    gfx.text(surf, f"Lv {mon['level']}", (r.right - 20, r.y + 24), 20, ui.SIGNAL, None, 0, anchor="midright")
    if mon.get("shiny"):
        gfx.text(surf, "*", (x + gfx.font(24).size(A.name_of(dex, mon))[0] + 10, r.y + 20), 24, (255, 220, 90),
                 None, 0, anchor="midleft")
    gfx.hp_bar(surf, (x, r.y + 52, r.right - 140 - x, 12), hp / max(1, mx))
    gfx.text(surf, f"{hp}/{mx}", (r.right - 20, r.y + 58), 16, ui.TEXT, None, 0, anchor="midright", chunky=False)
    if mon.get("status") and hp > 0:
        gfx.pill(surf, mon["status"].upper(), (x + 30, r.y + 84), (180, 90, 60), 13)
    elif hp <= 0:
        gfx.pill(surf, "FAINTED", (x + 36, r.y + 84), (160, 50, 60), 13)
    type_row(surf, dex.all[mon["species"]]["types"], r.right - 110, r.y + 86, 12)


# ====================================================================== title
class AdventureTitle(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.save = A.load()
        self.confirm = False
        self._layout()

    def _layout(self):
        self.buttons = []
        if self.save:
            self.buttons.append(ui.Button((60, 760, 600, 120), "Continue", (34, 140, 88), 40,
                                          f"{self.save['name']}  -  {len(self.save['badges'])} badges  -  "
                                          f"{A.playtime_text(self.save.get('playtime', 0))} played", tag="continue"))
        label = "Really start over?" if self.confirm else "New game"
        self.buttons.append(ui.Button((60, 900 if self.save else 800, 600, 100), label,
                                      ui.SHELL if self.confirm else (38, 104, 188), 34,
                                      "your old save will be replaced" if self.confirm else
                                      "pick your starter and set off", tag="new"))
        self.buttons.append(ui.Button((60, 1160, 200, 70), "Back", ui.PANEL2, 24, tag="back"))

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        for b in self.buttons:
            if not b.hit(pos):
                continue
            if b.tag == "back":
                self.app.pop()
            elif b.tag == "continue":
                from .overworld import OverworldScene
                self.app.replace(OverworldScene(self.app, self.save))
            elif b.tag == "new":
                if self.save and not self.confirm:
                    self.confirm = True
                    self._layout()
                    return
                self.app.replace(NewGame(self.app))
            return

    def update(self, dt):
        AUDIO.music("town")

    def draw(self, surf):
        t = self.app.t
        surf.fill((120, 200, 104))
        # a little scene: hills, the sun, Pokemon in the grass
        pygame.draw.circle(surf, (255, 236, 150), (560, 220), 90)
        for i, (c, yy) in enumerate((((98, 176, 84), 520), ((80, 156, 72), 600))):
            pts = [(x, yy + math.sin(x / 120 + i) * 40) for x in range(0, W + 20, 20)] + [(W, H), (0, H)]
            pygame.draw.polygon(surf, c, pts)
        pygame.draw.rect(surf, (226, 204, 150), (W // 2 - 50, 600, 100, H))
        for k, pid in enumerate((25, 1, 4, 7, 133)):
            img = SPRITES.get(pid, 90, flip=k % 2 == 0)
            x = 90 + k * 135
            surf.blit(img, img.get_rect(midbottom=(x, 690 - abs(math.sin(t * 3 + k)) * 12)))
        gfx.title_text(surf, "POKEBRAWL", (W / 2, 170), 80, color=(255, 230, 110))
        gfx.title_text(surf, "ADVENTURE", (W / 2, 260), 56)
        gfx.text(surf, "The Brawl region  -  8 gyms  -  the Pokemon League", (W / 2, 330), 20, INK, None, 0,
                 chunky=False)
        if self.save:
            party = self.save["party"]
            x0 = W / 2 - (len(party) - 1) * 50
            for i, m in enumerate(party):
                img = fit(m["species"], 80, 64, m.get("shiny", False))
                surf.blit(img, img.get_rect(center=(x0 + i * 100, 700 - 0)))
        for b in self.buttons:
            b.draw(surf)


# ====================================================================== new game
class NewGame(Scene):
    """Professor Hazel's intro, your name, then three starters (any generation)."""

    def __init__(self, app):
        super().__init__(app)
        self.stage = "talk"
        self.lines = ["Hello there! Welcome to the world of Pokemon!",
                      "My name is Hazel. People call me the Pokemon Professor.",
                      "This world is full of creatures called Pokemon. Some people keep them as pets...",
                      "...and others use them to battle. The Brawl region has eight gyms and the Pokemon League.",
                      "But first - what's your name?"]
        self.i = 0
        self.shown = 0.0
        self.name = ui.TextInput((110, 620, 500, 70), "", app.settings.get("name", "Trainer"), "Your name")
        self.name.focus = True
        self.gen = 1
        self.pick = 1
        self.buttons = []
        self._layout()

    def _layout(self):
        if self.stage == "name":
            self.buttons = [ui.Button((160, 730, 400, 90), "That's me!", (34, 140, 88), 32, tag="ok")]
        elif self.stage == "starter":
            self.buttons = [ui.Button((20, 1000, 120, 80), "<", ui.SCREEN2, 34, tag="prev"),
                            ui.Button((580, 1000, 120, 80), ">", ui.SCREEN2, 34, tag="next"),
                            ui.Button((160, 1000, 400, 80), "Choose!", (34, 140, 88), 32, tag="choose")]
        else:
            self.buttons = []

    def update(self, dt):
        AUDIO.music("town")
        self.shown = min(999.0, self.shown + dt * 50)

    def _advance(self):
        line = self.lines[self.i]
        if self.shown < len(line):
            self.shown = len(line)
            return
        self.i += 1
        self.shown = 0
        if self.i >= len(self.lines):
            self.stage = "name" if self.stage == "talk" else "starter"
            self._layout()

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
            return
        if self.stage == "talk" or self.stage == "talk2":
            if (ev.type == pygame.KEYDOWN and ev.key in (pygame.K_SPACE, pygame.K_RETURN)) or \
                    (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1):
                self._advance()
            return
        if self.stage == "name":
            if self.name.handle(ev, pos) and not (ev.type == pygame.KEYDOWN and ev.key == pygame.K_RETURN):
                return
            done = (ev.type == pygame.KEYDOWN and ev.key == pygame.K_RETURN) or \
                (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.buttons[0].hit(pos))
            if done and self.name.value.strip():
                nm = self.name.value.strip()[:12]
                self.stage = "talk2"
                self.lines = [f"{nm}! What a great name.",
                              "Now, every trainer needs a partner. I have a few here...",
                              "Choose the Pokemon that will start your journey!"]
                self.i, self.shown = 0, 0
                self._layout()
            return
        if self.stage == "starter":
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_LEFT, pygame.K_a):
                    self.pick = (self.pick - 1) % 3
                elif ev.key in (pygame.K_RIGHT, pygame.K_d):
                    self.pick = (self.pick + 1) % 3
                elif ev.key in (pygame.K_UP, pygame.K_DOWN):
                    self.gen = (self.gen % 9) + 1 if ev.key == pygame.K_UP else (self.gen - 2) % 9 + 1
                elif ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self._choose()
                return
            if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
                return
            for i in range(3):
                if self._card(i).collidepoint(pos):
                    if self.pick == i:
                        self._choose()
                    self.pick = i
                    AUDIO.cry(A.STARTERS[self.gen][i], 0.8)
                    return
            for b in self.buttons:
                if b.hit(pos):
                    if b.tag == "prev":
                        self.gen = (self.gen - 2) % 9 + 1
                    elif b.tag == "next":
                        self.gen = self.gen % 9 + 1
                    else:
                        self._choose()

    def _card(self, i):
        return pygame.Rect(30 + i * 225, 520, 210, 440)

    def _choose(self):
        from .overworld import OverworldScene
        pid = A.STARTERS[self.gen][self.pick]
        game = A.new_game(self.name.value.strip()[:12], pid, self.app.dex)
        game["area"], game["x"], game["y"], game["face"] = 0, 3, 19, "down"
        game["center"] = [0, 3, 19]
        A.save(game)
        AUDIO.cry(pid, 1.0)
        ow = OverworldScene(self.app, game)
        nm = A.name_of(self.app.dex, game["party"][0])
        ow.say([f"You chose {nm}! It looks happy to meet you.",
                "Here are 5 Poke Balls and 3 Potions. Catch Pokemon in the tall grass on Route 1!",
                "The first gym is in Pebblecrest City, to the north. Good luck!"], "Prof. Hazel")
        self.app.replace(ow)

    def draw(self, surf):
        t = self.app.t
        surf.fill((236, 240, 232))
        for y in range(0, H, 40):
            pygame.draw.line(surf, (222, 228, 218), (0, y), (W, y), 2)
        if self.stage in ("talk", "talk2", "name"):
            # the professor (drawn simply): lab coat, big smile
            from .overworld import draw_person
            draw_person(surf, W / 2, 470, "down", 0, (250, 250, 250), hair=(120, 80, 50), scale=4.5)
        if self.stage in ("talk", "talk2"):
            line = self.lines[self.i]
            from .overworld import Dialogue
            d = Dialogue([line], "Prof. Hazel")
            d.shown = self.shown
            d.draw(surf, t)
        elif self.stage == "name":
            gfx.title_text(surf, "WHAT'S YOUR NAME?", (W / 2, 560), 40)
            self.name.draw(surf)
            for b in self.buttons:
                b.draw(surf)
        else:
            gfx.title_text(surf, "CHOOSE YOUR STARTER", (W / 2, 160), 46)
            gfx.text(surf, f"Generation {self.gen}  (up/down or < > for others)", (W / 2, 230), 20, (90, 90, 110),
                     None, 0, chunky=False)
            for i, pid in enumerate(A.STARTERS[self.gen]):
                r = self._card(i)
                e = self.app.dex.all[pid]
                sel = i == self.pick
                col = gfx.type_color(e["types"][0], 0)
                pygame.draw.rect(surf, INK, r.inflate(8, 8), border_radius=20)
                pygame.draw.rect(surf, tuple(min(255, int(c * 0.35 + 160)) for c in col), r, border_radius=16)
                if sel:
                    pygame.draw.rect(surf, col, r, 6, border_radius=16)
                img = fit(pid, r.w - 20, 200 if sel else 170)
                bob = math.sin(t * 4) * 6 if sel else 0
                surf.blit(img, img.get_rect(midbottom=(r.centerx, r.y + 250 + bob)))
                gfx.text(surf, e["name"], (r.centerx, r.y + 290), 26, INK, None, 0)
                type_row(surf, e["types"], r.centerx, r.y + 330, 15)
                gfx.text(surf, f"BST {sum(e['stats'].values())}", (r.centerx, r.y + 370), 16, (80, 80, 90), None,
                         0, chunky=False)
                # ball at the bottom of the card
                ball = gfx.ball_sprite(40)
                surf.blit(ball, ball.get_rect(center=(r.centerx, r.bottom - 30)))
            for b in self.buttons:
                b.draw(surf)


# ====================================================================== party
class PartyScene(Scene):
    def __init__(self, app, game, pick=None):
        super().__init__(app)
        self.game = game
        self.sel = None
        self.box_view = False
        self.pick = pick          # callback(index) for "use item on which Pokemon?"
        self._layout()

    def _layout(self):
        if self.sel is None:
            self.buttons = [ui.Button((40, 1180, 200, 70), "Back", ui.PANEL2, 24, tag="back")]
            if not self.pick:
                self.buttons.append(ui.Button((480, 1180, 200, 70), f"Box ({len(self.game['box'])})", ui.SCREEN2,
                                              24, tag="box"))
        else:
            self.buttons = [ui.Button((40, 1180, 200, 70), "Back", ui.PANEL2, 24, tag="close")]
            if self.box_view:
                self.buttons.append(ui.Button((260, 1180, 420, 70), "Add to party", (34, 140, 88), 24, tag="take",
                                              enabled=len(self.game["party"]) < 6))
            else:
                self.buttons.append(ui.Button((260, 1180, 200, 70), "Make lead", (38, 104, 188), 22, tag="lead",
                                              enabled=self.sel > 0))
                self.buttons.append(ui.Button((480, 1180, 200, 70), "To Box", ui.SCREEN2, 22, tag="stash",
                                              enabled=len(self.game["party"]) > 1))

    def _list(self):
        return self.game["box"] if self.box_view else self.game["party"]

    def _slot(self, i):
        if self.box_view:
            return pygame.Rect(40 + (i % 4) * 160, 170 + (i // 4) * 150, 150, 140)
        return pygame.Rect(40, 170 + i * 162, 640, 150)

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            if self.sel is not None:
                self.sel = None
                self._layout()
            elif self.box_view:
                self.box_view = False
                self._layout()
            else:
                self.app.pop()
            return
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        for b in self.buttons:
            if not b.hit(pos):
                continue
            g = self.game
            if b.tag == "back":
                if self.box_view:
                    self.box_view = False
                else:
                    self.app.pop()
            elif b.tag == "box":
                self.box_view = True
            elif b.tag == "close":
                self.sel = None
            elif b.tag == "lead":
                g["party"].insert(0, g["party"].pop(self.sel))
                self.sel = 0
            elif b.tag == "stash":
                g["box"].append(g["party"].pop(self.sel))
                self.sel = None
            elif b.tag == "take":
                g["party"].append(g["box"].pop(self.sel))
                self.sel = None
            AUDIO.play("select", 0.5)
            self._layout()
            return
        if self.sel is None:
            for i in range(len(self._list())):
                if self._slot(i).collidepoint(pos):
                    if self.pick:
                        if self.pick(i):
                            self.app.pop()
                        return
                    self.sel = i
                    AUDIO.cry(self._list()[i]["species"], 0.7)
                    self._layout()
                    return

    def draw(self, surf):
        t = self.app.t
        ui.menu_background(surf, t)
        dex = self.app.dex
        title = "Box" if self.box_view else ("Use on which Pokemon?" if self.pick else "Pokemon")
        ui.header(surf, title, f"{len(self.game['party'])} in your party  -  {len(self.game['box'])} in the Box")
        lst = self._list()
        if self.sel is None:
            for i, m in enumerate(lst):
                r = self._slot(i)
                if self.box_view:
                    ui.panel(surf, r, ui.SCREEN2, 12)
                    img = fit(m["species"], r.w - 20, 90, m.get("shiny", False))
                    surf.blit(img, img.get_rect(center=(r.centerx, r.y + 58)))
                    gfx.text(surf, f"{A.name_of(dex, m)[:10]}  Lv{m['level']}", (r.centerx, r.bottom - 20), 14,
                             ui.TEXT, None, 0, chunky=False)
                else:
                    mon_card(surf, dex, m, r, False, t)
            if self.box_view and not lst:
                gfx.text(surf, "The Box is empty. Catch more than 6 Pokemon!", (W / 2, 400), 20, ui.MUTED, None, 0,
                         chunky=False)
        else:
            self._draw_summary(surf, lst[self.sel], t)
        for b in self.buttons:
            b.draw(surf)

    def _draw_summary(self, surf, m, t):
        dex = self.app.dex
        e = dex.all[m["species"]]
        r = pygame.Rect(40, 170, 640, 990)
        ui.panel(surf, r, ui.SCREEN2, 18, border=gfx.type_color(e["types"][0], 0))
        img = fit(m["species"], 300, 240, m.get("shiny", False))
        surf.blit(img, img.get_rect(midbottom=(r.centerx, r.y + 270 + math.sin(t * 2) * 4)))
        if m.get("shiny"):
            gfx.sparkles(surf, (r.centerx, r.y + 160), 130, t, m["species"], 10)
        gfx.text(surf, A.name_of(dex, m), (r.centerx, r.y + 300), 36, ui.TEXT, ui.SHELL_DARK, 3)
        gfx.text(surf, f"Lv {m['level']}  -  {m.get('nature', '')} nature  -  met at {m.get('origin') or '?'}",
                 (r.centerx, r.y + 340), 16, ui.MUTED, None, 0, chunky=False)
        type_row(surf, e["types"], r.centerx, r.y + 372, 15)
        # experience bar
        lo, hi = A.xp_for(m["level"]), A.xp_for(m["level"] + 1)
        frac = (m["xp"] - lo) / max(1, hi - lo)
        gfx.text(surf, "EXP", (r.x + 40, r.y + 410), 15, ui.MUTED, None, 0, anchor="midleft")
        pygame.draw.rect(surf, (14, 18, 26), (r.x + 90, r.y + 402, 400, 14), border_radius=7)
        pygame.draw.rect(surf, (80, 170, 240), (r.x + 90, r.y + 402, max(14, int(400 * frac)), 14), border_radius=7)
        gfx.text(surf, f"{hi - m['xp']} to next", (r.right - 40, r.y + 410), 14, ui.MUTED, None, 0,
                 anchor="midright", chunky=False)
        st = A.stats(dex, m)
        hp, mx = A.hp_of(dex, m)
        for i, (k, label) in enumerate(STAT_NAMES):
            y = r.y + 456 + i * 36
            gfx.text(surf, label, (r.x + 40, y), 16, ui.MUTED, None, 0, anchor="midleft", chunky=False)
            val = f"{hp}/{mx}" if k == "hp" else str(st[k])
            gfx.text(surf, val, (r.x + 260, y), 18, ui.TEXT, None, 0, anchor="midright")
            pygame.draw.rect(surf, (14, 18, 26), (r.x + 280, y - 7, 320, 14), border_radius=7)
            pygame.draw.rect(surf, gfx.hsv(min(st[k], 250) / 250 * 0.35),
                             (r.x + 280, y - 7, max(14, int(320 * min(1.0, st[k] / 250))), 14), border_radius=7)
        y = r.y + 690
        gfx.text(surf, "Moves", (r.x + 40, y), 20, ui.TEXT, None, 0, anchor="midleft")
        for i, mid in enumerate(m["moves"]):
            mv = dex.moves[mid]
            yy = y + 40 + i * 58
            box = pygame.Rect(r.x + 30, yy - 22, r.w - 60, 50)
            pygame.draw.rect(surf, gfx.type_color(mv["type"], 2), box, border_radius=10)
            gfx.text(surf, mv["name"], (box.x + 16, box.centery), 20, ui.TEXT, None, 0, anchor="midleft")
            pp = (m.get("pp") or [None] * 4)[i] if m.get("pp") and i < len(m["pp"]) else mv["pp"]
            gfx.text(surf, f"{mv['type'].upper()}   {mv['power'] or '-'} POW   {pp}/{mv['pp']} PP",
                     (box.right - 16, box.centery), 14, (235, 235, 240), None, 0, anchor="midright", chunky=False)


# ====================================================================== bag
class BagScene(Scene):
    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.msg = ""
        self._layout()

    def _layout(self):
        self.buttons = []
        items = [(k, n) for k, n in self.game["bag"].items() if n > 0]
        items.sort(key=lambda kv: list(A.SHOP).index(kv[0]) if kv[0] in A.SHOP else 99)
        for i, (k, n) in enumerate(items):
            name, price, desc = A.SHOP.get(k, (k, 0, ""))
            usable = k not in A.BALL_KEYS
            self.buttons.append(ui.Button((40, 170 + i * 92, 640, 82), f"{name}  x{n}",
                                          (60, 150, 90) if usable else (200, 60, 70), 26, desc, tag=k))
        self.buttons.append(ui.Button((40, 1180, 200, 70), "Back", ui.PANEL2, 24, tag="back"))

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        for b in self.buttons:
            if b.hit(pos):
                if b.tag == "back":
                    self.app.pop()
                elif b.tag in A.BALL_KEYS:
                    self.msg = "Throw Poke Balls at wild Pokemon in battle!"
                else:
                    item = b.tag
                    self.app.push(PartyScene(self.app, self.game, pick=lambda i, item=item: self._use(item, i)))
                return

    def _use(self, item, i):
        from .turnsim import MEDICINE
        dex = self.app.dex
        mon = self.game["party"][i]
        name, heal, cure, revive = MEDICINE[item]
        hp, mx = A.hp_of(dex, mon)
        if revive != (hp <= 0):
            return False
        if revive:
            mon["cur_hp"] = max(1, int(mx * heal))
        elif heal:
            if hp >= mx and not (cure and mon.get("status")):
                return False
            new = mx if heal < 0 else min(mx, hp + heal)
            mon["cur_hp"] = None if new >= mx else new
        if cure:
            if not mon.get("status") and not heal:
                return False
            mon["status"] = None
        self.game["bag"][item] -= 1
        if self.game["bag"][item] <= 0:
            del self.game["bag"][item]
        AUDIO.play("heal")
        self.msg = f"Used a {name} on {A.name_of(dex, mon)}."
        self._layout()
        return True

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "Bag", f"{self.game['money']} coins")
        if len(self.buttons) == 1:
            gfx.text(surf, "Your bag is empty.", (W / 2, 400), 22, ui.MUTED, None, 0)
        for b in self.buttons:
            b.draw(surf)
        if self.msg:
            gfx.text(surf, self.msg, (W / 2, 1140), 18, ui.SIGNAL, None, 0, chunky=False)


# ====================================================================== mart
class MartScene(Scene):
    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.msg = "Welcome! How may I help you?"
        self._layout()

    def _layout(self):
        self.buttons = []
        for i, k in enumerate(A.mart_stock(len(self.game["badges"]))):
            name, price, desc = A.SHOP[k]
            have = self.game["bag"].get(k, 0)
            y = 170 + i * 88
            self.buttons.append(ui.Button((40, y, 440, 78), name, ui.SCREEN2, 24, f"{desc}  -  you have {have}",
                                          tag=("info", k)))
            self.buttons.append(ui.Button((490, y, 90, 78), f"{price}", (38, 104, 188), 18, "buy 1",
                                          enabled=self.game["money"] >= price, tag=("buy", k, 1)))
            self.buttons.append(ui.Button((590, y, 90, 78), "x10", (34, 140, 88), 18, f"{price * 10}",
                                          enabled=self.game["money"] >= price * 10, tag=("buy", k, 10)))
        self.buttons.append(ui.Button((40, 1180, 200, 70), "Leave", ui.PANEL2, 24, tag=("back",)))

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        for b in self.buttons:
            if b.hit(pos):
                if b.tag[0] == "back":
                    A.save(self.game)
                    self.app.pop()
                elif b.tag[0] == "buy":
                    _, k, n = b.tag
                    cost = A.SHOP[k][1] * n
                    if self.game["money"] >= cost:
                        self.game["money"] -= cost
                        self.game["bag"][k] = self.game["bag"].get(k, 0) + n
                        self.msg = f"Here you are! {n} x {A.SHOP[k][0]}. Thank you!"
                        AUDIO.play("catch", 0.5)
                    self._layout()
                return

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "Poke Mart", f"{self.game['money']} coins")
        for b in self.buttons:
            b.draw(surf)
        gfx.text(surf, self.msg, (W / 2, 1140), 18, ui.SIGNAL, None, 0, chunky=False)


# ====================================================================== evolution
class EvolutionScene(Scene):
    no_transition = True

    def __init__(self, app, game, mon, to):
        super().__init__(app)
        self.game = game
        self.mon = mon
        self.old = mon["species"]
        self.to = to
        self.t = 0.0
        self.done = False
        self.learned = []
        self.old_name = A.name_of(app.dex, mon)
        AUDIO.cry(self.old, 0.9)

    def update(self, dt):
        AUDIO.music(None)
        self.t += dt
        if self.t >= 4.6 and not self.done:
            self.done = True
            self.learned = A.evolve(self.app.dex, self.mon, self.to)
            A.save(self.game)
            AUDIO.play("mega")
            AUDIO.cry(self.to, 1.0)

    def handle(self, ev, pos):
        if self.done and self.t > 5.6 and ((ev.type == pygame.KEYDOWN and ev.key in (pygame.K_SPACE,
                                                                                      pygame.K_RETURN)) or
                                           (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1)):
            self.app.pop()

    def draw(self, surf):
        t = self.t
        surf.fill((14, 14, 30))
        cx, cy = W / 2, H * 0.45
        # swirling light
        for i in range(24):
            a = i / 24 * math.tau + t * (1 + t * 0.4)
            r = 120 + 200 * ((i * 37) % 10) / 10
            pygame.draw.circle(surf, (180, 200, 255), (int(cx + math.cos(a) * r), int(cy + math.sin(a) * r)), 3)
        old_img = fit(self.old, 420, 300, self.mon.get("shiny", False))
        new_img = fit(self.to, 420, 300, self.mon.get("shiny", False))
        if t < 4.6:
            # the two shapes swap faster and faster
            speed = 1.5 + t * t * 0.9
            show_new = math.sin(t * speed * 2) > 0.3 and t > 1.2
            img = new_img if show_new else old_img
            sil = gfx.silhouette(img, (255, 255, 255)) if t > 0.8 else img
            surf.blit(sil, sil.get_rect(midbottom=(cx, cy + 150)))
            gfx.text(surf, f"What? {self.old_name} is evolving!", (W / 2, H * 0.78), 26, (255, 255, 255), INK, 2)
            if t > 4.2:
                fl = pygame.Surface((W, H))
                fl.fill((255, 255, 255))
                fl.set_alpha(int(255 * (t - 4.2) / 0.4))
                surf.blit(fl, (0, 0))
        else:
            q = min(1.0, (t - 4.6) / 0.8)
            fl = pygame.Surface((W, H))
            fl.fill((255, 255, 255))
            fl.set_alpha(int(255 * (1 - q)))
            surf.blit(new_img, new_img.get_rect(midbottom=(cx, cy + 150)))
            surf.blit(fl, (0, 0))
            new_name = A.name_of(self.app.dex, self.mon)
            gfx.title_text(surf, "CONGRATULATIONS!", (W / 2, H * 0.12), 50, color=(255, 230, 110))
            gfx.text(surf, f"Your {self.old_name} evolved into {new_name}!", (W / 2, H * 0.78), 26,
                     (255, 255, 255), INK, 2)
            for k, (_, mid, forgot) in enumerate(self.learned):
                gfx.text(surf, f"{new_name} learned {self.app.dex.moves[mid]['name']}!", (W / 2, H * 0.83 + k * 34),
                         20, (200, 230, 255), INK, 1)
            if t > 5.6 and int(t * 2) % 2:
                gfx.text(surf, "tap to continue", (W / 2, H - 60), 18, ui.MUTED, None, 0, chunky=False)


# ====================================================================== hall of fame
class HallOfFame(Scene):
    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.t = 0.0
        A.save(game)

    def update(self, dt):
        self.t += dt
        AUDIO.music("showcase")

    def handle(self, ev, pos):
        if self.t > 3 and ((ev.type == pygame.KEYDOWN and ev.key in (pygame.K_SPACE, pygame.K_RETURN,
                                                                      pygame.K_ESCAPE)) or
                           (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1)):
            self.app.pop()

    def draw(self, surf):
        t = self.t
        surf.fill((30, 20, 8))
        rays = pygame.Surface((W, H), pygame.SRCALPHA)
        for i in range(16):
            a = i / 16 * math.tau + t * 0.3
            pts = [(W / 2, H * 0.45), (W / 2 + math.cos(a - 0.09) * 1500, H * 0.45 + math.sin(a - 0.09) * 1500),
                   (W / 2 + math.cos(a + 0.09) * 1500, H * 0.45 + math.sin(a + 0.09) * 1500)]
            pygame.draw.polygon(rays, (255, 210, 90, 40), pts)
        surf.blit(rays, (0, 0))
        gfx.title_text(surf, "HALL OF FAME", (W / 2, 140), 64, color=(255, 230, 110))
        gfx.text(surf, f"Champion {self.game['name']}", (W / 2, 220), 30, (255, 255, 255), INK, 2)
        party = self.game["party"]
        for i, m in enumerate(party):
            k = min(1.0, max(0.0, (t - i * 0.5) / 0.5))
            if k <= 0:
                continue
            col, row = i % 3, i // 3
            x, y = 130 + col * 230, 520 + row * 330
            img = fit(m["species"], 200, 190, m.get("shiny", False))
            img.set_alpha(int(255 * k))
            surf.blit(img, img.get_rect(midbottom=(x, y + (1 - k) * 40)))
            gfx.text(surf, f"{A.name_of(self.app.dex, m)}  Lv{m['level']}", (x, y + 26), 18, (255, 240, 200), INK, 1)
        if t > 3:
            gfx.text(surf, f"Play time {A.playtime_text(self.game.get('playtime', 0))}  -  "
                           f"{len(self.game['caught'])} Pokemon caught", (W / 2, H - 120), 18, (255, 230, 180),
                     None, 0, chunky=False)
            gfx.text(surf, "Legendary Pokemon now appear more often on the routes...", (W / 2, H - 80), 16,
                     (220, 200, 160), None, 0, chunky=False)


class AdventureCard(Scene):
    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.buttons = [ui.Button((40, 1180, 200, 70), "Back", ui.PANEL2, 24)]

    def handle(self, ev, pos):
        if (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE) or \
                (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.buttons[0].hit(pos)):
            self.app.pop()

    def draw(self, surf):
        g = self.game
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "Trainer card", g["name"])
        r = pygame.Rect(40, 180, 640, 360)
        ui.panel(surf, r, (250, 246, 232), 18)
        from .overworld import draw_person
        draw_person(surf, r.x + 120, r.y + 300, "down", 0, (220, 60, 70), hat=(220, 60, 70), scale=4.0)
        rows = [("Money", f"{g['money']} coins"), ("Pokedex", f"{len(g['seen'])} seen, {len(g['caught'])} caught"),
                ("Play time", A.playtime_text(g.get("playtime", 0))), ("Badges", f"{len(g['badges'])} / 8"),
                ("Champion", "Yes!" if g.get("champion") else "Not yet")]
        for i, (k, v) in enumerate(rows):
            y = r.y + 50 + i * 60
            gfx.text(surf, k, (r.x + 260, y), 18, (100, 100, 110), None, 0, anchor="midleft", chunky=False)
            gfx.text(surf, v, (r.right - 30, y), 22, INK, None, 0, anchor="midright")
        gfx.text(surf, "Badges", (W / 2, 600), 26, ui.TEXT, None, 0)
        for i, gym in enumerate(A.GYMS):
            x, y = 110 + (i % 4) * 166, 700 + (i // 4) * 170
            have = gym[6] in g["badges"]
            col = gfx.type_color(gym[2], 0) if have else (50, 58, 72)
            pts = [(x + 46 * math.cos(a), y + 46 * math.sin(a)) for a in [k * math.tau / 8 + math.pi / 8
                                                                          for k in range(8)]]
            pygame.draw.polygon(surf, INK, [(px * 1.0, py + 3) for px, py in pts])
            pygame.draw.polygon(surf, col, pts)
            if have:
                pygame.draw.circle(surf, (255, 255, 255), (int(x - 14), int(y - 14)), 8)
            gfx.text(surf, gym[6].replace(" Badge", ""), (x, y + 70), 15, ui.TEXT if have else ui.MUTED, None, 0,
                     chunky=False)
        for b in self.buttons:
            b.draw(surf)
