"""Engine tests. They use the downloaded Pokedex (~/.pokebrawl or $POKEBRAWL_HOME); skipped if it isn't there
and can't be downloaded."""
import random
import threading
import time

import pytest

from pokebrawl import net
from pokebrawl.types import effectiveness


@pytest.fixture(scope="session")
def dex():
    from pokebrawl.pokedex import load_dex
    try:
        return load_dex(progress=lambda m: None)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no Pokedex data: {e}")


def test_type_chart():
    assert effectiveness("water", ["fire"]) == 2
    assert effectiveness("electric", ["ground"]) == 0
    assert effectiveness("ice", ["dragon", "flying"]) == 4
    assert effectiveness("fire", ["water", "rock"]) == 0.25


def test_dex_has_everything(dex):
    assert len(dex.selectable()) > 1100
    assert dex.get("mewtwo")["megas"]
    assert dex.all[dex.get("kyogre")["megas"][0]]["key"] == "kyogre-primal"
    assert dex.move("psystrike")["id"] in dex.get("mewtwo")["learn"]
    assert dex.move("moonblast")["id"] not in dex.get("garchomp")["learn"]


def test_stat_formula(dex):
    from pokebrawl.team import Member, calc_stats
    g = dex.get("garchomp")
    m = Member(g["id"], [], nature="Jolly", evs={"atk": 252, "spe": 252, "spd": 4})
    st = calc_stats(g, m)
    assert st["spe"] == 333 and st["atk"] == 359 and st["hp"] == 357


def test_showdown_roundtrip(dex):
    from pokebrawl.team import export_showdown, import_showdown, random_team, validate
    team = random_team(dex, random.Random(4))
    assert validate(dex, team) == []
    back, warns = import_showdown(dex, export_showdown(dex, team))
    assert not warns
    assert [m.species for m in back] == [m.species for m in team]
    assert [m.moves for m in back] == [m.moves for m in team]
    assert [m.item for m in back] == [m.item for m in team]


def test_turn_battles_finish(dex):
    from pokebrawl.bot import TurnBot
    from pokebrawl.team import random_team
    from pokebrawl.turnsim import TurnBattle
    for seed in range(15):
        b = TurnBattle(dex, [random_team(dex, random.Random(seed)), random_team(dex, random.Random(seed + 99))], seed)
        bots = [TurnBot(["easy", "normal", "hard", "insane"][seed % 4], seed), TurnBot("normal", seed + 1)]
        for _ in range(500):
            if b.over:
                break
            for side, req in b.requests().items():
                assert b.choose(side, bots[side].choose(b, side, req))
            b.run()
        assert b.over


def test_mass_showcase_sim(dex):
    from pokebrawl.showcase import build_teams, load_config
    from pokebrawl.sim import Sim
    cfg = load_config({"teams": [{"filter": {"gen": 1}, "count": 40}, {"filter": {"gen": 3}, "count": 40}]})
    teams, names = build_teams(dex, cfg, random.Random(2))
    sim = Sim(dex, teams, seed=2, hp_mult=6, radius=13)
    while not sim.over and sim.t < 300:
        sim.step()
        sim.snapshot()
    assert sim.over


def test_relay_pairs_players():
    port = random.randint(30000, 50000)
    threading.Thread(target=net.run_relay, args=(port, lambda *a: None), daemon=True).start()
    time.sleep(0.3)
    host = net.Host(relay=f"127.0.0.1:{port}", room="test")
    joiner = net.relay_connect(f"127.0.0.1:{port}", "TEST", "join")
    for _ in range(100):
        if host.conn:
            break
        time.sleep(0.02)
    host.conn.send({"t": "hi"})
    joiner.send({"t": "yo"})
    time.sleep(0.5)
    assert joiner.poll() == [{"t": "hi"}]
    assert host.conn.poll() == [{"t": "yo"}]
    assert host.conn.rtt is not None  # heartbeat measured ping


