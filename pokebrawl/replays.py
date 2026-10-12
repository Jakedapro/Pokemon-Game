"""Replays: every battle is saved as its seed + teams + inputs (a few KB) and re-simulated to watch it."""
import glob
import json
import os
import time

from .pokedex import HOME

REPLAY_DIR = os.path.join(HOME, "replays")
KEEP = 200


def save(replay):
    if not replay:
        return None
    os.makedirs(REPLAY_DIR, exist_ok=True)
    names = "_vs_".join("".join(c for c in n if c.isalnum())[:12] for n in replay.get("names", ["P1", "P2"]))
    path = os.path.join(REPLAY_DIR, f"{time.strftime('%Y%m%d_%H%M%S')}_{replay['style']}_{names}.json")
    with open(path, "w") as f:
        json.dump(replay, f, separators=(",", ":"))
    for old in sorted(glob.glob(os.path.join(REPLAY_DIR, "*.json")))[:-KEEP]:
        os.remove(old)
    return path


def list_replays():
    out = []
    for path in sorted(glob.glob(os.path.join(REPLAY_DIR, "*.json")), reverse=True):
        try:
            with open(path) as f:
                r = json.load(f)
            out.append((path, r))
        except (OSError, ValueError):
            pass
    return out


def load(path):
    with open(path) as f:
        return json.load(f)
