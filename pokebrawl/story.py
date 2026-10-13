"""Adventure mode's story, side quests, Mega Stones and secrets.

The plot: Professor Hazel gives you your first Pokemon. Your rival Blake picks the one that beats yours. Team Rift
is stealing Mega Stones across the Brawl region to power their machine and rig the Pokemon World Tournament.
Hazel gives you a Key Stone so your Pokemon can Mega Evolve - collect the stones (gym leaders, hidden spots,
side quests, stones won back from Team Rift), stop Team Rift's boss Vex on Victory Road, then win the World
Tournament: the Elite Four back to back and the Grand Final against the World Champion.

Everything here is data: NPCs with a 'script' (a list of steps run by the overworld), quests and secrets.
Script steps:
  ("say", speaker, [lines])            dialogue
  ("battle", key)                      a story battle (teams built in battle_team); stops the script if lost
  ("flag", name)                       remember something happened
  ("give", item, count)                put items in the bag
  ("mega", stone_key)                  a Mega Stone
  ("keystone",)                        the Key Stone (Mega Evolution unlocked)
  ("money", n) / ("heal",)
  ("wild", species, level, shiny)      a one-off wild encounter (the Snorlax, the red Gyarados...)
  ("tournament",)                      the World Tournament (Elite Four + Grand Final)
"""
import random

from . import adventure as A

RIVAL = "Blake"
BOSS = "Vex"
ADMIN = "Morga"
E4 = [  # (name, type, title, intro, lose, ace level)
    ("Frost", "ice", "Elite Four", "Welcome to the World Tournament! I'm Frost. Let's see if you can handle the cold!",
     "Brr... you're the real deal.", 58),
    ("Brutus", "fighting", "Elite Four", "I'm Brutus! My Pokemon and I trained under waterfalls for this!",
     "Haha! What a fight!", 59),
    ("Morrow", "ghost", "Elite Four", "Morrow... is my name. Your Pokemon look tired. Shall we make them... rest?",
     "...Impressive. Go on, then.", 60),
    ("Drakon", "dragon", "Elite Four", "I am Drakon, the strongest of the Elite Four. Dragons bow to no one!",
     "You... you beat my dragons. The final awaits you.", 62),
]
CHAMP = ("Aurelia", "World Champion")


# ====================================================================== flags and conditions
def has(game, flag):
    return flag in game.setdefault("flags", [])


def set_flag(game, flag):
    if not has(game, flag):
        game["flags"].append(flag)


def check(game, dex, cond):
    """cond: None, "flag", "!flag", "badges>=N", "caught>=N", "stones>=N", "champion", "partytype:fire"."""
    if not cond:
        return True
    if isinstance(cond, (list, tuple)):
        return all(check(game, dex, c) for c in cond)
    if cond.startswith("!"):
        return not check(game, dex, cond[1:])
    if cond.startswith("badges>="):
        return len(game["badges"]) >= int(cond[8:])
    if cond.startswith("caught>="):
        return len(game["caught"]) >= int(cond[8:])
    if cond.startswith("stones>="):
        return len(game.get("megastones", [])) >= int(cond[8:])
    if cond.startswith("partytype:"):
        t = cond[10:]
        return any(t in dex.all[m["species"]]["types"] for m in game["party"])
    if cond.startswith("item:"):
        return game["bag"].get(cond[5:], 0) > 0
    if cond == "champion":
        return bool(game.get("champion"))
    return has(game, cond)


# ====================================================================== mega stones
def all_stones(dex):
    """(stone key, stone name, base species id) for every Mega Evolution."""
    from .team import mega_item_name
    out = []
    for e in sorted(dex.all.values(), key=lambda e: e["id"]):
        if not e["default"]:
            continue
        for fid in e.get("megas", []):
            f = dex.all.get(fid)
            if f and "primal" not in f["key"]:
                out.append((f["key"], mega_item_name(dex, f), e["id"]))
    return out


def stone_name(dex, key):
    for k, name, _ in all_stones(dex):
        if k == key:
            return name
    return key


def _ordinary_stones(dex):
    """Stones of non-legendary Pokemon (those are the ones you can win and find)."""
    return [s for s in all_stones(dex) if not (dex.all[s[2]]["legendary"] or dex.all[s[2]]["mythical"])
            and s[2] not in A.SPECIAL_IDS]


