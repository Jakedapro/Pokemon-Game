"""Downloads the Pokedex, real move data and learnsets (from the open PokeAPI data set) plus sprites,
and caches them locally.

Nothing from the games is shipped in this repo: everything is fetched on the player's machine
into ~/.pokebrawl/ the first time it is needed.
"""
import csv
import json
import os
import shutil
import ssl
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .types import TYPES

HOME = os.environ.get("POKEBRAWL_HOME", os.path.join(os.path.expanduser("~"), ".pokebrawl"))
DATA_DIR = os.path.join(HOME, "data")
SPRITE_DIR = os.path.join(HOME, "sprites")
DEX_FILE = os.path.join(DATA_DIR, "pokedex.json")
DEX_VERSION = 7

CSV_URL = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/{}.csv"
SPRITE_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{}.png"
ITEM_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/items/{}.png"

STAT_KEYS = {1: "hp", 2: "atk", 3: "def", 4: "spa", 5: "spd", 6: "spe", 7: "acc", 8: "eva"}
TRANSFORM_MARKERS = ("-mega", "-primal")
# Gigantamax: the G-Max move each Gigantamax Pokemon's moves of its type become
GMAX_MOVES = {
    "venusaur": ("Vine Lash", "grass"), "charizard": ("Wildfire", "fire"), "blastoise": ("Cannonade", "water"),
    "butterfree": ("Befuddle", "bug"), "pikachu": ("Volt Crash", "electric"), "meowth": ("Gold Rush", "normal"),
    "machamp": ("Chi Strike", "fighting"), "gengar": ("Terror", "ghost"), "kingler": ("Foam Burst", "water"),
    "lapras": ("Resonance", "ice"), "eevee": ("Cuddle", "normal"), "snorlax": ("Replenish", "normal"),
    "garbodor": ("Malodor", "poison"), "melmetal": ("Meltdown", "steel"), "rillaboom": ("Drum Solo", "grass"),
    "cinderace": ("Fireball", "fire"), "inteleon": ("Hydrosnipe", "water"), "corviknight": ("Wind Rage", "flying"),
    "orbeetle": ("Gravitas", "psychic"), "drednaw": ("Stonesurge", "water"), "coalossal": ("Volcalith", "rock"),
    "flapple": ("Tartness", "grass"), "appletun": ("Sweetness", "grass"), "sandaconda": ("Sandblast", "ground"),
    "toxtricity": ("Stun Shock", "electric"), "centiskorch": ("Centiferno", "fire"), "hatterene": ("Smite", "fairy"),
    "grimmsnarl": ("Snooze", "dark"), "alcremie": ("Finale", "fairy"), "copperajah": ("Steelsurge", "steel"),
    "duraludon": ("Depletion", "dragon"), "urshifu": ("One Blow", "dark"),
}
SKIP_FORM_MARKERS = ("-totem", "-cap", "-starter", "-cosplay", "-rock-star", "-belle", "-pop-star",
                     "-phd", "-libre", "-busted", "-eternamax", "-own-tempo", "-power-construct")
FLAG_NAMES = {1: "contact", 2: "charge", 3: "recharge", 8: "punch", 9: "sound", 13: "heal", 15: "powder",
              16: "bite", 17: "pulse", 18: "ballistics"}
CLASS_NAMES = {1: "status", 2: "phys", 3: "spec"}
# status moves with special handling in the engines (everything else needs a meta category we understand)
SPECIAL_STATUS = {"protect", "detect", "stealth-rock", "spikes", "toxic-spikes", "rain-dance", "sunny-day",
                  "sandstorm", "defog", "roar", "whirlwind", "haze", "parting-shot", "substitute", "trick-room",
                  "leech-seed", "taunt", "will-o-wisp", "toxic", "spore", "yawn", "destiny-bond", "wish",
                  "light-screen", "reflect", "aurora-veil", "tailwind", "trick", "switcheroo",
                  "baton-pass", "teleport", "chilly-reception", "memento", "healing-wish", "pain-split",
                  "belly-drum", "shell-smash", "quiver-dance",
                  "nasty-plot", "swords-dance", "dragon-dance", "calm-mind", "bulk-up", "agility", "rock-polish",
                  "coil", "shift-gear", "victory-dance", "tidy-up", "curse", "iron-defense", "amnesia", "growth"}