def test_replays_reproduce_battles(dex):
    import json

    from pokebrawl.replays_ui import TurnReplaySession
    from pokebrawl.session import TurnLocal
    from pokebrawl.team import random_team
    t = TurnLocal(dex, random_team(dex, random.Random(5)), random_team(dex, random.Random(6)), "hard", seed=5)
    for _ in range(500):
        if t.battle.over:
            break
        req = t.battle.requests().get(0)
        if req:
            t.choose({"type": "switch", "index": req["switches"][0]} if req["kind"] != "move" else
                     {"type": "move", "slot": next(m["slot"] for m in req["moves"] if not m["disabled"])})
    tr = TurnReplaySession(dex, json.loads(json.dumps(t.replay())))
    assert [m.hp for sd in t.battle.sides for m in sd.mons] == [m.hp for sd in tr.battle.sides for m in sd.mons]


def test_autoedit_plan_is_deterministic_and_shortens(dex):
    from pokebrawl.autoedit import Planner, schedule
    from pokebrawl.showcase import ShowcaseScene, load_config
    cfg = load_config({"title": "t", "teams": [{"name": "A", "filter": {"gen": 1}, "count": 20},
                                                 {"name": "B", "filter": {"gen": 3}, "count": 20}],
                       "seed": 4, "events": "none", "finale": False})
    a, b = Planner(ShowcaseScene(dex, cfg), 30, 20), Planner(ShowcaseScene(dex, cfg), 30, 20)
    while not a.step():
        pass
    while not b.step():
        pass
    assert a.flags == b.flags  # the recording replays exactly the battle that was planned
    draw, speed, ff, length = a.schedule()
    assert len(draw) == len(a.flags) and length < len(a.flags) / 30 / 2  # much shorter than the battle
    # short battles are left alone
    assert schedule([2] * 300, 30, 60)[3] == 10.0


def test_ranks_and_legend_collection(dex, tmp_path, monkeypatch):
    from pokebrawl import profile
    monkeypatch.setattr(profile, "PROFILE_FILE", str(tmp_path / "profile.json"))
    monkeypatch.setattr(profile, "HOME", str(tmp_path))
    assert profile.rank_of(0)["label"] == "Poke Ball III"
    assert profile.rank_of(2500)["label"] == "Champion"
    rng = random.Random(3)
    out = None
    for _ in range(30):
        out = profile.record("bots", "insane", True, dex, rng)
        if out["encounter"]:
            profile.add_legend(dex.get(out["encounter"][0]), out["encounter"][1])
    data = profile.load()
    assert data["rp"] > 650 and data["best_streak"] == 30 and data["legends"]
    assert all(dex.get(k)["legendary"] or dex.get(k)["mythical"] for k in data["legends"])
    lost = profile.record("bots", "insane", False, dex, rng)
    assert lost["delta"] < 0 and lost["encounter"] is None and lost["streak"] == -1


def test_adventure_world_and_progress(dex, tmp_path, monkeypatch):
    from pokebrawl import adventure as A
    from pokebrawl.adventure_battle import AdventureSession
    monkeypatch.setattr(A, "SAVE_FILE", str(tmp_path / "adv.json"))
    w = A.World(dex)
    assert len(w.areas) == 2 * len(A.GYMS) + 3 and w.areas[0]["kind"] == "town" and w.areas[1]["kind"] == "route"
    for a in w.areas:  # every map is 15 wide and the exits line up
        assert all(len(r) == A.COLS for r in a["rows"])
        if a["kind"] == "route":
            assert all(a["rows"][y][7] in '="' for y in (0, len(a["rows"]) - 1))
    g = A.new_game("Red", 4, dex)
    mon = g["party"][0]
    events = A.gain_xp(dex, mon, A.xp_for(16) - mon["xp"])
    assert ("evolve", 5) in events and mon["level"] == 16
    # a wild battle where we just throw Master Balls: always caught
    g["bag"]["master-ball"] = 1
    foe = A.make_mon(dex, dex.get("pidgey"), 4, random.Random(1))
    s = AdventureSession(g, dex, [foe], "wild", seed=3)
    assert s.choose({"type": "ball", "ball": "master-ball"})
    r = s.results()
    assert r["caught"] and r["caught"]["species"] == foe["species"] and "master-ball" not in g["bag"]
    assert A.add_caught(g, dex, r["caught"]) == "party"
    A.save(g)
    assert A.load()["party"][1]["species"] == foe["species"]