def gym_stone(dex, k):
    """The Mega Stone a gym leader hands over: a different one per gym, of a Pokemon of their type."""
    used = set(QUEST_STONES.values())
    for j in range(8):
        typ = A.GYMS[j][2]
        pick = [s for s in _ordinary_stones(dex) if typ in dex.all[s[2]]["types"] and s[0] not in used]
        pick = pick or [s for s in _ordinary_stones(dex) if s[0] not in used]
        choice = pick[(j * 7) % len(pick)][0]
        if j == k:
            return choice
        used.add(choice)
    return None


def route_stones(dex):
    """Two hidden Mega Stones per route (sparkles on the ground), chosen once for the whole region."""
    stones = [s[0] for s in _ordinary_stones(dex)]
    taken = {gym_stone(dex, k) for k in range(8)} | set(QUEST_STONES.values())
    free = [s for s in stones if s not in taken]
    random.Random(77).shuffle(free)
    return {r: free[(r - 1) * 2:(r - 1) * 2 + 2] for r in range(1, 10)}


QUEST_STONES = {"q_letter": "venusaur-mega", "q_psyduck": "alakazam-mega", "q_rift1": "gyarados-mega",
                "q_rift2": "gengar-mega", "q_vex": "garchomp-mega", "q_starter": None}


# ====================================================================== story battles
def rival_team(world, game, level, size):
    dex = world.dex
    first = dex.all[game["party"][0]["species"]] if game.get("starter") is None else dex.all[game["starter"]]
    gen = next((g for g, trio in A.STARTERS.items() if first["id"] in trio or
                world.base_form(first["id"]) in trio), 1)
    trio = A.STARTERS[gen]
    mine = world.base_form(first["id"])
    i = trio.index(mine) if mine in trio else 0
    starter = dex.all[trio[(i + 1) % 3]]   # the one that beats yours
    rng = random.Random(len(game["name"]) * 31 + level)
    team = world.team_for(["normal", "flying", "electric", "psychic", "dark"], level - 2, size - 1, rng, strong=True)
    ace = A.make_mon(dex, A.grown_species(dex, starter, level), level, rng, shiny=False)
    if level >= 50:
        megas = dex.all[A.grown_species(dex, starter, 100)["id"]].get("megas", [])
        if megas:
            ace["mega"] = megas[0]
    return team + [ace]


