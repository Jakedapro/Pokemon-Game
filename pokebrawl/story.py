"""Adventure mode's story, side quests, Mega Stones and secrets.

THE PLOT - "The First Rift"
Ten years ago Professor Hazel's son, Dr. Elias, was studying Mega energy at the Rootleaf pond. One night the pond
glowed purple, a rift opened - the FIRST Mega Rift - and Elias and his partner Pokemon were swallowed by it.
Hazel never spoke of it again. Her grandson Blake (your rival) grew up wanting to be strong enough to find him.

Team Rocket stole Elias's notes and built the RIFT ENGINE: a machine that tears rifts open all over the Brawl region
to force Pokemon to Mega Evolve and harvest their Mega Stones. Boss Giovanni wants enough stones to power the Engine
all the way - to rip the First Rift open and take the power at its heart - and to rig the World Tournament.

Hazel gives you the Key Stone. You seal rifts, earn badges and stones, and keep running into Team Rocket. Admin Morga
tempts Blake with a CORRUPTED Mega Stone ("Team Rocket can open the First Rift. Your father is inside."); Blake
takes it, and in Duskmoor his Mega nearly destroys itself fighting you. He throws the stone away, and from then on
he's on your side. Giovanni makes his last stand on Victory Road with a corrupted Mega Garchomp; when he loses, the
Rift Engine overloads and the First Rift tears open in Rootleaf.

You win the World Tournament - and the Champion, Aurelia, turns out to be Elias's old rival. As the new Champion you
go into the First Rift, calm the Mega Mewtwo raging inside, and bring Elias home. He tells you what he saw in there:
the rifts are cracks in creation itself, and something ancient at the summit of Victory Road has been watching.
The true ending: the Origin - the guardian of the rifts, then Arceus itself.

Everything here is data: NPCs with a 'script' (a list of steps run by the overworld), quests and secrets.
Script steps:
  ("say", speaker, [lines])            dialogue
  ("battle", key)                      a story battle (teams built in battle_team); stops the script if lost
  ("flag", name)                       remember something happened
  ("give", item, count)                put items in the bag
  ("mega", stone_key)                  a Mega Stone
  ("keystone",)                        the Key Stone (Mega Evolution unlocked)
  ("money", n) / ("heal",)
  ("pay", n)                           pay coins (the script stops if you can't)
  ("purify",)                          turn a corrupted Mega Stone back into a clean one
  ("wild", species, level, shiny)      a one-off wild encounter (the Snorlax, the red Gyarados...)
  ("gift", species id, level)          a Pokemon joins you
  ("riftboss", key, level, anomaly)    a raging legendary inside a rift that doesn't collapse (the finale)
  ("tournament",)                      the World Tournament (Elite Four + Grand Final)
"""
import random

from . import adventure as A

