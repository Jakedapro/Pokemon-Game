"""Mega Arcanine: the drawn add-on layer (dragon horns); the rest of the recipe lives in pokebrawl/megas.py."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
from studio import Model  # noqa: E402

BONE = [(120, 104, 120), (192, 180, 184), (232, 226, 222), (255, 255, 250)]


def parts():
    m = Model()
    bone = m.mat("bone", None, colors=BONE, line=(72, 56, 72), dark_line=(16, 16, 16), gloss=True)
    m.tube([(9, 10, 4, 2.7), (11, 5, 3, 2.1), (15, 1.5, 2, 1.3), (20.5, 0, 1, 0.4)], bone, "h1")
    m.tube([(16, 10, 0, 2.5), (19, 5.5, -1, 1.9), (23, 3, -2, 1.1), (28.5, 2.5, -3, 0.35)], bone, "h2")
    return m.render()


def export(dest):
    import pygame
    pygame.image.save(parts(), os.path.join(dest, "arcanine_over.png"))


def build(L):
    from pokebrawl import megas
    export(megas.PARTS)
    return megas.arcanine(L)