def battle_team(world, game, key):
    """Teams for the story battles."""
    dex = world.dex
    rng = random.Random(hash(key) & 0xFFFF)
    if key == "rival1":
        return rival_team(world, game, 5, 1), {"name": RIVAL, "look": "rival", "money": 300, "ai": "easy",
                                              "lose": "What?! I picked the strongest one, too!"}
    if key == "rival2":
        return rival_team(world, game, 21, 3), {"name": RIVAL, "look": "rival", "money": 2100, "ai": "normal",
                                               "lose": "Tch. You got lucky. Next time I'll crush you!"}
    if key == "rival3":
        return rival_team(world, game, 52, 6), {"name": RIVAL, "look": "rival", "money": 7800, "ai": "hard",
                                               "lose": "...You're really strong. Win that tournament for both of us."}
    if key.startswith("grunt"):
        lv = {"grunt1": 12, "grunt2": 24, "grunt3": 34, "grunt4": 40}.get(key, 20)
        team = world.team_for(["poison", "dark"], lv, 2 + (lv > 30), rng)
        return team, {"name": "Rift Grunt", "look": "grunt", "money": 50 * lv, "ai": "normal",
                      "lose": "No way! Team Rift lost to a kid?!"}
    if key == "admin":
        team = world.team_for(["poison", "dark", "ghost"], 39, 4, rng, strong=True)
        return team, {"name": f"Rift Admin {ADMIN}", "look": "admin", "money": 4000, "ai": "hard",
                      "lose": "Fine! Take your silly stone back!"}
    if key == "vex1":
        team = world.team_for(["dark", "psychic", "steel"], 45, 5, rng, strong=True)
        return team, {"name": f"Rift Boss {BOSS}", "look": "boss", "money": 6000, "ai": "hard",
                      "lose": "Interesting... You are a variable I did not plan for."}
    if key == "vex2":
        team = world.team_for(["dark", "dragon", "steel"], 56, 5, rng, strong=True)
        ace = A.make_mon(dex, dex.get("garchomp"), 58, rng, shiny=False)
        ace["mega"] = dex.get("garchomp")["megas"][0]
        return team + [ace], {"name": f"Rift Boss {BOSS}", "look": "boss", "money": 10000, "ai": "insane",
                              "lose": "Impossible... The machine... my plan..."}
    if key.startswith("e4_"):
        k = int(key[3:])
        name, typ, title, intro, lose, lv = E4[k]
        team = world.team_for([typ], lv, 5, random.Random(900 + k), strong=True)
        megas = [s for s in all_stones(dex) if typ in dex.all[s[2]]["types"]]
        if megas:   # their ace Mega Evolves
            sp = dex.all[megas[0][2]]
            ace = A.make_mon(dex, sp, lv + 1, rng, shiny=False)
            ace["mega"] = next(fid for fid in sp["megas"] if dex.all[fid]["key"] == megas[0][0])
            team.append(ace)
        return team, {"name": f"{title} {name}", "look": name.lower(), "money": 200 * lv, "ai": "insane",
                      "lose": lose}
    if key == "final":
        team = world.champion_team()
        ace = A.make_mon(dex, dex.get("rayquaza"), 66, rng, shiny=False)
        ace["mega"] = dex.get("rayquaza")["megas"][0] if dex.get("rayquaza")["megas"] else None
        return team[:5] + [ace], {"name": f"{CHAMP[1]} {CHAMP[0]}", "look": "champ", "money": 30000,
                                  "ai": "insane", "lose": "I've waited years for someone like you. Well done."}
    if key == "creator":
        team = []
        for nm in ("mewtwo", "arceus", "rayquaza", "lugia", "giratina", "necrozma"):
            e = dex.get(nm)
            if e:
                team.append(A.make_mon(dex, e, 80, rng, shiny=nm == "rayquaza"))
        return team, {"name": "The Creator", "look": "creator", "money": 99999, "ai": "insane",
                      "lose": "GG. You beat the person who made this game. Respect."}
    raise KeyError(key)


