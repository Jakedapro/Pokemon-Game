"""Type chart and the colors each type uses for labels and effects."""

TYPES = [
    "normal", "fire", "water", "grass", "electric", "ice", "fighting", "poison",
    "ground", "flying", "psychic", "bug", "rock", "ghost", "dragon", "dark",
    "steel", "fairy",
]

# attacker -> {defender: multiplier}; anything missing is 1.0
_CHART = {
    "normal": {"rock": 0.5, "ghost": 0.0, "steel": 0.5},
    "fire": {"fire": 0.5, "water": 0.5, "grass": 2, "ice": 2, "bug": 2, "rock": 0.5, "dragon": 0.5, "steel": 2},
    "water": {"fire": 2, "water": 0.5, "grass": 0.5, "ground": 2, "rock": 2, "dragon": 0.5},
    "grass": {"fire": 0.5, "water": 2, "grass": 0.5, "poison": 0.5, "ground": 2, "flying": 0.5, "bug": 0.5,
              "rock": 2, "dragon": 0.5, "steel": 0.5},
    "electric": {"water": 2, "grass": 0.5, "electric": 0.5, "ground": 0.0, "flying": 2, "dragon": 0.5},
    "ice": {"fire": 0.5, "water": 0.5, "grass": 2, "ice": 0.5, "ground": 2, "flying": 2, "dragon": 2, "steel": 0.5},
    "fighting": {"normal": 2, "ice": 2, "poison": 0.5, "flying": 0.5, "psychic": 0.5, "bug": 0.5, "rock": 2,
                 "ghost": 0.0, "dark": 2, "steel": 2, "fairy": 0.5},
    "poison": {"grass": 2, "poison": 0.5, "ground": 0.5, "rock": 0.5, "ghost": 0.5, "steel": 0.0, "fairy": 2},
    "ground": {"fire": 2, "grass": 0.5, "electric": 2, "poison": 2, "flying": 0.0, "bug": 0.5, "rock": 2, "steel": 2},
    "flying": {"grass": 2, "electric": 0.5, "fighting": 2, "bug": 2, "rock": 0.5, "steel": 0.5},
    "psychic": {"fighting": 2, "poison": 2, "psychic": 0.5, "dark": 0.0, "steel": 0.5},
    "bug": {"fire": 0.5, "grass": 2, "fighting": 0.5, "poison": 0.5, "flying": 0.5, "psychic": 2, "ghost": 0.5,
            "dark": 2, "steel": 0.5, "fairy": 0.5},
    "rock": {"fire": 2, "ice": 2, "fighting": 0.5, "ground": 0.5, "flying": 2, "bug": 2, "steel": 0.5},
    "ghost": {"normal": 0.0, "psychic": 2, "ghost": 2, "dark": 0.5},
    "dragon": {"dragon": 2, "steel": 0.5, "fairy": 0.0},
    "dark": {"fighting": 0.5, "psychic": 2, "ghost": 2, "dark": 0.5, "fairy": 0.5},
    "steel": {"fire": 0.5, "water": 0.5, "electric": 0.5, "ice": 2, "rock": 2, "steel": 0.5, "fairy": 2},
    "fairy": {"fire": 0.5, "fighting": 2, "poison": 0.5, "dragon": 2, "dark": 2, "steel": 0.5},
}


def effectiveness(move_type, defender_types):
    mult = 1.0
    for t in defender_types:
        mult *= _CHART.get(move_type, {}).get(t, 1.0)
    return mult


# (main, light, dark) per type
COLORS = {
    "normal": ((168, 168, 120), (215, 210, 175), (100, 96, 70)),
    "fire": ((240, 110, 48), (255, 190, 90), (150, 50, 25)),
    "water": ((90, 140, 240), (160, 200, 255), (40, 70, 150)),
    "grass": ((110, 200, 80), (180, 235, 130), (50, 115, 40)),
    "electric": ((250, 210, 50), (255, 245, 150), (170, 130, 20)),
    "ice": ((140, 215, 215), (215, 250, 250), (70, 140, 150)),
    "fighting": ((195, 50, 40), (240, 120, 100), (110, 25, 20)),
    "poison": ((165, 70, 165), (215, 140, 215), (90, 35, 95)),
    "ground": ((220, 190, 105), (240, 220, 160), (140, 110, 55)),
    "flying": ((165, 145, 240), (210, 200, 255), (95, 80, 165)),
    "psychic": ((245, 85, 135), (255, 160, 190), (150, 40, 80)),
    "bug": ((165, 185, 30), (210, 225, 110), (95, 110, 15)),
    "rock": ((185, 160, 60), (220, 200, 130), (110, 95, 35)),
    "ghost": ((110, 90, 150), (170, 150, 210), (60, 45, 90)),
    "dragon": ((110, 60, 245), (170, 140, 255), (55, 30, 150)),
    "dark": ((110, 88, 72), (165, 145, 130), (55, 42, 35)),
    "steel": ((185, 185, 205), (225, 225, 240), (110, 110, 135)),
    "fairy": ((240, 150, 190), (255, 205, 225), (160, 85, 120)),
}
