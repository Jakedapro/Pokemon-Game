"""Mega Snorlax, hybrid: the GBA Snorlax sprite itself, stood up on new legs, fists wrapped, headband on.
New parts are rendered with Snorlax's own palette so they sit in the sprite like they were drawn with it."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
from studio import Model  # noqa: E402

OUT = (16, 16, 8)           # Snorlax's outline
TEAL = [(16, 57, 65), (49, 90, 123), (82, 139, 172), (115, 164, 189)]
CREAM = [(230, 197, 172), (246, 213, 189), (246, 230, 189), (252, 244, 220)]
CLAW = [(112, 112, 112), (200, 200, 200), (248, 248, 248)]
RED = [(120, 24, 40), (184, 40, 48), (232, 72, 64), (248, 136, 112)]
GOLD = [(128, 80, 24), (200, 136, 32), (240, 192, 64), (252, 236, 152)]
SHIFT = -5


def parts(over):
    m = Model()
    teal = m.mat("teal", None, colors=TEAL, line=(16, 48, 56), dark_line=OUT)
    cream = m.mat("cream", None, colors=CREAM, line=(164, 115, 82), dark_line=OUT)
    claw = m.mat("claw", None, colors=CLAW, line=(112, 112, 112), dark_line=OUT)
    red = m.mat("red", None, colors=RED, line=(96, 16, 32), dark_line=OUT)
    if not over:
        # the rest of the belly + legs, behind the original sprite
        m.ell((33, 40 + SHIFT, -4), (24, 17, 12), teal, "body")
        m.ell((30, 41 + SHIFT, 2), (19, 15, 12), cream, "belly")
        m.tube([(20, 47, -2, 7.5), (18, 56, 0, 7)], teal, "legL")
        m.tube([(44, 47, -4, 7.5), (46, 56, -2, 7)], teal, "legR")
        m.ell((17, 60, 2), (8, 3.3, 5), teal, "footL")
        m.ell((47, 60, 0), (8, 3.3, 5), teal, "footR")
        for x in (11.5, 16.5, 21.5):
            m.tube([(x, 59.5, 6, 1.7), (x - 0.4, 62.5, 7, 0.5)], claw, "footL")
        for x in (42.5, 47.5, 52.5):
            m.tube([(x, 59.5, 4, 1.7), (x + 0.4, 62.5, 5, 0.5)], claw, "footR")
    else:
        gold = m.mat("gold", None, colors=GOLD, line=(120, 72, 16), dark_line=OUT, gloss=True)
        gem = m.mat("gem", None, colors=RED, line=(96, 16, 32), dark_line=OUT, gloss=True)
        tape = m.mat("tape", None, colors=CLAW, line=(112, 112, 112), dark_line=OUT)
        # boxing gloves with knuckle spikes
        m.ell((12.5, 19, 14), (7.6, 7.2, 6), red, "gloveL", rot=(0, 0, -15))
        m.ell((49.5, 15.5, 12), (7.6, 7.2, 6), red, "gloveR", rot=(0, 0, 15))
        m.tube([(16.5, 24, 13, 3.3), (18.5, 26.5, 11, 3.2)], tape, "cuffL")
        m.tube([(45, 21, 11, 3.3), (43.5, 23.5, 9, 3.2)], tape, "cuffR")
        for x, y in ((7.5, 14), (11.5, 12), (15.5, 12.5)):
            m.tube([(x, y + 1.5, 17, 1.2), (x - 0.6, y - 2, 18, 0.35)], claw, "gloveL")
        for x, y in ((45.5, 10), (49.5, 8.5), (53.5, 9.5)):
            m.tube([(x, y + 1.5, 15, 1.2), (x + 0.6, y - 2, 16, 0.35)], claw, "gloveR")
        # champion belt
        m.tube([(9, 43, 4, 2.1), (18, 46.5, 11, 2.2), (29, 47.5, 14, 2.2), (40, 46.5, 11, 2.2), (50, 42.5, 4, 2.1)],
               gold, "belt")
        m.ell((29, 47, 15.5), (6.2, 4.4, 2.2), gold, "plate")
        m.ell((29, 47, 17.4), (2.1, 1.8, 1), gem, "gem")
        # fighter's headband with tails
        m.tube([(18, 14 + SHIFT, 3, 1.5), (24, 11 + SHIFT, 9, 1.6), (32, 10.5 + SHIFT, 11, 1.6),
                (40, 11.5 + SHIFT, 9, 1.6), (45, 15 + SHIFT, 3, 1.5)], red, "band")
        m.tube([(45, 14 + SHIFT, 2, 1.5), (50, 11 + SHIFT, -2, 1.4), (55, 12 + SHIFT, -4, 1.0),
                (59, 9 + SHIFT, -5, 0.45)], red, "t1")
        m.tube([(45, 15 + SHIFT, 2, 1.4), (50, 17 + SHIFT, -2, 1.2), (54.5, 19.5 + SHIFT, -4, 0.85),
                (58, 18.5 + SHIFT, -5, 0.4)], red, "t2")
    return m.render()


def export(dest):
    """Save the drawn add-on layers the game uses (art/megaparts)."""
    import pygame
    pygame.image.save(parts(False), os.path.join(dest, "snorlax_under.png"))
    pygame.image.save(parts(True), os.path.join(dest, "snorlax_over.png"))


def build(L):
    from pokebrawl import megas
    export(megas.PARTS)
    return megas.snorlax(L)
