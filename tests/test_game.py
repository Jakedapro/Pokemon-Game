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


def test_realtime_battle_finishes(dex):
    from pokebrawl.session import RTLocal
    from pokebrawl.team import random_team
    s = RTLocal(dex, random_team(dex, random.Random(1)), random_team(dex, random.Random(2)), "hard", seed=1)
    for _ in range(30 * 400):
        snaps = s.step(1 / 30)
        if snaps and snaps[-1]["over"]:
            break
    assert s.sim.over


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
    host.conn.send({"t": "ping"})
    joiner.send({"t": "pong"})
    time.sleep(0.2)
    assert joiner.poll() == [{"t": "ping"}]
    assert host.conn.poll() == [{"t": "pong"}]