# ====================================================================== the cast, per area
def npcs_for(world, index, game):
    """Story, quest and secret NPCs standing in an area (or a room: index = ('room', kind, area, door))."""
    dex = world.dex
    out = []
    if isinstance(index, tuple):
        _, kind, area, door = index
        return [n for n in _room_npcs(world, kind, area, door, game) if check(game, dex, n.get("if"))]
    area = world.areas[index]
    town = area.get("town")
    route = area.get("route")

    def add(**n):
        n.setdefault("face", "down")
        n.setdefault("name", "")
        out.append(n)

    if index == 0:   # Rootleaf Town
        add(id="rival_home", kind="story", look="rival", x=7, y=12, face="down", sight=3, name=RIVAL, auto=True,
            **{"if": "!rival1"}, script=[
                ("say", RIVAL, ["Hey! Gramps - I mean, Prof. Hazel - gave you a Pokemon too?",
                                "Then you're battling me. Right now!"]),
                ("battle", "rival1"),
                ("say", RIVAL, ["Hmph. I'll train way harder than you. See you at the World Tournament!"]),
                ("flag", "rival1")])
        add(id="egg_sign_kid", kind="talk", look="Youngster", x=12, y=22, face="left",
            lines=["Did you know? If you talk to someone over and over, sometimes they get annoyed.",
                   "...Or they give you something. Try it!"])
        add(id="mom_gift", kind="story", look="mom", x=4, y=8, name="Mom", **{"if": "champion"}, script=[
            ("say", "Mom", ["The World Champion! That's my kid!", "Here - I saved this for a special day."]),
            ("give", "master-ball", 1), ("flag", "mom_gift")], once="mom_gift")
    if route == 1:
        add(id="aide1", kind="story", look="prof", x=7, y=len(area["rows"]) - 3, face="up", name="Hazel's Aide",
            **{"if": "!aide1"}, script=[
                ("say", "Hazel's Aide", ["Oh! You're the new trainer! The Professor asked me to give you these.",
                                         "Hold X while you walk to run. Catch lots of Pokemon!"]),
                ("give", "poke-ball", 5), ("give", "potion", 2), ("flag", "aide1")])
        add(id="q_charm_girl", kind="quest", quest="q_charm", look="Lass", x=3, y=len(area["rows"]) - 8, face="right")
    if town == 1:   # Pebblecrest: Team Rift shows up
        add(id="grunt1", kind="story", look="grunt", x=11, y=12, face="up", name="Rift Grunt", **{"if": "!grunt1"},
            script=[("say", "Rift Grunt", ["Hey! This gym is closed! Team Rift is searching it for Mega Stones!",
                                           "...You want in? Then beat me!"]),
                    ("battle", "grunt1"),
                    ("say", "Rift Grunt", ["Ugh... Whatever! The boss will get every stone in the region anyway!"]),
                    ("flag", "grunt1")])
        add(id="q_fire_boy", kind="quest", quest="q_fire", look="Youngster", x=12, y=14, face="left")
    if town == 2:   # Tidewater: the Key Stone
        add(id="hazel_key", kind="story", look="prof", x=4, y=7, name="Prof. Hazel",
            **{"if": ["badges>=2", "!keystone"]}, script=[
                ("say", "Prof. Hazel", [f"{game['name']}! Two badges already? Wonderful!",
                                        "Listen. Team Rift is stealing MEGA STONES all over the region.",
                                        "When a Pokemon holds its Mega Stone and its trainer has a KEY STONE,",
                                        "it can MEGA EVOLVE in battle - for a huge power boost!",
                                        "Take this Key Stone. Find the Mega Stones before Team Rift does!"]),
                ("keystone",), ("flag", "keystone"),
                ("say", "Prof. Hazel", ["In battle, press M (or the MEGA button) before picking a move.",
                                        "Gym Leaders have stones too. And some are hidden on the routes - look for "
                                        "sparkles on the ground!"])])
        add(id="hazel_key_wait", kind="talk", look="prof", x=4, y=7, name="Prof. Hazel", **{"if": "!badges>=2"},
            lines=["Oh, hello! Come and find me when you have two badges. I have something for you."])
        add(id="q_letter_man", kind="quest", quest="q_letter", look="Hiker", x=12, y=14, face="left")
        add(id="q_dex10_aide", kind="quest", quest="q_dex10", look="prof", x=2, y=14, face="right",
            name="Hazel's Aide")
    if route == 3:
        add(id="rival2", kind="story", look="rival", x=7, y=len(area["rows"]) // 2, face="down", sight=4, auto=True,
            name=RIVAL, **{"if": "!rival2"}, script=[
                ("say", RIVAL, ["There you are! I've been training nonstop.", "Let's see who's stronger now!"]),
                ("battle", "rival2"), ("flag", "rival2")])
        add(id="red_gyarados", kind="static", pokemon="gyarados", level=30, shiny=True, x=_pond_edge(area), y=None,
            **{"if": "!red_gyarados"}, script=[("say", "", ["The water is churning... A huge red Pokemon leaps out!"]),
                                               ("wild", "gyarados", 30, True), ("flag", "red_gyarados")])
    if town == 3:   # Voltara
        add(id="grunt2", kind="story", look="grunt", x=4, y=12, face="right", sight=4, auto=True, name="Rift Grunt",
            **{"if": "!grunt2"}, script=[
                ("say", "Rift Grunt", ["You again?! Team Rift's admin is in Toxmire Town. Don't you dare follow!"]),
                ("battle", "grunt2"), ("flag", "grunt2")])
        add(id="egg_joke", kind="talk", look="Biker", x=12, y=20, face="left",
            lines=["My Electric Pokemon stopped working yesterday.",
                   "Have you tried turning it off and on again? ...It worked."])
    if route == 4:
        add(id="q_ranger", kind="quest", quest="q_route4", look="Ace Trainer", x=2, y=len(area["rows"]) - 4,
            face="right", name="Ranger")
    if route == 5:
        add(id="snorlax", kind="static", pokemon="snorlax", level=30, x=7, y=len(area["rows"]) // 2 + 3,
            **{"if": "!snorlax"}, script=[("say", "", ["A huge Pokemon is fast asleep in the middle of the road!",
                                                       "...It woke up! It looks angry!"]),
                                          ("wild", "snorlax", 30, False), ("flag", "snorlax")])
    if town == 5:   # Toxmire: Team Rift's admin
        add(id="admin", kind="story", look="admin", x=7, y=9, face="down", sight=5, auto=True,
            name=f"Admin {ADMIN}", **{"if": "!admin"}, script=[
                ("say", f"Admin {ADMIN}", ["So you're the brat who keeps beating our grunts.",
                                            "These Mega Stones will power Boss Vex's machine.",
                                            "With it, Team Rift will control every battle at the World Tournament!"]),
                ("battle", "admin"),
                ("say", f"Admin {ADMIN}", ["Grr... Here, take it! The boss has plenty more in Mindspire City!"]),
                ("mega", QUEST_STONES["q_rift1"]), ("flag", "admin")])
    if route == 6:
        add(id="lost_psyduck", kind="static", pokemon="psyduck", level=0, x=_quiet_spot(area), y=None,
            **{"if": ["q_psyduck_started", "!q_psyduck_found"]},
            script=[("say", "", ["It's a Psyduck with a little bow on its head. It looks lost.",
                                 "Psyduck started following you!"]), ("flag", "q_psyduck_found")])
    if town == 6:   # Mindspire: Boss Vex
        add(id="vex1", kind="story", look="boss", x=7, y=12, face="down", sight=5, auto=True, name=f"Boss {BOSS}",
            **{"if": ["admin", "!vex1"]}, script=[
                ("say", f"Boss {BOSS}", ["I am Vex, leader of Team Rift.",
                                         "Mega Evolution is the ultimate power. Why should it belong to children?",
                                         "My machine will drain every Mega Stone it touches.",
                                         "At the World Tournament, no Mega Evolution will work... except mine."]),
                ("battle", "vex1"),
                ("say", f"Boss {BOSS}", ["You are strong. Keep your stone. We will meet at Victory Road."]),
                ("mega", QUEST_STONES["q_rift2"]), ("flag", "vex1")])
        add(id="q_psyduck_girl", kind="quest", quest="q_psyduck", look="Lass", x=12, y=14, face="left")
    if town == 7:
        add(id="q_dex30_sci", kind="quest", quest="q_dex30", look="prof", x=3, y=14, face="right", name="Scientist")
    if town == 8:
        add(id="q_mega_maniac", kind="quest", quest="q_stones", look="Psychic", x=12, y=14, face="left",
            name="Mega Maniac")
    if route == 8:
        add(id="rival3", kind="story", look="rival", x=7, y=6, face="down", sight=4, auto=True, name=RIVAL,
            **{"if": "!rival3"}, script=[
                ("say", RIVAL, ["The World Tournament is right past Victory Road.",
                                "Only one of us is going. Give it everything you've got!"]),
                ("battle", "rival3"), ("flag", "rival3")])
    if route == 9:   # Victory Road
        add(id="vex2", kind="story", look="boss", x=7, y=8, face="down", sight=5, auto=True, name=f"Boss {BOSS}",
            **{"if": ["vex1", "!vex2"]}, script=[
                ("say", f"Boss {BOSS}", ["You came. The machine is ready.",
                                         "My Garchomp holds the last stone it needs. Watch true Mega power!"]),
                ("battle", "vex2"),
                ("say", f"Boss {BOSS}", ["...The machine is broken. Team Rift is finished.",
                                         "Take the stone. You've earned the right to the tournament."]),
                ("mega", QUEST_STONES["q_vex"]), ("flag", "vex2")])
        add(id="arceus", kind="static", pokemon="arceus", level=70, x=7, y=3,
            **{"if": ["champion", "stones>=20", "!arceus"]},
            script=[("say", "", ["A blinding light... Something ancient was waiting for a true champion."]),
                    ("wild", "arceus", 70, False), ("flag", "arceus")])
    if route == 2:
        add(id="mew", kind="static", pokemon="mew", level=50, x=1, y=4, **{"if": ["champion", "!mew"]},
            script=[("say", "", ["There's something hiding behind the trees... It's giggling!"]),
                    ("wild", "mew", 50, False), ("flag", "mew")])
    if index == len(world.areas) - 1:   # the League town
        add(id="league_guard", kind="talk", look="guard", x=8, y=8, face="down",
            lines=["Beyond here is the POKeMON WORLD TOURNAMENT.", "Only trainers with all 8 badges may enter."])
    # hidden Mega Stones on routes (sparkles), and the hidden items you find by checking the ground
    return [n for n in out if check(game, dex, n.get("if")) and not (n.get("once") and has(game, n["once"]))]


