# Mega Evolution sprites (artist overrides)

PokeBrawl's own Mega Evolutions (Mega Flygon, Luxray, Arcanine, Milotic, Typhlosion, Snorlax, Lapras,
Ninetales, Machamp and Togekiss) are built on the player's machine by sprite-editing recipes in
`pokebrawl/megas.py`. An artist's sprite placed here replaces the built one.

- Named after the base Pokemon: `flygon.png` (front) and optionally `flygon_back.png` (back).
- Transparent background, GBA style, 64x64 (or 80x80). It's shown at 2x in battle.
- Types, stats and abilities are in `pokebrawl/riftdex.py` (`CUSTOM_MEGAS`).
