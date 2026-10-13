"""Team builder: saved teams, species/move pickers, items, natures, EV builds, Showdown import/export."""
import random

import pygame

from . import clip, gfx, ui
from .app import Scene
from .gfx import SPRITES, W
from . import abilities as AB
from .team import (BUILDS, ITEMS, NATURES, STAT_NAMES, Member, auto_member, auto_moves, best_ability, calc_stats,
                   delete_team, export_showdown, import_showdown, load_saved, mega_item_name, random_team,
                   save_team, validate)
from .types import TYPES

ITEM_KEYS = [k for k in ITEMS if k != "mega-stone"]


def team_strip(surf, members, x, y, size=44):
    for i, m in enumerate(members):
        img = SPRITES.get(m.species, size)
        surf.blit(img, img.get_rect(midbottom=(x + i * (size + 8) + size // 2, y)))


class TeamList(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.list = ui.ListView((40, 160, 640, 640), 76)
        self.msg = ""
        self.buttons = [
            ui.Button((40, 830, 200, 80), "New", (34, 140, 88), 28, tag="new"),
            ui.Button((260, 830, 200, 80), "Random", ui.PANEL2, 28, tag="random"),
            ui.Button((480, 830, 200, 80), "Import", ui.PANEL2, 28, "from clipboard", tag="import"),
            ui.Button((40, 930, 200, 80), "Edit", (38, 104, 188), 28, tag="edit"),
            ui.Button((260, 930, 200, 80), "Export", ui.PANEL2, 28, "copy Showdown", tag="export"),
            ui.Button((480, 930, 200, 80), "Delete", ui.SHELL_DARK, 28, tag="delete"),
            ui.Button((40, 1160, 200, 70), "Back", ui.PANEL2, 24, tag="back"),
        ]
        self.refresh()

    def refresh(self):
        self.teams = load_saved()
        rows = []
        for name in sorted(self.teams):
            members = self.teams[name]

            def draw(surf, r, sel, name=name, members=members):
                gfx.text(surf, name, (r.x + 14, r.y + 18), 20, anchor="midleft", ow=1)
                team_strip(surf, members, r.x + 230, r.bottom - 6, 50)
            rows.append((name, draw))
        self.list.set_rows(rows)
        if self.list.selected not in self.teams:
            self.list.selected = None

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        self.list.handle(ev, pos)
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for b in self.buttons:
                if b.hit(pos):
                    self.action(b.tag)

    def _fresh_name(self, base):
        n = 1
        while f"{base} {n}" in self.teams:
            n += 1
        return f"{base} {n}"

    def action(self, tag):
        dex = self.app.dex
        sel = self.list.selected
        if tag == "back":
            self.app.pop()
        elif tag == "new":
            self.app.push(TeamEdit(self.app, self._fresh_name("Team"), [], self.refresh))
        elif tag == "random":
            self.app.push(TeamEdit(self.app, self._fresh_name("Random"), random_team(dex), self.refresh))
        elif tag == "import":
            members, warns = import_showdown(dex, clip.paste())
            if not members:
                self.msg = "Clipboard has no Showdown team. Copy one (Showdown > Export) first."
            else:
                self.msg = f"Imported {len(members)} Pokemon" + (f" ({len(warns)} warnings)" if warns else "")
                self.app.push(TeamEdit(self.app, self._fresh_name("Imported"), members, self.refresh, warns))
        elif tag == "edit" and sel:
            self.app.push(TeamEdit(self.app, sel, [Member.from_dict(m.to_dict()) for m in self.teams[sel]],
                                   self.refresh))
        elif tag == "export" and sel:
            ok = clip.copy(export_showdown(dex, self.teams[sel]))
            self.msg = "Copied! Paste it to your friends or into Showdown." if ok else "Couldn't access clipboard"
        elif tag == "delete" and sel:
            delete_team(sel)
            self.msg = f"Deleted {sel}"
            self.refresh()

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "Teams", "Build teams for PvP and practice")
        self.list.draw(surf)
        if not self.teams:
            gfx.text(surf, "No teams yet - make one!", (W / 2, 450), 24, ui.MUTED)
        for b in self.buttons:
            b.draw(surf)
        if self.msg:
            gfx.text(surf, self.msg, (W / 2, 1050), 19, (255, 240, 150), ow=1, chunky=False)


class TeamEdit(Scene):
    def __init__(self, app, name, members, on_save=None, warnings=None):
        super().__init__(app)
        self.dex = app.dex
        self.members = list(members)
        self.on_save = on_save
        self.orig_name = name
        self.name = ui.TextInput((40, 140, 640, 54), "Team name", name)
        self.sel = 0
        self.msg = "; ".join(warnings[:2]) if warnings else ""
        self.buttons = []
        self.rebuild()

    # ------------------------------------------------------------------ widgets
    def rebuild(self):
        self.slot_rects = [pygame.Rect(40 + (i % 3) * 218, 220 + (i // 3) * 130, 204, 120) for i in range(6)]
        self.cycles = {}
        self.move_btns = []
        m = self.members[self.sel] if self.sel < len(self.members) else None
        y = 500
        self.species_btn = ui.Button((40, y, 640, 64), self.dex.all[m.species]["name"] if m else "+ ADD POKEMON",
                                     (70, 120, 220), 26, "tap to change" if m else None)
        if m:
            e = self.dex.all[m.species]
            items = ITEM_KEYS + (["mega-stone"] if e["megas"] else [])
            item = ui.Cycle((40, y + 84, 640, 56), "Item", items,
                            fmt=lambda k: mega_item_name(self.dex, self.dex.all[m.mega]) if k == "mega-stone" and m.mega
                            else ITEMS[k][0])
            item.set(m.item)
            self.cycles["item"] = item
            if m.item == "mega-stone" and len(e["megas"]) > 1:
                mc = ui.Cycle((40, y + 150, 640, 56), "Mega form", e["megas"],
                              fmt=lambda i: self.dex.all[i]["name"])
                mc.set(m.mega)
                self.cycles["mega"] = mc
            off = 66 if "mega" in self.cycles else 0
            abil = [a for a, _ in e["abilities"]] or [None]
            ac = ui.Cycle((40, y + 150 + off, 315, 56), "Ability", abil,
                          fmt=lambda a: AB.ability_name(a) + ("" if a in AB.DESCRIPTIONS or a is None else " *"))
            ac.set(m.ability or best_ability(e))
            self.cycles["ability"] = ac
            tc = ui.Cycle((365, y + 150 + off, 315, 56), "Tera", TYPES, fmt=str.title)
            tc.set(m.tera or e["types"][0])
            self.cycles["tera"] = tc
            nat = ui.Cycle((40, y + 216 + off, 315, 56), "Nature", list(NATURES), fmt=self._nature_fmt)
            nat.set(m.nature)
            self.cycles["nature"] = nat
            builds = list(BUILDS) + (["Custom"] if self._build_of(m) == "Custom" else [])
            bc = ui.Cycle((365, y + 216 + off, 315, 56), "EVs", builds)
            bc.set(self._build_of(m))
            self.cycles["build"] = bc
            my = y + 290 + off
            for i in range(4):
                mv = self.dex.moves.get(m.moves[i]) if i < len(m.moves) else None
                label = mv["name"] if mv else "+ move"
                col = gfx.type_color(mv["type"], 2) if mv else ui.PANEL2
                sub = f"{mv['type'].upper()}  {mv['power'] or '-'} pow  {mv['cls']}" if mv else None
                self.move_btns.append(ui.Button((40 + (i % 2) * 325, my + (i // 2) * 76, 315, 68), label, col, 22,
                                                sub, tag=i))
        self.side_btns = [
            ui.Button((40, 1060, 150, 60), "Auto moves", ui.PANEL2, 18, tag="auto"),
            ui.Button((205, 1060, 150, 60), "Remove", ui.SHELL_DARK, 20, tag="remove"),
            ui.Button((370, 1060, 150, 60), "Randomize", ui.PANEL2, 18, tag="reroll"),
        ]
        self.save_btn = ui.Button((480, 1160, 200, 70), "Save", (34, 140, 88), 26, tag="save")
        self.back_btn = ui.Button((40, 1160, 200, 70), "Back", ui.PANEL2, 24, tag="back")
        self.buttons = [self.species_btn, self.save_btn, self.back_btn] + self.move_btns + \
            (self.side_btns if m else [])

    def _nature_fmt(self, n):
        up, down = NATURES[n]
        return f"{n} +{STAT_NAMES[up]}" if up else f"{n}"

    def _build_of(self, m):
        for name, (evs, nat) in BUILDS.items():
            if {k: v for k, v in evs.items() if v} == {k: v for k, v in m.evs.items() if v}:
                return name
        return "Custom"

    # ------------------------------------------------------------------ input
    def handle(self, ev, pos):
        if self.name.handle(ev, pos):
            return
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        for i, r in enumerate(self.slot_rects):
            if r.collidepoint(pos):
                self.sel = min(i, len(self.members))
                self.rebuild()
                return
        m = self.members[self.sel] if self.sel < len(self.members) else None
        if self.species_btn.hit(pos):
            self.app.push(SpeciesPicker(self.app, self._set_species))
            return
        for key, c in self.cycles.items():
            if c.click(pos) and m:
                if key == "item":
                    m.item = c.value
                    if c.value == "mega-stone":
                        m.mega = m.mega if m.mega in self.dex.all[m.species]["megas"] else \
                            self.dex.all[m.species]["megas"][0]
                elif key == "mega":
                    m.mega = c.value
                elif key == "nature":
                    m.nature = c.value
                elif key == "ability":
                    m.ability = c.value
                elif key == "tera":
                    m.tera = c.value
                elif key == "build" and c.value in BUILDS:
                    m.evs = dict(BUILDS[c.value][0])
                self.rebuild()
                return
        for b in self.move_btns:
            if b.hit(pos) and m:
                self.app.push(MovePicker(self.app, self.dex.all[m.species], lambda mid, i=b.tag: self._set_move(i, mid)))
                return
        for b in (self.side_btns if m else []):
            if b.hit(pos):
                rng = random.Random()
                e = self.dex.all[m.species]
                if b.tag == "auto":
                    m.moves = auto_moves(self.dex, e, rng)
                elif b.tag == "remove":
                    self.members.pop(self.sel)
                    self.sel = min(self.sel, len(self.members))
                elif b.tag == "reroll":
                    used = {x.item for x in self.members if x is not m}
                    pool = [k for k in ITEM_KEYS if k not in used and k != "none"]
                    self.members[self.sel] = auto_member(self.dex, e, rng, pool,
                                                         allow_mega=not any(x.item == "mega-stone" for x in
                                                                            self.members if x is not m))
                self.rebuild()
                return
        if self.save_btn.hit(pos):
            self.save()
        elif self.back_btn.hit(pos):
            self.app.pop()

    def _set_species(self, entry):
        rng = random.Random()
        used = {x.item for i, x in enumerate(self.members) if i != self.sel}
        pool = [k for k in ITEM_KEYS if k not in used and k != "none"]
        allow_mega = not any(x.item == "mega-stone" for i, x in enumerate(self.members) if i != self.sel)
        m = auto_member(self.dex, entry, rng, pool, allow_mega=allow_mega)
        if self.sel < len(self.members):
            self.members[self.sel] = m
        else:
            self.members.append(m)
        self.rebuild()

    def _set_move(self, i, mid):
        m = self.members[self.sel]
        if mid in m.moves:
            m.moves.remove(mid)
        while len(m.moves) <= i:
            m.moves.append(mid)
        m.moves[i] = mid
        m.moves = m.moves[:4]
        self.rebuild()

    def save(self):
        errs = validate(self.dex, self.members)
        if errs:
            self.msg = errs[0]
            return
        name = self.name.value.strip() or self.orig_name
        if name != self.orig_name:
            delete_team(self.orig_name)
        save_team(name, self.members)
        if self.on_save:
            self.on_save()
        self.app.pop()

    # ------------------------------------------------------------------ draw
    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "Edit team")
        self.name.draw(surf)
        for i, r in enumerate(self.slot_rects):
            sel = i == self.sel
            ui.panel(surf, r, (70, 64, 96) if sel else (34, 32, 46), 12,
                     border=(255, 230, 120) if sel else gfx.INK)
            if i < len(self.members):
                m = self.members[i]
                e = self.dex.all[m.species]
                img = SPRITES.get(m.species, 74)
                surf.blit(img, img.get_rect(midbottom=(r.centerx, r.y + 84)))
                gfx.text(surf, e["name"][:16], (r.centerx, r.y + 98), 16, ow=1, chunky=False)
                if m.item != "none":
                    gfx.text(surf, m.item_name(self.dex)[:18], (r.centerx, r.y + 112), 12, ui.MUTED, ow=1,
                             chunky=False)
            elif i == len(self.members):
                gfx.text(surf, "+", (r.centerx, r.centery), 48, ui.MUTED)
        for b in self.buttons:
            b.draw(surf)
        for c in self.cycles.values():
            c.draw(surf)
        if self.sel < len(self.members):
            m = self.members[self.sel]
            e = self.dex.all[m.species]
            st = calc_stats(e, m)
            line = "  ".join(f"{STAT_NAMES[k]} {v}" for k, v in st.items())
            types = " / ".join(t.upper() for t in e["types"])
            gfx.text(surf, f"{types}   Lv{m.level}   {line}", (W / 2, 1140 - 10), 15, (200, 200, 215), ow=1,
                     chunky=False)
            ab_key = m.ability or best_ability(e)
            desc = AB.DESCRIPTIONS.get(ab_key, "No battle effect in this game yet")
            gfx.text(surf, f"{AB.ability_name(ab_key)}: {desc}", (W / 2, 1040), 15, (255, 230, 150), ow=1,
                     chunky=False)
        errs = validate(self.dex, self.members) if self.members else ["Add at least one Pokemon"]
        msg = self.msg or (errs[0] if errs else "Team is legal - ready for battle!")
        gfx.text(surf, msg, (W / 2, 1258), 16, (255, 140, 140) if (errs or self.msg) else (140, 240, 150), ow=1,
                 chunky=False)


class SpeciesPicker(Scene):
    def __init__(self, app, on_pick):
        super().__init__(app)
        self.on_pick = on_pick
        self.search = ui.TextInput((40, 140, 640, 56), "Search name or type", "", "e.g. garchomp, fire, gen 4")
        self.search.focus = True
        self.list = ui.ListView((40, 220, 640, 920), 70)
        self.all = sorted(app.dex.selectable(), key=lambda e: e["id"])
        self.last_q = None
        self.buttons = [ui.Button((40, 1160, 200, 70), "Back", ui.PANEL2, 24)]
        self.filter()

    def filter(self):
        q = self.search.value.strip().lower()
        self.last_q = q
        out = []
        for e in self.all:
            if q:
                hay = f"{e['name'].lower()} {' '.join(e['types'])} gen {e['gen']} #{e['id']}" + \
                      (" legendary" if e["legendary"] or e["mythical"] else "") + (" mega" if e["megas"] else "")
                if not all(part in hay for part in q.split()):
                    continue
            out.append(e)

        def row(e):
            def draw(surf, r, sel):
                img = SPRITES.get(e["id"], 58)
                surf.blit(img, img.get_rect(center=(r.x + 40, r.centery)))
                gfx.text(surf, e["name"], (r.x + 84, r.y + 20), 20, anchor="midleft", ow=1)
                x = r.x + 84
                for t in e["types"]:
                    pr = gfx.pill(surf, t.upper(), (x + 34, r.y + 48), gfx.type_color(t), 11)
                    x = pr.right + 4
                bst = sum(e["stats"].values())
                extra = ("  MEGA" if e["megas"] else "") + ("  LEGEND" if e["legendary"] or e["mythical"] else "")
                gfx.text(surf, f"BST {bst}  Gen {e['gen']}{extra}", (r.right - 12, r.centery), 15, ui.MUTED,
                         anchor="midright", ow=1, chunky=False)
            return draw
        self.list.set_rows([(e["id"], row(e)) for e in out])
        self.list.scroll = 0

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
            return
        if self.search.handle(ev, pos) and ev.type != pygame.MOUSEBUTTONDOWN:
            return
        picked = self.list.handle(ev, pos)
        if picked:
            self.app.pop()
            self.on_pick(self.app.dex.all[picked])
            return
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.buttons[0].hit(pos):
            self.app.pop()

    def update(self, dt):
        if self.search.value.strip().lower() != self.last_q:
            self.filter()

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        ui.header(surf, "Pick a Pokemon")
        self.search.draw(surf)
        self.list.draw(surf)
        gfx.text(surf, f"{len(self.list.rows)} results", (W - 40, 1195), 16, ui.MUTED, anchor="midright", ow=1,
                 chunky=False)
        for b in self.buttons:
            b.draw(surf)


class MovePicker(Scene):
    def __init__(self, app, entry, on_pick):
        super().__init__(app)
        self.on_pick = on_pick
        self.entry = entry
        self.moves = sorted(app.dex.learnset(entry), key=lambda m: (-(m["power"] or 0), m["name"]))
        self.search = ui.TextInput((40, 140, 640, 56), "Search moves", "", "name, type, physical, status...")
        self.search.focus = True
        self.list = ui.ListView((40, 220, 640, 920), 58)
        self.last_q = None
        self.buttons = [ui.Button((40, 1160, 200, 70), "Back", ui.PANEL2, 24)]
        self.filter()

    def filter(self):
        q = self.search.value.strip().lower()
        self.last_q = q
        cls_word = {"phys": "physical", "spec": "special", "status": "status"}

        def row(m):
            def draw(surf, r, sel):
                gfx.text(surf, m["name"], (r.x + 14, r.centery), 20, anchor="midleft", ow=1)
                gfx.pill(surf, m["type"].upper(), (r.x + 300, r.centery), gfx.type_color(m["type"]), 12)
                acc = "-" if m["acc"] > 100 else m["acc"]
                info = f"{cls_word[m['cls']][:4].upper()}  {m['power'] or '-'} pow  {acc} acc" + \
                       (f"  +{m['pri']}" if m["pri"] > 0 else "")
                gfx.text(surf, info, (r.right - 12, r.centery), 15, ui.MUTED, anchor="midright", ow=1, chunky=False)
            return draw
        rows = []
        for m in self.moves:
            hay = f"{m['name'].lower()} {m['type']} {cls_word[m['cls']]}"
            if q and not all(p in hay for p in q.split()):
                continue
            rows.append((m["id"], row(m)))
        self.list.set_rows(rows)
        self.list.scroll = 0

    def handle(self, ev, pos):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            self.app.pop()
            return
        if self.search.handle(ev, pos) and ev.type != pygame.MOUSEBUTTONDOWN:
            return
        picked = self.list.handle(ev, pos)
        if picked:
            self.app.pop()
            self.on_pick(picked)
            return
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.buttons[0].hit(pos):
            self.app.pop()

    def update(self, dt):
        if self.search.value.strip().lower() != self.last_q:
            self.filter()

    def draw(self, surf):
        ui.menu_background(surf, self.app.t)
        gfx.title_text(surf, f"{self.entry['name'].upper()} MOVES", (W / 2, 70), 40)
        self.search.draw(surf)
        self.list.draw(surf)
        for b in self.buttons:
            b.draw(surf)
