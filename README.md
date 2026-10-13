# PokeBrawl

A Pokemon battle game for Mac with **every Pokemon** (all 1,025 species plus regional forms, Megas and Primals), real moves and learnsets, and three modes:

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

## Showcases (content mode)

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

A proper Pokemon journey in the style of the Game Boy Advance games. It opens in its own window with crisp
pixel art: 16-pixel tiles, pixel trainers and a pixel font (all drawn by the game itself).

**Controls:** arrow keys / WASD to walk, hold **X** (or Shift) to run, **Z** / Space to talk and confirm,
**X** / Esc to go back, **Enter** for the START menu. The mouse works in menus too.

- **Start:** Professor Hazel introduces the world, you type your name and pick a starter from any generation.
- **Explore:** towns, routes with tall grass, Victory Road and the Pokemon League. Your lead Pokemon follows you.
  Walk into buildings: Pokemon Centers (the nurse heals your team; the PC holds your Box), Poke Marts (buy and
  sell), houses, the professor's lab, and gyms with trainers inside.
- **Battles:** FIGHT / BAG / POKeMON / RUN, HP boxes with an EXP bar, sliding intros, send-out animations.
  Experience is given right after each knockout, with level-ups and new moves mid-battle, and evolutions after.
- **Catching:** throw Poke Balls from the BAG - the ball wobbles and clicks shut, or the Pokemon breaks free.
  Rare legendaries hide on the later routes (they also go into your Legend collection). Shinies are 1 in 512.
- **Trainers** spot you and walk over. **Gym leaders** give badges, and the road north stays closed until you
  have a town's badge. Beat all 8, then the Champion, and enter the Hall of Fame.
- **START menu:** Pokedex, party (summary pages, switching order), bag, trainer card with badges, save.
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