def test_ranked_rating(tmp_path, monkeypatch):
    from pokebrawl import profile
    monkeypatch.setattr(profile, "PROFILE_FILE", str(tmp_path / "profile.json"))
    monkeypatch.setattr(profile, "HOME", str(tmp_path))
    me = profile.my_rating()
    assert me["mmr"] == 1000 and me["games"] == 0 and me["id"] == profile.my_rating()["id"]   # id is kept
    assert profile.mmr_rank(1000, 0)["placing"]
    up = profile.record_ranked("Rival", {"mmr": 1400}, True)    # beating a stronger player is worth a lot
    down = profile.record_ranked("Newbie", {"mmr": 700}, False)  # losing to a weaker one costs a lot
    assert up["delta"] > 30 and down["delta"] < -30
    for _ in range(5):
        out = profile.record_ranked("Friend", {"mmr": 1000}, True)
    assert not out["rank"].get("placing") and out["games"] == 7
    assert profile.mmr_rank(1700, 50)["name"] == "Champion"
    assert profile.mmr_rank(1260, 50)["label"].startswith("Ultra Ball")


def test_story_every_area_every_stage(dex):
    from pokebrawl import adventure as A, story as S
    w = A.World(dex)
    rng = random.Random(5)
    g = A.new_game("RED", 6, dex)
    g["party"] = [A.make_mon(dex, dex.get("charizard"), 60, rng)]
    g["starter"] = 6
    stages = [[], ["rival1", "keystone", "rival2", "morga_offer", "admin", "vex1"],
              ["vex1", "rival_dark", "rival3", "vex2", "first_rift"], ["first_rift", "rift_zero", "origin_quest"]]
    for flags in stages:
        g["flags"] = list(flags)
        g["champion"] = "first_rift" in flags
        g["keystone"] = bool(flags)
        for i, area in enumerate(w.areas):
            rows = area["rows"]
            spots = set()
            for n in S.npcs_for(w, i, g):
                x, y = n["x"], n["y"]
                if isinstance(x, int) and isinstance(y, int):
                    assert rows[y][x] in '.,"=_', (area.get("name"), n["id"])   # nobody stands in a wall
                    assert (x, y) not in spots, (area.get("name"), n["id"])
                    spots.add((x, y))
            if area.get("route"):
                S.hidden_items(w, i)   # every route has its hidden item (19 routes)
    for key in ("rival_dark", "elias", "vex2"):
        team, trainer = S.battle_team(w, g, key)
        assert team and trainer["name"]
    assert S.battle_team(w, g, "vex2")[0][-1].get("corrupt")


def test_spritekit_and_mega_recipes():
    from pokebrawl import megas, riftdex, spritekit as K
    img = K.Img(8, 8)
    for x, y in K.rect(2, 2, 4, 4):
        img.set(x, y, (200, 50, 50))
    big = K.scale2x(img)
    assert big.w == 16 and len(big.points()) == 60   # Scale2x rounds the square's 4 corners off
    img.outline()
    assert img.get(1, 3) is not None and K.is_dark(img.get(1, 3))
    fire = K.flame(K.Img(32, 32), [(16, 30), (16, 16), (18, 4)], 4, [(40, 72, 208), (72, 144, 248),
                                                                     (150, 214, 255), (240, 252, 255)], (16, 24, 88))
    assert len(fire.colors()) == 5
    keys = {m[0] for m in riftdex.CUSTOM_MEGAS}
    assert set(megas.RECIPES) == keys == set(megas.NEEDS)   # every new Mega has a recipe
