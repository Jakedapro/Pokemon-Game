"""Sound: synthesized sound effects + chiptune music (generated once, cached as WAVs), Pokemon cries from
PokeAPI, and an offline mixer that bakes all of it into recorded showcase MP4s."""
import array
import math
import os
import random
import subprocess
import time
import wave

from . import pokedex

RATE = 44100
SFX_DIR = os.path.join(pokedex.HOME, "audio")
CRY_DIR = os.path.join(pokedex.HOME, "cries")
CRY_URL = "https://raw.githubusercontent.com/PokeAPI/cries/main/cries/pokemon/latest/{}.ogg"
AUDIO_VERSION = 3

# minimum seconds between two plays of the same sound (keeps 300-Pokemon battles from turning into noise)
THROTTLE = {"ball": 0.03, "hit": 0.045, "hit_super": 0.08, "hit_weak": 0.07, "beam": 0.07, "blast": 0.09, "impact": 0.05,
            "faint": 0.06, "boost": 0.12, "drop": 0.12, "heal": 0.12, "status": 0.1, "miss": 0.12, "melee": 0.05,
            "cry": 0.25}


# ---------------------------------------------------------------------------- synthesis
def _env(i, n, attack=0.005, release=None):
    t = i / RATE
    a = min(1.0, t / attack) if attack > 0 else 1.0
    rel = (1 - i / n) if release is None else max(0.0, 1 - max(0, i - (n - release * RATE)) / (release * RATE))
    return a * rel


def _square(ph):
    return 1.0 if (ph % 1.0) < 0.5 else -1.0


def _tri(ph):
    p = ph % 1.0
    return 4 * p - 1 if p < 0.5 else 3 - 4 * p


def _render(dur, fn):
    n = int(dur * RATE)
    return [fn(i, n) for i in range(n)]


def _noise_gen(seed):
    rng = random.Random(seed)
    return lambda: rng.uniform(-1, 1)


def _make_sfx():
    S = {}
    nz = _noise_gen(1)

    def hit(i, n, f0=180, bright=0.6):
        t = i / RATE
        e = (1 - i / n) ** 2
        return (math.sin(2 * math.pi * (f0 - 120 * t / (n / RATE)) * t) * 0.7 + nz() * bright) * e

    S["hit"] = _render(0.11, lambda i, n: hit(i, n) * 0.6)
    S["hit_super"] = _render(0.2, lambda i, n: (hit(i, n, 220, 0.8) + 0.4 * _square(i * 1200 / RATE) *
                                                (1 - i / n) ** 3) * 0.7)
    S["hit_weak"] = _render(0.08, lambda i, n: hit(i, n, 140, 0.25) * 0.4)
    S["melee"] = _render(0.07, lambda i, n: nz() * (1 - i / n) ** 3 * 0.45)
    S["impact"] = _render(0.09, lambda i, n: (nz() * 0.6 + math.sin(i * 0.02)) * (1 - i / n) ** 2 * 0.4)

    def beam(i, n):
        t = i / RATE
        f = 300 + 900 * (i / n)
        return math.sin(2 * math.pi * f * t + 3 * math.sin(2 * math.pi * 30 * t)) * _env(i, n, 0.01) * 0.35
    S["beam"] = _render(0.32, beam)
    lp = [0.0]

    def blast(i, n, k=0.08):
        lp[0] += (nz() - lp[0]) * k
        return lp[0] * 3.0 * (1 - i / n) ** 1.5
    S["blast"] = _render(0.5, lambda i, n: blast(i, n) * 0.8)
    S["boom"] = _render(1.1, lambda i, n: (blast(i, n, 0.04) * 1.4 + math.sin(2 * math.pi * 55 * i / RATE) *
                                           (1 - i / n) ** 3) * 0.6)
    S["faint"] = _render(0.5, lambda i, n: _square((600 - 450 * i / n) * i / RATE) * (1 - i / n) * 0.25)
    S["miss"] = _render(0.16, lambda i, n: math.sin(2 * math.pi * (900 - 500 * i / n) * i / RATE) *
                        (1 - i / n) * 0.25)

    def arp(notes, step, dur, wave_fn=_square, vol=0.25):
        def f(i, n):
            k = min(len(notes) - 1, int(i / (step * RATE)))
            return wave_fn(notes[k] * i / RATE) * _env(i, n, 0.004) * vol
        return _render(dur, f)
    S["mega"] = [a + b for a, b in zip(arp([523, 659, 784, 1047, 1319, 1568, 2093], 0.07, 1.0),
                                       _render(1.0, lambda i, n: math.sin(2 * math.pi * 1568 * i / RATE) *
                                               math.sin(math.pi * i / n) * 0.15))]

    def bell(freqs, dur, vol=0.3):
        def f(i, n):
            t = i / RATE
            return sum(math.sin(2 * math.pi * fr * t) * math.exp(-t * (3 + k * 2)) for k, fr in
                       enumerate(freqs)) * vol / len(freqs)
        return _render(dur, f)
    S["tera"] = bell([1318, 1976, 2637, 3951], 0.9, 0.5)
    S["heal"] = arp([784, 988, 1175, 1568], 0.06, 0.35, math.sin, 0.25)
    S["boost"] = arp([440, 554, 659, 880], 0.04, 0.2, _square, 0.15)
    S["drop"] = arp([880, 659, 554, 440], 0.04, 0.2, _square, 0.15)
    S["status"] = _render(0.3, lambda i, n: _square(220 * i / RATE + 0.02 * math.sin(i * 0.004)) *
                          (1 - i / n) * 0.18)
    S["click"] = _render(0.035, lambda i, n: _square(1200 * i / RATE) * (1 - i / n) * 0.15)
    S["select"] = arp([880, 1320], 0.04, 0.09, _square, 0.15)
    S["ball"] = _render(0.25, lambda i, n: (nz() * 0.5 * (1 - i / n) ** 4 + math.sin(2 * math.pi * (1400 - 900 *
                                            i / n) * i / RATE) * 0.3 * (1 - i / n)) * 0.7)
    S["count"] = _render(0.16, lambda i, n: _square(880 * i / RATE) * _env(i, n, 0.003) * 0.22)
    S["go"] = [a + b for a, b in zip(_render(0.5, lambda i, n: _square(1320 * i / RATE) * (1 - i / n) * 0.18),
                                     _render(0.5, lambda i, n: _square(1760 * i / RATE) * (1 - i / n) * 0.14))]
    S["win"] = arp([523, 659, 784, 1047, 784, 1047, 1319], 0.13, 1.4, _square, 0.22)
    S["lose"] = arp([523, 494, 466, 440, 392], 0.2, 1.2, _tri, 0.3)
    S["wiggle"] = _render(0.12, lambda i, n: (math.sin(2 * math.pi * 160 * i / RATE) + nz() * 0.3) *
                          (1 - i / n) ** 2 * 0.5)
    S["catch"] = arp([784, 988, 1175, 1568, 1175, 1568], 0.1, 1.0, _square, 0.22)
    return S