# ---------------------------------------------------------------------------- downloading
# Some networks (school/work Wi-Fi filters, antivirus "web shields") re-sign HTTPS traffic with their own
# certificate. The Mac trusts it (it's in the Keychain) but Python's bundled certificates don't, so we try,
# in order: the OS trust store (truststore), Python's defaults + certifi, the certificates exported from the
# macOS Keychain, and finally the system `curl`, which always uses the Keychain.
_ctx_lock = threading.Lock()
_good_ctx = None
_use_curl = False


def _candidate_contexts():
    try:
        import truststore
        yield "system", truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # noqa: BLE001 - not installed (Python 3.9) or unsupported
        pass
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except Exception:  # noqa: BLE001
        pass
    yield "default", ctx
    pem = _keychain_pem()
    if pem:
        ctx = ssl.create_default_context(cafile=pem)
        if hasattr(ssl, "VERIFY_X509_STRICT"):
            ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT  # filter certificates are often not "strict"
        yield "keychain", ctx


def _keychain_pem():
    """Export every certificate the Mac trusts into one PEM file Python can load."""
    if sys.platform != "darwin" or not shutil.which("security"):
        return None
    path = os.path.join(HOME, "keychain-certs.pem")
    chains = ["/System/Library/Keychains/SystemRootCertificates.keychain", "/Library/Keychains/System.keychain",
              os.path.expanduser("~/Library/Keychains/login.keychain-db")]
    out = b""
    for kc in chains:
        if os.path.exists(kc):
            try:
                out += subprocess.run(["security", "find-certificate", "-a", "-p", kc], capture_output=True,
                                      timeout=20).stdout
            except (OSError, subprocess.SubprocessError):
                pass
    if not out:
        return None
    os.makedirs(HOME, exist_ok=True)
    with open(path, "wb") as f:
        f.write(out)
    return path


def _is_cert_error(e):
    reason = getattr(e, "reason", e)
    return isinstance(reason, ssl.SSLError) or "CERTIFICATE" in str(e).upper()


