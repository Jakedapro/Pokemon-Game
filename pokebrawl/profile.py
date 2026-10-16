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
        with open(PROFILE_FILE, encoding="utf-8") as f:
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
    with open(tmp, "w", encoding="utf-8") as f:
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


# ====================================================================== ranked 1v1 (skill rating)
# A true skill rating for online 1v1s: Elo, starting at 1000. The first PLACEMENTS games move it fast; after that
# it settles. It maps onto the same ball tiers as the rank points, so a trainer's ball shows how good they are.
MMR_START = 1000
PLACEMENTS = 5
MMR_TIERS = [("Poke Ball", 0), ("Great Ball", 1100), ("Ultra Ball", 1250), ("Master Ball", 1400), ("Champion", 1600)]
UNRANKED_COLOR = (150, 150, 165)


def player_id(data=None):
    """A random id for this player (so the global ladder knows it's you), made once."""
    data = data if data is not None else load()
    if not data.get("pid"):
        data["pid"] = "%012x" % random.getrandbits(48)
        save(data)
    return data["pid"]


def mmr_rank(mmr, games):
    """A ranked tier for a skill rating: {tier, name, div, color, label, mmr, games}."""
    if games < PLACEMENTS:
        return {"tier": 0, "name": "Unranked", "div": "", "color": UNRANKED_COLOR, "mmr": mmr, "games": games,
                "label": f"Placement {games}/{PLACEMENTS}", "placing": True}
    for i in range(len(MMR_TIERS) - 1, -1, -1):
        if mmr >= MMR_TIERS[i][1]:
            break
    name, floor = MMR_TIERS[i]
    col = RANKS[i][2]
    if i == len(MMR_TIERS) - 1:
        return {"tier": i, "name": name, "div": "", "color": col, "label": f"{name}", "mmr": mmr, "games": games}
    step = (MMR_TIERS[i + 1][1] - floor) / 3
    d = min(2, max(0, int((mmr - floor) // step)))
    return {"tier": i, "name": name, "div": DIVISIONS[d], "color": col, "label": f"{name} {DIVISIONS[d]}",
            "mmr": mmr, "games": games}


def my_rating(data=None):
    """What we tell an opponent about ourselves: {mmr, games, w, l, id}."""
    data = data or load()
    w, l_ = data.get("ranked", [0, 0])
    return {"mmr": int(data.get("mmr", MMR_START)), "games": w + l_, "w": w, "l": l_, "id": player_id(data)}


def expected(me, them):
    return 1 / (1 + 10 ** ((them - me) / 400))


def record_ranked(opp_name, opp_rating, won):
    """Update the skill rating after a ranked 1v1. Returns {mmr, delta, old_rank, rank, games, promoted}."""
    data = load()
    player_id(data)
    old = int(data.get("mmr", MMR_START))
    w, l_ = data.get("ranked", [0, 0])
    games = w + l_
    opp = int((opp_rating or {}).get("mmr", MMR_START))
    k = 48 if games < PLACEMENTS else 32 if games < 30 else 24
    delta = round(k * ((1 if won else 0) - expected(old, opp)))
    if won:
        delta = max(delta, 1)
    new = max(100, old + delta)
    data["mmr"] = new
    data["ranked"] = [w + (1 if won else 0), l_ + (0 if won else 1)]
    data["peak_mmr"] = max(data.get("peak_mmr", MMR_START), new)
    hist = data.setdefault("ranked_history", [])
    hist.append({"vs": str(opp_name)[:16], "opp": opp, "won": bool(won), "mmr": new, "t": int(time.time())})
    del hist[:-20]
    save(data)
    r_old, r_new = mmr_rank(old, games), mmr_rank(new, games + 1)
    return {"mmr": new, "delta": new - old, "old_rank": r_old, "rank": r_new, "games": games + 1,
            "promoted": bool(r_new["tier"] > r_old["tier"] or (r_old.get("placing") and not r_new.get("placing"))),
            "demoted": bool(r_new["tier"] < r_old["tier"] and not r_old.get("placing"))}