NOTE = {n: 440 * 2 ** ((i - 9) / 12) for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#",
                                                             "A", "A#", "B"])}


def _freq(name, octave):
    return NOTE[name] * 2 ** (octave - 4)


def _make_music(kind):
    """A looping chiptune track. kind: 'battle' (fast, minor) or 'menu' (chill)."""
    rng = random.Random({"battle": 7, "menu": 3, "showcase": 11}[kind])
    bpm = {"battle": 150, "menu": 104, "showcase": 138}[kind]
    prog = {"battle": ["A", "F", "C", "G"], "menu": ["C", "A", "F", "G"], "showcase": ["D", "A#", "F", "C"]}[kind]
    minor = {"A": "m", "F": "", "C": "", "G": "", "D": "m", "A#": ""}
    beat = 60 / bpm
    bars = 8
    total = bars * 4 * beat
    n = int(total * RATE)
    out = [0.0] * n
    names = list(NOTE)

    def add(start, dur, fn, vol):
        s = int(start * RATE)
        e = min(n, s + int(dur * RATE))
        ln = e - s
        for i in range(s, e):
            k = i - s
            out[i] += fn(k / RATE) * vol * min(1.0, k / 200) * (1 - k / max(1, ln)) ** 0.6

    for bar in range(bars):
        root = prog[bar % len(prog)]
        ri = names.index(root)
        third = names[(ri + (3 if minor.get(root) == "m" else 4)) % 12]
        fifth = names[(ri + 7) % 12]
        chord = [root, third, fifth]
        t0 = bar * 4 * beat
        for e8 in range(8):  # bass eighths
            f = _freq(root, 2) * (2 if e8 % 4 == 3 else 1)
            add(t0 + e8 * beat / 2, beat / 2 * 0.9, lambda t, f=f: _tri(f * t), 0.32)
        for step in range(8 if kind != "menu" else 4):  # lead melody
            if rng.random() < 0.18:
                continue
            nm = rng.choice(chord + [names[(ri + 2) % 12]])
            octv = 5 if rng.random() < 0.7 else 6
            f = _freq(nm, octv)
            ln = beat / 2 if kind != "menu" else beat
            add(t0 + step * ln, ln * 0.85, lambda t, f=f: _square(f * t) * 0.6 + _square(f * 1.005 * t) * 0.4,
                0.07)
        for b in range(4):  # arpeggio pad
            for k, nm in enumerate(chord):
                f = _freq(nm, 4)
                add(t0 + b * beat + k * beat / 3, beat / 3, lambda t, f=f: _square(f * t), 0.035)
        nz = _noise_gen(bar)
        for e8 in range(8):  # drums
            st = t0 + e8 * beat / 2
            add(st, 0.03, lambda t: nz(), 0.06)                                   # hat
            if e8 in (0, 4) or (kind == "battle" and e8 == 5):
                add(st, 0.12, lambda t: math.sin(2 * math.pi * (110 - 400 * t) * t), 0.5)  # kick
            if e8 in (2, 6):
                add(st, 0.1, lambda t: nz() * 0.8 + math.sin(2 * math.pi * 190 * t) * 0.3, 0.22)  # snare
    return out


