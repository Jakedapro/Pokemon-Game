"""Your trainer profile: record vs each friend and bot difficulty, ranked points, streaks and the legendary
collection (legendaries you meet after wins and catch)."""
import json
import os
import random
import time

from .pokedex import HOME

PROFILE_FILE = os.path.join(HOME, "profile.json")

# ranks: (name, rank points needed, color). Every rank but Champion has divisions III, II, I.
RANKS = [("Poke Ball", 0, (225, 60, 60)), ("Great Ball", 250, (60, 120, 230)),
         ("Ultra Ball", 650, (240, 200, 50)), ("Master Ball", 1200, (170, 80, 220)),
         ("Champion", 2000, (255, 210, 90))]
DIVISIONS = ["III", "II", "I"]
# rank points for a (win, loss) by opponent
RP_TABLE = {"easy": (6, -3), "normal": (14, -7), "hard": (22, -10), "insane": (32, -12), "vs": (30, -18)}
# chance a legendary shows up after a win (a rank-up always brings one)
LEGEND_CHANCE = {"easy": 0.06, "normal": 0.15, "hard": 0.25, "insane": 0.35, "vs": 0.3}
SHINY_ODDS = 64


def load():
    try:
        with open(PROFILE_FILE) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data.setdefault("vs", {})
    data.setdefault("bots", {})
    data.setdefault("rp", 0)
    data.setdefault("streak", 0)
    data.setdefault("best_streak", 0)
    data.setdefault("peak_rp", data["rp"])
    data.setdefault("legends", {})
    return data


def save(data):
    os.makedirs(HOME, exist_ok=True)
    tmp = PROFILE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, PROFILE_FILE)


def rank_of(rp):
    """(index, name, division or '', color, floor rp, next rank's rp or None)."""
    for i in range(len(RANKS) - 1, -1, -1):
        name, need, col = RANKS[i]
        if rp >= need:
            break
    if i == len(RANKS) - 1:
        return {"tier": i, "name": name, "div": "", "color": col, "floor": need, "next": None,
                "label": name}
    top = RANKS[i + 1][1]
    step = (top - need) / 3
    d = min(2, int((rp - need) // step))
    floor = need + d * step
    return {"tier": i, "name": name, "div": DIVISIONS[d], "color": col, "floor": int(floor),
            "next": int(floor + step), "label": f"{name} {DIVISIONS[d]}"}


def legendary_pool(dex):
    return sorted((e for e in dex.all.values() if e["default"] and not e["transform"] and
                   (e["legendary"] or e["mythical"])), key=lambda e: e["id"])


def record(kind, opponent, won, dex=None, rng=None):
    """kind: 'vs' (a friend's name) or 'bots' (a difficulty). Returns what changed:
    {row, rp, delta, old_rank, rank, rank_up, rank_down, streak, encounter: (entry id, shiny) or None}."""
    rng = rng or random.Random()
    data = load()
    row = data[kind].setdefault(opponent, [0, 0])
    row[0 if won else 1] += 1
    key = "vs" if kind == "vs" else opponent
    gain, loss = RP_TABLE.get(key, RP_TABLE["normal"])
    old = data["rp"]
    if won:
        data["streak"] = data["streak"] + 1 if data["streak"] >= 0 else 1
        delta = gain + min(10, 2 * (data["streak"] - 1))   # win streak bonus
    else:
        data["streak"] = data["streak"] - 1 if data["streak"] <= 0 else -1
        delta = loss
    data["rp"] = max(0, old + delta)
    data["best_streak"] = max(data["best_streak"], data["streak"])
    data["peak_rp"] = max(data["peak_rp"], data["rp"])
    r_old, r_new = rank_of(old), rank_of(data["rp"])
    up = r_new["floor"] > r_old["floor"]
    encounter = None
    if won and dex is not None and (up or rng.random() < LEGEND_CHANCE.get(key, 0.15)):
        missing = [e for e in legendary_pool(dex) if e["key"] not in data["legends"]]
        if missing:
            encounter = (rng.choice(missing)["id"], rng.randrange(SHINY_ODDS) == 0)
    save(data)
    return {"row": row, "rp": data["rp"], "delta": data["rp"] - old, "old_rank": r_old, "rank": r_new,
            "rank_up": up, "rank_down": r_new["floor"] < r_old["floor"], "streak": data["streak"],
            "encounter": encounter}


def add_legend(entry, shiny=False):
    data = load()
    data["legends"][entry["key"]] = {"shiny": bool(shiny), "t": int(time.time())}
    save(data)


def summary(kind, opponent):
    w, l_ = load().get(kind, {}).get(opponent, [0, 0])
    return f"{w}-{l_}"