def _urlopen(url, timeout, ctx):
    req = urllib.request.Request(url, headers={"User-Agent": "pokebrawl/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()


def _curl(url, timeout):
    res = subprocess.run(["curl", "-fsSL", "--max-time", str(int(timeout)), "-A", "pokebrawl/1.0", url],
                         capture_output=True, timeout=timeout + 10)
    if res.returncode != 0:
        raise OSError(f"curl failed ({res.returncode}): {res.stderr.decode(errors='ignore').strip()[:200]}")
    return res.stdout


def fetch(url, timeout=60):
    global _good_ctx, _use_curl
    if _use_curl:
        return _curl(url, timeout)
    if _good_ctx is not None:
        return _urlopen(url, timeout, _good_ctx)
    with _ctx_lock:  # first download: find a way that works, then reuse it
        if _use_curl:
            return _curl(url, timeout)
        if _good_ctx is not None:
            return _urlopen(url, timeout, _good_ctx)
        last = None
        for name, ctx in _candidate_contexts():
            try:
                data = _urlopen(url, timeout, ctx)
                _good_ctx = ctx
                return data
            except urllib.error.HTTPError:
                _good_ctx = ctx  # TLS worked; the file just isn't there
                raise
            except Exception as e:  # noqa: BLE001
                last = e
                if not _is_cert_error(e):
                    raise
        if shutil.which("curl"):
            data = _curl(url, timeout)
            _use_curl = True
            return data
        raise last


def pretty_name(ident):
    special = {
        "mr-mime": "Mr. Mime", "mime-jr": "Mime Jr.", "mr-rime": "Mr. Rime", "ho-oh": "Ho-Oh",
        "porygon-z": "Porygon-Z", "jangmo-o": "Jangmo-o", "hakamo-o": "Hakamo-o", "kommo-o": "Kommo-o",
        "type-null": "Type: Null", "farfetchd": "Farfetch'd", "sirfetchd": "Sirfetch'd",
        "nidoran-f": "Nidoran F", "nidoran-m": "Nidoran M",
    }
    if ident in special:
        return special[ident]
    parts = ident.split("-")
    if parts[-1] == "gmax":
        return "Gigantamax " + " ".join(p.title() for p in parts[:-1])
    if "mega" in parts:
        i = parts.index("mega")
        base = " ".join(p.title() for p in parts[:i])
        rest = " ".join(p.upper() for p in parts[i + 1:])
        return ("Mega " + base + (" " + rest if rest else "")).strip()
    if "primal" in parts:
        return "Primal " + " ".join(p.title() for p in parts if p != "primal")
    if parts[-1] in ("alola", "galar", "hisui", "paldea"):
        region = {"alola": "Alolan", "galar": "Galarian", "hisui": "Hisuian", "paldea": "Paldean"}[parts[-1]]
        return region + " " + " ".join(p.title() for p in parts[:-1])
    return " ".join(p.title() for p in parts)


def move_name(ident):
    special = {"u-turn": "U-turn", "x-scissor": "X-Scissor", "v-create": "V-create", "will-o-wisp": "Will-O-Wisp",
               "self-destruct": "Self-Destruct", "double-edge": "Double-Edge", "soft-boiled": "Soft-Boiled",
               "freeze-dry": "Freeze-Dry", "wake-up-slap": "Wake-Up Slap", "baby-doll-eyes": "Baby-Doll Eyes",
               "lock-on": "Lock-On", "mud-slap": "Mud-Slap", "trick-or-treat": "Trick-or-Treat"}
    return special.get(ident, " ".join(p.title() for p in ident.split("-")))


def _read_csv(name):
    path = os.path.join(DATA_DIR, name + ".csv")
    if not os.path.exists(path):
        data = fetch(CSV_URL.format(name))
        with open(path, "wb") as f:
            f.write(data)
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _int(v, default=0):
    return int(v) if v not in (None, "") else default


def _build_moves(type_name):
    moves = _read_csv("moves")
    meta = {int(r["move_id"]): r for r in _read_csv("move_meta")}
    cats = {int(r["id"]): r["identifier"] for r in _read_csv("move_meta_categories")}
    ails = {int(r["id"]): r["identifier"] for r in _read_csv("move_meta_ailments")}
    targets = {int(r["id"]): r["identifier"] for r in _read_csv("move_targets")}
    changes, flags = {}, {}
    for r in _read_csv("move_meta_stat_changes"):
        changes.setdefault(int(r["move_id"]), {})[STAT_KEYS[int(r["stat_id"])]] = int(r["change"])
    for r in _read_csv("move_flag_map"):
        f = FLAG_NAMES.get(int(r["move_flag_id"]))
        if f:
            flags.setdefault(int(r["move_id"]), []).append(f)

    out = {}
    for r in moves:
        mid = int(r["id"])
        key = r["identifier"]
        if mid >= 10000 or key.startswith(("max-", "g-max-")) or key.endswith(("--physical", "--special")):
            continue
        if not r["damage_class_id"] or type_name.get(int(r["type_id"])) not in TYPES:
            continue
        m = meta.get(mid, {})
        cat = cats.get(_int(m.get("meta_category_id"), 13), "unique")
        power = _int(r["power"])
        cls = CLASS_NAMES[int(r["damage_class_id"])]
        if cat == "ohko":
            continue
        if cls == "status" and key not in SPECIAL_STATUS and cat not in ("ailment", "net-good-stats", "heal"):
            continue
        out[mid] = {
            "id": mid, "key": key, "name": move_name(key), "type": type_name[int(r["type_id"])],
            "power": power, "acc": _int(r["accuracy"], 101), "pp": _int(r["pp"], 10),
            "pri": _int(r["priority"]), "cls": cls, "target": targets.get(_int(r["target_id"]), "selected-pokemon"),
            "cat": cat, "ailment": ails.get(_int(m.get("meta_ailment_id")), "none"),
            "ail_chance": _int(m.get("ailment_chance")), "drain": _int(m.get("drain")),
            "healing": _int(m.get("healing")), "crit": _int(m.get("crit_rate")),
            "flinch": _int(m.get("flinch_chance")), "stat_chance": _int(m.get("stat_chance")),
            "hits": [_int(m.get("min_hits"), 1), _int(m.get("max_hits"), 1)],
            "stats": changes.get(mid, {}), "flags": flags.get(mid, []),
        }
    return out


def build_dex(progress=print):
    os.makedirs(DATA_DIR, exist_ok=True)
    progress("[pokebrawl] downloading Pokedex data (one time, ~11 MB)...")
    pokemon = _read_csv("pokemon")
    stats = _read_csv("pokemon_stats")
    ptypes = _read_csv("pokemon_types")
    species = _read_csv("pokemon_species")
    type_name = {int(t["id"]): t["identifier"] for t in _read_csv("types")}
    moves = _build_moves(type_name)

    sp = {int(s["id"]): s for s in species}
    evolves_into = {int(s["evolves_from_species_id"]) for s in species if s["evolves_from_species_id"]}
    st, ty = {}, {}
    for row in stats:
        st.setdefault(int(row["pokemon_id"]), {})[STAT_KEYS[int(row["stat_id"])]] = int(row["base_stat"])
    for row in sorted(ptypes, key=lambda r: int(r["slot"])):
        ty.setdefault(int(row["pokemon_id"]), []).append(type_name[int(row["type_id"])])

    ability_name = {int(r["id"]): r["identifier"] for r in _read_csv("abilities")}
    abil = {}
    for r in sorted(_read_csv("pokemon_abilities"), key=lambda r: int(r["slot"])):
        a = ability_name.get(int(r["ability_id"]))
        if a:
            abil.setdefault(int(r["pokemon_id"]), []).append([a, r["is_hidden"] == "1"])

    progress("[pokebrawl] reading learnsets...")
    learn = {}
    with open(os.path.join(DATA_DIR, "pokemon_moves.csv") if os.path.exists(os.path.join(DATA_DIR, "pokemon_moves.csv"))
              else _download_to("pokemon_moves"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mid = int(row["move_id"])
            if mid in moves:
                learn.setdefault(int(row["pokemon_id"]), set()).add(mid)

    entries = {}
    for p in pokemon:
        pid, ident, sid = int(p["id"]), p["identifier"], int(p["species_id"])
        if sid not in sp or pid not in st or pid not in ty:
            continue
        default = p["is_default"] == "1"
        transform = any(m in ident for m in TRANSFORM_MARKERS) or ident.endswith("-gmax")
        if not default and not transform and any(m in ident for m in SKIP_FORM_MARKERS):
            continue
        s = sp[sid]
        entries[pid] = {
            "id": pid, "key": ident, "name": pretty_name(ident), "species": sid,
            "gen": int(s["generation_id"]), "legendary": s["is_legendary"] == "1",
            "mythical": s["is_mythical"] == "1", "fully_evolved": sid not in evolves_into,
            "default": default, "transform": transform,
            "types": [t for t in ty[pid] if t in TYPES] or ["normal"],
            "stats": {k: v for k, v in st[pid].items() if k in ("hp", "atk", "def", "spa", "spd", "spe")},
            "megas": [], "gmax": None, "base": None, "learn": sorted(learn.get(pid, ())),
            "abilities": abil.get(pid, []),
        }
    default_for_species = {e["species"]: e["id"] for e in entries.values() if e["default"]}
    for e in entries.values():
        base = default_for_species.get(e["species"])
        if e["transform"] and base:
            if e["key"].endswith("-gmax"):  # Gigantamax forms are their own gimmick, not megas
                entries[base]["gmax"] = e["id"]
            else:
                entries[base]["megas"].append(e["id"])
            e["base"] = base
        if not e["learn"] and base:  # alternate forms without their own learnset use the base form's
            e["learn"] = sorted(learn.get(base, ()))
        if not e["abilities"] and base:
            e["abilities"] = list(entries[base]["abilities"])
    dex = {"version": DEX_VERSION, "pokemon": sorted(entries.values(), key=lambda e: e["id"]),
           "moves": sorted(moves.values(), key=lambda m: m["id"])}
    with open(DEX_FILE, "w") as f:
        json.dump(dex, f, separators=(",", ":"))
    try:
        os.remove(os.path.join(DATA_DIR, "pokemon_moves.csv"))  # 10 MB, no longer needed
    except OSError:
        pass
    return dex


def _download_to(name):
    path = os.path.join(DATA_DIR, name + ".csv")
    with open(path, "wb") as f:
        f.write(fetch(CSV_URL.format(name), timeout=180))
    return path


class Dex:
    def __init__(self, data):
        self.all = {e["id"]: e for e in data["pokemon"]}
        self.moves = {m["id"]: m for m in data["moves"]}
        self.move_by_key = {m["key"]: m for m in data["moves"]}
        self.by_key = {e["key"]: e for e in data["pokemon"]}
        for e in data["pokemon"]:
            if e["default"]:
                self.by_key.setdefault(e["key"].split("-")[0], e)

    def get(self, ref):
        """Look up by numeric id, identifier ('charizard', 'charizard-mega-x') or display name."""
        if ref is None:
            return None
        if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
            return self.all.get(int(ref))
        key = ref.strip().lower().replace(" ", "-").replace(".", "").replace("'", "").replace(":", "")
        if key in self.by_key:
            return self.by_key[key]
        low = ref.strip().lower()
        for e in self.all.values():
            if e["name"].lower() == low:
                return e
        return None

    def move(self, ref):
        if isinstance(ref, int):
            return self.moves.get(ref)
        key = ref.strip().lower().replace(" ", "-").replace("'", "")
        return self.move_by_key.get(key)

    def learnset(self, entry):
        return [self.moves[m] for m in entry["learn"] if m in self.moves]

    def selectable(self):
        """Every pick-able Pokemon: default forms plus regional/alternate forms (not megas)."""
        return [e for e in self.all.values() if not e["transform"]]

    def filter(self, spec):
        """Filter used by showcase files. See showcases/README.md for the keys."""
        if "pokemon" in spec:
            out = []
            for ref in spec["pokemon"]:
                e = self.get(ref)
                if e is None:
                    print(f"[pokebrawl] unknown pokemon: {ref}", file=sys.stderr)
                else:
                    out.append(e)
            return out
        pool = self.selectable()
        if not spec.get("forms", False):
            pool = [e for e in pool if e["default"]]
        if "gen" in spec:
            gens = spec["gen"] if isinstance(spec["gen"], list) else [spec["gen"]]
            pool = [e for e in pool if e["gen"] in gens]
        if "type" in spec:
            want = spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
            pool = [e for e in pool if any(t in e["types"] for t in want)]
        if "legendary" in spec:
            pool = [e for e in pool if (e["legendary"] or e["mythical"]) == spec["legendary"]]
        if spec.get("fully_evolved"):
            pool = [e for e in pool if e["fully_evolved"]]
        if "min_bst" in spec:
            pool = [e for e in pool if sum(e["stats"].values()) >= spec["min_bst"]]
        if "max_bst" in spec:
            pool = [e for e in pool if sum(e["stats"].values()) <= spec["max_bst"]]
        return pool


_dex = None


def load_dex(progress=print):
    global _dex
    if _dex is None:
        data = None
        if os.path.exists(DEX_FILE):
            with open(DEX_FILE) as f:
                data = json.load(f)
            if data.get("version") != DEX_VERSION:
                data = None
        if data is None:
            data = build_dex(progress)
        _dex = Dex(data)
    return _dex


def sprite_path(pid):
    return os.path.join(SPRITE_DIR, f"{pid}.png")


def item_path(name):
    return os.path.join(SPRITE_DIR, f"item-{name}.png")


def ensure_sprite(pid):
    """Download one sprite if it is not cached. Returns the path, or None if unavailable."""
    path = sprite_path(pid)
    if os.path.exists(path):
        return path if os.path.getsize(path) > 0 else None
    os.makedirs(SPRITE_DIR, exist_ok=True)
    try:
        data = fetch(SPRITE_URL.format(pid), timeout=20)
    except Exception:
        return None
    with open(path, "wb") as f:
        f.write(data)
    return path


def ensure_item(name):
    path = item_path(name)
    if not os.path.exists(path):
        os.makedirs(SPRITE_DIR, exist_ok=True)
        try:
            data = fetch(ITEM_URL.format(name))
        except Exception:
            return None
        with open(path, "wb") as f:
            f.write(data)
    return path


def prefetch(ids, progress=None, workers=24):
    ids = [i for i in ids if not os.path.exists(sprite_path(i))]
    if not ids:
        if progress:
            progress(1, 1)
        return
    done = 0
    with ThreadPoolExecutor(workers) as ex:
        for _ in ex.map(ensure_sprite, ids):
            done += 1
            if progress:
                progress(done, len(ids))


def download_all():
    dex = load_dex()
    ensure_item("poke-ball")

    def bar(done, total):
        n = int(30 * done / total)
        sys.stdout.write(f"\r[pokebrawl] sprites [{'#' * n}{'.' * (30 - n)}] {done}/{total}")
        sys.stdout.flush()

    prefetch(list(dex.all), bar)
    print()
    from .audio import ensure_assets, prefetch_cries
    ensure_assets()
    prefetch_cries([e["id"] for e in dex.all.values()],
                   lambda d, t: sys.stdout.write(f"\r[pokebrawl] cries [{'#' * int(30 * d / t)}{'.' * (30 - int(30 * d / t))}] {d}/{t}"))
    print(f"\n[pokebrawl] ready: {len(dex.all)} Pokemon and {len(dex.moves)} moves cached in {HOME}")
