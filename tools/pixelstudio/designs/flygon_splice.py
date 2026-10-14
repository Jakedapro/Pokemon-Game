"""Mega Flygon preview (the recipe lives in pokebrawl/megas.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))


def build(L):
    from pokebrawl import megas
    return megas.flygon(L)
