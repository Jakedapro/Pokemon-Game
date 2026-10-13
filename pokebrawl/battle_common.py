"""Things both battle screens share: ping, emotes, rematch, saving replays and your record."""
import math
import time

import pygame

from . import gfx, profile, replays, ui
from .gfx import W
from .session import EMOTES

EMOTE_KEYS = [pygame.K_F1, pygame.K_F2, pygame.K_F3, pygame.K_F4, pygame.K_F5, pygame.K_F6]


class BattleExtras:
    def __init__(self, app, session, emote_y):
        self.app = app
        self.s = session
        self.done = False
        self.saved_path = None
        self.result_text = ""
        self.outcome = None      # rank points / rank change / legendary encounter (profile.record)
        self.outcome_t = 0.0
        self.caught = False
        self.emote_btns = []
        if session.online:
            w = (W - 40 - 8 * (len(EMOTES) - 1)) // len(EMOTES)
            self.emote_btns = [ui.Button((20 + i * (w + 8), emote_y, w, 34), e, (60, 56, 84), 15, tag=e)
                               for i, e in enumerate(EMOTES)]

    @property
    def me(self):
        return self.s.me_index

    # ------------------------------------------------------------------ end of battle
    def finish(self, winner):
        """Call every frame once the battle is over: records the result and saves the replay (once)."""
        if getattr(self.s, "adventure", False):   # Adventure battles don't count for ranks or replays
            self.done = True
            return
        if not self.done:
            self.done = True
            won = winner == self.me
            dex = getattr(self.app, "dex", None)
            if self.s.online:
                opp = self.s.names[1 - self.me]
                out = profile.record("vs", opp, won, dex)
                self.result_text = f"You vs {opp}: {out['row'][0]}-{out['row'][1]}"
            else:
                diff = getattr(getattr(self.s, "bot", None), "level", "bot")
                out = profile.record("bots", diff, won, dex)
                self.result_text = f"vs {diff.upper()} bots: {out['row'][0]}-{out['row'][1]}"
            self.outcome = out
            self.outcome_t = time.time()
        if self.saved_path is None:
            r = self.s.replay()
            if r:
                self.saved_path = replays.save(r) or ""

    def end_buttons(self, y):
        btns = []
        if self.outcome and self.outcome["encounter"] and not self.caught:
            btns.append(ui.Button((110, y - 118, 500, 96), "A legendary appeared!", (130, 60, 200), 32,
                                  "tap to catch it", tag="catch"))
        if self.s.online:
            label = "REMATCH?"
            if self.s.rematch_me:
                label = "WAITING..."
            elif self.s.rematch_them:
                label = "Accept rematch"
            btns.append(ui.Button((160, y, 400, 90), label, ui.SHELL, 30, tag="rematch"))
        else:
            btns.append(ui.Button((160, y, 400, 90), "Rematch", ui.SHELL, 30, tag="rematch"))
        btns.append(ui.Button((160, y + 110, 400, 90), "Main menu", ui.PANEL2, 30, tag="menu"))
        return btns

    def check_rematch(self):
        """Online: once both players asked, swap to the new battle."""
        nxt = getattr(self.s, "next_session", None)
        if nxt is not None:
            from .pvp_ui import start_battle
            start_battle(self.app, nxt, getattr(self.s, "teams", [None])[0] if hasattr(self.s, "teams") else None,
                         replace=True)
            return True
        return False

    # ------------------------------------------------------------------ emotes / ping
    def handle(self, ev, pos):
        if not self.s.online:
            return False
        if ev.type == pygame.KEYDOWN and ev.key in EMOTE_KEYS:
            self.s.emote(EMOTES[EMOTE_KEYS.index(ev.key)])
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and pos:
            for b in self.emote_btns:
                if b.hit(pos):
                    self.s.emote(b.tag)
                    return True
        return False

    def draw(self, surf, bubble_pos):
        """bubble_pos(index) -> (x, y) where that player's emotes pop up."""
        if not self.s.online:
            return
        for b in self.emote_btns:
            b.draw(surf)
        ping = self.s.ping_ms
        col = (120, 230, 120) if ping is not None and ping < 120 else (240, 200, 80) if ping is not None and \
            ping < 250 else (240, 100, 90)
        gfx.text(surf, f"ping {ping} ms" if ping is not None else "ping ...", (W - 12, 90), 15, col,
                 anchor="midright", ow=1, chunky=False)
        now = time.time()
        for who, text, t in self.s.emotes[-6:]:
            age = now - t
            if age < 2.6:
                x, y = bubble_pos(who)
                ui.panel(surf, pygame.Rect(0, 0, 130, 46).move(x - 65, y - 23 - age * 12), (255, 255, 255), 14)
                gfx.text(surf, text, (x, y - age * 12), 22, gfx.INK, None)


def draw_rank_change(surf, outcome, center, t):
    """Under VICTORY / DEFEAT: the rank badge, +RP counting up and RANK UP! when it happens."""
    if not outcome:
        return
    x, y = center
    k = min(1.0, max(0.0, (time.time() - t) / 1.0))
    rk = outcome["rank"]
    ui.rank_badge(surf, (x - 150, y), 34, rk, time.time())
    d = outcome["delta"]
    shown = int(round(d * k))
    gfx.text(surf, rk["label"], (x - 100, y - 14), 24, rk["color"], gfx.INK, 2, anchor="midleft")
    gfx.text(surf, f"{'+' if d >= 0 else ''}{shown} RP   ({outcome['rp']} total)", (x - 100, y + 16), 18,
             (150, 240, 150) if d > 0 else (240, 150, 150) if d < 0 else ui.MUTED, gfx.INK, 1, anchor="midleft")
    if outcome["streak"] >= 3:
        gfx.pill(surf, f"{outcome['streak']} WIN STREAK", (x, y + 52), (200, 110, 30), 14)
    if outcome["rank_up"] and k >= 1:
        pulse = 1 + 0.06 * math.sin(time.time() * 6)
        gfx.title_text(surf, "RANK UP!", (x + 210, y), 34, scale=pulse, color=rk["color"])
    elif outcome["rank_down"] and k >= 1:
        gfx.text(surf, "Rank down", (x + 210, y), 20, (240, 150, 150), gfx.INK, 2)