def _write_wav(path, samples, rate=RATE):
    data = array.array("h", (max(-32767, min(32767, int(s * 30000))) for s in samples))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


def ensure_assets():
    """Generate SFX + music WAVs once."""
    marker = os.path.join(SFX_DIR, f"v{AUDIO_VERSION}")
    if os.path.exists(marker):
        return
    os.makedirs(SFX_DIR, exist_ok=True)
    for name, samples in _make_sfx().items():
        _write_wav(os.path.join(SFX_DIR, f"{name}.wav"), samples)
    for kind in ("battle", "menu", "showcase"):
        _write_wav(os.path.join(SFX_DIR, f"music_{kind}.wav"), _make_music(kind))
    open(marker, "w").close()


def cry_path(pid):
    return os.path.join(CRY_DIR, f"{pid}.ogg")


def ensure_cry(pid):
    path = cry_path(pid)
    if os.path.exists(path):
        return path if os.path.getsize(path) else None
    os.makedirs(CRY_DIR, exist_ok=True)
    try:
        data = pokedex.fetch(CRY_URL.format(pid), timeout=15)
    except Exception:  # noqa: BLE001
        return None
    with open(path, "wb") as f:
        f.write(data)
    return path


def prefetch_cries(ids, progress=None):
    from concurrent.futures import ThreadPoolExecutor
    ids = [i for i in set(ids) if not os.path.exists(cry_path(i))]
    with ThreadPoolExecutor(16) as ex:
        for k, _ in enumerate(ex.map(ensure_cry, ids)):
            if progress:
                progress(k + 1, len(ids))


