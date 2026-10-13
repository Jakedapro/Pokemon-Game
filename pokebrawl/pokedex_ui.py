"""Pokedex browser: every Pokemon in the game. Search by name, filter by type and generation, open one for its
types, base stats, abilities, weaknesses and forms (Mega, Gigantamax, regional). Tap the sprite for its shiny."""
import math

import pygame

from . import gfx, profile, ui
from .abilities import DESCRIPTIONS, ability_name
from .app import Scene
from .audio import AUDIO
from .gfx import H, W
from .trainer_ui import STAT_NAMES, fit, type_row
from .tournament import short_name
from .types import TYPES, effectiveness


class PokedexScene(Scene):
    COLS, CW, CH, TOP, BOTTOM = 5, 128, 150, 320, 1150

    def __init__(self, app):
        super().__init__(app)
        self.all = sorted((e for e in app.dex.selectable() if e["default"]), key=lambda e: e["id"])
        self.search = ui.TextInput((40, 176, 640, 58), "", "", "Search by name...")
        self.type = ui.Cycle((40, 246, 330, 56), "Type", ["All"] + [t.title() for t in TYPES])
        self.gen = ui.Cycle((390, 246, 290, 56), "Gen", ["All"] + [str(g) for g in range(1, 10)])
        self.back = ui.Button((40, 1180, 200, 70), "Back", ui.PANEL2, 24)
        self.scroll = 0.0
        self.detail = None
        self.legends = profile.load()["legends"]
        self._key = None
        self.rows = self.all

    def _filtered(self):
        key = (self.search.value.strip().lower(), self.type.value, self.gen.value)
        if key != self._key:
            self._key = key
            q, typ, gen = key
            rows = self.all
            if q:
                rows = [e for e in rows if q in e["name"].lower() or q == str(e["id"])]
            if typ != "All":
                rows = [e for e in rows if typ.lower() in e["types"]]
            if gen != "All":
                rows = [e for e in rows if e["gen"] == int(gen)]
            self.rows = rows
            self.scroll = 0.0
        return self.rows

    def _cell(self, i):
        x = 40 + (i % self.COLS) * self.CW
        y = self.TOP + (i // self.COLS) * self.CH - self.scroll
        return pygame.Rect(x, y, self.CW - 8, self.CH - 8)

    def handle(self, ev, pos):
        if self.detail is not None:
            self.detail.handle(ev, pos)
            if self.detail.closed:
                self.detail = None
            return
        if self.search.handle(ev, pos):
            return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        if ev.type == pygame.MOUSEWHEEL:
            rows = (len(self._filtered()) + self.COLS - 1) // self.COLS
            self.scroll = max(0, min(max(0, rows * self.CH - (self.BOTTOM - self.TOP)), self.scroll - ev.y * 80))
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        if self.back.hit(pos):
            self.app.pop()
            return
        if self.type.click(pos) or self.gen.click(pos):
            return
        if self.TOP <= pos[1] <= self.BOTTOM:
            for i, e in enumerate(self._filtered()):
                if self._cell(i).collidepoint(pos):
                    self.detail = DexEntry(self.app, e, self.legends.get(e["key"]))
                    AUDIO.cry(e["id"], 0.8)
                    return

    def draw(self, surf):
        t = self.app.t
        ui.menu_background(surf, t)
        rows = self._filtered()
        clip = surf.get_clip()
        surf.set_clip(pygame.Rect(0, self.TOP - 6, W, self.BOTTOM - self.TOP + 6))
        first = max(0, int(self.scroll // self.CH) * self.COLS)
        last = min(len(rows), first + ((self.BOTTOM - self.TOP) // self.CH + 2) * self.COLS)
        for i in range(first, last):
            e = rows[i]
            r = self._cell(i)
            ui.panel(surf, r, ui.SCREEN2, 10)
            img = fit(e["id"], r.w - 14, 92)
            surf.blit(img, img.get_rect(midbottom=(r.centerx, r.y + 108)))
            gfx.text(surf, short_name(e)[:11], (r.centerx, r.bottom - 22), 14, ui.TEXT, None, 0)
            gfx.text(surf, f"{e['id']}", (r.x + 8, r.y + 12), 11, (110, 120, 140), None, 0, anchor="midleft",
                     chunky=False)
            for k, typ in enumerate(e["types"]):
                pygame.draw.circle(surf, gfx.type_color(typ, 0), (r.right - 12 - k * 13, r.y + 12), 5)
        surf.set_clip(clip)
        if not rows:
            gfx.text(surf, "No Pokemon match", (W / 2, 520), 22, ui.MUTED, None, 0)
        ui.header(surf, "Pokedex", f"{len(self.all)} Pokemon  -  showing {len(rows)}")
        self.search.draw(surf)
        self.type.draw(surf)
        self.gen.draw(surf)
        self.back.draw(surf)
        total = (len(rows) + self.COLS - 1) // self.COLS * self.CH
        view = self.BOTTOM - self.TOP
        if total > view:
            hgt = max(40, view * view / total)
            y = self.TOP + (view - hgt) * self.scroll / max(1, total - view)
            pygame.draw.rect(surf, ui.LCD_LINE, (W - 22, y, 6, hgt), border_radius=3)
        if self.detail is not None:
            self.detail.draw(surf, t)


class DexEntry:
    """The page for one Pokemon (drawn over the browser)."""

    def __init__(self, app, entry, caught=None):
        self.app = app
        self.base = entry
        self.forms = [entry] + [app.dex.all[i] for i in entry.get("megas", []) if i in app.dex.all]
        if entry.get("gmax") and entry["gmax"] in app.dex.all:
            self.forms.append(app.dex.all[entry["gmax"]])
        # regional / alternate forms of the same species
        self.forms += [e for e in app.dex.selectable() if e["species"] == entry["species"] and e is not entry and
                       not e["default"]][:4]
        self.i = 0
        self.shiny = False
        self.caught = caught
        self.t0 = app.t
        self.closed = False
        self.card = pygame.Rect(30, 120, 660, 1060)
        self.form_btns = []

    @property
    def e(self):
        return self.forms[self.i]

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self.closed = True
            elif ev.key in (pygame.K_RIGHT, pygame.K_LEFT) and len(self.forms) > 1:
                self.i = (self.i + (1 if ev.key == pygame.K_RIGHT else -1)) % len(self.forms)
            elif ev.key == pygame.K_s:
                self.shiny = not self.shiny
            return
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        if not self.card.collidepoint(pos):
            self.closed = True
            return
        for rect, i in self.form_btns:
            if rect.collidepoint(pos):
                self.i = i
                AUDIO.play("select")
                return
        if pygame.Rect(self.card.x, self.card.y, self.card.w, 330).collidepoint(pos):
            self.shiny = not self.shiny
            AUDIO.play("tera" if self.shiny else "select", 0.6)
            return
        if pygame.Rect(self.card.centerx - 100, self.card.bottom - 70, 200, 60).collidepoint(pos):
            self.closed = True

    def draw(self, surf, t):
        e = self.e
        q = t - self.t0
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 190))
        surf.blit(shade, (0, 0))
        r = self.card.move(0, int((1 - min(1.0, q / 0.2)) * 60))
        col = gfx.type_color(e["types"][0], 0)
        ui.panel(surf, r, ui.SCREEN2, 22, border=col)
        # top: the sprite on a type-colored stage
        stage = pygame.Rect(r.x + 16, r.y + 16, r.w - 32, 300)
        pygame.draw.rect(surf, tuple(int(c * 0.35) for c in col), stage, border_radius=16)
        surf.set_clip(stage.inflate(-12, -12))
        for i in range(8):
            a = i / 8 * math.tau + q * 0.3
            pygame.draw.line(surf, tuple(int(c * 0.45) for c in col), stage.center,
                             (stage.centerx + math.cos(a) * 400, stage.centery + math.sin(a) * 400), 18)
        surf.set_clip(None)
        img = fit(e["id"], stage.w - 40, 260, self.shiny)
        surf.blit(img, img.get_rect(midbottom=(stage.centerx, stage.bottom - 14 + math.sin(q * 2) * 4)))
        if self.shiny:
            gfx.sparkles(surf, stage.center, 140, q, e["id"], 12)
            gfx.pill(surf, "SHINY", (stage.right - 50, stage.y + 22), (200, 150, 30), 15)
        else:
            gfx.text(surf, "tap for shiny", (stage.right - 14, stage.y + 22), 13, (220, 220, 230), None, 0,
                     anchor="midright", chunky=False)
        if self.caught:
            gfx.pill(surf, "IN YOUR COLLECTION", (stage.x + 100, stage.y + 22), (130, 60, 200), 13)
        y = r.y + 350
        gfx.text(surf, e["name"], (r.centerx, y), 38 if len(e["name"]) < 16 else 28, ui.TEXT, ui.SHELL_DARK, 3)
        tag = "Mythical" if e["mythical"] else "Legendary" if e["legendary"] else f"Gen {e['gen']}"
        gfx.text(surf, f"#{e['species']:04d}  -  {tag}", (r.centerx, y + 40), 16, ui.MUTED, None, 0, chunky=False)
        type_row(surf, e["types"], r.centerx, y + 74, 16)
        # forms
        self.form_btns = []
        if len(self.forms) > 1:
            fx = r.centerx - (len(self.forms) * 110 - 10) / 2
            for i, f in enumerate(self.forms):
                br = pygame.Rect(fx + i * 110, y + 100, 100, 70)
                pygame.draw.rect(surf, (32, 62, 92) if i == self.i else ui.SCREEN, br, border_radius=10)
                if i == self.i:
                    pygame.draw.rect(surf, ui.LENS, br, 2, border_radius=10)
                im = fit(f["id"], 60, 46)
                surf.blit(im, im.get_rect(center=(br.centerx, br.y + 28)))
                parts = f["key"].split("-")
                label = "Base" if i == 0 else "G-Max" if "gmax" in parts else \
                    ("Mega " + " ".join(parts[parts.index("mega") + 1:]).upper()).strip() if "mega" in parts \
                    else f["name"].split()[-1][:7]
                gfx.text(surf, label, (br.centerx, br.bottom - 12), 12, ui.TEXT, None, 0, chunky=False)
                self.form_btns.append((br, i))
            y += 84
        # base stats
        y += 120
        for i, (key, label) in enumerate(STAT_NAMES):
            yy = y + i * 34
            v = e["stats"][key]
            gfx.text(surf, label, (r.x + 40, yy), 16, ui.MUTED, None, 0, anchor="midleft", chunky=False)
            gfx.text(surf, str(v), (r.x + 190, yy), 16, ui.TEXT, None, 0, anchor="midright")
            pygame.draw.rect(surf, (14, 18, 26), (r.x + 206, yy - 8, 300, 16), border_radius=8)
            w = int(300 * min(1.0, v / 200) * min(1.0, q / 0.5))
            pygame.draw.rect(surf, gfx.hsv(min(v, 180) / 180 * 0.35), (r.x + 206, yy - 8, max(16, w), 16),
                             border_radius=8)
        gfx.text(surf, f"Total {sum(e['stats'].values())}", (r.right - 40, y + 2 * 34), 18, ui.SIGNAL, None, 0,
                 anchor="midright")
        # abilities
        y += 6 * 34 + 16
        for k, (ab, hidden) in enumerate(e["abilities"][:3]):
            yy = y + k * 26
            gfx.text(surf, ability_name(ab) + ("  (hidden)" if hidden else ""), (r.x + 40, yy), 16,
                     (255, 225, 150) if hidden else ui.TEXT, None, 0, anchor="midleft")
            desc = DESCRIPTIONS.get(ab)
            if desc:
                gfx.text(surf, desc[:44], (r.right - 40, yy), 13, ui.MUTED, None, 0, anchor="midright", chunky=False)
        # weaknesses / resistances
        y += min(3, len(e["abilities"])) * 26 + 20
        groups = {}
        for typ in TYPES:
            m = effectiveness(typ, e["types"])
            if m != 1:
                groups.setdefault(m, []).append(typ)
        lines = [(4.0, "4x weak"), (2.0, "Weak to"), (0.5, "Resists"), (0.25, "4x resist"), (0.0, "Immune")]
        for m, label in lines:
            if m not in groups or y > r.bottom - 100:
                continue
            gfx.text(surf, label, (r.x + 40, y), 15, (240, 140, 140) if m > 1 else (150, 220, 160), None, 0,
                     anchor="midleft", chunky=False)
            x = r.x + 150
            for typ in groups[m]:
                wpx = gfx.font(12, False).size(typ.upper())[0] + 14
                if x + wpx > r.right - 30:
                    break
                gfx.pill(surf, typ.upper(), (x + wpx / 2, y), gfx.type_color(typ, 0), 12)
                x += wpx + 4
            y += 30
        gfx.text(surf, "close", (r.centerx, r.bottom - 40), 16, ui.MUTED, None, 0, chunky=False)