RIVAL = "Blake"
ELIAS = "Dr. Elias"
BOSS = "Giovanni"
ADMIN = "Morga"
E4 = [  # (name, type, title, intro, lose, ace level)
    ("Frost", "ice", "Elite Four", "Welcome to the World Tournament! I'm Frost. Let's see if you can handle the cold!",
     "Brr... you're the real deal.", 66),
    ("Brutus", "fighting", "Elite Four", "I'm Brutus! My Pokemon and I trained under waterfalls for this!",
     "Haha! What a fight!", 67),
    ("Morrow", "ghost", "Elite Four", "Morrow... is my name. Your Pokemon look tired. Shall we make them... rest?",
     "...Impressive. Go on, then.", 68),
    ("Drakon", "dragon", "Elite Four", "I am Drakon, the strongest of the Elite Four. Dragons bow to no one!",
     "You... you beat my dragons. The final awaits you.", 70),
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
    if cond == "shinyparty":
        return any(m.get("shiny") for m in game["party"])
    if cond.startswith("partylevel>="):
        return any(m["level"] >= int(cond[12:]) for m in game["party"])
    if cond.startswith("corrupted>="):
        return len(game.get("corrupted", [])) >= int(cond[11:])
    if cond.startswith("rifts>="):
        return rifts_sealed(game) >= int(cond[7:])
    if cond.startswith("customstone>="):
        from .riftdex import custom_stones
        mine = set(game.get("megastones", []))
        return sum(1 for k, _, _ in custom_stones(dex) if k in mine) >= int(cond[13:])
    if cond.startswith("name:"):
        return game.get("name", "").upper() in cond[5:].split(",")
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
            if f and "primal" not in f["key"] and not f.get("custom"):
                out.append((f["key"], mega_item_name(dex, f), e["id"]))
    return out


def stone_name(dex, key):
    from .riftdex import custom_stones
    for k, name, _ in all_stones(dex) + custom_stones(dex):
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
    for j in range(len(A.GYMS)):
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
    taken = {gym_stone(dex, k) for k in range(len(A.GYMS))} | set(QUEST_STONES.values())
    free = [s for s in stones if s not in taken]
    random.Random(77).shuffle(free)
    return {r: free[(r - 1) * 2:(r - 1) * 2 + 2] for r in range(1, A.NUM_ROUTES + 1)}


def rift_stone(dex, r):
    """The Mega Stone sealed inside route r's Mega Rift (none of these can be found anywhere else)."""
    stones = [s[0] for s in _ordinary_stones(dex)]
    taken = {gym_stone(dex, k) for k in range(len(A.GYMS))} | set(QUEST_STONES.values())
    taken |= {k for v in route_stones(dex).values() for k in v}
    free = [s for s in stones if s not in taken]
    random.Random(4242).shuffle(free)
    return free[(r - 1) % len(free)] if free else None


def mega_form(dex, key):
    """The form id for a Mega Stone key (e.g. 'charizard-mega-x' -> 10034)."""
    return next((e["id"] for e in dex.all.values() if e["key"] == key), None)


def echo_species(dex):
    """Who can turn up in an echo rift: any Pokemon with a Mega Evolution (ours included), non-legendary."""
    out = []
    for e in dex.all.values():
        if e["default"] and not (e["legendary"] or e["mythical"]) and e["species"] not in A.SPECIAL_IDS:
            forms = [f for f in e.get("megas", []) if f in dex.all and "primal" not in dex.all[f]["key"]]
            out += forms
    return sorted(out)


def _rift_spot(area, r):
    """An open spot off the path for a route's rift."""
    rows = area["rows"]
    rng = random.Random(r * 313)
    spots = [(x, y) for y in range(8, len(rows) - 8) for x in range(1, A.COLS - 1)
             if rows[y][x] in '.,"' and all(rows[y][xx] != "=" for xx in range(max(0, x - 1), min(A.COLS, x + 2)))]
    return rng.choice(spots) if spots else (2, len(rows) // 2)


QUEST_STONES = {"q_letter": "venusaur-mega", "q_psyduck": "alakazam-mega", "q_rift1": "gyarados-mega",
                "q_rift2": "gengar-mega", "q_vex": "garchomp-mega", "q_starter": None}


# ====================================================================== story battles
def rival_team(world, game, level, size):
    dex = world.dex
    first = dex.all[game["party"][0]["species"]] if game.get("starter") is None else dex.all[game["starter"]]
    trio = A.starters(dex)   # Kanto's three (or the randomizer's)
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
        return rival_team(world, game, 20, 3), {"name": RIVAL, "look": "rival", "money": 2100, "ai": "normal",
                                               "lose": "Tch. You got lucky. Next time I'll crush you!"}
    if key == "rival_dark":   # Blake with the corrupted stone Team Rocket gave him
        team = rival_team(world, game, 47, 5)
        ace = team[-1]
        megas = dex.all[A.grown_species(dex, dex.all[ace["species"]], 100)["id"]].get("megas", [])
        if megas:
            ace["species"] = A.grown_species(dex, dex.all[ace["species"]], 100)["id"]
            ace["mega"], ace["corrupt"] = megas[0], True
        return team, {"name": RIVAL, "look": "rival", "money": 5000, "ai": "hard",
                      "lose": "Stop... STOP! It's hurting itself! Make it stop!"}
    if key == "elias":   # the post-game: Elias and the Megas the rift showed him
        team = []
        for nm, form in (("snorlax", "snorlax-mega"), ("arcanine", "arcanine-mega"), ("typhlosion", "typhlosion-mega"),
                         ("lapras", "lapras-mega"), ("flygon", "flygon-mega"), ("togekiss", "togekiss-mega")):
            e, f = dex.get(nm), dex.get(form)
            if e:
                mon = A.make_mon(dex, e, 76, rng, shiny=False)
                if f:
                    mon["mega"] = f["id"]
                team.append(mon)
        return team, {"name": ELIAS, "look": "elias", "money": 20000, "ai": "insane",
                      "lose": "Ha! Ten years in a rift and I still can't beat a Champion. Well fought."}
    if key == "rival3":
        return rival_team(world, game, 60, 6), {"name": RIVAL, "look": "rival", "money": 7800, "ai": "hard",
                                               "lose": "...You're really strong. Win that tournament for both of us."}
    if key.startswith("grunt"):
        lv = {"grunt1": 12, "grunt2": 24, "grunt3": 34, "grunt4": 40}.get(key, 20)
        team = world.team_for(["poison", "dark"], lv, 2 + (lv > 30), rng)
        return team, {"name": "Rocket Grunt", "look": "grunt", "money": 50 * lv, "ai": "normal",
                      "lose": "No way! Team Rocket lost to a kid?!"}
    if key == "admin":
        team = world.team_for(["poison", "dark", "ghost"], 39, 4, rng, strong=True)
        return team, {"name": f"Rocket Admin {ADMIN}", "look": "admin", "money": 4000, "ai": "hard",
                      "lose": "Fine! Take your silly stone back!"}
    if key == "vex1":
        team = world.team_for(["dark", "psychic", "steel"], 45, 5, rng, strong=True)
        return team, {"name": f"Rocket Boss {BOSS}", "look": "boss", "money": 6000, "ai": "hard",
                      "lose": "Interesting... You are a variable I did not plan for."}
    if key == "vex2":
        team = world.team_for(["dark", "dragon", "steel"], 64, 5, rng, strong=True)
        ace = A.make_mon(dex, dex.get("garchomp"), 66, rng, shiny=False)
        ace["mega"], ace["corrupt"] = dex.get("garchomp")["megas"][0], True   # the last stone, corrupted
        return team + [ace], {"name": f"Rocket Boss {BOSS}", "look": "boss", "money": 10000, "ai": "insane",
                              "lose": "Impossible... The Engine... it's overloading!"}
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
        ace = A.make_mon(dex, dex.get("rayquaza"), 74, rng, shiny=False)
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
    # the story was written for the first 8-gym region: map this place back to its old town / route number
    inv = {v: k for k, v in A.LEGACY.items()}
    real_route = area.get("route")
    town = inv.get(area.get("town")) if area.get("kind") == "town" else None
    route = inv.get(real_route)
    rtown = area.get("town") if area.get("kind") == "town" else None

    def add(**n):
        n.setdefault("face", "down")
        n.setdefault("name", "")
        out.append(n)

    if index == 0:   # Rootleaf Town
        add(id="rival_home", kind="story", look="rival", x=7, y=12, face="down", sight=3, name=RIVAL, auto=True,
            **{"if": "!rival1"}, script=[
                ("say", RIVAL, ["Hey! Gramps - I mean, Prof. Hazel - gave you a Pokemon too?",
                                "Then you're battling me. Right now! I need to get strong. FAST."]),
                ("battle", "rival1"),
                ("say", RIVAL, ["Hmph. I'll train way harder than you.",
                                "...Someday I'm going to find out what happened to my dad. See you at the Tournament!"]),
                ("flag", "rival1")])
        add(id="pond_elder", kind="talk", look="villager", x=5, y=21, face="left", name="Old Man",
            **{"if": ["!first_rift", "!rift_zero"]},
            lines=["Ten years ago this pond glowed purple for a whole night.",
                   "Prof. Hazel's boy, Elias, was studying it. By morning he was gone. His Pokemon too.",
                   "Hazel never talks about it. Blake was only little... he still comes and stares at the water."])
        add(id="pond_elder2", kind="talk", look="villager", x=5, y=21, face="left", name="Old Man",
            **{"if": ["first_rift", "!rift_zero"]},
            lines=["The pond! It's glowing again, just like ten years ago!",
                   "That's no ordinary rift. Only a Champion should go near it..."])
        add(id="pond_elder3", kind="talk", look="villager", x=5, y=21, face="left", name="Old Man",
            **{"if": "rift_zero"},
            lines=["Elias is home. Ten years, and he walked out of that pond like he'd popped out for milk.",
                   "Hazel cried for an hour. Then she made him do the dishes."])
        add(id="elias_home", kind="story", look="elias", x=11, y=8, face="down", name=ELIAS,
            **{"if": ["rift_zero", "!elias_beaten"]}, script=[
                ("say", ELIAS, [f"{game['name']}. I owe you my life - and my family.",
                                "Inside the rift, time doesn't move. I saw Mega Evolutions no one has ever seen:",
                                "Snorlax standing tall, Arcanine burning blue, Togekiss crowned with light...",
                                "Their stones are scattered under the routes. Your Mega Radar can find them.",
                                "But first - let a scientist see the trainer who sealed nineteen rifts. Battle me!"]),
                ("battle", "elias"),
                ("say", ELIAS, ["...Mother was right about you.",
                                "Listen. The rifts weren't only Giovanni's doing. His Engine just widened cracks",
                                "that were already there. Cracks in creation itself.",
                                "Inside the First Rift I felt something vast watching me. Patient. Ancient.",
                                "It's waiting at the summit of Victory Road. I think it's waiting for YOU."]),
                ("flag", "elias_beaten"), ("flag", "origin_quest")])
        add(id="elias_after", kind="talk", look="elias", x=11, y=8, face="down", name=ELIAS,
            **{"if": ["elias_beaten", "!arceus"]},
            lines=["The summit of Victory Road. Whatever is up there... it built the world we live in.",
                   "Bring your strongest team. And Full Restores. Lots of Full Restores."])
        add(id="elias_end", kind="talk", look="elias", x=11, y=8, face="down", name=ELIAS,
            **{"if": "arceus"},
            lines=["You met Arceus. You actually met Arceus.",
                   "I'm rewriting ten years of research. Blake says I'm 'being a nerd about it'. He's right."])
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
    if town == 1:   # Pebblecrest: Team Rocket shows up
        add(id="grunt1", kind="story", look="grunt", x=11, y=13, face="up", name="Rocket Grunt", **{"if": "!grunt1"},
            script=[("say", "Rocket Grunt", ["Hey! This gym is closed! Team Rocket is searching it for Mega Stones!",
                                           "The boss has a machine - built from some missing professor's notes -",
                                           "and it eats Mega Stones for breakfast. ...You want in? Then beat me!"]),
                    ("battle", "grunt1"),
                    ("say", "Rocket Grunt", ["Ugh... Whatever! The boss will get every stone in the region anyway!"]),
                    ("flag", "grunt1")])
        add(id="q_fire_boy", kind="quest", quest="q_fire", look="Youngster", x=12, y=14, face="left")
    if town == 2:   # Tidewater: the Key Stone
        add(id="hazel_key", kind="story", look="prof", x=4, y=7, name="Prof. Hazel",
            **{"if": ["badges>=2", "!keystone"]}, script=[
                ("say", "Prof. Hazel", [f"{game['name']}! Two badges already? Wonderful!",
                                        "Listen. Team Rocket is tearing holes in the world - MEGA RIFTS.",
                                        "Any Pokemon caught in one is forced to Mega Evolve, and goes wild.",
                                        "...I've seen one before. Ten years ago, at the pond in Rootleaf.",
                                        "My son Elias was researching Mega energy there. Blake's father.",
                                        "The rift took him, and his Pokemon. I've never found a trace.",
                                        "Team Rocket's machine is built from HIS notes. I'd know them anywhere.",
                                        "When a Pokemon holds its Mega Stone and its trainer has a KEY STONE,",
                                        "it can MEGA EVOLVE in battle - by choice, as a partner.",
                                        "Take this Key Stone. With it you can see the rifts on every route.",
                                        "Calm the Pokemon inside and the rift seals... leaving its Mega Stone!"]),
                ("keystone",), ("flag", "keystone"), ("give", "mega-radar", 1),
                ("say", "Prof. Hazel", ["In battle, press M (or the MEGA button) before picking a move.",
                                        "Gym Leaders have stones too. And some are hidden on the routes - look for "
                                        "sparkles on the ground!",
                                        "That MEGA RADAR picks up stones buried deep underground. Use it from your "
                                        "BAG on a route, follow the signal, and dig!",
                                        "Some buried stones are CORRUPTED. They give staggering power... "
                                        "but they eat away at the Pokemon using them. Careful.",
                                        "And... keep an eye on Blake for me. He's chasing these rifts too.",
                                        "I'm afraid of what he'd do to get his father back."])])
        add(id="hazel_key_wait", kind="talk", look="prof", x=4, y=7, name="Prof. Hazel", **{"if": "!badges>=2"},
            lines=["Oh, hello! Come and find me when you have two badges. I have something for you."])
        add(id="q_letter_man", kind="quest", quest="q_letter", look="Hiker", x=12, y=14, face="left")
        add(id="q_dex10_aide", kind="quest", quest="q_dex10", look="prof", x=2, y=14, face="right",
            name="Hazel's Aide")
    if route == 3:
        add(id="rival2", kind="story", look="rival", x=7, y=len(area["rows"]) // 2, face="down", sight=4, auto=True,
            name=RIVAL, **{"if": "!rival2"}, script=[
                ("say", RIVAL, ["There you are! I've been training nonstop.",
                                "...Gramps told you, didn't she. About my dad.",
                                "Don't look at me like that. If a rift took him, a rift can give him back.",
                                "And I'll be strong enough to go in after him. Starting with beating YOU!"]),
                ("battle", "rival2"),
                ("say", RIVAL, ["Tch. Still not strong enough...", "Whatever. I'll find another way."]),
                ("flag", "rival2")])
        add(id="red_gyarados", kind="static", pokemon="gyarados", level=30, shiny=True, x=_pond_edge(area), y=None,
            **{"if": "!red_gyarados"}, script=[("say", "", ["The water is churning... A huge red Pokemon leaps out!"]),
                                               ("wild", "gyarados", 30, True), ("flag", "red_gyarados")])
    if town == 3:   # Voltara
        add(id="grunt2", kind="story", look="grunt", x=4, y=12, face="right", sight=4, auto=True, name="Rocket Grunt",
            **{"if": "!grunt2"}, script=[
                ("say", "Rocket Grunt", ["You again?! Team Rocket's admin is in Toxmire Town. Don't you dare follow!"]),
                ("battle", "grunt2"), ("flag", "grunt2")])
        add(id="egg_joke", kind="talk", look="Biker", x=12, y=20, face="left",
            lines=["My Electric Pokemon stopped working yesterday.",
                   "Have you tried turning it off and on again? ...It worked."])
        add(id="pika_hint", kind="talk", look="old_man_1", x=3, y=14, face="right", name="Old Man",
            lines=["When I was a boy, a little yellow mouse lived behind the fence by the Gym.",
                   "It only ever came out for trainers who'd beaten this town's Gym Leader.",
                   "...I wonder if it's still back there."])
        # the secret Pikachu: squeezed behind the power-lot fence next to the Gym
        add(id="pikachu", kind="static", pokemon="pikachu", level=0, x=12, y=7, face="down",
            **{"if": ["badges>=5", "!pikachu"]}, script=[
                ("say", "", ["Something yellow is hiding behind the fence...", "Pika? Pika-pi!",
                             "The Pikachu sniffs your hand. It looks like it wants to come with you!"]),
                ("gift", 25, 18), ("flag", "pikachu")])
    if route == 4:
        add(id="q_ranger", kind="quest", quest="q_route4", look="Ace Trainer", x=2, y=len(area["rows"]) - 4,
            face="right", name="Ranger")
    if route == 5:
        add(id="snorlax", kind="static", pokemon="snorlax", level=30, x=7, y=len(area["rows"]) // 2 + 3,
            **{"if": "!snorlax"}, script=[("say", "", ["A huge Pokemon is fast asleep in the middle of the road!",
                                                       "...It woke up! It looks angry!"]),
                                          ("wild", "snorlax", 30, False), ("flag", "snorlax")])
    if rtown == 8:   # Brawlport: Morga makes Blake an offer
        add(id="morga_offer", kind="story", look="admin", x=7, y=6, face="down", sight=4, auto=True,
            name=f"Admin {ADMIN}", **{"if": ["badges>=7", "!morga_offer"]}, script=[
                ("say", "", ["Down by the docks, a Rocket Admin is talking to someone in a dark jacket..."]),
                ("say", f"Admin {ADMIN}", ["...a seat by the First Rift, the moment the Engine opens it.",
                                            "All you have to do is use this. Think of what you'll find inside."]),
                ("say", RIVAL, ["...Fine. Give it here."]),
                ("say", f"Admin {ADMIN}", ["Smart boy. Oh look - your little friend. Too late, sweetie!",
                                            "Come find me in Toxmire Town, if you dare."]),
                ("say", "", ["Morga and Blake are gone before you can reach them..."]),
                ("flag", "morga_offer")])
    if town == 5:   # Toxmire: Team Rocket's admin
        add(id="admin", kind="story", look="admin", x=7, y=9, face="down", sight=5, auto=True,
            name=f"Admin {ADMIN}", **{"if": "!admin"}, script=[
                ("say", f"Admin {ADMIN}", ["So you're the brat who keeps beating our grunts.",
                                            "These Mega Stones will power Boss Giovanni's Rift Engine.",
                                            "Oh, and your little friend Blake? He took my offer.",
                                            "One corrupted stone, in exchange for a seat by the First Rift",
                                            "when we open it. Family reunions are SO touching."]),
                ("battle", "admin"),
                ("say", f"Admin {ADMIN}", ["Grr... Here, take it! The boss has plenty more in Mindspire City!",
                                            "And Blake's gone to Duskmoor to try out his new toy. Hope he survives it!"]),
                ("mega", QUEST_STONES["q_rift1"]), ("flag", "admin")])
    if route == 6:
        add(id="lost_psyduck", kind="static", pokemon="psyduck", level=0, x=_quiet_spot(area), y=None,
            **{"if": ["q_psyduck_started", "!q_psyduck_found"]},
            script=[("say", "", ["It's a Psyduck with a little bow on its head. It looks lost.",
                                 "Psyduck started following you!"]), ("flag", "q_psyduck_found")])
    if town == 6:   # Mindspire: Boss Giovanni
        add(id="vex1", kind="story", look="boss", x=7, y=12, face="down", sight=5, auto=True, name=f"Boss {BOSS}",
            **{"if": ["admin", "!vex1"]}, script=[
                ("say", f"Boss {BOSS}", ["I am Giovanni, leader of Team Rocket.",
                                         "Mega Evolution is the ultimate power. Why should it belong to children?",
                                         "A foolish professor found the source of it ten years ago - and fell in.",
                                         "His notes were very thorough. My Rift Engine tears the world open.",
                                         "Every rift feeds it Mega Stones. With enough, it opens the FIRST rift,",
                                         "and whatever power waits at its heart... will answer to me."]),
                ("battle", "vex1"),
                ("say", f"Boss {BOSS}", ["You are strong. Keep your stone. We will meet at Victory Road."]),
                ("mega", QUEST_STONES["q_rift2"]), ("flag", "vex1")])
        add(id="q_psyduck_girl", kind="quest", quest="q_psyduck", look="Lass", x=12, y=14, face="left")
    if rtown == 12:   # Duskmoor: Blake and the corrupted stone
        add(id="rival_dark", kind="story", look="rival", x=7, y=14, face="down", sight=5, auto=True, name=RIVAL,
            **{"if": ["vex1", "!rival_dark"]}, script=[
                ("say", RIVAL, [f"{game['name']}. Don't try to stop me.",
                                "Team Rocket is going to open the First Rift. Dad's in there. I KNOW he is.",
                                "Look what Morga gave me - a corrupted Mega Stone. Feel that power!",
                                "With this, nobody can stop me. Not even you!"]),
                ("battle", "rival_dark"),
                ("say", "", ["Blake's Pokemon collapses. Black energy crackles off it...",
                             "Blake drops to his knees beside it."]),
                ("say", RIVAL, ["No, no, no... I'm sorry. I'm so sorry, buddy.",
                                "I was so busy chasing Dad, I didn't see what this thing was doing to you.",
                                "...Dad would never have used something like this. Never."]),
                ("say", "", ["Blake hurls the corrupted stone into the marsh. It sinks with a hiss.",
                             "Slowly, his Pokemon opens its eyes."]),
                ("say", RIVAL, [f"...Thanks, {game['name']}. You beat some sense into me.",
                                "Team Rocket used me. I'm done with them - and I'm going to make them pay.",
                                "Here. These are for you. Go win the stuff I can't."]),
                ("give", "full-restore", 3), ("heal",), ("flag", "rival_dark")])
    if town == 7:
        add(id="q_dex30_sci", kind="quest", quest="q_dex30", look="prof", x=3, y=14, face="right", name="Scientist")
    if town == 8:
        add(id="q_mega_maniac", kind="quest", quest="q_stones", look="Psychic", x=12, y=14, face="left",
            name="Mega Maniac")
    if route == 8:
        add(id="rival3", kind="story", look="rival", x=7, y=6, face="down", sight=4, auto=True, name=RIVAL,
            **{"if": "!rival3"}, script=[
                ("say", RIVAL, ["The World Tournament is right past Victory Road.",
                                "No corrupted stones this time. No shortcuts. Just me and my team,",
                                "the way it should've been all along. Give it everything you've got!"]),
                ("battle", "rival3"),
                ("say", RIVAL, ["...Yeah. You're better than me. I can live with that.",
                                "Giovanni's waiting on Victory Road with the Rift Engine.",
                                "I'll keep his grunts off your back. You take him down. Deal?"]),
                ("heal",), ("flag", "rival3")])
    if route == 9:   # Victory Road
        add(id="vex2", kind="story", look="boss", x=7, y=8, face="down", sight=5, auto=True, name=f"Boss {BOSS}",
            **{"if": ["vex1", "!vex2"]}, script=[
                ("say", f"Boss {BOSS}", ["You came. The Rift Engine is ready.",
                                         "One stone left. A corrupted one - the most powerful stone in the world.",
                                         "My Garchomp will wear it, and the First Rift will open for ME."]),
                ("battle", "vex2"),
                ("say", "", ["The Rift Engine shrieks. Purple light pours out of every seam!"]),
                ("say", f"Boss {BOSS}", ["Impossible... it's overloading! Without the last stone it can't hold!",
                                         "...Team Rocket is finished. Take the stone. Take all of it.",
                                         "But know this: the First Rift is open now. Back where it all began."]),
                ("say", RIVAL, [f"{game['name']}! You did it! Rocket's running for the hills!",
                                "...Wait. 'Back where it began'? That's Rootleaf. That's the pond...",
                                "Win the Tournament first. Become Champion. Then we go get my dad. Together."]),
                ("mega", QUEST_STONES["q_vex"]), ("flag", "vex2"), ("flag", "first_rift")])
        add(id="arceus", kind="static", pokemon="arceus", level=80, x=7, y=3,
            **{"if": ["origin_quest", "!arceus"]}, script=[
                ("say", "", ["The summit of Victory Road. The air shimmers like heat over a road...",
                             "Every rift you ever sealed is humming in your bag, all at once."]),
                ("say", "???", ["...CHILD OF THE RIFTS.",
                                "YOU HAVE MENDED NINETEEN WOUNDS IN MY WORLD. ONE HUMAN'S GREED OPENED THEM.",
                                "BUT A WORLD THAT TEARS SO EASILY... SHOULD IT BE KEPT?",
                                "SHOW ME. FIRST, FACE THE ONE WHO GUARDS THE SPACE BETWEEN."]),
                ("riftboss", "giratina-origin", 76, "entropy"),
                ("say", "???", ["...THE GUARDIAN YIELDS. THEN FACE ME. I AM ARCEUS. I AM THE ORIGIN.",
                                "IF YOU WOULD KEEP THIS WORLD, PROVE IT IS WORTH KEEPING!"]),
                ("riftboss", "arceus", 80, "surge"),
                ("say", "", ["The light softens. Arceus lowers its head.",
                             "Far below, every rift scar in the Brawl region fades away, like it was never there."]),
                ("say", "Arceus", ["THE WORLD IS WORTH KEEPING. YOU HAVE SHOWN ME WHY.",
                                   "NO RIFT WILL OPEN AGAIN. LIVE WELL, CHAMPION OF ALL THINGS."]),
                ("say", RIVAL, [f"{game['name']}!! You're okay! We saw the light from Rootleaf!",
                                "Dad says that was ARCEUS. Like, THE Arceus. You battled GOD?!"]),
                ("say", ELIAS, ["The rifts are gone. All of them. Ten years of my life, finished in an afternoon.",
                                "Thank you. From all three of us."]),
                ("say", "Prof. Hazel", [f"{game['name']}... I gave you a Pokemon and asked you to fill a Pokedex.",
                                        "You brought my family home and saved the world.",
                                        "I think that counts as completing your research."]),
                ("give", "master-ball", 3), ("flag", "arceus"), ("flag", "true_ending")])
    if route == 2:
        add(id="mew", kind="static", pokemon="mew", level=50, x=1, y=4, **{"if": ["champion", "!mew"]},
            script=[("say", "", ["There's something hiding behind the trees... It's giggling!"]),
                    ("wild", "mew", 50, False), ("flag", "mew")])
    if real_route and game.get("keystone"):   # Mega Rifts: tears Team Rocket's machine leaves behind
        key = rift_stone(dex, real_route)
        fid = mega_form(dex, key) if key else None
        if fid and not has(game, f"rift_{real_route}"):
            lv = A.World.route_levels(real_route)[1] + 5
            moved = game.get("rift_moved", {}).get(str(real_route), 0)   # it moves after a collapse
            add(id=f"rift_{real_route}", kind="rift", x=_rift_spot(area, real_route + 1000 * moved), y=None,
                pokemon=fid, level=lv, script=[
                ("say", "", ["The air here is torn open... it's crackling with Mega energy!",
                             "Something is raging inside the rift!"]),
                ("rift", fid, lv),
                ("say", "", ["The Pokemon calmed down... and the rift sealed itself shut.",
                             "Something was left behind on the ground!"]),
                ("mega", key), ("flag", f"rift_{real_route}")])
    echo = game.get("echo") or {}
    if echo.get("area") == index and real_route:   # an echo rift: a sealed rift flickering open again
        add(id="echo_rift", kind="rift", echo=True, x=(echo["x"], echo["y"]), y=None, pokemon=echo["pid"],
            level=echo["lv"], script=[
                ("say", "", ["The sealed rift is flickering open again...", "A wild Mega Pokemon is raging inside!"]),
                ("rift", echo["pid"], echo["lv"]),
                ("say", "", ["The echo rift faded away."])])
    if index == 0 and has(game, "first_rift") and game.get("champion") and not has(game, "rift_zero"):
        fid = mega_form(dex, "mewtwo-mega-y")
        if fid:   # sealing every rift wakes the first one, right at home
            add(id="rift_zero", kind="rift", x=3, y=23, pokemon=fid, level=75, script=[
                ("say", RIVAL, ["This is it. The First Rift.", "Dad's in there somewhere. Let's go. Together."]),
                ("say", "", ["You step into the light... Inside, time stands still.",
                             "A Mewtwo, wreathed in Mega energy, stands guard over a man in a lab coat."]),
                ("say", ELIAS, ["...Blake? Is that... you've gotten so tall...",
                                "Careful! Mewtwo was caught in the blast with me. It's been raging for ten years!",
                                "Calm it down - and we can all go home!"]),
                ("rift", fid, 75),
                ("say", "", ["Mewtwo's Mega energy fades. The First Rift folds shut behind you."]),
                ("say", RIVAL, ["DAD!"]),
                ("say", ELIAS, ["Ten years... it felt like ten minutes. Blake, I'm so sorry.",
                                f"And you - you're the one who sealed the rifts. {game['name']}, was it?",
                                "Come find me at Mother's lab once I've had a shower. I owe you a battle."]),
                ("say", "", ["Mewtwo left behind two stones that hum with power..."]),
                ("mega", "mewtwo-mega-y"), ("mega", "mewtwo-mega-x"), ("flag", "rift_zero"), ("flag", "vale_home")])
    if index == 0 and all(has(game, f"rift_{r}") for r in range(1, A.NUM_ROUTES + 1)) and \
            not has(game, "rift_keeper"):   # sealing every rift on the routes: Hazel's thanks
        add(id="rift_keeper", kind="story", look="prof", x=9, y=9, face="down", name="Prof. Hazel", script=[
            ("say", "Prof. Hazel", ["Every rift on every route... sealed. You did it.",
                                    "You're a true RIFT KEEPER. Elias would be so proud. I'm so proud.",
                                    "Take these. Catch something legendary for me."]),
            ("give", "master-ball", 2), ("flag", "rift_keeper")])
    if rtown:
        _town_extras(world, area, rtown, game, add, out)
    if index == len(world.areas) - 1:   # the League town
        add(id="league_guard", kind="talk", look="guard", x=8, y=8, face="down",
            lines=["Beyond here is the POKeMON WORLD TOURNAMENT.", "Only trainers with all 18 badges may enter."])
    # hidden Mega Stones on routes (sparkles), and the hidden items you find by checking the ground
    out = [n for n in out if check(game, dex, n.get("if")) and not (n.get("once") and has(game, n["once"]))]
    _settle(area, out)
    return out


WALK = set('.,"=_')


def _settle(area, npcs):
    """Anyone standing on a wall, tree or roof (the region grew since their spot was picked) steps to the
    nearest free walkable tile."""
    rows = area["rows"]
    taken = {(n["x"], n["y"]) for n in area.get("npcs", [])}

    def free(x, y):
        return 0 <= y < len(rows) and 0 <= x < len(rows[0]) and rows[y][x] in WALK and (x, y) not in taken
    for n in npcs:
        x, y = n.get("x"), n.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            continue
        if not free(x, y):
            best = None
            for r in range(1, 12):
                ring = [(x + dx, y + dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1)
                        if max(abs(dx), abs(dy)) == r]
                ring.sort(key=lambda p: abs(p[0] - x) + abs(p[1] - y))
                best = next((p for p in ring if free(*p)), None)
                if best:
                    break
            if best:
                n["x"], n["y"] = best
        taken.add((n["x"], n["y"]))


# townsfolk with something to say, per town (real town number): (look, name, lines, condition)
TOWN_TALK = {
    1: [("Hiker", "Hiker", ["Pebblecrest is built on a mountain of rock. Petra's Pokemon are just as stubborn.",
                            "Water and Grass moves crack them right open, though!"], None),
        ("Lass", "", ["Team Rocket ran off with the museum's fossil Mega Stone display!",
                      "...It was a replica. The real ones are in the vault. Hehe."], "grunt1")],
    2: [("Bug Catcher", "", ["The trees here are older than the region itself, Grandpa says.",
                             "Sometimes the leaves whisper. Like they're remembering something."], None)],
    3: [("Swimmer", "", ["Coral's Gym floods at high tide. Bring an Electric or Grass type!"], None),
        ("villager", "Fisherman", ["A red Gyarados jumped out of the lake on the route north of here!",
                                   "Nobody believes me. NOBODY."], "!red_gyarados"),
        ("villager", "Fisherman", ["You CAUGHT the red Gyarados?! I KNEW it was real!"], "red_gyarados")],
    4: [("mom", "Baker", ["Patty's the Gym Leader AND she runs the bakery. Her Normal types are tough as dough!",
                          "...Sorry. I've been waiting all day to say that one."], None)],
    5: [("Biker", "", ["The power plant here runs on Electric Pokemon. They get paid in berries.",
                       "...Better pay than me, honestly."], None),
        ("Youngster", "", ["Up, up, down, down, left, right, left, right... B, A, START!",
                           "...Nothing happened. My brother lied to me AGAIN."], None)],
    6: [("Picnicker", "", ["The wind on the cliffs is so strong, Flying Pokemon practice here every day.",
                           "Skye says if you can battle up here, you can battle anywhere."], None)],
    7: [("Beauty", "", ["Fern grows her Grass Pokemon in the greenhouse behind the Gym.",
                        "Fire types aren't allowed in. For obvious reasons."], None)],
    8: [("Black Belt", "", ["Brawlport! Where sailors arm-wrestle Machamp for fun!",
                            "I lost eleven times. Then Machamp let me win. We're best friends now."], None),
        ("villager", "Dockhand", ["A Rocket Admin was down by the docks with some kid in a dark jacket.",
                                  "Looked like trouble. The kid looked... sad, mostly."], "morga_offer")],
    9: [("villager", "", ["Toxmire's marsh gas makes your eyes water. Nox says you get used to it.",
                          "Nox has been saying that for nine years."], None)],
    10: [("Lass", "", ["Glimmerdell's fairies only show themselves to trainers with kind Pokemon.",
                       "...Pixie is NOT kind. Pixie is terrifying. Be careful."], None)],
    11: [("Psychic", "", ["I foresaw your arrival. I also foresaw you'd ask about the Gym.",
                          "Sage reads minds, so don't think about your next move. Just do it."], None),
         ("Psychic", "", ["Giovanni stood right where you're standing. His mind was so... cold."], "vex1")],
    12: [("villager", "Old Woman", ["Duskmoor is quiet. Too quiet. That's why the ghosts like it.",
                                    "If a little girl asks you about her Pokemon... answer her kindly."], None)],
    13: [("Hiker", "", ["Emberpeak's volcano hasn't erupted in a hundred years.",
                        "Blaze says that's because her Fire Pokemon keep it happy. I believe her."], None)],
    14: [("Ace Trainer", "", ["Steelhaven forges the region's Poke Balls. Every one passes a Ferris inspection.",
                              "Ferris dropped one on his foot once. The BALL was fine."], None),
         ("villager", "Engineer", ["The PC in my workshop says: TODO - ADD MORE SECRETS.",
                                   "...I don't know who wrote that. I don't own a PC."], None)],
    15: [("Swimmer", "", ["Swimming in Frostmere? In THIS weather? Yes. Every morning. It builds character.",
                          "Also hypothermia. But mostly character."], None)],
    16: [("Ace Trainer", "", ["Raven turns the Gym lights off for the whole battle.",
                              "Dark Pokemon don't mind. Your Pokemon might."], None)],
    17: [("Hiker", "", ["The sand here hides all kinds of things. Old stones, older bones.",
                        "Sometimes the ground glows at night. Mega Radar folk come from all over."], None)],
    18: [("Ace Trainer", "", ["Wyrmspire is the last Gym before the League. Draco's Dragons have never lost here.",
                              "...Well. Not before you, anyway."], "!badges>=18"),
         ("Ace Trainer", "", ["You beat Draco?! Then go. The World Tournament is waiting."], "badges>=18")],
}
SPOTS = [(2, 6), (12, 6), (1, 15), (13, 15), (3, 15), (11, 15), (2, 25), (12, 25), (4, 26), (10, 26), (1, 24),
         (13, 24), (4, 6), (10, 6), (2, 14), (12, 14), (3, 22), (11, 22), (1, 26), (13, 26)]


def _spot(area, used, i=0):
    """A free, walkable standing spot in a town (not in front of a door, not taken)."""
    rows = area["rows"]
    taken = used | {(n["x"], n["y"]) for n in area.get("npcs", [])}

    def ok(x, y):
        return (0 < y < len(rows) - 1 and 0 < x < len(rows[0]) - 1 and rows[y][x] in ".,=_" and
                (x, y) not in taken and rows[y - 1][x] != "D" and rows[y + 1][x] != "D")
    cands = SPOTS[i % len(SPOTS):] + SPOTS[:i % len(SPOTS)]
    for x, y in cands:
        if ok(x, y):
            return x, y
    for y in range(4, len(rows) - 2):
        for x in range(1, len(rows[0]) - 1):
            if ok(x, y):
                return x, y
    return None


def _town_extras(world, area, rtown, game, add, out):
    """Townsfolk, the new side quests and the secrets of each town."""
    used = {(n["x"], n["y"]) for n in out}

    def place(i, **n):
        xy = _spot(area, used, i)
        if xy:
            used.add(xy)
            n["x"], n["y"] = xy
            add(**n)
    for k, (look, name, lines, cond) in enumerate(TOWN_TALK.get(rtown, [])):
        if check(game, world.dex, cond):
            place(rtown * 3 + k, id=f"talk{rtown}_{k}", kind="talk", look=look, name=name, lines=lines,
                  face=["down", "left", "right"][k % 3])
    quest = {2: ("q_bugs", "Bug Catcher", "Bug Maniac"), 6: ("q_riftwatch", "Psychic", "Rift Watcher"),
             8: ("q_lv50", "Black Belt", "Coach"), 10: ("q_shiny", "Beauty", "Collector"),
             14: ("q_dex100", "prof", "Hazel's Aide"), 15: ("q_newmega", "Ace Trainer", "Mega Hunter"),
             17: ("q_purify", "Hiker", "Old Miner")}.get(rtown)
    if quest:
        place(rtown * 5, id=f"{quest[0]}_giver", kind="quest", quest=quest[0], look=quest[1], name=quest[2],
              face="down")
    if rtown == 3:   # the Magikarp salesman (it IS a good deal. probably.)
        if not has(game, "karp_offer"):
            place(31, id="karp_man", kind="story", look="villager", name="Salesman", face="down", script=[
                ("say", "Salesman", ["Psst! Kid! Want a MAGIKARP? Only 500 coins! A steal!",
                                     "Every one's a future Gyarados. Talk to me again if you want one!"]),
                ("flag", "karp_offer")])
        elif not has(game, "magikarp_deal"):
            place(31, id="karp_man", kind="story", look="villager", name="Salesman", face="down", script=[
                ("say", "Salesman", ["Back for the MAGIKARP? 500 coins, no refunds!"]), ("pay", 500),
                ("gift", 129, 5), ("say", "Salesman", ["Pleasure doing business! ...Hehe."]),
                ("flag", "magikarp_deal")])
    if rtown == 4 and not has(game, "legend_name"):   # a familiar name
        if check(game, world.dex, "name:RED,ASH,BLUE,GOLD,LEAF,GREEN,SILVER,ETHAN,LYRA"):
            place(41, id="legend_fan", kind="story", look="Hiker", name="Old Trainer", face="down", script=[
                ("say", "Old Trainer", [f"{game['name']}...? That name... I knew a trainer called that, long ago.",
                                        "Never said a word. Just battled. Beat everyone. Climbed a mountain and",
                                        "waited at the top for anyone strong enough to find him.",
                                        "Here. He'd want you to have these."]),
                ("give", "rare-candy", 5), ("flag", "legend_name")])
    if rtown == 12:
        if not has(game, "ghost_girl"):
            place(121, id="ghost_girl", kind="story", look="Lass", name="Little Girl", face="down", script=[
                ("say", "Little Girl", ["Have you seen my Pokemon? It's purple and it giggles.",
                                        "We were playing hide and seek... a long, long time ago."]),
                ("say", "", ["You blink. There's nobody there.",
                             "...Somewhere behind you, something giggles."]),
                ("flag", "ghost_girl")])
        if game.get("champion") and not has(game, "darkrai"):
            place(122, id="darkrai", kind="static", pokemon="darkrai", level=70, script=[
                ("say", "", ["Everyone in Duskmoor is having the same nightmare.",
                             "...The shadow at the end of the street is looking right at you."]),
                ("wild", "darkrai", 70, False), ("flag", "darkrai")])
    if rtown == 2 and game.get("champion") and not has(game, "celebi"):
        place(23, id="celebi", kind="static", pokemon="celebi", level=60, script=[
            ("say", "", ["The leaves whisper... a tiny green light drifts out from between the old trees.",
                         "It looks like it's travelled a very long way to meet you."]),
            ("wild", "celebi", 60, False), ("flag", "celebi")])
    if rtown == 6 and check(game, world.dex, ["rifts>=10", "!jirachi"]):
        place(62, id="jirachi", kind="static", pokemon="jirachi", level=50, script=[
            ("say", "", ["A star falls out of a sealed rift and lands at your feet...",
                         "It yawns. It's been asleep for a thousand years. It wants to grant you a wish!"]),
            ("wild", "jirachi", 50, False), ("flag", "jirachi")])


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


LAB_BALLS = [(8, 4), (9, 4), (10, 4)]   # the table in Hazel's lab (PalletTown_ProfessorOaksLab)
LAB_RIVAL = (5, 4)


def _room_npcs(world, kind, area, door, game):
    out = []
    if kind == "lab" and area == 0 and (game.get("starter") or not game.get("party")):   # chosen in the lab
        trio = A.starters(world.dex)
        mine = game.get("starter")
        theirs = trio[(trio.index(mine) + 1) % 3] if mine in trio else None
        for i, (x, y) in enumerate(LAB_BALLS):
            if trio[i] in (mine, theirs):
                continue
            out.append({"id": f"starter_ball{i}", "kind": "ball", "x": x, "y": y, "face": "down", "fixed": True,
                        "pokemon": trio[i], "name": ""})
        if has(game, "rival1"):
            return out
        out.append({"id": "rival_lab", "kind": "talk", "look": "rival", "x": LAB_RIVAL[0], "y": LAB_RIVAL[1],
                    "face": "down", "fixed": True, "name": RIVAL,
                    "lines": (["Go on, hurry up and pick one! I'm taking whichever's best against yours."]
                              if not mine else ["Heh. My Pokemon looks way tougher than yours."])})
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
    if kind == "house" and world.areas[area].get("town") == A.LEGACY[4] and door[0] < 7:   # the letter's sister
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
        if len(game.get("badges", [])) < len(A.GYMS):
            out.append({"id": "host", "kind": "talk", "look": "guard", "x": 7, "y": 10, "face": "up",
                        "name": "Host", "lines": ["Welcome to the POKeMON WORLD TOURNAMENT!",
                                                  "Sorry - only trainers with all 18 Gym Badges can enter.",
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
QUESTS.update({
    "q_bugs": {"name": "Bug Maniac", "giver": "Bug Maniac in Mossgrove Town",
               "ask": ["Bugs are the BEST Pokemon. Don't argue.", "Show me a Bug-type in your party and I'll prove it!"],
               "need": "partytype:bug", "done": ["LOOK at those legs! A true bug fan! Here, have some Great Balls!"],
               "reward": [("give", "great-ball", 10)]},
    "q_riftwatch": {"name": "Rift Watcher", "giver": "Rift Watcher in Gustcliff City",
                    "ask": ["I chart the rifts from up here. They're getting worse.",
                            "Seal five of them for me and I'll make it worth your while."],
                    "need": "rifts>=5", "done": ["Five sealed! The sky's calmer already. Take these, hero!"],
                    "reward": [("give", "ultra-ball", 10), ("money", 5000)]},
    "q_lv50": {"name": "Raise a Champion", "giver": "Coach in Brawlport City",
               "ask": ["Strength is earned, kid. Raise a Pokemon to level 50 and show me."],
               "need": "partylevel>=50", "done": ["THAT is a trained Pokemon! You've got the spirit! Take these!"],
               "reward": [("give", "max-revive", 3), ("give", "rare-candy", 2)]},
    "q_shiny": {"name": "Something Shiny", "giver": "Collector in Glimmerdell Town",
                "ask": ["I collect shiny things. Shiny POKEMON are the shiniest things of all!",
                        "Bring one in your party and I'll pay handsomely."],
                "need": "shinyparty", "done": ["It SPARKLES! Ohh, I could look at it forever. Here - you've earned it!"],
                "reward": [("money", 20000), ("give", "rare-candy", 5)]},
    "q_dex100": {"name": "Living Legend", "giver": "Hazel's aide in Steelhaven City",
                 "ask": ["The Professor's dream is a complete Pokedex.", "Catch 100 different kinds of Pokemon!"],
                 "need": "caught>=100", "done": ["100 kinds! The Professor wants you to have her most precious ball."],
                 "reward": [("give", "master-ball", 1)]},
    "q_newmega": {"name": "Born of the Rift", "giver": "Mega Hunter in Frostmere Town",
                  "ask": ["They say there are Mega Stones no one's ever seen, buried under the routes.",
                          "Stones for Pokemon that were never meant to Mega Evolve. Dig one up for me!"],
                  "need": "customstone>=1",
                  "done": ["It's REAL! A brand-new Mega Stone! The rumours were true! Take these, you legend!"],
                  "reward": [("give", "rare-candy", 10)]},
    "q_purify": {"name": "The Stone Cleanser", "giver": "Old Miner in Duneholt City",
                 "ask": ["Corrupted stones... I can smell 'em on you.",
                         "I spent forty years down the mines. I know how to clean one. Bring me a corrupted stone."],
                 "need": "corrupted>=1", "done": ["Hold still... there. Clean as the day it was born."],
                 "reward": [("purify",)]},
})
KEY_ITEMS = {"mega-radar": ("Mega Radar", "Detects Mega Stones buried on a route. Use it, follow the signal, dig."),
             "lucky-charm": ("Lucky Charm", "A lucky charm someone dropped."),
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
           "arceus": "The Origin", "creator_beaten": "The Creator", "rift_zero": "The First Rift",
           "pikachu": "The Mouse Behind the Fence", "magikarp_deal": "The Magikarp Deal",
           "legend_name": "A Familiar Name", "ghost_girl": "The Girl in Duskmoor", "celebi": "Out of Time",
           "jirachi": "A Wish Upon a Rift", "darkrai": "The Nightmare", "rift_keeper": "Rift Keeper",
           "elias_beaten": "Like Father, Like Son", "true_ending": "The World Worth Keeping"}


def rifts_sealed(game):
    return sum(1 for r in range(1, A.NUM_ROUTES + 1) if has(game, f"rift_{r}"))


def secrets_found(game):
    return sum(1 for f in SECRETS if has(game, f))


def next_goal(game, dex):
    """One line telling you where the main story goes next."""
    b = len(game.get("badges", []))
    n = len(A.GYMS)
    gym = A.GYMS[b][0] if b < n else None
    if game.get("champion") and has(game, "first_rift") and not has(game, "rift_zero"):
        return "The First Rift is open at the pond in Rootleaf Town. Bring Blake's dad home."
    if has(game, "rift_zero") and not has(game, "elias_beaten"):
        return f"{ELIAS} is waiting outside Prof. Hazel's lab in Rootleaf Town."
    if has(game, "origin_quest") and not has(game, "arceus"):
        return "Something ancient waits at the summit of Victory Road..."
    if game.get("champion"):
        stones = len(game.get("megastones", []))
        from .riftdex import custom_stones
        return (f"You're the World Champion! Mega Stones: {stones}/{len(all_stones(dex)) + len(custom_stones(dex))}. "
                "Secrets still hide out there...")
    if not game.get("party"):
        return "Choose your first Pokemon from the three Poke Balls on Prof. Hazel's table."
    if not has(game, "rival1"):
        return f"Your rival {RIVAL} is waiting for you in Rootleaf Town."
    if b == 0 and not has(game, "grunt1"):
        return "Head north to Pebblecrest City. Something is going on at the Gym..."
    if b >= 2 and not game.get("keystone"):
        return "Prof. Hazel is waiting for you in Tidewater City."
    if b >= 7 and not has(game, "morga_offer"):
        return "Something's going on at the docks in Brawlport City..."
    if b >= 8 and not has(game, "admin"):
        return f"Team Rocket's Admin {ADMIN} is causing trouble in Toxmire Town!"
    if b >= 10 and not has(game, "vex1"):
        return f"Confront Boss {BOSS} of Team Rocket in Mindspire City."
    if has(game, "vex1") and b >= 11 and not has(game, "rival_dark"):
        return f"{RIVAL} has gone to Duskmoor Town with a corrupted Mega Stone. Stop him!"
    if b < n:
        return f"Badge {b + 1} of {n}: the {A.GYMS[b][2].upper()} Gym in {gym}."
    if not has(game, "vex2"):
        return f"Stop {BOSS} on Victory Road, then enter the World Tournament!"
    return "Enter the POKeMON WORLD TOURNAMENT and become the best trainer in the world!"