# ---------------------------------------------------------------------------- playback
class Audio:
    def __init__(self):
        self.enabled = False
        self.sfx = {}
        self.cries = {}
        self.sfx_vol = 0.7
        self.music_vol = 0.45
        self.cry_vol = 0.6
        self.last = {}
        self.track = None
        self.capture = None    # list of (time, key, vol) while recording a video
        self.clock = None      # callable giving the recording time
        self.ready = False

    def init(self, settings=None, headless=False):
        settings = settings or {}
        self.sfx_vol = float(settings.get("sfx_vol", self.sfx_vol))
        self.music_vol = float(settings.get("music_vol", self.music_vol))
        self.cry_vol = float(settings.get("cry_vol", self.cry_vol))
        try:
            ensure_assets()
            self.ready = True
        except OSError:
            return
        if headless:
            return
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(RATE, -16, 2, 512)
            pygame.mixer.set_num_channels(24)
            self.enabled = True
        except Exception:  # noqa: BLE001 - no audio device: play silently
            self.enabled = False

    def _sound(self, key):
        import pygame
        if key not in self.sfx:
            try:
                self.sfx[key] = pygame.mixer.Sound(os.path.join(SFX_DIR, f"{key}.wav"))
            except Exception:  # noqa: BLE001
                self.sfx[key] = None
        return self.sfx[key]

    def play(self, key, vol=1.0):
        now = time.time() if self.clock is None else self.clock()
        if now - self.last.get(key, -9) < THROTTLE.get(key, 0.0):
            return
        self.last[key] = now
        if self.capture is not None:
            self.capture.append((now, key, vol * self.sfx_vol))
            return
        if self.enabled and self.sfx_vol > 0:
            s = self._sound(key)
            if s:
                ch = s.play()
                if ch:
                    ch.set_volume(min(1.0, vol * self.sfx_vol))

    def cry(self, pid, vol=1.0):
        now = time.time() if self.clock is None else self.clock()
        if now - self.last.get("cry", -9) < THROTTLE["cry"]:
            return
        self.last["cry"] = now
        if self.capture is not None:
            self.capture.append((now, f"cry:{pid}", vol * self.cry_vol))
            return
        if not self.enabled or self.cry_vol <= 0:
            return
        import pygame
        if pid not in self.cries:
            path = ensure_cry(pid)
            try:
                self.cries[pid] = pygame.mixer.Sound(path) if path else None
            except Exception:  # noqa: BLE001
                self.cries[pid] = None
        s = self.cries[pid]
        if s:
            ch = s.play()
            if ch:
                ch.set_volume(min(1.0, vol * self.cry_vol))

    def music(self, kind):
        if self.capture is not None:
            self.capture.append((self.clock() if self.clock else 0.0, f"music:{kind}", max(self.music_vol, 0.35)))
            return
        if not self.enabled or kind == self.track:
            return
        import pygame
        self.track = kind
        try:
            if kind is None or self.music_vol <= 0:
                pygame.mixer.music.fadeout(400)
                return
            pygame.mixer.music.load(os.path.join(SFX_DIR, f"music_{kind}.wav"))
            pygame.mixer.music.set_volume(self.music_vol)
            pygame.mixer.music.play(-1, fade_ms=600)
        except Exception:  # noqa: BLE001
            pass

    def set_volumes(self, sfx=None, music=None, cry=None):
        if sfx is not None:
            self.sfx_vol = sfx
        if cry is not None:
            self.cry_vol = cry
        if music is not None:
            self.music_vol = music
            if self.enabled:
                import pygame
                pygame.mixer.music.set_volume(music)
                if music > 0 and self.track and not pygame.mixer.music.get_busy():
                    t, self.track = self.track, None
                    self.music(t)


AUDIO = Audio()


# ---------------------------------------------------------------------------- baking audio into videos
def _read_wav(path):
    with wave.open(path, "rb") as w:
        data = array.array("h", w.readframes(w.getnframes()))
        if w.getnchannels() == 2:
            data = data[::2]
        return data


def _decode_cry(pid):
    """Cries are OGG: let ffmpeg decode them to mono 44.1 kHz."""
    from .recorder import ffmpeg_path
    path, exe = ensure_cry(pid), ffmpeg_path()
    if not path or not exe:
        return None
    try:
        raw = subprocess.run([exe, "-loglevel", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar",
                              str(RATE), "-"], capture_output=True, check=True, timeout=20).stdout
        return array.array("h", raw)
    except (OSError, subprocess.SubprocessError):
        return None


def mix(events, duration, out_wav):
    """Mix captured (time, key, vol) events into a mono WAV `duration` seconds long."""
    n = int(duration * RATE) + 1
    buf = array.array("i", bytes(4 * n))
    cache = {}
    music = []
    for t, key, vol in events:
        if key.startswith("music:"):
            music.append((t, key[6:], vol))
            continue
        if key not in cache:
            if key.startswith("cry:"):
                cache[key] = _decode_cry(int(key[4:]))
            else:
                p = os.path.join(SFX_DIR, f"{key}.wav")
                cache[key] = _read_wav(p) if os.path.exists(p) else None
        src = cache[key]
        if not src:
            continue
        start = int(t * RATE)
        end = min(n, start + len(src))
        v = int(vol * 0.8 * 256)
        for i in range(start, end):
            buf[i] += (src[i - start] * v) >> 8
    for idx, (t, kind, vol) in enumerate(music):  # music runs until the next music event
        if kind in ("None", None) or vol <= 0:
            continue
        p = os.path.join(SFX_DIR, f"music_{kind}.wav")
        if not os.path.exists(p):
            continue
        src = _read_wav(p)
        start = int(t * RATE)
        stop = int(music[idx + 1][0] * RATE) if idx + 1 < len(music) else n
        v = int(vol * 0.55 * 256)
        L = len(src)
        for i in range(start, min(stop, n)):
            buf[i] += (src[(i - start) % L] * v) >> 8
    out = array.array("h", (32767 if s > 32767 else -32767 if s < -32767 else s for s in buf))
    with wave.open(out_wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(out.tobytes())


def mux_track(video, wav, out):
    from .recorder import ffmpeg_path
    subprocess.run([ffmpeg_path() or "ffmpeg", "-loglevel", "error", "-y", "-i", video, "-i", wav, "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "160k", "-shortest", "-movflags", "+faststart", out], check=True)
