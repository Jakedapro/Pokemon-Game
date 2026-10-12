# PokeBrawl

A Pokemon battle game for Mac with **every Pokemon** (all 1,025 species plus regional forms, Megas and Primals), real moves and learnsets, and three modes:

| Mode | What it is |
|---|---|
| **Practice** | Fight a bot on **Easy / Normal / Hard / Insane**, in either battle style |
| **Showcase** | Huge auto-battles for content: *Gen 1 vs Gen 3*, *Fire vs Water*, *10 Legends vs 200*... Watch live or **record a vertical MP4** (720x1280, ready for TikTok / Reels / Shorts) |
| **PvP** | Play your friends online with your own comp teams: held items, natures, EVs, Mega Stones, Showdown import/export |

Two battle styles (for Practice and PvP):

- **Real-time Arena:** both teams fight live on the field, like the showcase videos. Click your Pokemon, then click an enemy to focus it. Right-click to move, 1-4 to fire a move, **M** to Mega Evolve.
- **Turn-based (Showdown-style):** 6v6 singles with team preview, switching, priority, hazards (Stealth Rock, Spikes, Toxic Spikes), weather, screens, U-turn/Volt Switch pivots, Protect, Substitute, Trick Room and more.

## Install (one command)

Open **Terminal** and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/jamalmusialla81-hub/Pok-mon-Game/HEAD/install.sh | bash
```

Then type `pokebrawl` (or open **PokeBrawl** from `~/Applications`).

The installer:
- installs into `~/.pokebrawl`
- uses the Mac's Python and installs the Apple Command Line Tools if needed
- installs the game engine (`pygame-ce`)
- installs `ffmpeg` with Homebrew for video recording, if you have Homebrew
- downloads the Pokedex and sprites once (about 20 MB)

Run the same command again, or `pokebrawl update`, to update. Your friends install it the same way.

> The repo must be **public** for the one-liner to work for your friends (or add them as collaborators and have them `git clone` it).

## Playing with friends online

Both players open **PVP**, pick a team and the same connection type. One presses **HOST**, the other **JOIN**.

- **Same Wi-Fi:** the joiner types the address the host's screen shows (e.g. `192.168.1.20`).
- **Over the internet (easiest):** both install [Tailscale](https://tailscale.com) (free) and the joiner uses the host's Tailscale IP (`100.x.y.z`).
- **Port forwarding:** forward TCP port **7777** on the host's router to their Mac.
- **Relay server:** run `pokebrawl relay` on any cheap VPS. Both players choose *Relay server*, enter `that-server:7778` and the same room code. No port forwarding needed.

The host runs the battle and picks the style (real-time or turn-based). Rules: Species Clause, Item Clause, one Mega Stone/Orb per team.

## Showcases (content mode)

Pick a preset or build a custom matchup in the app:

- **Matchups:** any generation, Legendaries, fully evolved Pokemon, by BST, or any type
- **Team size:** All, 100, 50, 25, 10, 3 or 1
- **Toggles:** Megas, boss HP bars for legendaries, the trainer-catches-the-winner finale, speed

Then **Play** to watch live (Space = pause, +/- = speed) or **Record MP4**. Videos go to `~/Movies/PokeBrawl/`.

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

## Team builder

**Team Builder** lets you:
- pick any Pokemon (search by name, type, `gen 4`, `legendary`, `mega`)
- choose moves from its **real learnset**
- set item, nature and EV build
- pick a Mega Stone, plus the Mega form for Charizard and Mewtwo X/Y

**Export** copies a team in Pokemon Showdown format to share. **Import** reads a Showdown team from your clipboard.

Supported items: Leftovers, Life Orb, Choice Band/Specs/Scarf, Focus Sash, Assault Vest, Rocky Helmet, Sitrus Berry, Lum Berry, Expert Belt, Eviolite, Weakness Policy, Heavy-Duty Boots, Black Sludge, Air Balloon, White Herb, Mega Stones and the Red/Blue Orbs.

Not modeled yet: abilities, Z-Moves, Dynamax and Terastallization.

## Commands

```
pokebrawl                     open the game
pokebrawl showcase FILE.json  play a showcase (--record out.mp4 --seed N)
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
| `sim.py` | Real-time engine |
| `turnsim.py` | Turn-based engine |
| `bot.py` | Practice AI |
| `net.py` | Networking and relay |
| `session.py` | Local and online battle sessions |
| `render.py` | Arena effects |
| `showcase.py` | Showcase director |

No game assets are stored in this repo. Pokemon data and sprites download from PokeAPI onto each player's machine.

---

Fan-made project for playing with friends. Not affiliated with Nintendo, Game Freak or The Pokemon Company. Pokemon and all related names are trademarks of their respective owners.
