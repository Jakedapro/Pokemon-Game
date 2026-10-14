"""Mega Machamp add-on layer: the bigger champion's belt (the chrome body is a recolour in megas.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
from studio import Model  # noqa: E402

OUT = (16, 16, 16)
GOLD = [(131, 115, 41), (172, 156, 65), (205, 197, 98), (246, 238, 156)]
RED = [(140, 0, 0), (189, 0, 0), (255, 74, 57), (255, 150, 120)]


def parts():
    m = Model()
    gold = m.mat("gold", None, colors=GOLD, line=(82, 65, 0), dark_line=OUT, gloss=True)
    gem = m.mat("gem", None, colors=RED, line=(90, 0, 0), dark_line=OUT, gloss=True)
    # champion belt
    m.tube([(25, 41.5, 6, 2.2), (35, 43, 10, 2.3), (45, 41.5, 6, 2.2)], gold, "belt")
    m.ell((35, 42.5, 11.5), (5.6, 4.4, 2.2), gold, "plate")
    m.ell((35, 42.5, 13.4), (2.0, 1.7, 1), gem, "gem")
    return m.render()


def export(dest):
    import pygame
    pygame.image.save(parts(), os.path.join(dest, "machamp_over.png"))


def build(L):
    from pokebrawl import megas
    export(megas.PARTS)
    return megas.machamp(L)
