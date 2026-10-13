"""Auto-editing for recorded showcases: keeps the hype moments at normal speed and fast-forwards the rest so
the video lands around a target length (TikTok-friendly).

How: battles are deterministic for a given seed, so we first run the showcase invisibly (no drawing, sound
muted) and ask the scene every step how much that moment matters (scene.interest(): 2 = intro, cutscenes,
the catch; 1 = boss KOs, the endgame; 0 = the long middle). From that we pick a fast-forward speed for the
boring stretches, ease in and out of it, and decide which simulation steps become video frames. The real
recording then replays the same battle step for step and only draws the chosen ones.
"""
from .audio import AUDIO

PRE_ROLL = 0.6     # seconds to slow down *before* something important happens
EASE = 0.5         # seconds to ramp between normal speed and fast-forward


class Planner:
    """Runs a throwaway copy of the showcase a slice at a time (so the UI stays responsive)."""

    def __init__(self, scene, fps=30, target=60.0, max_speed=10.0, limit_s=480):
        self.sc = scene
        self.fps = fps
        self.target = target
        self.max_speed = max_speed
        self.limit = int(limit_s * fps)
        self.flags = []
        self.done = False

    def step(self, n=600):
        saved = AUDIO.capture, AUDIO.clock
        AUDIO.capture, AUDIO.clock = [], (lambda: 0.0)   # silent: the throwaway run makes no sound
        try:
            for _ in range(n):
                if self.sc.done or len(self.flags) >= self.limit:
                    self.done = True
                    break
                self.sc.update(1 / self.fps)
                self.flags.append(self.sc.interest())
        finally:
            AUDIO.capture, AUDIO.clock = saved
        return self.done

    @property
    def seconds(self):
        return len(self.flags) / self.fps

    def schedule(self):
        return schedule(self.flags, self.fps, self.target, self.max_speed)


def schedule(flags, fps=30, target=60.0, max_speed=10.0):
    """flags: per simulation step, 2 = must keep at normal speed, 1 = nice to see (played at up to 2x),
    0 = skippable. Returns (draw, speed, ff, seconds): draw[i] says whether step i becomes a video frame,
    speed[i] the playback speed there (for the >> label), the fast-forward speed chosen for the boring parts
    and the expected video length."""
    n = len(flags)
    if n == 0:
        return [], [], 1.0, 0.0
    pre = int(PRE_ROLL * fps)
    level = [0] * n
    # an important moment also keeps the bit just before it (we can look ahead - we know the future)
    nxt = {1: n + pre + 1, 2: n + pre + 1}
    for i in range(n - 1, -1, -1):
        f = flags[i]
        if f >= 1:
            nxt[1] = i
        if f >= 2:
            nxt[2] = i
        level[i] = 2 if nxt[2] - i <= pre else 1 if nxt[1] - i <= pre else 0
    must, nice, boring = level.count(2), level.count(1), level.count(0)
    budget = target * fps

    def frames(ff, cap):
        return must + nice / min(cap, ff) + boring / ff

    # speed up the boring parts first; only if that's not enough, let the "nice" parts go a bit faster too
    for cap in (2.0, 2.5, 3.0):
        ff = 1.0
        while frames(ff, cap) > budget and ff < max_speed:
            ff = min(max_speed, ff + 0.25)
        if frames(ff, cap) <= budget:
            break
    goal_for = {2: 1.0, 1: min(cap, ff), 0: ff}
    # ease the speed in and out instead of jumping
    k = min(1.0, 3.0 / max(1, EASE * fps))
    speed, s = [], 1.0
    for i in range(n):
        s += (goal_for[level[i]] - s) * k
        speed.append(s)
    draw, acc = [], 1.0
    for i in range(n):
        acc += 1.0 / speed[i]
        if acc >= 1.0:
            acc -= 1.0
            draw.append(True)
        else:
            draw.append(False)
    draw[-1] = True
    return draw, speed, ff, sum(draw) / fps


def ff_label(surf, speed):
    """Small >> x3 tag in the corner while fast-forwarding."""
    if speed < 1.4:
        return
    from . import gfx
    from .gfx import W
    gfx.pill(surf, f">> x{speed:.0f}", (W - 60, 150), (30, 30, 40), 18)
