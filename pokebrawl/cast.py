"""PokeBrawl's own cast, made the way the handheld games make new characters: palette swaps of the FireRed
sprites. Each look names an overworld sprite (graphics/object_events/pics/people), a battle picture
(graphics/trainers/front_pics) and the recolour rules (see frlg.recolor_palette).

Hues: red 0, orange 30, yellow 55, green 120, teal 175, blue 220, purple 275, pink 320."""

# rule = (hue from, hue to, new hue, saturation x, brightness x)


def _all(hue, sm=1.0, vm=1.0):
    """Every clothing colour to one hue (skin tones and reds-oranges are left alone)."""
    return ((45, 340, hue, sm, vm), (340, 45, hue, sm, vm, 0.47))


CAST = {
    # the player: teal cap, charcoal jacket
    "player": ("red_normal", "red", ((330, 20, 172, 1.0, 0.95), (200, 260, 225, 0.3, 0.75))),
    # Blake, the rival: orange
    "rival": ("blue", "rival_early", ((240, 300, 22, 1.1, 1.05),)),
    "rival_late": ("blue", "rival_late", ((240, 300, 22, 1.1, 1.05),)),
    # Prof. Oak: navy trousers
    "prof": ("prof_oak", "professor_oak", ((0, 60, 215, 1.0, 0.8),)),
    # Team Rocket, exactly as they are: grunts, Admin Morga and Boss Giovanni
    "grunt": ("rocket_m", "rocket_grunt_m", ()),
    "grunt_f": ("rocket_f", "rocket_grunt_f", ()),
    "admin": ("rocket_f", "rocket_grunt_f", ()),
    "boss": ("giovanni", "leader_giovanni", ()),
    # the eighteen Gym Leaders, each in their type's colours (numbered in Gym order)
    "leader0": ("sabrina", "leader_sabrina", _all(28, 0.9, 0.95)),          # Petra, rock
    "leader1": ("bug_catcher", "bug_maniac", _all(80, 1.0, 1.0)),          # Hive, bug
    "leader2": ("misty", "leader_misty", ((5, 50, 328, 1.0, 1.0),)),        # Coral, water: pink hair
    "leader3": ("woman_2", "lady", _all(20, 0.6, 1.0)),                    # Patty, normal
    "leader4": ("lt_surge", "leader_lt_surge", ((60, 160, 52, 1.2, 1.15),)),   # Zappa, electric
    "leader5": ("cooltrainer_m", "bird_keeper", _all(200, 1.0, 1.05)),     # Skye, flying
    "leader6": ("erika", "leader_erika", _all(118, 1.0, 1.0)),             # Fern, grass
    "leader7": ("black_belt", "black_belt", _all(2, 1.2, 0.95)),           # Knox, fighting
    "leader8": ("koga", "leader_koga", _all(288, 1.0, 1.0)),               # Nox, poison
    "leader9": ("lass", "lass", _all(330, 1.0, 1.05)),                     # Pixie, fairy
    "leader10": ("gentleman", "gentleman", _all(305, 1.0, 1.0)),           # Sage, psychic
    "leader11": ("channeler", "channeler", _all(268, 1.0, 0.85)),          # Wren, ghost
    "leader12": ("rocker", "biker", _all(8, 1.2, 1.0)),                    # Blaze, fire
    "leader13": ("worker_m", "engineer", _all(212, 0.35, 0.9)),            # Ferris, steel
    "leader14": ("picnicker", "picnicker", _all(192, 0.8, 1.1)),           # Nieve, ice
    "leader15": ("man", "burglar", _all(250, 0.6, 0.6)),                   # Raven, dark
    "leader16": ("cooltrainer_f", "cool_trainer_f", _all(36, 0.8, 0.8)),   # Terra, ground
    "leader17": ("cooltrainer_m", "cool_trainer_m", _all(235, 1.0, 0.8)),  # Draco, dragon
    # the Elite Four and World Champion Aurelia
    "frost": ("lorelei", "elite_four_lorelei", _all(200, 0.9, 1.05)),
    "brutus": ("bruno", "elite_four_bruno", ((0, 60, 12, 1.2, 0.9),)),
    "morrow": ("agatha", "elite_four_agatha", _all(272, 1.0, 0.9)),
    "drakon": ("lance", "elite_four_lance", ((330, 30, 168, 1.0, 0.85),)),
    "champ": ("beauty", "beauty", _all(45, 1.0, 1.05)),
    # the girl player: Leaf, as she is
    "player_f": ("green_normal", "leaf", ()),
}
BACK_PICS = {"player": "red", "player_f": "leaf"}
PLAYER = ["player"]


def set_player(gender):
    PLAYER[0] = "player_f" if gender == "GIRL" else "player"


def player_look():
    return PLAYER[0]

LEADERS = {f"leader{k}" for k in range(18)}


def overworld(look):
    """(people sprite name, recolour rules) for a look, or None."""
    c = CAST.get(look)
    return (c[0], c[2]) if c else None


def picture(look):
    """(front pic name, recolour rules) for a look, or None."""
    c = CAST.get(look)
    return (c[1], c[2]) if c else None