def _pond_edge(area):
    rows = area["rows"]
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "~" and 0 < y and rows[y - 1][x] in ".,":
                return (x, y - 1)
    return (2, len(rows) // 2)


def _quiet_spot(area):
    rows = area["rows"]
    for y in range(len(rows) - 6, 4, -1):
        for x in (2, 12, 3, 11):
            if rows[y][x] in ".,":
                return (x, y)
    return (7, len(rows) // 2)


def _room_npcs(world, kind, area, door, game):
    out = []
    if kind == "house" and area == 0 and door == creator_door(world):
        out.append({"id": "creator", "kind": "story", "look": "creator", "x": 7, "y": 4, "face": "down",
                    "name": "The Creator", "script": [
                        ("say", "The Creator", ["Oh, hi! I'm the one who made this game.",
                                                "Thanks for playing it. Seriously."] +
                         (["...You're the World Champion now? Then I have one last challenge for you."]
                          if game.get("champion") else
                          ["Come back when you're the World Champion. I'll be waiting."]))] +
                    ([("battle", "creator"), ("give", "master-ball", 3), ("flag", "creator_beaten"),
                      ("say", "The Creator", ["You beat my dream team. You really are the best in the world."])]
                     if game.get("champion") and not has(game, "creator_beaten") else [])})
    if kind == "house" and world.areas[area].get("town") == 4 and door[0] < 7:   # the letter's sister
        if check(game, world.dex, ["item:old-letter", "!letter_delivered"]):
            out.append({"id": "sister", "kind": "story", "look": "mom", "x": 8, "y": 5, "face": "down",
                        "name": "Old Lady", "script": [
                            ("say", "Old Lady", ["A letter? From my brother in Tidewater?",
                                                 "...Oh, that old fool. He still remembers my birthday.",
                                                 "Please tell him I'll visit in the spring."]),
                            ("take", "old-letter"), ("flag", "letter_delivered")]})
        else:
            out.append({"id": "sister", "kind": "talk", "look": "mom", "x": 8, "y": 5, "face": "down",
                        "name": "Old Lady", "lines": ["My brother lives in Tidewater City. He never visits!"]})
    if kind == "league":
        # the Elite Four and the Champion wait at the far end of the arena
        for k, (name, typ, title, intro, lose, lv) in enumerate(E4):
            x, y = (3, 3) if k == 0 else (11, 3) if k == 1 else (3, 6) if k == 2 else (11, 6)
            out.append({"id": f"e4_{k}_stand", "kind": "talk", "look": name.lower(), "x": x, "y": y,
                        "face": "down", "name": name,
                        "lines": [f"I'm {name} of the Elite Four. I use {typ.upper()} Pokemon.",
                                  "Talk to the Host when you're ready. We'll be waiting in the arena."]})
        out.append({"id": "champ_stand", "kind": "talk", "look": "champ", "x": 7, "y": 2, "face": "down",
                    "name": CHAMP[0], "lines": (["You took my title fair and square. Come defend it any time!"]
                                                if game.get("champion") else
                                                ["I am Aurelia, the World Champion.",
                                                 "Beat all four of the Elite Four, and I'll face you myself."])})
        if len(game.get("badges", [])) < 8:
            out.append({"id": "host", "kind": "talk", "look": "guard", "x": 7, "y": 10, "face": "up",
                        "name": "Host", "lines": ["Welcome to the POKeMON WORLD TOURNAMENT!",
                                                  "Sorry - only trainers with all 8 Gym Badges can enter.",
                                                  f"You have {len(game.get('badges', []))}. Come back soon!"]})
            return out
        out.append({"id": "host", "kind": "story", "look": "guard", "x": 7, "y": 10, "face": "up",
                    "name": "Host", "script": [
                        ("say", "Host", ["Welcome to the POKeMON WORLD TOURNAMENT!",
                                         "You'll face the four members of the Elite Four, one after another.",
                                         "No breaks, no healing between rounds. Win them all to reach the GRAND FINAL",
                                         "against the World Champion. Ready? Then let the tournament begin!"]),
                        ("tournament",)]})
    return out


def creator_door(world):
    rows = world.areas[0]["rows"]
    doors = [(x, y) for y, row in enumerate(rows) for x, ch in enumerate(row) if ch == "D"]
    return doors[-1] if doors else None


# ====================================================================== side quests
QUESTS = {
    "q_charm": {"name": "The Lucky Charm", "giver": "Lass on Route 1",
                "ask": ["I dropped my lucky charm somewhere on Route 2...", "Could you look for it? Please?"],
                "need": "item:lucky-charm", "done": ["My lucky charm! Thank you so much! Take these!"],
                "reward": [("give", "great-ball", 5)], "take": "lucky-charm"},
    "q_fire": {"name": "Show Me Fire", "giver": "Boy in Pebblecrest City",
               "ask": ["I've never seen a Fire-type Pokemon up close.", "Can you show me one? Bring one in your party!"],
               "need": "partytype:fire", "done": ["Whoa, it's so warm! That's so cool! Here, take these!"],
               "reward": [("give", "super-potion", 3)]},
    "q_letter": {"name": "The Old Letter", "giver": "Old man in Tidewater City",
                 "ask": ["I wrote a letter to my sister in Bloomfield City, but my legs are too old for the trip.",
                         "Would you deliver it? She lives in the house on the left."],
                 "start": [("give", "old-letter", 1)], "need": "letter_delivered",
                 "done": ["She wrote back? Oh, thank you! Here - our family treasure. It's a Mega Stone!"],
                 "reward": [("mega", QUEST_STONES["q_letter"])]},
    "q_dex10": {"name": "Ten Kinds", "giver": "Hazel's aide in Tidewater City",
                "ask": ["Prof. Hazel wants data! Catch 10 different kinds of Pokemon and come back."],
                "need": "caught>=10", "done": ["10 kinds! The Professor will be thrilled. Here are some Rare Candies!"],
                "reward": [("give", "rare-candy", 3)]},
    "q_route4": {"name": "Route 4 Rumble", "giver": "Ranger on Route 4",
                 "ask": ["The trainers on this route think they're tough.", "Beat every one of them, then come see me."],
                 "need": "route4_clear", "done": ["You beat them all? Incredible! Here's your prize."],
                 "reward": [("money", 3000), ("give", "ultra-ball", 5)]},
    "q_psyduck": {"name": "Lost Psyduck", "giver": "Girl in Mindspire City",
                  "ask": ["My Psyduck wandered off to Route 6 and hasn't come back!",
                          "It has a little bow on its head. Please find it!"],
                  "start": [("flag", "q_psyduck_started")], "need": "q_psyduck_found",
                  "done": ["PSYDUCK! You found him! Thank you! Please take this Mega Stone."],
                  "reward": [("mega", QUEST_STONES["q_psyduck"])]},
    "q_dex30": {"name": "Shiny Research", "giver": "Scientist in Emberpeak City",
                "ask": ["I study shiny Pokemon. Catch 30 different kinds and I'll share my secret."],
                "need": "caught>=30", "done": ["30 kinds! Take this SHINY CHARM. Shiny Pokemon will appear far more often."],
                "reward": [("flag", "shiny_charm")]},
    "q_stones": {"name": "Mega Maniac", "giver": "Mega Maniac in Duneholt City",
                 "ask": ["MEGA STONES! I love them! Collect 10 and I'll give you my greatest treasure!"],
                 "need": "stones>=10", "done": ["10 Mega Stones! You're a true Mega Maniac! Take this MASTER BALL!"],
                 "reward": [("give", "master-ball", 1)]},
}
KEY_ITEMS = {"lucky-charm": ("Lucky Charm", "A lucky charm someone dropped."),
             "old-letter": ("Old Letter", "A letter for someone in Bloomfield City.")}


def quest_script(game, dex, qid):
    """The steps a quest giver runs when you talk to them."""
    q = QUESTS[qid]
    state = game.setdefault("quests", {})
    st = state.get(qid)
    if st == "done":
        return [("say", "", ["Thanks again for your help!"])]
    if st is None:
        state[qid] = "active"
        return [("say", "", q["ask"])] + q.get("start", []) + [("say", "", [f"Quest started: {q['name']}"])]
    if check(game, dex, q["need"]):
        steps = [("say", "", q["done"])] + q["reward"]
        if q.get("take"):
            steps.append(("take", q["take"]))
        steps.append(("quest_done", qid))
        return steps
    return [("say", "", q["ask"][-1:])]


def quest_list(game):
    st = game.get("quests", {})
    return [(qid, q["name"], q["giver"], st.get(qid)) for qid, q in QUESTS.items() if st.get(qid)]


def route_extras(world, area_index, game):
    """Ground items added by the story: hidden Mega Stones and quest items."""
    area = world.areas[area_index]
    route = area.get("route")
    if not route:
        return []
    dex = world.dex
    rows = area["rows"]
    out = []
    rng = random.Random(route * 101)
    spots = [(x, y) for y in range(4, len(rows) - 4) for x in range(1, A.COLS - 1) if rows[y][x] in ".,"]
    rng.shuffle(spots)
    for k, stone in enumerate(route_stones(dex).get(route, [])):
        if k < len(spots):
            x, y = spots[k]
            out.append({"id": f"stone-{stone}", "x": x, "y": y, "item": stone, "count": 1, "mega": True})
    if route == 2 and k + 1 < len(spots):
        x, y = spots[-1]
        out.append({"id": "lucky-charm", "x": x, "y": y, "item": "lucky-charm", "count": 1})
    return out


# hidden items: check the right spot (no sparkle) - one per route
def hidden_items(world, area_index):
    area = world.areas[area_index]
    route = area.get("route")
    if not route:
        return []
    rows = area["rows"]
    rng = random.Random(route * 55)
    spots = [(x, y) for y in range(4, len(rows) - 4) for x in range(1, A.COLS - 1) if rows[y][x] in ".,"]
    if not spots:
        return []
    x, y = rng.choice(spots)
    item = ["rare-candy", "ultra-ball", "max-revive", "rare-candy", "full-restore", "rare-candy", "max-potion",
            "rare-candy", "master-ball"][route - 1]
    return [{"id": f"hidden{route}", "x": x, "y": y, "item": item}]


# ====================================================================== the quest log
SECRETS = {"chatterbox": "The Chatterbox", "red_gyarados": "The Red Gyarados", "snorlax": "The Sleeping Giant",
           "shiny_charm": "Shiny Charm", "mom_gift": "Mom's Gift", "mew": "The Giggle in the Trees",
           "arceus": "The Origin", "creator_beaten": "The Creator"}


def secrets_found(game):
    return sum(1 for f in SECRETS if has(game, f))


def next_goal(game, dex):
    """One line telling you where the main story goes next."""
    b = len(game.get("badges", []))
    gym = A.GYMS[b][0] if b < 8 else None
    if game.get("champion"):
        n = len(game.get("megastones", []))
        return (f"You're the World Champion! Mega Stones: {n}/{len(all_stones(dex))}. "
                "Secrets still hide out there...")
    if not has(game, "rival1"):
        return f"Your rival {RIVAL} is waiting for you in Rootleaf Town."
    if b == 0 and not has(game, "grunt1"):
        return "Head north to Pebblecrest City. Something is going on at the Gym..."
    if b < 2:
        return f"Earn your next badge at the {gym} Gym."
    if not game.get("keystone"):
        return "Prof. Hazel is waiting for you in Tidewater City."
    if b < 5:
        return f"Find Mega Stones and earn your next badge in {gym}."
    if not has(game, "admin"):
        return f"Team Rift's Admin {ADMIN} is causing trouble in Toxmire Town!"
    if not has(game, "vex1"):
        return f"Confront Boss {BOSS} of Team Rift in Mindspire City."
    if b < 8:
        return f"Earn your next badge at the {gym} Gym."
    if not has(game, "vex2"):
        return f"Stop {BOSS} on Victory Road, then enter the World Tournament!"
    return "Enter the POKeMON WORLD TOURNAMENT and become the best trainer in the world!"
