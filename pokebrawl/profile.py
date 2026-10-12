"""Your record: wins/losses against each friend and each bot difficulty."""
import json
import os

from .pokedex import HOME

PROFILE_FILE = os.path.join(HOME, "profile.json")


def load():
    try:
        with open(PROFILE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"vs": {}, "bots": {}}


def record(kind, opponent, won):
    """kind: 'vs' (a friend's name) or 'bots' (a difficulty)."""
    data = load()
    row = data.setdefault(kind, {}).setdefault(opponent, [0, 0])
    row[0 if won else 1] += 1
    os.makedirs(HOME, exist_ok=True)
    with open(PROFILE_FILE, "w") as f:
        json.dump(data, f, indent=1)
    return row


def summary(kind, opponent):
    w, l_ = load().get(kind, {}).get(opponent, [0, 0])
    return f"{w}-{l_}"
