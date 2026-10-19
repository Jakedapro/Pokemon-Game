"""Adventure mode screens, GBA style (480x320): title, the professor's intro and starter pick, party, summary,
Box, bag, Poke Mart, Pokedex, trainer card, evolution and the Hall of Fame.
Controls: arrows move, Z/Enter = A, X/Esc = B. The mouse works too."""
import math
import random

import pygame

from . import adventure as A
from . import battlegfx as BG
from . import story as S
from . import gbaart as G
from . import gbaui as U
from . import pixelfont as F
from .app import Scene
from .audio import AUDIO
from .gfx import PIXEL, type_color
from .turnsim import MEDICINE

VW, VH = PIXEL
STATS = [("hp", "HP"), ("atk", "ATTACK"), ("def", "DEFENSE"), ("spa", "SP. ATK"), ("spd", "SP. DEF"),
         ("spe", "SPEED")]


def bg(surf, top=(160, 200, 240), bottom=(232, 240, 248), stripes=True):
    for y in range(0, VH, 4):
        k = y / VH
        surf.fill(tuple(int(a * (1 - k) + b * k) for a, b in zip(top, bottom)), (0, y, VW, 4))
    if stripes:
        for y in range(0, VH, 16):
            pygame.draw.line(surf, tuple(min(255, c + 8) for c in bottom), (0, y), (VW, y))


def title_bar(surf, text, color=(200, 72, 72)):
    pygame.draw.rect(surf, (48, 48, 56), (0, 0, VW, 34))
    pygame.draw.rect(surf, color, (0, 0, VW, 30))
    F.draw(surf, text, (14, 8), U.WHITE, tuple(max(0, c - 70) for c in color))


