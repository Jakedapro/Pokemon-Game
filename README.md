# PokeBrawl

A Pokemon battle game for Mac and Windows with **every Pokemon** (all 1,025 species plus regional forms, Megas and Primals), real moves and learnsets, and three modes:

| Mode | What it is |
|---|---|
| **Practice** | Turn-based battles vs a bot on **Easy / Normal / Hard / Insane** |
| **Showcase** | Huge auto-battles for content: *Gen 1 vs Gen 3*, *Fire vs Water*, *10 Legends vs 200*... Watch live or **record a vertical MP4** (720x1280, ready for TikTok / Reels / Shorts) |
| **PvP** | Play your friends online with just a room code. Comp teams with abilities, Tera, items, natures, EVs, Mega Stones, Showdown import/export |

Practice and PvP are **turn-based (Showdown-style)**: 6v6 singles with:
- team preview, switching and priority
- hazards (Stealth Rock, Spikes, Toxic Spikes), weather and screens
- U-turn/Volt Switch pivots, Protect, Substitute, Trick Room and more

Keys: **1-4** pick a move, **M** to Mega Evolve, **T** to Terastallize.

The real-time arena is used only for showcases.

## Install (one command)

### Mac

Open **Terminal** and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/jamalmusialla81-hub/Pokemon-Game/HEAD/install.sh | bash
```

Then type `pokebrawl` (or open **PokeBrawl** from `~/Applications`).

The installer:
- installs into `~/.pokebrawl`
- doesn't need Apple's Command Line Tools or git: if your Mac has no suitable Python, it downloads a private copy just for PokeBrawl
- installs the game engine (`pygame-ce`)
- installs `ffmpeg` with Homebrew for video recording, if you have Homebrew
- downloads the Pokedex and sprites once (about 20 MB)

### Windows 10 / 11

Open **PowerShell** (Start menu, type *PowerShell*) and paste:

```powershell
irm https://raw.githubusercontent.com/jamalmusialla81-hub/Pokemon-Game/HEAD/install.ps1 | iex
```

Then double-click **PokeBrawl** on your Desktop (or in the Start menu), or type `pokebrawl` in a new window.

The Windows installer:
- installs into `%USERPROFILE%\.pokebrawl` with its own private copy of Python (nothing else on your PC changes)
- adds Desktop and Start menu shortcuts and a `pokebrawl` command
- installs `ffmpeg` with `winget` for video recording
- downloads the Pokedex and sprites once (about 20 MB)

### Updating

The game **updates itself**: it downloads new versions in the background while you're in the menu and installs
them the next time you open it (or hit *Update ready - Restart*). Turn it off in Settings. You can also run the
install command again, or `pokebrawl update`. Your friends install it the same way.

> The repo must be **public** for the one-liner to work for your friends (or add them as collaborators and have them `git clone` it).

## Playing with friends online

Open **PVP**, pick your team, and choose a connection:

- **Online room code (default, works anywhere):** press **HOST** to get a 5-letter code. Your friend types it and presses **JOIN**. No IP addresses or port forwarding needed. It runs through free public MQTT message servers and falls back to the next server if one is down. Set *List room publicly* and friends can just pick your room from **BROWSE OPEN ROOMS**.
- **Same Wi-Fi:** HOST, and your friend's JOIN screen finds you automatically.
- **Direct IP:** works with Tailscale IPs, or with port 7777 forwarded.
- **Relay server:** run `pokebrawl relay` on any server you own.

During the match:
- ping meter
- emotes (GG, LOL, EZ... also F1-F6)
- 60-second turn timer
- **Rematch** button

Every battle is saved as a replay and counted in your win/loss record against that friend.

The host runs the battle. Rules: Species Clause, Item Clause, one Mega and one Tera per team.

Room codes go over normal HTTPS (via the free ntfy.sh service), so they work even on school or work Wi-Fi that blocks games. If that's unavailable, the game falls back to public MQTT servers. Run `pokebrawl nettest` to see what works on your network.

## Showcases (content mode, owner only)

Showcase is hidden for everyone except the game's owner, who unlocks it on their computer with a secret code.

Pick a preset or build a custom matchup in the app:

- **Matchups:** any generation, Legendaries, fully evolved Pokemon, by BST, or any type
- **Team size:** All, 100, 50, 25, 10, 3 or 1
- **Toggles:** Megas, boss HP bars for legendaries, the trainer-catches-the-winner finale, speed

Then **Watch live** (Space = pause, +/- = speed) or **Record video**. Videos go to `~/Movies/PokeBrawl/`.

- **Auto-edit:** recordings are cut down to the *Video length* you pick (TikTok 60s by default). The intro,
  cutscenes, finishers and the catch play at normal speed; the long middle of the fight is fast-forwarded with
  a small `>> x6` tag. Pick *Full battle* to keep everything.
- **Battle royale:** set *Mode* to Royale (or pick a royale preset): every Pokemon for itself while a storm
  shrinks the arena. Royales with 60+ Pokemon go full screen in a wide arena while you watch; recordings stay
  vertical.
- **Gigantamax:** the 32 Pokemon with a Gigantamax form can Gigantamax (no plain Dynamax) - in showcases they
  grow huge with a red cloud crown, and in 1v1 battles it's a gimmick next to Mega and Tera: 3 turns, more HP,
  G-Max moves, no flinching. Mega Evolution and Gigantamax both have their own cutscenes.
- **Mewtwo:** when Mewtwo snaps it gets a rampage cutscene, says a line (spoken with the Mac's built-in voice,
  shown as subtitles) and a psychic shockwave wipes out everyone near it.
- **Final battle:** the last Pokemon standing faces the other side's champion on a full duel stage - big fighters,
  move callouts, slow-motion crits, clash beats and Sudden Death so it always ends.
- **Events:** Arceus can show up and drop off a legendary group (or, rarely, fight itself), Primal Kyogre and
  Groudon bring their domains, Mega Rayquaza calms the weather, meteors rain down. Events never bring a
  Pokemon that's already fighting.
- **Tournament:** set *Mode* to Tournament (or pick the Legends Cup / Kanto Cup presets): 8 or 16 Pokemon,
  single elimination, every match on the duel stage, an animated bracket between rounds and a trophy for
  the champion. Recordings fast-forward the early rounds and keep the knockouts and the final.
- **Shinies:** 1 in 64 Pokemon in a showcase is shiny - real shiny sprites, twinkles and a "SHINY X SPOTTED!"
  banner.

From the terminal (renders faster than real time):

```bash
pokebrawl showcase ~/.pokebrawl/app/showcases/gen1_vs_gen3.json --record gen1v3.mp4 --seed 42
```

Make your own showcase by dropping a JSON file in `showcases/`:

```json
{
  "title": "Gen 1 vs Gen 3!",
  "subtitle": "WHO WILL WIN???",
  "teams": [
    {"name": "Gen 1", "filter": {"gen": 1}},
    {"name": "Gen 3", "filter": {"gen": 3}}
  ],
  "bosses": "legendary",
  "megas": true,
  "hp_mult": 12
}
```

`filter` keys: `gen` (number or list), `type`, `legendary` (true/false), `fully_evolved`, `min_bst`, `max_bst`, `forms` (include regional forms).
Instead of a `filter`, a team can list exact Pokemon: `"pokemon": ["mewtwo", "rayquaza"]`. Other options:
- `"count": 50` picks a random 50
- `"bosses"`: `"legendary"`, `"none"`, or a list of names
- `"boss_hp_mult"`, `"seed"`, `"finale": false`, `"speed": 2`

Tournaments: `{"title": "Legends Cup", "mode": "tournament", "size": 8, "pokemon": ["mewtwo", ...]}`, or give
`teams` with filters instead of `pokemon` for a random draw.

## Sound, replays, settings

- **Sound:** sound effects and chiptune music are generated by the game. Pokemon cries come from PokeAPI. Recorded showcase MP4s include the sound.
- **Replays:** every battle is saved automatically (a few KB each). Open **REPLAYS** to rewatch at any speed (+/-) or **EXPORT MP4**.
- **Settings:** music, sound effect and cry volume; your name; your win/loss record vs each friend and bot level.

## Adventure mode

A proper Pokemon journey that looks and plays like FireRed / LeafGreen. The first time you open it, Adventure
mode downloads the FireRed graphics from the public [pret/pokefirered](https://github.com/pret/pokefirered)
decompilation project into `~/.pokebrawl/frlg/` (nothing from the original games is stored in this repository).
Every map tile, building, interior, trainer sprite, battle background, healthbox, text box, window frame and the
font itself is the real thing. Pokemon #1-386 use their FireRed battle sprites. Without internet the game falls
back to its own drawn art.

- **Our own world in that style:** every character is a palette swap of a FireRed sprite, the way the games
  make new characters - your teal-capped trainer, orange-haired rival Blake, the real Team Rocket, and Gym Leaders and Elite Four in their type colours. Every town has its own look
  (Tidewater's beach and sea, Voltara's fenced power lots, Bloomfield's flower fields, the Toxmire swamp, the
  Duneholt desert...), routes have ledges to hop down and boulders, and each gym is recoloured in its type.
- **Mega Rifts:** once you have the Key Stone, every route has a crackling rift. Inside, a raging wild Mega
  Pokemon - beat or catch it to seal the rift and take its Mega Stone (found nowhere else). Seal all 19
  for a secret. Mega Evolution has its own sequence (the stone reacts, the Pokemon is wrapped in light,
  then bursts out under the Mega mark), and Mega forms are redrawn GBA-style to match.
- **Inside a rift:** the Mega is boosted (+25% stats, +1 Attack and Sp. Atk), fights with the hardest AI and is
  far harder to catch. The rift collapses after a few turns (10 on Easy down to 6 on Insane) - run out of time and
  you're thrown back out, the Pokemon is gone and the rift re-forms elsewhere on the route. Every rift battle has
  an anomaly: Gravity Distortion (Flying types grounded, moves don't miss), Time Distortion (permanent Trick Room),
  Type Inversion, Mega Surge (harder hits), Entropy Field (everyone loses HP) or an Elemental Storm. Sealed rifts
  flicker back open now and then as echo rifts with a random wild Mega to hunt.
- **Rift-Born:** a Pokemon caught inside a rift keeps the rare ability Rift Heart (moves hit 20% harder) and a
  fifth move no other Pokemon can learn, Rift Breaker (its own type, uses its better attack stat, double damage
  against Megas).
- **Mega Radar and digging:** Prof. Hazel's Mega Radar (with the Key Stone) points to stones buried on each route.
  Stand on the spot, press Z, break into the cave and chip the stone out of the wall with the pick and hammer
  before the wall caves in.
- **Corrupted Mega Stones:** some buried stones are corrupted. They double every stat after Mega Evolving, but
  the Pokemon loses HP every turn and can be poisoned, burned or paralysed by the corruption. Pick clean or
  corrupted per stone in the BAG's Mega Stone case.
- **New Mega Evolutions (coming):** ten Megas the official games never made - Flygon, Luxray, Arcanine,
  Milotic, Typhlosion, Snorlax, Lapras, Ninetales, Machamp and Togekiss. Their stats are ready; each one switches
  on as soon as its sprite is dropped into `pokebrawl/art/megas/` (see the README there). Until then, digging
  turns up corrupted Mega Stones.
- **No more one-Mega rule:** every Pokemon holding its stone can Mega Evolve in the same battle, and from the
  fourth Gym on, leaders bring two Megas.
- **Real interiors:** Pokemon Centers, Marts, houses and Prof. Hazel's lab are FireRed's own rooms, with their
  counters, shelves and PCs.
- **A Gym for every type:** 18 Gyms in 18 towns - Rock, Bug, Water, Normal, Electric, Flying, Grass, Fighting,
  Poison, Fairy, Psychic, Ghost, Fire, Steel, Ice, Dark, Ground and Dragon - each with its own leader, badge,
  Mega Stone, town look and recoloured gym. 19 routes lead from Rootleaf to Victory Road.

**Controls:** arrow keys / WASD to walk, hold **X** (or Shift) to run, **Z** / Space to talk and confirm,
**X** / Esc to go back, **Enter** for the START menu. The mouse works in menus too.

- **New game options:** difficulty (EASY / NORMAL / HARD / INSANE - EXP, trainer levels, AI and prices), boy or
  girl, text speed, battle scene and sound. Change them later from OPTION in the START menu.
- **Randomizer:** unlocked once you become World Champion. Turn it on in a new game's OPTION screen and choose
  what to mix up: wild Pokemon (similar strength or anything, legendaries or not), starters, trainer teams and
  Gym types - from all 1,025 Pokemon.
- **Start:** Professor Hazel's speech on FireRed's real intro screen, then you wake up in her lab. Check the three
  Poke Balls on her table to choose Bulbasaur, Charmander or Squirtle - your rival Blake grabs the one with the type
  advantage and battles you on the spot.
  A secret Pikachu hides somewhere in Voltara City. Shinies are 1 in 200 and sparkle when they appear.
- **Explore:** towns, routes with tall grass, Victory Road and the Pokemon League. Your lead Pokemon follows you.
  Walk into buildings: Pokemon Centers (the nurse heals your team; the PC holds your Box), Poke Marts (buy and
  sell), houses, the professor's lab, and gyms with trainers inside.
- **Battles:** FIGHT / BAG / POKeMON / RUN, HP boxes with an EXP bar, sliding intros, send-out animations.
  Experience is given right after each knockout, with level-ups and new moves mid-battle, and evolutions after.
- **Catching:** throw Poke Balls from the BAG - the ball wobbles and clicks shut, or the Pokemon breaks free.
  Rare legendaries hide on the later routes (they also go into your Legend collection). Shinies are 1 in 512.
- **Story:** your rival Blake, Team Rocket (grunts, Admin Morga and Boss Giovanni) stealing Mega Stones, and
  Prof. Hazel's Key Stone after your second badge.
- **Mega Stones:** gym leaders give one with each badge, story fights and quests give more, and some sparkle on the
  routes. With the Key Stone, press **M** in the move menu to Mega Evolve. The BAG has a Mega Stone case.
- **Side quests:** a lost lucky charm, a letter to deliver, a lost Psyduck, Pokedex goals, a route clean sweep and
  more. **QUESTS** in the START menu shows your next story goal and every quest.
- **Secrets:** a few hidden things to find (there's a counter in the quest log). Hidden items too: check the ground.
- **The World Tournament:** with all 18 badges, enter the League and face the Elite Four back to back with no
  healing, then World Champion Aurelia in the Grand Final. Win to become the best trainer in the world.
- **Trainers** spot you and walk over. **Gym leaders** give badges, and the road north stays closed until you
  have a town's badge.
- **START menu:** Pokedex, party, quests (summary pages, switching order), bag, trainer card with badges, save.
  The game also saves on every map change. Blacking out sends you back to a Pokemon Center with half your money.

## Ranks, legends and the Pokedex

- **Ranks:** every battle earns or costs rank points (more for harder bots and PvP, bonus for win streaks).
  Climb Poke Ball, Great Ball, Ultra Ball and Master Ball (three divisions each) up to Champion. Your badge sits
  in the corner of the main menu; **TRAINER** shows your card, the ladder, record and streaks.
- **Legend collection:** after a win a legendary or mythical can appear (a rank-up always brings one). Throw the
  ball and it's yours - 1 in 64 are shiny. **TRAINER > LEGEND COLLECTION** shows every one, with silhouettes
  for the ones you're missing. Caught legends also show up as a *My legends* group in the showcase menu.
- **Pokedex:** every Pokemon, searchable and filterable by type and generation. Each entry has base stats,
  abilities, weaknesses and resistances, its Mega / Gigantamax / regional forms, and its shiny (tap the sprite).
- **Weather:** rain, harsh sun, sandstorms and snow show on the 1v1 battle screen.

## Team builder

**Team Builder** lets you:
- pick any Pokemon (search by name, type, `gen 4`, `legendary`, `mega`)
- choose moves from its **real learnset**
- set item, nature and EV build
- pick a Mega Stone, plus the Mega form for Charizard and Mewtwo X/Y

**Export** copies a team in Pokemon Showdown format to share. **Import** reads a Showdown team from your clipboard.

Supported items: Leftovers, Life Orb, Choice Band/Specs/Scarf, Focus Sash, Assault Vest, Rocky Helmet, Sitrus Berry, Lum Berry, Expert Belt, Eviolite, Weakness Policy, Heavy-Duty Boots, Black Sludge, Air Balloon, White Herb, Mega Stones and the Red/Blue Orbs.

**Abilities:** about 110 competitive abilities work in battles and showcases, including:
- Intimidate, weather setters, Levitate, absorb abilities
- Protean, Multiscale, Sturdy, Huge Power, Moxie, Beast Boost, Disguise
- the Ruin abilities

Mega Evolutions take their Mega ability (Mega Charizard Y gets Drought).

**Terastallization:** pick each Pokemon's Tera type. One Tera per team.

Not modeled yet: Z-Moves, Dynamax and terrains.

## Commands

```
pokebrawl                     open the game
pokebrawl showcase FILE.json  play a showcase (--record out.mp4 [--length 45 | --full] --seed N)
pokebrawl relay               run a relay server (port 7778)
pokebrawl download            re-download data and sprites
pokebrawl update              update the game
```

## For developers

```bash
pip install pygame-ce certifi pytest
python -m pokebrawl          # run from the repo
python -m pytest tests       # engine tests
```

| File | What it does |
|---|---|
| `pokebrawl/pokedex.py` | Downloads and caches data from [PokeAPI](https://pokeapi.co) |
| `sim.py` | Real-time arena engine (showcases) |
| `turnsim.py` | Turn-based engine |
| `bot.py` | Practice AI |
| `net.py` | Networking and relay |
| `session.py` | Local and online battle sessions |
| `render.py` | Arena effects |
| `showcase.py` | Showcase director |

No game assets are stored in this repo. Pokemon data and sprites download from PokeAPI onto each player's machine.

---

Fan-made project for playing with friends. Not affiliated with Nintendo, Game Freak or The Pokemon Company. Pokemon and all related names are trademarks of their respective owners.