def type_tag(surf, typ, x, y):
    col = type_color(typ, 0)
    pygame.draw.rect(surf, (48, 48, 56), (x, y, 64, 18), border_radius=4)
    pygame.draw.rect(surf, col, (x + 1, y + 1, 62, 16), border_radius=3)
    label = typ.upper()
    F.draw(surf, label, (x + 32 - F.width(label, 1) // 2, y + 5), U.WHITE, tuple(max(0, c - 80) for c in col),
           scale=1)
    return 68


class GBAScene(Scene):
    canvas_size = PIXEL


# ====================================================================== title
class AdventureTitle(GBAScene):
    transition = "ball"   # a Poke Ball wipe in and out

    def __init__(self, app):
        super().__init__(app)
        self.save = A.load()
        self.t = 0.0
        self.stage = "press"
        self.confirm = None
        opts = ([("continue", "CONTINUE")] if self.save else []) + [("new", "NEW GAME"), ("back", "BACK")]
        self.menu = U.Menu(opts)
        from . import battlegfx, fieldmap, frlg
        frlg.start(fieldmap.warm)   # the graphics download in the background the first time
        import threading
        threading.Thread(target=battlegfx.prefetch_mons, daemon=True).start()   # FireRed Pokemon sprites too

    def update(self, dt):
        self.t += dt
        AUDIO.music("town")

    @staticmethod
    def _graphics():
        """'ready', 'loading' or 'failed': Adventure only starts once the FireRed graphics are all there."""
        from . import fieldmap, frlg
        if not frlg.is_ready():
            return "loading"
        return "ready" if fieldmap.available() else "failed"

    def handle(self, ev, pos):
        state = self._graphics()
        if state != "ready":
            if state == "failed" and U.is_a(ev):   # try the download again
                from . import fieldmap, frlg
                frlg.retry(fieldmap.warm)
                AUDIO.play("select")
            elif U.is_b(ev):
                self.app.pop()
            return
        if self.stage == "press":
            if U.is_a(ev):
                self.stage = "menu"
                AUDIO.play("select")
            elif U.is_b(ev):
                self.app.pop()
            return
        if self.confirm is not None:
            k = self.confirm.handle(ev, pos)
            if k == "yes":
                self.app.replace(NewGame(self.app))
            elif k in ("no", "back"):
                self.confirm = None
            return
        k = self.menu.handle(ev, pos)
        if k == "continue":
            from .overworld import OverworldScene
            self.app.replace(OverworldScene(self.app, self.save))
        elif k == "new":
            if self.save:
                self.confirm = U.Menu([("no", "NO"), ("yes", "YES")])
            else:
                self.app.replace(NewGame(self.app))
        elif k in ("back",):
            self.app.pop()

    def draw(self, surf):
        t = self.t
        bg(surf, (64, 104, 200), (152, 200, 240), stripes=False)
        # rolling hills, a sunset glow and a Pokemon on the hill
        pygame.draw.circle(surf, (248, 216, 128), (380, 120), 60)
        for i, (c, yy) in enumerate((((96, 168, 88), 210), ((72, 144, 72), 240))):
            pts = [(x, yy + int(math.sin(x / 50 + i * 2 + t * 0.2) * 10)) for x in range(0, VW + 8, 8)]
            pygame.draw.polygon(surf, c, pts + [(VW, VH), (0, VH)])
        img = G.battle_sprite(6, max_h=120)
        surf.blit(img, img.get_rect(midbottom=(370, 228 + int(math.sin(t * 2) * 3))))
        F.draw(surf, "PokeBrawl", (34, 40), (248, 216, 64), (120, 56, 32), scale=5)
        F.draw(surf, "ADVENTURE", (40, 92), U.WHITE, (48, 64, 120), scale=3)
        F.draw(surf, "The Brawl Region", (42, 124), (232, 240, 248), (48, 64, 120))
        state = self._graphics()
        if state != "ready":   # the one-time download: nothing starts until it's done
            from . import frlg
            box = U.box(surf, (40, 214, VW - 80, 92))
            if state == "loading":
                done, total = frlg.PROGRESS
                F.draw(surf, "Loading graphics" + "." * (int(t * 3) % 4), (box.x + 8, box.y + 4),
                       U.TEXT, U.SHADOW)
                bar = pygame.Rect(box.x + 8, box.y + 36, box.w - 16, 12)
                pygame.draw.rect(surf, (64, 72, 88), bar, border_radius=4)
                k = done / total if total else 0.05 + 0.05 * math.sin(t * 3)
                pygame.draw.rect(surf, (88, 200, 120), (bar.x + 2, bar.y + 2, int((bar.w - 4) * k), bar.h - 4),
                                 border_radius=3)
                F.draw(surf, "Only the first time - after this it works offline.", (box.x + 8, box.y + 54),
                       (120, 120, 136), None, scale=1)
            else:
                F.draw(surf, "Couldn't download the graphics.", (box.x + 8, box.y + 4), (200, 64, 48), U.SHADOW)
                F.draw(surf, "Check your internet, then press Z to try again.", (box.x + 8, box.y + 36), U.TEXT,
                       None, scale=1)
            return
        if self.stage == "press":
            if int(t * 2) % 2 == 0:
                F.draw(surf, "PRESS Z / ENTER", (VW // 2, 288), U.WHITE, (48, 48, 64), anchor="center")
            return
        self.menu.draw(surf, (24, 170, 170, 20 + 26 * len(self.menu.options)))
        if self.save and self.menu.options[self.menu.index][0] == "continue":
            s = self.save
            inner = U.box(surf, (210, 170, 256, 130))
            F.draw(surf, f"PLAYER   {s['name'].upper()}", (inner.x + 8, inner.y + 6), U.TEXT, U.SHADOW)
            F.draw(surf, f"TIME     {A.playtime_text(s.get('playtime', 0))}", (inner.x + 8, inner.y + 30), U.TEXT,
                   U.SHADOW)
            F.draw(surf, f"POKeDEX  {len(s['caught'])}", (inner.x + 8, inner.y + 54), U.TEXT, U.SHADOW)
            F.draw(surf, f"BADGES   {len(s['badges'])}", (inner.x + 8, inner.y + 78), U.TEXT, U.SHADOW)
        if self.confirm is not None:
            box = U.box(surf, (4, 240, 330, 76))
            F.draw(surf, "Start over? Your old save", (box.x + 10, box.y + 6), U.TEXT, U.SHADOW)
            F.draw(surf, "will be replaced.", (box.x + 10, box.y + 32), U.TEXT, U.SHADOW)
            self.confirm.draw(surf, (360, 240, 116, 76))


# ====================================================================== new game
def randomizer_unlocked():
    from . import profile
    return bool(profile.load().get("adventure_champion"))


class OptionsPanel:
    """FireRed's OPTION screen: one row per setting, LEFT / RIGHT to change it, START at the bottom."""

    def __init__(self, opts, new_game=True):
        self.opts = opts
        self.new_game = new_game
        self.index = 0

    def rows(self):
        out = list(A.OPTION_DEFS)
        if self.new_game and randomizer_unlocked():
            out += A.RANDOM_DEFS if self.opts.get("random") == "ON" else A.RANDOM_DEFS[:1]
        if not self.new_game:   # mid-game: the world stays as it is
            out = [r for r in out if r[0] not in ("gender",)]
        return out + [("done", "START" if self.new_game else "CLOSE", [])]

    def handle(self, ev, pos):
        rows = self.rows()
        d = U.direction(ev)
        if d in ("up", "down"):
            self.index = (self.index + (1 if d == "down" else -1)) % len(rows)
            AUDIO.play("click", 0.25)
            return None
        key, _, vals = rows[self.index]
        if d in ("left", "right") and vals:
            i = vals.index(self.opts.get(key, vals[0])) if self.opts.get(key) in vals else 0
            self.opts[key] = vals[(i + (1 if d == "right" else -1)) % len(vals)]
            self.index = min(self.index, len(self.rows()) - 1)
            AUDIO.play("select", 0.3)
            return None
        if U.is_a(ev) and key == "done":
            return "done"
        if U.is_a(ev) and vals:   # A also cycles
            i = vals.index(self.opts.get(key, vals[0])) if self.opts.get(key) in vals else 0
            self.opts[key] = vals[(i + 1) % len(vals)]
            return None
        if U.is_b(ev):
            return "back"
        return None

    def draw(self, surf, t):
        rows = self.rows()
        bg(surf, (64, 104, 200), (152, 200, 240))
        head = U.box(surf, (8, 6, VW - 16, 40))
        F.draw(surf, "OPTION" if not self.new_game else "NEW GAME - OPTION", (head.x + 8, head.y + 2), U.TEXT,
               U.SHADOW)
        box = U.box(surf, (8, 50, VW - 16, min(VH - 124, 20 + 24 * len(rows))))
        per = max(1, (box.h - 4) // 24)
        top = max(0, min(self.index - per + 2, len(rows) - per))
        if top > 0:
            F.draw(surf, "^", (box.right - 14, box.y - 6), (120, 120, 136), None, scale=1)
        if top + per < len(rows):
            F.draw(surf, "v", (box.right - 14, box.bottom - 6), (120, 120, 136), None, scale=1)
        for i, (key, label, vals) in enumerate(rows[top:top + per]):
            y = box.y + 2 + i * 24
            j = top + i
            sel = j == self.index
            if sel:
                U.cursor(surf, (box.x + 2, y))
            if key == "done":
                F.draw(surf, label, (box.x + 22, y), (200, 64, 48), U.SHADOW)
                continue
            rnd = key.startswith("r_") or key == "random"
            F.draw(surf, label, (box.x + 22, y), (64, 104, 176) if rnd else U.TEXT, U.SHADOW)
            val = self.opts.get(key, vals[0])
            F.draw(surf, ("< " + val + " >") if sel else val, (box.right - 10, y), (232, 96, 64), U.SHADOW,
                   anchor="topright")
        key = rows[self.index][0]
        tip = OPTION_TIPS.get(key, "") if key != "difficulty" else DIFF_TIPS[self.opts.get("difficulty", "NORMAL")]
        hint = U.box(surf, (8, VH - 66, VW - 16, 60))
        F.draw(surf, tip, (hint.x + 8, hint.y + 4), U.TEXT, U.SHADOW, scale=1)
        F.draw(surf, "UP/DOWN: choose   LEFT/RIGHT: change   Z: " + ("start" if self.new_game else "close"),
               (hint.x + 8, hint.y + 26), (120, 120, 136), None, scale=1)


DIFF_TIPS = {"EASY": "More EXP, gentler trainers. For relaxing.",
             "NORMAL": "The intended journey. You'll need to train your team.",
             "HARD": "Stronger, smarter trainers and less EXP. Pricier items.",
             "INSANE": "Trainers far above you and very little EXP. Good luck."}
OPTION_TIPS = {"gender": "Play as a boy or a girl.", "text": "How fast messages type out.",
               "scene": "Battle animations like Mega Evolution and shiny sparkles.",
               "sound": "Music, sound effects and cries.",
               "random": "RANDOMIZER: unlocked for World Champions. Mixes up the Pokemon!",
               "r_wild": "SIMILAR keeps wild Pokemon about as strong as before; ANY is anything.",
               "r_starters": "Three random starters instead of Bulbasaur, Charmander and Squirtle.",
               "r_trainers": "Trainers, leaders and the Elite Four use random Pokemon.",
               "r_types": "Gym Leaders specialise in a random type.",
               "r_legends": "Allow legendary Pokemon in the wild."}


class OptionsScene(GBAScene):
    """The START menu's OPTION screen (mid-game)."""

    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.t = 0.0
        self.panel = OptionsPanel(dict(A.default_options(), **(game.get("opts") or {})), new_game=False)

    def update(self, dt):
        self.t += dt

    def handle(self, ev, pos):
        k = self.panel.handle(ev, pos)
        if k in ("done", "back"):
            self.game["opts"] = self.panel.opts
            A.use_options(self.game)
            A.save(self.game)
            self.app.pop()

    def draw(self, surf):
        self.panel.draw(surf, self.t)


class NewGame(GBAScene):
    """Prof. Oak's speech on FireRed's intro backdrop, then you walk into his lab to choose a Pokemon."""
    SPEECH_MON = 133   # Eevee hops onto the platform while Oak talks about Pokemon

    def __init__(self, app):
        super().__init__(app)
        self.t = 0.0
        self.name = app.settings.get("name", "")[:10]
        self.opts = A.default_options()
        self.panel = OptionsPanel(self.opts)
        self.stage = "setup"
        self.scene = "prof"       # who's on screen: prof, mon, player, rival
        self.scene_t = 0.0
        self.text = None
        self.go_t = None          # the player shrinking away into the world

    def _begin(self):
        A.use_options({"opts": self.opts})
        self.stage = "talk"
        self._talk("prof", ["Hello there! Glad to meet you! Welcome to the world of POKeMON!",
                            "My name is OAK. Everyone around here calls me the POKeMON PROF."], self._part2)

    def _part2(self):
        AUDIO.cry(self.SPEECH_MON, 0.8)
        self._talk("mon", ["This world is inhabited far and wide by creatures called POKeMON.",
                           "People live alongside them - some as friends, some as partners in battle.",
                           "But lately, something strange has been happening...",
                           "Tears of purple light are opening across the region, and the Pokemon",
                           "caught in them MEGA EVOLVE and go wild. I've seen a light like that once before...",
                           "...Never mind. That's a story for another day."], self._part3)

    def _part3(self):
        self._talk("player", ["Now, tell me a little about yourself.", "Let's begin with your name. What is it?"],
                   self._to_name)

    def _talk(self, scene, lines, then):
        if scene != self.scene:
            self.scene, self.scene_t = scene, 0.0
        self.stage = "talk"
        self.text = U.TextBox(lines, then, speaker="")

    def _to_name(self):
        self.stage = "name"
        self.text = None

    def _after_name(self):
        nm = (self.name.strip() or "RED").upper()
        self._talk("player", [f"Right... So your name is {nm}."], lambda: self._talk(
            "rival", ["This is my grandson. He's been your rival since you were both babies.",
                      f"His name is {S.RIVAL.upper()}. He's waiting for you at my lab."],
            lambda: self._talk("player", [f"{nm}! Your very own POKeMON legend is about to unfold!",
                                          "A world of dreams and adventures with POKeMON awaits! Let's go!"],
                               self._leave)))

    def _leave(self):
        self.stage = "go"
        self.text = None
        self.go_t = 0.0

    def _start(self):
        """The new save begins inside Oak's lab with no Pokemon: the three Poke Balls are on his table."""
        from .overworld import OverworldScene
        game = A.new_game((self.name.strip() or "RED")[:10], None, self.app.dex)
        game["opts"] = dict(self.opts)
        game["bag"] = {}
        lab = next((b for b in _lab_door(game, self.app)), (7, 12))
        game["area"] = 0
        game["center"] = [0, lab[0], lab[1] + 1]
        game["room"] = {"kind": "lab", "area": 0, "door": list(lab)}
        game["x"], game["y"] = 6, 4   # right in front of Oak
        A.save(game)
        ow = OverworldScene(self.app, game)
        game["face"] = "up"
        nm = game["name"].upper()
        ow.run_script([
            ("say", S.RIVAL, [f"{nm}! There you are! Gramps! I'm fed up with waiting!"]),
            ("say", "Prof. Oak", [f"{S.RIVAL}? Patience! I asked you both here, didn't I?",
                                    f"{nm}, there are three POKeMON on that table.",
                                    "They're inside these POKe BALLS. When I was young, I was a serious trainer.",
                                    "Now I only have these three left. You can have one. Go on, choose!"]),
            ("say", S.RIVAL, ["Hey! Gramps! What about me?"]),
            ("say", "Prof. Oak", [f"Be patient, {S.RIVAL}! You can have one too, after {nm} chooses."])])
        self.app.replace(ow)

    def update(self, dt):
        self.t += dt
        self.scene_t += dt
        AUDIO.music("town")
        if self.text is not None:
            self.text.update(dt)
        if self.go_t is not None:
            self.go_t += dt
            if self.go_t >= 1.6:
                self.go_t = None
                self._start()

    def handle(self, ev, pos):
        if self.stage == "setup":
            k = self.panel.handle(ev, pos)
            if k == "done":
                self._begin()
            elif k == "back":
                self.app.pop()
            return
        if self.stage == "talk" and self.text is not None:
            self.text.handle(ev)
            return
        if self.stage == "name":
            if ev.type == pygame.TEXTINPUT and len(self.name) < 10:
                self.name += "".join(c for c in ev.text if c.isalnum() or c == " ")[:10 - len(self.name)]
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_BACKSPACE:
                    self.name = self.name[:-1]
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.name.strip():
                    self._after_name()
                elif ev.key == pygame.K_ESCAPE:
                    self.app.pop()
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.name.strip():
                self._after_name()

    def _portrait(self, who):
        from . import cast
        if who == "player":
            who = cast.player_look()
        return BG.intro_pic(who)

    def draw(self, surf):
        t = self.t
        if self.stage == "setup":
            self.panel.draw(surf, t)
            return
        back = BG.intro_bg()
        if back is not None:
            surf.blit(back, (0, 0))
        else:
            bg(surf, (232, 232, 224), (96, 168, 160), stripes=False)
        k = min(1.0, self.scene_t / 0.35)   # each new face fades in
        cx, floor = VW // 2, 236
        if self.scene == "mon":
            plat = BG.intro_platform()
            if plat is not None:
                surf.blit(plat, plat.get_rect(center=(cx, floor - 44)))
            img = G.battle_sprite(self.SPEECH_MON, max_h=128)
            hop = int(abs(math.sin(min(self.scene_t, 0.6) * math.pi / 0.6)) * 10) if self.scene_t < 0.6 else 0
            img = img.copy()
            img.set_alpha(int(255 * k))
            surf.blit(img, img.get_rect(midbottom=(cx, floor - 40 - hop)))
        else:
            pic = self._portrait(self.scene)
            if pic is not None:
                pic = pic.copy()
                x = cx
                if self.stage == "name":
                    x = 120
                if self.go_t is not None:   # FireRed: you shrink away into the world
                    s = max(0.05, 1.0 - self.go_t / 1.0)
                    pic = pygame.transform.scale_by(pic, s)
                pic.set_alpha(int(255 * k))
                surf.blit(pic, pic.get_rect(midbottom=(x, floor + 10 if self.go_t is None else
                                                       floor - 60 + int(70 * max(0.05, 1 - self.go_t)))))
        if self.go_t is not None:
            U.fade(surf, max(0.0, min(1.0, (self.go_t - 0.9) / 0.6)))
            return
        if self.stage == "talk" and self.text is not None:
            self.text.draw(surf, t)
        elif self.stage == "name":
            inner = U.box(surf, (236, 64, 232, 118))
            F.draw(surf, "YOUR NAME?", (inner.x + 12, inner.y + 6), U.TEXT, U.SHADOW)
            pygame.draw.rect(surf, (216, 224, 240), (inner.x + 10, inner.y + 38, inner.w - 20, 34), border_radius=4)
            caret = "_" if int(t * 3) % 2 else " "
            F.draw(surf, self.name.upper() + caret, (inner.x + 18, inner.y + 42), U.TEXT, U.SHADOW, scale=2)
            F.draw(surf, "Type it, then ENTER", (inner.x + 12, inner.y + 84), (120, 120, 136), None, scale=1)


def _lab_door(game, app):
    w = A.World(app.dex)
    for y, row in enumerate(w.areas[0]["rows"]):
        for x, ch in enumerate(row):
            if ch == "P":
                yield (x, y)


# ====================================================================== party
class PartyScene(GBAScene):
    """GBA party screen: the lead in the big slot on the left, the rest on the right."""

    def __init__(self, app, game, pick=None, title=None):
        super().__init__(app)
        self.game = game
        self.dex = app.dex
        self.index = 0
        self.pick = pick
        self.sub = None
        self.swap = None
        self.title = title
        self.t = 0.0
        self.msg = None

    def update(self, dt):
        self.t += dt

    def _real(self):
        from . import battlegfx as BG
        return BG.party_bg() is not None and BG.party_slot(0) is not None

    def _slot(self, i):
        if self._real():   # FireRed's windows: (1, 3) 10x7 for the lead, (12, 1 + 3k) 18x3 for the rest
            if i == 0:
                return pygame.Rect(16, 48, 160, 112)
            return pygame.Rect(192, 16 + (i - 1) * 48, 288, 48)
        if i == 0:
            return pygame.Rect(8, 36, 196, 108)
        return pygame.Rect(212, 6 + (i - 1) * 46, 262, 42)

    def handle(self, ev, pos):
        party = self.game["party"]
        n = len(party)
        if self.sub is not None:
            k = self.sub.handle(ev, pos)
            if k == "summary":
                self.sub = None
                self.app.push(SummaryScene(self.app, self.game, self.index))
            elif k == "switch":
                self.sub = None
                self.swap = self.index
            elif k == "box":
                self.sub = None
                if n > 1:
                    self.game["box"].append(party.pop(self.index))
                    self.index = min(self.index, len(party) - 1)
            elif k in ("cancel", "back"):
                self.sub = None
            return
        d = U.direction(ev)
        if d:
            if d == "right" and self.index == 0 and n > 1:
                self.index = 1
            elif d == "left" and self.index > 0:
                self.index = 0
            elif d == "down" and self.index < n - 1:
                self.index += 1
            elif d == "up" and self.index > 0:
                self.index -= 1
            AUDIO.play("click", 0.25)
            return
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and pos:
            for i in range(n):
                if self._slot(i).collidepoint(pos):
                    self.index = i
                    break
            else:
                return
        if U.is_a(ev):
            if self.swap is not None:
                a, b = self.swap, self.index
                party[a], party[b] = party[b], party[a]
                self.swap = None
                AUDIO.play("select", 0.5)
                return
            if self.pick:
                res = self.pick(self.index)
                if res:
                    self.msg = res if isinstance(res, str) else None
                    if not isinstance(res, str):
                        self.app.pop()
                return
            self.sub = U.Menu([("summary", "SUMMARY"), ("switch", "SWITCH"), ("box", "TO BOX", n > 1),
                               ("cancel", "CANCEL")])
        elif U.is_b(ev):
            if self.swap is not None:
                self.swap = None
            else:
                self.app.pop()

    def _draw_real(self, surf):
        from . import battlegfx as BG
        surf.blit(BG.party_bg(), (0, 0))
        party = self.game["party"]
        white, shade = (255, 255, 255), (112, 112, 112)
        for i in range(6):
            r = self._slot(i)
            if i >= len(party):
                if i > 0:
                    surf.blit(BG.party_slot(i, empty=True), r.topleft)
                continue
            m = party[i]
            hp, mx = A.hp_of(self.dex, m)
            sel = i == self.index
            state = ("fainted_sel" if sel else "fainted") if hp <= 0 else "selected" if sel else "normal"
            if self.swap == i:
                state = "switch"
            surf.blit(BG.party_slot(i, state), r.topleft)
            icon = G.icon(m["species"], m.get("shiny", False))
            bob = int(math.sin(self.t * 8) * 2) if sel and hp > 0 else 0
            nm = A.name_of(self.dex, m).upper()[:10]
            frac = hp / max(1, mx)
            level = "green" if frac > 0.5 else "yellow" if frac > 0.2 else "red"
            cols = BG.party_hp_colors(level) or (U.hp_color(frac), U.hp_color(frac))
            if i == 0:
                surf.blit(icon, icon.get_rect(center=(r.x + 22, r.y + 28 + bob)))
                F.draw_fit(surf, nm, (r.x + 56, r.y + 22), r.w - 64, white, shade)
                F.draw(surf, f"Lv{m['level']}", (r.x + 66, r.y + 46), white, shade, small=True)
                bar = pygame.Rect(r.x + 50, r.y + 70, 92, 6)
                F.draw(surf, f"{hp}/ {mx}", (r.right - 14, r.y + 82), white, shade, anchor="topright", small=True)
            else:
                surf.blit(icon, icon.get_rect(center=(r.x + 20, r.y + 22 + bob)))
                F.draw_fit(surf, nm, (r.x + 52, r.y + 6), 122, white, shade)
                F.draw(surf, f"Lv{m['level']}", (r.x + 64, r.y + 28), white, shade, small=True)
                bar = pygame.Rect(r.x + 178, r.y + 22, 92, 6)
                F.draw(surf, f"{hp}/ {mx}", (r.right - 14, r.y + 30), white, shade, anchor="topright", small=True)
            if m.get("shiny"):   # shinies get their star
                from .gbabattle import GBABattle
                GBABattle._star(surf, r.x + 12, r.y + 12) if i == 0 else GBABattle._star(surf, r.x + 40, r.y + 38)
            w = int(bar.w * max(0.0, min(1.0, frac)))
            if w:
                pygame.draw.rect(surf, cols[0], (bar.x, bar.y, w, bar.h))
                pygame.draw.rect(surf, cols[1], (bar.x, bar.y, w, 2))
            if m.get("status") and hp > 0:
                F.draw(surf, m["status"].upper(), (r.x + (110 if i else 160), r.y + (46 if i else 28)),
                       (248, 200, 64), None, scale=1)
        F.draw(surf, "CANCEL", (424, 278), white, shade, anchor="center")
        msg = self.msg or self.title or ("Move to where?" if self.swap is not None else "Choose a POKeMON.")
        inner = U.box(surf, (8, 260, 352 if not self.sub else 300, 56))
        F.draw(surf, msg, (inner.x + 8, inner.y + 8), U.TEXT, U.SHADOW)
        if self.sub is not None:
            self.sub.draw(surf, (318, 170, 158, 20 + 26 * len(self.sub.options)))

    def draw(self, surf):
        if self._real():
            self._draw_real(surf)
            return
        bg(surf, (64, 136, 120), (104, 184, 160))
        party = self.game["party"]
        for i, m in enumerate(party):
            self._draw_slot(surf, i, m)
        for i in range(len(party), 6):
            r = self._slot(i)
            pygame.draw.rect(surf, (80, 152, 136), r, border_radius=8)
        msg = self.msg or self.title or ("Move to where?" if self.swap is not None else "Choose a POKeMON.")
        inner = U.box(surf, (4, 256, 330 if self.sub else 472, 60))
        F.draw(surf, msg, (inner.x + 8, inner.y + 10), U.TEXT, U.SHADOW)
        if self.sub is not None:
            self.sub.draw(surf, (338, 184, 138, 20 + 26 * len(self.sub.options)))

    def _draw_slot(self, surf, i, m):
        r = self._slot(i)
        sel = i == self.index
        hp, mx = A.hp_of(self.dex, m)
        fainted = hp <= 0
        col = (232, 112, 104) if fainted else (96, 176, 240) if sel else (72, 128, 200)
        if self.swap == i:
            col = (240, 200, 88)
        pygame.draw.rect(surf, (40, 48, 64), r, border_radius=8)
        pygame.draw.rect(surf, col, r.inflate(-4, -4), border_radius=7)
        if sel:
            pygame.draw.rect(surf, (248, 104, 88), r, 3, border_radius=8)
        icon = G.icon(m["species"], m.get("shiny", False))
        bob = int(math.sin(self.t * 8) * 2) if sel else 0
        nm = A.name_of(self.dex, m).upper()[:10]
        if i == 0:
            surf.blit(icon, icon.get_rect(center=(r.x + 30, r.y + 30 + bob)))
            F.draw(surf, nm, (r.x + 60, r.y + 14), U.WHITE, (40, 56, 96))
            F.draw(surf, f"Lv{m['level']}", (r.x + 60, r.y + 38), U.WHITE, (40, 56, 96))
            U.hp_bar(surf, r.x + 30, r.y + 66, 140, hp / max(1, mx))
            F.draw(surf, f"{hp}/{mx}", (r.right - 12, r.y + 82), U.WHITE, (40, 56, 96), anchor="topright")
        else:
            surf.blit(icon, icon.get_rect(center=(r.x + 22, r.centery + bob)))
            F.draw(surf, nm, (r.x + 46, r.y + 4), U.WHITE, (40, 56, 96))
            F.draw(surf, f"Lv{m['level']}", (r.x + 46, r.y + 24), U.WHITE, (40, 56, 96), scale=1)
            U.hp_bar(surf, r.x + 140, r.y + 8, 110, hp / max(1, mx))
            F.draw(surf, f"{hp}/{mx}", (r.right - 10, r.y + 22), U.WHITE, (40, 56, 96), anchor="topright")
        if m.get("status") and not fainted:
            F.draw(surf, m["status"].upper(), (r.x + (100 if i else 14), r.y + (24 if i else 82)), (248, 200, 64),
                   None, scale=1)


class SummaryScene(GBAScene):
    def __init__(self, app, game, index, box=False):
        super().__init__(app)
        self.game = game
        self.list = game["box"] if box else game["party"]
        self.index = index
        self.page = 0
        self.t = 0.0

    def update(self, dt):
        self.t += dt

    def handle(self, ev, pos):
        d = U.direction(ev)
        if d == "right":
            self.page = (self.page + 1) % 2
        elif d == "left":
            self.page = (self.page - 1) % 2
        elif d == "down" and self.index < len(self.list) - 1:
            self.index += 1
        elif d == "up" and self.index > 0:
            self.index -= 1
        elif U.is_b(ev) or (ev.type == pygame.KEYDOWN and ev.key in U.A_KEYS):
            self.app.pop()
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self.page = (self.page + 1) % 2

    def draw(self, surf):
        dex = self.app.dex
        m = self.list[self.index]
        e = dex.all[m["species"]]
        bg(surf, (232, 224, 200), (248, 240, 216))
        title_bar(surf, ["POKeMON INFO", "KNOWN MOVES"][self.page] + "   < >")
        # left: the Pokemon
        pygame.draw.rect(surf, (48, 48, 56), (8, 40, 180, 272), border_radius=8)
        pygame.draw.rect(surf, (200, 216, 232), (10, 42, 176, 268), border_radius=7)
        img = G.battle_sprite(m["species"], shiny=m.get("shiny", False), max_h=140)
        surf.blit(img, img.get_rect(midbottom=(98, 200 + int(math.sin(self.t * 2) * 2))))
        F.draw(surf, A.name_of(dex, m).upper()[:10], (20, 48), U.TEXT, U.SHADOW)
        F.draw(surf, f"Lv{m['level']}", (20, 72), U.TEXT, U.SHADOW)
        if m.get("shiny"):
            F.draw(surf, "*", (160, 48), (232, 176, 32), None)
        x = 20
        for typ in e["types"]:
            x += type_tag(surf, typ, x, 212)
        lo, hi = A.xp_for(m["level"]), A.xp_for(m["level"] + 1)
        F.draw(surf, "EXP", (20, 244), U.TEXT, U.SHADOW, scale=1)
        U.exp_bar(surf, 48, 246, 128, (m["xp"] - lo) / max(1, hi - lo))
        F.draw(surf, f"To next Lv: {hi - m['xp']}", (20, 262), U.TEXT, U.SHADOW, scale=1)
        F.draw(surf, f"No.{e['species']:03d}", (20, 282), U.TEXT, U.SHADOW, scale=1)
        inner = U.box(surf, (196, 40, 280, 274))
        if self.page == 0:
            st = A.stats(dex, m)
            hp, mx = A.hp_of(dex, m)
            for i, (k, label) in enumerate(STATS):
                y = inner.y + 6 + i * 26
                F.draw(surf, label, (inner.x + 8, y), U.TEXT, U.SHADOW)
                F.draw(surf, f"{hp}/{mx}" if k == "hp" else str(st[k]), (inner.right - 8, y), U.TEXT, U.SHADOW,
                       anchor="topright")
            from .abilities import ability_name
            F.draw(surf, "ABILITY", (inner.x + 8, inner.y + 170), (120, 120, 136), None)
            F.draw(surf, ability_name(m.get("ability")).upper(), (inner.x + 8, inner.y + 192), U.TEXT, U.SHADOW)
            F.draw(surf, f"{m.get('nature', '').upper()} nature.", (inner.x + 8, inner.y + 220), U.TEXT, U.SHADOW)
            F.draw(surf, f"Met at Lv{m.get('met', m['level'])}, {m.get('origin') or 'ROUTE'}.",
                   (inner.x + 8, inner.y + 240), U.TEXT, U.SHADOW, scale=1)
        else:
            pps = m.get("pp") or []
            from .riftdex import RIFT_MOVE_ID, install
            install(dex)
            moves = list(m["moves"]) + ([RIFT_MOVE_ID] if m.get("rift_born") else [])
            step = 64 if len(moves) <= 4 else 52   # a Rift-Born Pokemon's fifth move
            for i, mid in enumerate(moves):
                mv = dex.moves[mid]
                y = inner.y + 4 + i * step
                type_tag(surf, dex.all[m["species"]]["types"][0] if mid == RIFT_MOVE_ID else mv["type"], inner.x + 6,
                         y + 2)
                F.draw(surf, mv["name"].upper(), (inner.x + 78, y + 2), (136, 40, 160) if mid == RIFT_MOVE_ID else
                       U.TEXT, U.SHADOW)
                pp = pps[i] if i < len(pps) else mv["pp"]
                F.draw(surf, f"PP {pp}/{mv['pp']}", (inner.x + 78, y + 26), U.TEXT, U.SHADOW)
                F.draw(surf, f"POW {mv['power'] or '-'}", (inner.right - 8, y + 26), (120, 120, 136), None,
                       anchor="topright")


class BoxScene(GBAScene):
    """Someone's PC: move Pokemon between the party and the Box."""

    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.side = "box"
        self.index = 0
        self.msg = "Pick a POKeMON to move."

    def _list(self):
        return self.game["box"] if self.side == "box" else self.game["party"]

    def handle(self, ev, pos):
        lst = self._list()
        d = U.direction(ev)
        if d in ("left", "right"):
            self.side = "party" if d == "left" else "box"
            self.index = 0
        elif d == "down" and self.index < len(lst) - 1:
            self.index += 1
        elif d == "up" and self.index > 0:
            self.index -= 1
        elif U.is_b(ev):
            A.save(self.game)
            self.app.pop()
        elif U.is_a(ev) and lst:
            g = self.game
            if self.side == "box":
                if len(g["party"]) >= 6:
                    self.msg = "Your party is full!"
                    return
                g["party"].append(g["box"].pop(self.index))
                self.msg = "Withdrew it into your party."
            else:
                if len(g["party"]) <= 1:
                    self.msg = "That's your last POKeMON!"
                    return
                g["box"].append(g["party"].pop(self.index))
                self.msg = "Deposited it in the Box."
            AUDIO.play("select", 0.5)
            self.index = max(0, min(self.index, len(self._list()) - 1))

    def draw(self, surf):
        dex = self.app.dex
        bg(surf, (120, 168, 216), (184, 216, 240))
        title_bar(surf, "POKeMON STORAGE   < party | box >", (72, 112, 200))
        for side, x0 in (("party", 8), ("box", 244)):
            lst = self.game[side]
            inner = U.box(surf, (x0, 40, 228, 212), border=(240, 192, 80) if side == self.side else (96, 160, 200))
            F.draw(surf, "PARTY" if side == "party" else f"BOX ({len(lst)})", (inner.x + 8, inner.y + 4), U.TEXT,
                   U.SHADOW)
            start = max(0, self.index - 4) if side == self.side else 0
            for i, m in enumerate(lst[start:start + 6]):
                j = start + i
                y = inner.y + 30 + i * 28
                icon = G.icon(m["species"], m.get("shiny", False))
                icon = pygame.transform.scale(icon, (int(icon.get_width() * 0.7), int(icon.get_height() * 0.7)))
                surf.blit(icon, icon.get_rect(midleft=(inner.x + 18, y + 8)))
                F.draw(surf, f"{A.name_of(dex, m).upper()[:9]} Lv{m['level']}", (inner.x + 50, y), U.TEXT, U.SHADOW)
                if side == self.side and j == self.index:
                    U.cursor(surf, (inner.x + 2, y))
        inner = U.box(surf, (4, 256, 472, 60))
        F.draw(surf, self.msg, (inner.x + 8, inner.y + 10), U.TEXT, U.SHADOW)


# ====================================================================== bag
class BagScene(GBAScene):
    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.sub = None
        self.msg = None
        self._refresh()

    def _refresh(self):
        items = [(k, n) for k, n in self.game["bag"].items() if n > 0]
        items.sort(key=lambda kv: list(A.SHOP).index(kv[0]) if kv[0] in A.SHOP else 99)
        self.items = items
        from . import story as S
        names = {k: A.SHOP.get(k, S.KEY_ITEMS.get(k, (k,)))[0].upper() for k, n in items}
        stones = len(self.game.get("megastones", []))
        self.menu = U.Menu([(k, names[k]) for k, n in items] +
                           ([("stones", f"MEGA STONES ({stones})")] if stones or self.game.get("keystone") else []) +
                           [("close", "CLOSE BAG")],
                           index=getattr(self, "menu", None).index if getattr(self, "menu", None) else 0)
        self.menu.index = min(self.menu.index, len(self.menu.options) - 1)

    def handle(self, ev, pos):
        if self.sub is not None:
            k = self.sub.handle(ev, pos)
            if k == "use":
                item = self.items[self.menu.index][0]
                self.sub = None
                self.app.push(PartyScene(self.app, self.game, pick=lambda i, item=item: self._use(item, i),
                                         title="Use on which POKeMON?"))
            elif k in ("cancel", "back"):
                self.sub = None
            return
        k = self.menu.handle(ev, pos)
        self.msg = None
        if k in ("close", "back"):
            self.app.pop()
        elif k is not None:
            if k == "stones":
                self.app.push(StonesScene(self.app, self.game))
            elif k == "mega-radar":   # back to the field with the radar switched on
                self.game["_radar"] = True
                self.app.pop()
            elif k == "exp-all":   # switch it on and off
                self.game["expall_off"] = not self.game.get("expall_off")
                AUDIO.play("select", 0.5)
                self.msg = "The EXP. ALL was turned " + ("OFF." if self.game["expall_off"] else "ON.")
            elif k in A.BALL_KEYS:
                self.msg = "Throw it at a wild POKeMON in battle!"
            elif k not in A.SHOP:
                self.msg = "A precious item. Better hold on to it."
            else:
                self.sub = U.Menu([("use", "USE"), ("cancel", "CANCEL")])

    def update(self, dt):
        if getattr(self, "evolve", None) and self.app.stack[-1] is self:
            mon, to = self.evolve
            self.evolve = None
            self.app.push(EvolutionScene(self.app, self.game, mon, to))

    def _candy(self, mon):
        dex = self.app.dex
        if mon["level"] >= A.MAX_LEVEL:
            AUDIO.play("miss", 0.5)
            return "It won't have any effect."
        events = A.gain_xp(dex, mon, A.xp_for(mon["level"] + 1) - mon["xp"])
        self.game["bag"]["rare-candy"] -= 1
        if self.game["bag"]["rare-candy"] <= 0:
            del self.game["bag"]["rare-candy"]
        AUDIO.play("levelup" if "levelup" in getattr(AUDIO, "sfx", {}) else "heal")
        nm = A.name_of(dex, mon).upper()
        learned = [dex.moves[e[1]]["name"].upper() for e in events if e[0] == "learn"]
        self.msg = f"{nm} grew to LV. {mon['level']}!" + (f" Learned {learned[0]}!" if learned else "")
        evo = [e[1] for e in events if e[0] == "evolve"]
        if evo:
            self.evolve = (mon, evo[0])
        self._refresh()
        return True

    def _use(self, item, i):
        dex = self.app.dex
        mon = self.game["party"][i]
        if item == "rare-candy":
            return self._candy(mon)
        name, heal, cure, revive = MEDICINE[item]
        hp, mx = A.hp_of(dex, mon)
        if revive != (hp <= 0) or (not revive and hp >= mx and not (cure and mon.get("status"))):
            AUDIO.play("miss", 0.5)
            return "It won't have any effect."
        if revive:
            mon["cur_hp"] = max(1, int(mx * heal))
        elif heal:
            new = mx if heal < 0 else min(mx, hp + heal)
            mon["cur_hp"] = None if new >= mx else new
        if cure:
            mon["status"] = None
        self.game["bag"][item] -= 1
        if self.game["bag"][item] <= 0:
            del self.game["bag"][item]
        AUDIO.play("heal")
        self._refresh()
        return True

    def draw(self, surf):
        bg(surf, (232, 168, 96), (248, 208, 144))
        # the bag
        pygame.draw.rect(surf, (48, 48, 56), (24, 40, 140, 150), border_radius=20)
        pygame.draw.rect(surf, (200, 104, 64), (28, 44, 132, 142), border_radius=18)
        pygame.draw.rect(surf, (168, 80, 48), (40, 80, 108, 80), border_radius=10)
        pygame.draw.rect(surf, (232, 200, 96), (84, 110, 20, 14), border_radius=3)
        F.draw(surf, "ITEMS", (94, 204), U.WHITE, (120, 64, 32), anchor="center", scale=3)
        rows = len(self.menu.options)
        self.menu.draw(surf, (184, 8, 292, min(240, 20 + 26 * rows)))
        top = getattr(self.menu, "top", 0)
        fit = max(1, (min(240, 20 + 26 * rows) - 8 - 6) // 26)
        for i, (k, n) in enumerate(self.items):
            if top <= i < top + fit:
                F.draw(surf, f"x{n}", (450, 8 + 12 + (i - top) * 26), U.TEXT, U.SHADOW, anchor="topright")
        inner = U.box(surf, (4, 256, 472, 60))
        k = self.menu.options[self.menu.index][0]
        from . import story as S
        desc = self.msg or (A.SHOP[k][2] if k in A.SHOP else S.KEY_ITEMS[k][1] if k in S.KEY_ITEMS else
                            "Your collection of Mega Stones." if k == "stones" else "Close the BAG.")
        F.draw(surf, desc, (inner.x + 8, inner.y + 10), U.TEXT, U.SHADOW)
        if self.sub is not None:
            self.sub.draw(surf, (338, 186, 138, 72))


class StonesScene(GBAScene):
    """The Mega Stone case: every stone you've found (corrupted ones too), and which of your Pokemon can use it.
    Z on a corrupted stone you also have a clean copy of picks which one your Pokemon holds."""

    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.top = 0
        self.index = 0

    def rows(self):
        g = self.game
        return [(k, False) for k in g.get("megastones", [])] + [(k, True) for k in g.get("corrupted", [])]

    def handle(self, ev, pos):
        d = U.direction(ev)
        rows = self.rows()
        n = len(rows)
        if d in ("down", "up") and n:
            self.index = max(0, min(n - 1, self.index + (1 if d == "down" else -1)))
            self.top = max(0, min(self.index, max(self.top, self.index - 7)))
        elif U.is_a(ev) and n and rows[self.index][1]:
            key = rows[self.index][0]
            if key in self.game.get("megastones", []):
                on = self.game.setdefault("corrupt_on", [])
                if key in on:
                    on.remove(key)
                else:
                    on.append(key)
                AUDIO.play("select")
            else:
                AUDIO.play("miss", 0.4)
        elif U.is_a(ev) or U.is_b(ev):
            self.app.pop()

    def draw(self, surf):
        from . import riftdex as R
        dex = self.app.dex
        g = self.game
        bg(surf, (112, 72, 160), (168, 128, 208))
        inner = U.box(surf, (8, 8, VW - 16, 44))
        total = len(S.all_stones(dex)) + len(R.custom_stones(dex))
        F.draw(surf, f"MEGA STONES  {len(g.get('megastones', []))}/{total}", (inner.x + 8, inner.y + 8),
               U.TEXT, U.SHADOW)
        F.draw(surf, "KEY STONE: " + ("YES" if g.get("keystone") else "NOT YET"), (inner.right - 8, inner.y + 8),
               (64, 136, 72) if g.get("keystone") else (200, 72, 64), U.SHADOW, anchor="topright")
        box = U.box(surf, (8, 58, VW - 16, VH - 66))
        rows = self.rows()
        if not rows:
            F.draw(surf, "No Mega Stones yet. Look for sparkles", (box.x + 8, box.y + 10), U.TEXT, U.SHADOW)
            F.draw(surf, "on the routes, and beat Gym Leaders!", (box.x + 8, box.y + 36), U.TEXT, U.SHADOW)
            return
        owned = {dex.all[m["species"]]["name"].split(" ")[0].lower() for m in g["party"] + g.get("box", [])}
        for i, (key, bad) in enumerate(rows[self.top:self.top + 8]):
            y = box.y + 6 + i * 30
            if self.top + i == self.index:
                U.cursor(surf, (box.x + 2, y + 2))
            base = key.split("-mega")[0].split("-primal")[0]
            e = dex.get(base)
            if e:
                surf.blit(G.icon(e["id"]), (box.x + 14, y - 4))
            have = base.replace("-", " ") in owned or base in owned
            name = (R.corrupted_name(dex, key) if bad else S.stone_name(dex, key)).upper()[:24]
            F.draw(surf, name, (box.x + 56, y + 4), (136, 40, 120) if bad else U.TEXT, U.SHADOW)
            tag = ""
            if bad:
                tag = "IN USE" if A.uses_corrupted(g, key) else "Z: USE"
            elif have:
                tag = "IN TEAM"
            F.draw(surf, tag, (box.right - 8, y + 4), (136, 40, 120) if bad else (64, 136, 72), U.SHADOW,
                   anchor="topright")
        if rows[self.index][1]:
            F.draw(surf, "Corrupted: doubles every stat after Mega Evolving - and hurts it every turn.",
                   (box.x + 8, box.bottom - 18), (136, 40, 120), None, scale=1)


class QuestScene(GBAScene):
    """The quest log: the main story's next step, then every side quest you've taken on."""

    def __init__(self, app, game):
        super().__init__(app)
        self.game = game

    def handle(self, ev, pos):
        if U.is_a(ev) or U.is_b(ev):
            self.app.pop()

    def draw(self, surf):
        from . import story as S
        g = self.game
        bg(surf, (64, 128, 96), (120, 184, 144))
        inner = U.box(surf, (8, 8, VW - 16, 74))
        F.draw(surf, "MAIN STORY", (inner.x + 8, inner.y + 6), (200, 72, 64), U.SHADOW)
        F.draw(surf, S.next_goal(g, self.app.dex), (inner.x + 8, inner.y + 32), U.TEXT, U.SHADOW, scale=1)
        box = U.box(surf, (8, 88, VW - 16, VH - 96))
        F.draw(surf, "SIDE QUESTS", (box.x + 8, box.y + 4), (64, 104, 176), U.SHADOW)
        qs = S.quest_list(g)
        if not qs:
            F.draw(surf, "None yet. Talk to people in towns and on routes!", (box.x + 8, box.y + 34), U.TEXT,
                   U.SHADOW, scale=1)
        for i, (qid, name, giver, st) in enumerate(qs):
            y = box.y + 30 + i * 24
            done = st == "done"
            pygame.draw.rect(surf, (64, 160, 88) if done else (232, 176, 64), (box.x + 10, y + 3, 10, 10),
                             border_radius=2)
            F.draw(surf, name.upper(), (box.x + 28, y), U.TEXT, U.SHADOW)
            F.draw(surf, "DONE" if done else giver, (box.right - 8, y + 4), (96, 104, 120), None, scale=1,
                   anchor="topright")
        F.draw(surf, f"SECRETS FOUND: {S.secrets_found(g)}/{len(S.SECRETS)}", (box.x + 8, box.bottom - 18),
               (112, 80, 160), None, scale=1)
        if g.get("keystone"):
            F.draw(surf, f"MEGA RIFTS SEALED: {S.rifts_sealed(g)}/{A.NUM_ROUTES}", (box.right - 8, box.bottom - 18),
                   (112, 80, 160), None, scale=1, anchor="topright")


# ====================================================================== mart
class MartScene(GBAScene):
    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.stage = "top"
        self.top = U.Menu([("buy", "BUY"), ("sell", "SELL"), ("bye", "SEE YA!")])
        self.list = None
        self.qty = 1
        self.text = None

    def _buy_list(self):
        stock = A.mart_stock(len(self.game["badges"]))
        self.list = U.Menu([(k, A.SHOP[k][0].upper()) for k in stock] + [("cancel", "CANCEL")])
        self.stage = "buy"

    def _sell_list(self):
        items = [k for k, n in self.game["bag"].items() if n > 0 and A.SHOP.get(k, (0, 0))[1] > 0]
        self.list = U.Menu([(k, A.SHOP[k][0].upper()) for k in items] + [("cancel", "CANCEL")])
        self.stage = "sell"

    def update(self, dt):
        if self.text is not None:
            self.text.update(dt)
            if self.text.done:
                self.text = None

    def handle(self, ev, pos):
        if self.text is not None:
            self.text.handle(ev)
            if self.text.done:
                self.text = None
            return
        g = self.game
        if self.stage == "top":
            k = self.top.handle(ev, pos)
            if k == "buy":
                self._buy_list()
            elif k == "sell":
                self._sell_list()
            elif k in ("bye", "back"):
                A.save(g)
                self.app.pop()
        elif self.stage in ("buy", "sell"):
            k = self.list.handle(ev, pos)
            if k in ("cancel", "back"):
                self.stage = "top"
            elif k is not None:
                self.item = k
                self.qty = 1
                self.stage = "qty_" + self.stage
        elif self.stage.startswith("qty_"):
            selling = self.stage == "qty_sell"
            price = int(A.SHOP[self.item][1] * (1 if selling else A.diff()["price"])) // (2 if selling else 1)
            cap = g["bag"].get(self.item, 0) if selling else max(1, min(99, g["money"] // max(1, price)))
            d = U.direction(ev)
            if d in ("up", "right"):
                self.qty = self.qty + (1 if d == "up" else 10)
                self.qty = 1 if self.qty > cap else self.qty
            elif d in ("down", "left"):
                self.qty = self.qty - (1 if d == "down" else 10)
                self.qty = cap if self.qty < 1 else self.qty
            elif U.is_b(ev):
                self.stage = self.stage[4:]
            elif U.is_a(ev):
                total = price * self.qty
                name = A.SHOP[self.item][0].upper()
                if selling:
                    g["bag"][self.item] -= self.qty
                    if g["bag"][self.item] <= 0:
                        del g["bag"][self.item]
                    g["money"] += total
                    self.text = U.TextBox([f"Turned over the {name} and received {total} coins."])
                    self._sell_list()
                elif g["money"] < total:
                    self.text = U.TextBox(["You don't have enough money."])
                    self.stage = "buy"
                else:
                    g["money"] -= total
                    g["bag"][self.item] = g["bag"].get(self.item, 0) + self.qty
                    AUDIO.play("catch", 0.5)
                    self.text = U.TextBox([f"{name}, and you want {self.qty}. That'll be {total} coins.",
                                           "Here you are! Thank you!"])
                    self.stage = "buy"

    def draw(self, surf):
        below = self.app.stack[-2] if len(self.app.stack) > 1 and self.app.stack[-1] is self else None
        if below is not None and type(below).__name__ == "OverworldScene":   # FireRed: the menus open over the shop
            text, below.text = below.text, None
            below.draw(surf)
            below.text = text
        else:
            bg(surf, (152, 200, 232), (224, 240, 248))
            clerk = pygame.transform.scale_by(G.person("clerk", "down", 0), 3)
            surf.blit(clerk, clerk.get_rect(midbottom=(80, 160)))
        g = self.game
        inner = U.box(surf, (4, 4, 170, 52))
        F.draw(surf, "MONEY", (inner.x + 8, inner.y + 2), U.TEXT, U.SHADOW, scale=1)
        F.draw(surf, f"{g['money']}", (inner.right - 8, inner.y + 14), U.TEXT, U.SHADOW, anchor="topright")
        if self.stage == "top":
            self.top.draw(surf, (330, 4, 146, 98))
            if self.text is None:
                box = U.box(surf, (4, 240, 472, 76))
                F.draw(surf, "Hi there! May I help you?", (box.x + 10, box.y + 6), U.TEXT, U.SHADOW)
        elif self.stage in ("buy", "sell") or self.stage.startswith("qty_"):
            selling = "sell" in self.stage
            self.list.draw(surf, (196, 4, 280, min(232, 20 + 26 * len(self.list.options))))
            for i, (k, *_) in enumerate(self.list.options[:8]):
                if k in A.SHOP:
                    price = int(A.SHOP[k][1] * (1 if selling else A.diff()["price"])) // (2 if selling else 1)
                    val = f"x{g['bag'].get(k, 0)}" if selling else f"{price}"
                    F.draw(surf, val, (466, 4 + 12 + i * 26), U.TEXT, U.SHADOW, anchor="topright")
            k = self.list.options[self.list.index][0]
            box = U.box(surf, (4, 240, 472, 76))
            F.draw(surf, A.SHOP[k][2] if k in A.SHOP else "Quit shopping.", (box.x + 10, box.y + 6), U.TEXT,
                   U.SHADOW)
            F.draw(surf, f"In bag: {g['bag'].get(k, 0)}" if k in A.SHOP else "", (box.x + 10, box.y + 32),
                   (120, 120, 136), None)
            if self.stage.startswith("qty_"):
                price = int(A.SHOP[self.item][1] * (1 if selling else A.diff()["price"])) // (2 if selling else 1)
                q = U.box(surf, (240, 186, 236, 52))
                F.draw(surf, f"x{self.qty:02d}", (q.x + 10, q.y + 6), U.TEXT, U.SHADOW)
                F.draw(surf, f"{price * self.qty} coins", (q.right - 8, q.y + 6), U.TEXT, U.SHADOW, anchor="topright")
        if self.text is not None:
            self.text.draw(surf, 0.0)


# ====================================================================== pokedex
class DexScene(GBAScene):
    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.dex = app.dex
        self.entries = sorted({self.dex.all[p]["species"] for p in game["seen"] if p in self.dex.all})
        self.index = 0
        self.view = False

    def _entry(self, sid):
        return next((e for e in self.dex.all.values() if e["species"] == sid and e["default"]), None)

    def handle(self, ev, pos):
        d = U.direction(ev)
        n = len(self.entries)
        if d == "down" and self.index < n - 1:
            self.index += 1
        elif d == "up" and self.index > 0:
            self.index -= 1
        elif d == "right":
            self.index = min(n - 1, self.index + 8)
        elif d == "left":
            self.index = max(0, self.index - 8)
        elif U.is_a(ev) and n:
            self.view = not self.view
            if self.view:
                AUDIO.cry(self._entry(self.entries[self.index])["id"], 0.8)
        elif U.is_b(ev):
            if self.view:
                self.view = False
            else:
                self.app.pop()

    def draw(self, surf):
        bg(surf, (200, 56, 56), (232, 104, 96), stripes=False)
        caught = {self.dex.all[p]["species"] for p in self.game["caught"] if p in self.dex.all}
        title_bar(surf, f"POKeDEX   SEEN {len(self.entries)}   OWN {len(caught)}", (56, 56, 64))
        if not self.entries:
            return
        sid = self.entries[self.index]
        e = self._entry(sid)
        if self.view and e:
            inner = U.box(surf, (8, 40, 464, 272))
            img = G.battle_sprite(e["id"], max_h=140)
            pygame.draw.rect(surf, (216, 224, 232), (inner.x + 8, inner.y + 8, 170, 170), border_radius=6)
            surf.blit(img, img.get_rect(center=(inner.x + 93, inner.y + 93)))
            F.draw(surf, f"No.{sid:03d}", (inner.x + 196, inner.y + 10), U.TEXT, U.SHADOW)
            F.draw(surf, e["name"].upper(), (inner.x + 196, inner.y + 36), U.TEXT, U.SHADOW)
            x = inner.x + 196
            for typ in e["types"]:
                x += type_tag(surf, typ, x, inner.y + 66)
            if sid in caught:
                for i, (k, label) in enumerate(STATS):
                    y = inner.y + 96 + i * 20
                    F.draw(surf, label, (inner.x + 196, y), U.TEXT, U.SHADOW, scale=1)
                    v = e["stats"][k]
                    pygame.draw.rect(surf, (216, 216, 216), (inner.x + 270, y + 2, 160, 8))
                    pygame.draw.rect(surf, U.hp_color(v / 150), (inner.x + 270, y + 2, min(160, v), 8))
            else:
                F.draw(surf, "Not caught yet.", (inner.x + 196, inner.y + 100), (120, 120, 136), None)
            return
        inner = U.box(surf, (8, 40, 464, 272))
        start = max(0, self.index - 4)
        for i, s in enumerate(self.entries[start:start + 9]):
            j = start + i
            y = inner.y + 6 + i * 28
            en = self._entry(s)
            if s in caught:
                U.ball(surf, (inner.x + 30, y + 8), 5)
            F.draw(surf, f"No.{s:03d}  {(en['name'] if en else '?').upper()}", (inner.x + 46, y), U.TEXT, U.SHADOW)
            if j == self.index:
                U.cursor(surf, (inner.x + 4, y))
        if e:
            img = G.icon(e["id"])
            surf.blit(pygame.transform.scale_by(img, 2), (380, 60))


# ====================================================================== trainer card
class CardScene(GBAScene):
    def __init__(self, app, game):
        super().__init__(app)
        self.game = game

    def handle(self, ev, pos):
        if U.is_a(ev) or U.is_b(ev):
            self.app.pop()

    def draw(self, surf):
        g = self.game
        bg(surf, (64, 120, 200), (120, 168, 232))
        r = pygame.Rect(20, 16, 440, 288)
        pygame.draw.rect(surf, (48, 48, 56), r, border_radius=12)
        pygame.draw.rect(surf, (232, 216, 160), r.inflate(-6, -6), border_radius=10)
        pygame.draw.rect(surf, (200, 168, 96), (r.x + 10, r.y + 10, r.w - 20, 30), border_radius=6)
        F.draw(surf, "TRAINER CARD", (r.x + 22, r.y + 16), U.WHITE, (120, 88, 40))
        rows = [("NAME", g["name"].upper()), ("MONEY", f"{g['money']}"), ("POKeDEX", f"{len(g['caught'])}"),
                ("TIME", A.playtime_text(g.get("playtime", 0)))]
        for i, (k, v) in enumerate(rows):
            y = r.y + 56 + i * 30
            F.draw(surf, k, (r.x + 22, y), U.TEXT, U.SHADOW)
            F.draw(surf, v, (r.x + 280, y), U.TEXT, U.SHADOW, anchor="topright")
        from . import cast
        pic = BG.intro_pic(cast.player_look()) if hasattr(BG, "intro_pic") else None
        if pic is not None:   # FireRed's card shows the trainer's full picture
            k = 150 / max(1, pic.get_height())
            me = pygame.transform.scale(pic, (int(pic.get_width() * k), 150)) if k < 1 else pic
            me = me.subsurface(me.get_bounding_rect()).copy() if me.get_bounding_rect().w else me
        else:
            me = pygame.transform.scale_by(G.person("player", "down", 0), 3)
        surf.blit(me, me.get_rect(midbottom=(r.right - 80, r.y + 182)))
        pygame.draw.rect(surf, (200, 168, 96), (r.x + 10, r.y + 190, r.w - 20, 86), border_radius=6)
        for i, gym in enumerate(A.GYMS):   # the badge case: two rows of nine
            x, y = r.x + 34 + (i % 9) * 46, r.y + 212 + (i // 9) * 38
            have = gym[6] in g["badges"]
            col = type_color(gym[2], 0) if have else (168, 136, 80)
            pts = [(x + 14 * math.cos(a), y + 14 * math.sin(a)) for a in [k * math.tau / 6 for k in range(6)]]
            pygame.draw.polygon(surf, (72, 56, 32), [(px + 1, py + 2) for px, py in pts])
            pygame.draw.polygon(surf, col, pts)
            if have:
                pygame.draw.circle(surf, (255, 255, 255), (x - 5, y - 5), 3)


# ====================================================================== evolution
class EvolutionScene(GBAScene):
    no_transition = True

    def __init__(self, app, game, mon, to):
        super().__init__(app)
        self.game, self.mon, self.to = game, mon, to
        self.old = mon["species"]
        self.old_name = A.name_of(app.dex, mon).upper()
        self.t = 0.0
        self.done = False
        self.learned = []
        self.text = U.TextBox([f"What? {self.old_name} is evolving!"], auto=1.6)
        AUDIO.cry(self.old, 0.9)

    def update(self, dt):
        self.t += dt
        AUDIO.music(None)
        if self.text is not None:
            self.text.update(dt)
        if self.t >= 5.0 and not self.done:
            self.done = True
            self.learned = A.evolve(self.app.dex, self.mon, self.to)
            A.save(self.game)
            AUDIO.play("win")
            AUDIO.cry(self.to, 1.0)
            new = A.name_of(self.app.dex, self.mon).upper()
            lines = [f"Congratulations! Your {self.old_name} evolved into {new}!"]
            lines += [f"{new} learned {self.app.dex.moves[mid]['name'].upper()}!" for _, mid, _ in self.learned]
            self.text = U.TextBox(lines)

    def handle(self, ev, pos):
        if not self.done or self.text is None:
            return
        if self.text.handle(ev) and self.text.done:
            self.app.pop()

    def draw(self, surf):
        t = self.t
        surf.fill((24, 24, 48))
        for i in range(30):
            a = i / 30 * math.tau + t * (0.6 + t * 0.3)
            rr = 40 + (i * 37 % 100)
            pygame.draw.circle(surf, (168, 200, 248), (int(240 + math.cos(a) * rr * 1.6), int(120 + math.sin(a) * rr)),
                               2)
        old = G.battle_sprite(self.old, shiny=self.mon.get("shiny", False), max_h=150)
        new = G.battle_sprite(self.to, shiny=self.mon.get("shiny", False), max_h=150)
        if t < 5.0:
            show_new = t > 1.5 and math.sin(t * (2 + t * t * 0.8)) > 0.2
            img = new if show_new else old
            if t > 1.0:
                img = img.copy()
                img.fill((248, 248, 248, 0), special_flags=pygame.BLEND_RGBA_MAX)
            surf.blit(img, img.get_rect(midbottom=(240, 220)))
            if t > 4.6:
                U.fade(surf, (t - 4.6) / 0.4, (248, 248, 248))
        else:
            surf.blit(new, new.get_rect(midbottom=(240, 220)))
            U.fade(surf, max(0.0, 1 - (t - 5.0) / 0.6), (248, 248, 248))
        if self.text is not None:
            self.text.draw(surf, t)


# ====================================================================== hall of fame
class HallOfFame(GBAScene):
    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.t = 0.0
        A.save(game)

    def update(self, dt):
        self.t += dt
        AUDIO.music("showcase")

    def handle(self, ev, pos):
        if self.t > 3 and (U.is_a(ev) or U.is_b(ev)):
            self.app.pop()

    def draw(self, surf):
        t = self.t
        surf.fill((40, 24, 8))
        for i in range(16):
            a = i / 16 * math.tau + t * 0.3
            pts = [(240, 150), (240 + math.cos(a - 0.08) * 600, 150 + math.sin(a - 0.08) * 600),
                   (240 + math.cos(a + 0.08) * 600, 150 + math.sin(a + 0.08) * 600)]
            pygame.draw.polygon(surf, (88, 64, 24), pts)
        F.draw(surf, "HALL OF FAME", (240, 24), (248, 216, 64), (120, 72, 16), scale=4, anchor="center")
        F.draw(surf, f"CHAMPION {self.game['name'].upper()}", (240, 56), U.WHITE, (96, 64, 24), anchor="center")
        for i, m in enumerate(self.game["party"]):
            k = min(1.0, max(0.0, (t - i * 0.4) / 0.4))
            if k <= 0:
                continue
            x, y = 80 + (i % 3) * 160, 170 + (i // 3) * 120
            img = G.battle_sprite(m["species"], shiny=m.get("shiny", False), max_h=90)
            surf.blit(img, img.get_rect(midbottom=(x, y + int((1 - k) * 20))))
            F.draw(surf, f"{A.name_of(self.app.dex, m).upper()} Lv{m['level']}", (x, y + 8), U.WHITE, (96, 64, 24),
                   scale=1, anchor="center")


class Credits(GBAScene):
    """The true ending's credits: the cast of the story scrolls up while your team walks along the bottom."""
    ROLL = [("THE FIRST RIFT", None), ("", None),
            ("PROFESSOR OAK", "prof"), ("who never stopped looking", None), ("", None),
            ("BLAKE", "rival"), ("who found his way back", None), ("", None),
            ("DR. ELIAS", "elias"), ("ten years in a rift, home at last", None), ("", None),
            ("AURELIA", "champ"), ("who kept the title warm", None), ("", None),
            ("GIOVANNI", "boss"), ("who opened the wounds", None), ("", None),
            ("ADMIN MORGA", "admin"), ("who made the offer", None), ("", None),
            ("THE ELITE FOUR", None), ("Frost - Brutus - Morrow - Drakon", None), ("", None),
            ("18 GYM LEADERS", None), ("Petra - Hive - Coral - Patty - Zappa - Skye", None),
            ("Fern - Knox - Nox - Pixie - Sage - Wren", None), ("Blaze - Ferris - Nieve - Raven - Terra - Draco", None),
            ("", None), ("ARCEUS", None), ("who decided the world was worth keeping", None), ("", None), ("", None),
            ("and YOU", None), ("", None), ("", None), ("THE END", None), ("", None), ("Thanks for playing PokeBrawl", None)]

    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        AUDIO.music("showcase")

    def handle(self, ev, pos):
        if (U.is_a(ev) or U.is_b(ev)) and self.t > 3:
            if self._done():
                self.app.pop()
            else:
                self.t += 6   # skip ahead

    def _done(self):
        return self.t * 22 > len(self.ROLL) * 26 + 260

    def draw(self, surf):
        t = self.t
        surf.fill((8, 6, 20))
        rng = random.Random(7)
        for _ in range(60):   # a slow starfield
            x, y = rng.randrange(480), rng.randrange(320)
            sp = rng.uniform(4, 16)
            yy = int((y - t * sp) % 320)
            surf.fill((200, 200, 255) if sp > 12 else (110, 110, 170), (x, yy, 2 if sp > 12 else 1, 2 if sp > 12 else 1))
        off = 300 - t * 22
        for i, (line, look) in enumerate(self.ROLL):
            y = off + i * 26
            if y < -40 or y > 300 or not line:
                continue
            big = line.isupper()
            end = line == "THE END"
            F.draw(surf, line, (240 + (14 if look else 0), int(y)), (248, 216, 64) if (big and not end) else U.WHITE,
                   (60, 40, 16), scale=4 if end else 2 if big else 1, anchor="center")
            if look:
                img = G.person(look, "down")
                surf.blit(img, img.get_rect(midright=(240 - F.width(line, 2) // 2 - 4, int(y))))
        # your team walks along the bottom
        for i, m in enumerate(self.game["party"]):
            img = G.battle_sprite(m["species"], shiny=m.get("shiny", False), max_h=56)
            img = pygame.transform.scale_by(img, 0.45)
            x = (t * 40 + i * 70) % 640 - 80
            surf.blit(img, img.get_rect(midbottom=(int(x), 318 - int(abs(math.sin(t * 6 + i)) * 4))))
        if self._done():
            F.draw(surf, "Press A", (240, 300), U.WHITE, (60, 40, 16), anchor="center")
