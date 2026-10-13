"""Real-time arena battle engine (no graphics).

Drives showcases (hundreds of Pokemon), practice battles and real-time PvP. The host runs this and
renderers (local or over the network) draw from `snapshot()`.
"""
import math
import random

from . import abilities as AB
from .battlecore import AILMENT_TO_STATUS, Mon, acc_mult, damage, move_type_and_power

WORLD_W, WORLD_H = 720, 1280
ARENA = (44, 66, 676, 1234)  # walkable x0, y0, x1, y1
TICK = 1 / 30

BOOM_MOVES = {"explosion", "self-destruct", "misty-explosion"}
PIVOT_MOVES = {"u-turn", "volt-switch", "flip-turn", "parting-shot", "teleport"}
WEATHER_MOVES = {"rain-dance": "rain", "sunny-day": "sun", "sandstorm": "sand", "snowscape": "snow",
                 "hail": "snow", "chilly-reception": "snow"}
PRIMAL_WEATHER = {"kyogre-primal": "rain", "groudon-primal": "sun"}
HAZARDS = {"stealth-rock", "spikes", "toxic-spikes"}
PROTECTS = {"protect", "detect", "kings-shield", "spiky-shield", "baneful-bunker", "obstruct", "silk-trap"}


def move_kind(m):
    key = m["key"]
    if key in BOOM_MOVES:
        return "boom"
    if m["cls"] == "status":
        if key in PROTECTS:
            return "protect"
        if key in HAZARDS or key in WEATHER_MOVES:
            return "field"
        if m["cat"] == "heal" or m["healing"] > 0:
            return "heal"
        if m["target"] == "user" or m["cat"] == "net-good-stats":
            return "buff"
        return "projectile"  # status inflicted on a target (Thunder Wave, Will-O-Wisp, Spore...)
    if m["target"] in ("all-opponents", "all-other-pokemon", "entire-field", "all-pokemon"):
        return "aoe"
    if "contact" in m["flags"]:
        return "melee"
    if m["cls"] == "spec" and ("pulse" in m["flags"] or "beam" in m["key"] or "thrower" in m["key"]
                               or m["key"] in ("psychic", "psystrike", "hydro-pump", "hyper-beam", "dark-pulse",
                                               "flash-cannon", "thunderbolt", "giga-drain", "roar-of-time",
                                               "steel-beam", "psycho-boost", "photon-geyser", "blue-flare")):
        return "beam"
    return "projectile"


RANGES = {"melee": 0, "projectile": 280, "beam": 330, "aoe": 250, "boom": 70, "heal": 0, "buff": 0,
          "protect": 0, "field": 300}


class Unit:
    __slots__ = ("mon", "uid", "team", "x", "y", "vx", "vy", "r", "boss", "face", "target", "focus", "retarget",
                 "cd", "anim", "stun", "charging", "charge_move", "shield", "kinds", "dmg_scale", "goto",
                 "goto_t", "queued", "status_t", "item_t", "spawn_t", "kills", "mega_at", "plan", "storm",
                 "gmax_at", "gmax_t")

    def __init__(self, mon, uid, team, x, y, r, boss, hp_mult):
        self.mon, self.uid, self.team = mon, uid, team
        self.x, self.y, self.vx, self.vy = x, y, 0.0, 0.0
        self.storm = 0.0        # battle royale storm damage waiting to be applied
        self.r, self.boss = r, boss
        self.face = 1
        self.target = self.focus = None
        self.retarget = 0.0
        self.cd = 0.0
        self.anim = 0.0
        self.stun = 0.0
        self.charging = 0.0
        self.charge_move = None
        self.shield = 0.0
        self.kinds = [move_kind(m) for m in mon.moves]
        self.dmg_scale = 1.0 / hp_mult
        self.goto = None
        self.goto_t = 0.0
        self.queued = None
        self.status_t = 0.0
        self.item_t = 0.0
        self.spawn_t = 0.0
        self.kills = 0
        self.mega_at = None
        self.plan = None
        self.gmax_at = None     # when this Pokemon will Gigantamax (Pokemon with a Gigantamax form only)
        self.gmax_t = 0.0       # seconds of Gigantamax left

    @property
    def alive(self):
        return not self.mon.fainted

    def norm_speed(self):
        return self.mon.stat("spe") * 50 / self.mon.member.level


class Projectile:
    __slots__ = ("src", "tgt", "move", "x", "y", "speed", "tx", "ty", "mult")

    def __init__(self, src, tgt, move, mult=1.0):
        self.src, self.tgt, self.move = src, tgt, move
        self.x, self.y = src.x, src.y - src.r * 0.4
        self.speed = 520 if move["power"] else 420
        self.tx, self.ty = tgt.x, tgt.y
        self.mult = mult


class Blast:
    __slots__ = ("src", "move", "x", "y", "rad", "t", "team")

    def __init__(self, src, move, x, y, rad, delay):
        self.src, self.move, self.x, self.y, self.rad, self.t = src, move, x, y, rad, delay
        self.team = src.team


class Sim:
    """opts:
        hp_mult        multiply everyone's HP (longer fights)
        boss_hp_mult   extra HP for units flagged boss
        radius         body radius (px) for normal units
        mega           {team: "auto" | "manual" | "off"}
        mega_limit     {team: max megas, None = unlimited}
        ai             {team: "easy" | "normal" | "hard" | "insane"}
        time_ramp      seconds after which damage ramps up to force an ending
        zone           battle royale storm: {"start": s, "end": s, "min": radius} - a circle that shrinks in
                       steps; anyone outside takes damage and runs back in
    """

    def __init__(self, dex, teams, seed=None, **opts):
        self.dex = dex
        self.rng = random.Random(seed)
        self.opts = opts
        self.t = 0.0
        self.units = []
        self.projectiles = []
        self.blasts = []
        self.events = []
        self.weather = None
        self.weather_t = 0.0
        self.winner = None
        self.over = False
        self.megas_used = {}
        self.teras_used = {}
        self.domain = None     # "sea" (Primal Kyogre), "land" (Primal Groudon), "sky" (Mega Rayquaza)
        self.env_blasts = []   # [x, y, rad, frac, type, delay] - meteors etc. that hurt everyone
        self.zone = None       # [cx, cy, radius] once the battle royale storm starts
        self.bench = set()     # uids standing back to watch (the final duel): they don't act and can't be hit
        self._zone_from = None
        self.tick = 0
        self.cmd_log = []      # [tick, team, cmd] - everything needed to replay the battle
        self.started = False
        hp_mult = opts.get("hp_mult", 9.0)
        boss_mult = opts.get("boss_hp_mult", 3.0)
        radius = opts.get("radius", 22)
        self.paused = False
        self.arena = opts.get("arena", ARENA)   # walkable x0, y0, x1, y1 (wide royales use a bigger one)
        uid = 1
        for ti, specs in enumerate(teams):
            for spec in specs:
                mon = Mon(dex, spec["member"], uid, ti)
                boss = spec.get("boss", False)
                x, y = spec.get("pos") or self._default_pos(ti, len(self.team_units(ti)), len(specs))
                r = radius * (1.7 if boss else 1.0)
                u = Unit(mon, uid, ti, x, y, r, boss, hp_mult * (boss_mult if boss else 1.0))
                u.cd = self.rng.uniform(0.2, 1.4)
                u.face = 1 if ti == 0 else -1
                if self.opts.get("mega", {}).get(ti, "auto") == "auto" and mon.can_mega:
                    u.mega_at = self.rng.uniform(4, 25)
                elif self.opts.get("gmax", True) and mon.can_gmax:
                    u.gmax_at = self.rng.uniform(6, 30)
                self.units.append(u)
                uid += 1
        self.by_id = {u.uid: u for u in self.units}
        self._hp_mult, self._boss_mult, self._radius = hp_mult, boss_mult, radius

    # ------------------------------------------------------------------ helpers
    def team_units(self, team):
        return [u for u in self.units if u.team == team]

    def _default_pos(self, team, i, n):
        cols = 3 if n <= 6 else max(6, int(math.sqrt(n * 2.4)))
        row, col = divmod(i, cols)
        w = self.arena[2] - self.arena[0] - 60
        x = self.arena[0] + 30 + (col + 0.5) * w / cols
        y_gap = 46 if n > 6 else 110
        y = (self.arena[1] + 90 + row * y_gap) if team == 0 else (self.arena[3] - 90 - row * y_gap)
        return x, y

    def emit(self, *ev):
        self.events.append(list(ev))

    def alive_teams(self):
        return sorted({u.team for u in self.units if u.alive})

    def enemies(self, u):
        return [e for e in self.units if e.alive and e.team != u.team and e.uid not in self.bench]

    # ------------------------------------------------------------------ commands
    def command(self, team, cmd):
        self.cmd_log.append([self.tick, team, cmd])
        kind = cmd.get("cmd")
        if kind == "focus":
            tgt = self.by_id.get(cmd.get("target"))
            if not tgt or not tgt.alive or tgt.team == team:
                return
            ids = cmd.get("units")
            for u in self.units:
                if u.team == team and u.alive and (not ids or u.uid in ids):
                    u.focus = tgt.uid
                    u.target = tgt
        elif kind == "mega":
            u = self.by_id.get(cmd.get("unit"))
            if u and u.team == team and u.alive:
                self.try_mega(u)
        elif kind == "tera":
            u = self.by_id.get(cmd.get("unit"))
            if u and u.team == team and u.alive:
                self.try_tera(u)
        elif kind == "move":
            u = self.by_id.get(cmd.get("unit"))
            if u and u.team == team and u.alive and 0 <= cmd.get("slot", -1) < len(u.mon.moves):
                u.queued = cmd["slot"]
        elif kind == "goto":
            u = self.by_id.get(cmd.get("unit"))
            if u and u.team == team and u.alive:
                u.goto = (float(cmd["pos"][0]), float(cmd["pos"][1]))
                u.goto_t = 2.5

    def mega_allowed(self, u):
        limit = self.opts.get("mega_limit", {}).get(u.team)
        return limit is None or self.megas_used.get(u.team, 0) < limit

    def spawn(self, member, team, pos, boss=True, hp_scale=1.0, radius_scale=1.0):
        """Add a Pokemon mid-battle (event bosses like Arceus). Returns the new unit."""
        uid = max(self.by_id) + 1 if self.by_id else 1
        mon = Mon(self.dex, member, uid, team)
        r = self._radius * (1.7 if boss else 1.0) * radius_scale
        u = Unit(mon, uid, team, pos[0], pos[1], r, boss,
                 self._hp_mult * (self._boss_mult if boss else 1.0) * hp_scale)
        u.cd = 0.6
        if mon.can_mega:
            u.mega_at = self.t + 0.1
        self.units.append(u)
        self.by_id[uid] = u
        return u

    def env_blast(self, x, y, rad, frac, mtype="rock", delay=0.6):
        """A hazard that hurts everyone in range by `frac` of their max HP (meteors, eruptions)."""
        self.env_blasts.append([x, y, rad, frac, mtype, delay])
        self.emit("aoe", round(x), round(y), round(rad), mtype, delay, "env")

    ZONE_STEPS = 5

    def _update_zone(self, dt):
        z = self.opts.get("zone")
        if not z:
            return
        start, end, rmin = z.get("start", 15), z.get("end", 95), z.get("min", 70)
        if self.t < start:
            return
        full = math.hypot(self.arena[2] - self.arena[0], self.arena[3] - self.arena[1]) / 2 + 20
        if self.zone is None:
            # center drifts somewhere inside the middle of the arena, picked once
            cx = (self.arena[0] + self.arena[2]) / 2 + self.rng.uniform(-90, 90)
            cy = (self.arena[1] + self.arena[3]) / 2 + self.rng.uniform(-160, 160)
            self.zone = [cx, cy, full]
            self._zone_from = full
            self.emit("zone", 1)
        # shrink in steps: each step = hold, then close in
        span = (end - start) / self.ZONE_STEPS
        step = min(self.ZONE_STEPS - 1, int((self.t - start) / span))
        within = (self.t - start) - step * span
        r_from = full - (full - rmin) * step / self.ZONE_STEPS
        r_to = full - (full - rmin) * (step + 1) / self.ZONE_STEPS
        hold = span * 0.45
        k = 0.0 if within < hold else min(1.0, (within - hold) / (span - hold))
        # after the last step the storm keeps closing until nobody can hide
        r = r_from + (r_to - r_from) * k if self.t < end else max(0.0, rmin * (1 - (self.t - end) / 15))
        if k > 0 and self._zone_from != r_from:
            self._zone_from = r_from
            self.emit("zone", step + 2)
        self.zone[2] = r
        cx, cy = self.zone[0], self.zone[1]
        for u in self.units:
            if u.alive and math.hypot(u.x - cx, u.y - cy) > r:
                # per-tick damage is under 1 HP, so build it up and apply whole points
                u.storm += u.mon.maxhp * 0.10 * dt * (0.6 if u.boss else 1.0)
                if u.storm >= 1:
                    whole = int(u.storm)
                    u.storm -= whole
                    self._hurt(u, whole, None, chip=True, guard=False)  # Magic Guard doesn't stop the storm

    def bench_units(self, units):
        """Send these Pokemon to the sidelines: they stop fighting and can't be hit (until the battle ends)."""
        for u in units:
            self.bench.add(u.uid)
            u.shield = 1e9
            u.target = None

    def shockwave(self, src, radius, frac, mtype="psychic"):
        """A blast centered on `src` that hits every other team's Pokemon in range (KOs count for `src`)."""
        self.emit("aoe", round(src.x), round(src.y), round(radius), mtype, 0.0, "env")
        self.emit("blast", round(src.x), round(src.y), round(radius), mtype)
        for u in self.units:
            if u.alive and u.team != src.team and math.hypot(u.x - src.x, u.y - src.y) < radius + u.r * 0.5:
                self._hurt(u, u.mon.maxhp * frac * (0.35 if u.boss else 1.0), src, chip=True, guard=False)

    def set_domain(self, d):
        if d == self.domain:
            return
        self.domain = d
        self.emit("domain", d)

    def tera_allowed(self, u):
        limit = self.opts.get("tera_limit", {}).get(u.team, 0)
        return (limit is None or self.teras_used.get(u.team, 0) < limit) and not u.mon.terastallized \
            and not u.mon.megaed and not u.mon.gmaxed

    def try_tera(self, u):
        if not self.tera_allowed(u):
            return False
        t = u.mon.terastallize()
        self.teras_used[u.team] = self.teras_used.get(u.team, 0) + 1
        u.stun = max(u.stun, 0.6)
        u.shield = max(u.shield, 0.6)
        self.emit("tera", u.uid, t)
        return True

    def _ability_label(self, u, name=None):
        self.emit("label", u.uid, AB.ability_name(name or u.mon.ability), "normal")

    def _battle_start(self):
        """Entry abilities for everyone: weather, Intimidate, Download..."""
        self.started = True
        for u in sorted(self.units, key=lambda u: u.mon.stat("spe")):
            foes = self.enemies(u)
            foe = min(foes, key=lambda f: math.hypot(f.x - u.x, f.y - u.y)) if foes else None
            for kind, payload in AB.entry_effects(u.mon, foe.mon if foe else None):
                if kind == "weather":
                    self._ability_label(u)
                    self.set_weather(payload[0], 9999 if payload[1] > 100 else 30.0)
                elif kind == "intimidate":
                    self._ability_label(u)
                    for f in foes:
                        if math.hypot(f.x - u.x, f.y - u.y) < 420 or len(foes) <= 6:
                            if f.mon.apply_stages({"atk": -1}, from_foe=True):
                                self.emit("boost", f.uid, 0)
                elif kind == "boost":
                    if u.mon.apply_stages(payload):
                        self.emit("boost", u.uid, 1)

    def try_mega(self, u):
        if not u.mon.can_mega or not self.mega_allowed(u):
            return False
        form = u.mon.mega_evolve()
        self.megas_used[u.team] = self.megas_used.get(u.team, 0) + 1
        u.r *= 1.12
        u.stun = max(u.stun, 0.9)
        u.shield = max(u.shield, 0.9)
        self.emit("mega", u.uid, form["id"], form["name"])
        if form["key"] in PRIMAL_WEATHER:
            self.set_weather(PRIMAL_WEATHER[form["key"]], 9999)
            self.set_domain("sea" if "kyogre" in form["key"] else "land")
        elif form["key"] == "rayquaza-mega":
            self.weather = None  # Delta Stream: the sky calms every other weather
            self.emit("weather", None)
            self.set_domain("sky")
        else:
            for kind, payload in AB.entry_effects(u.mon, None):
                if kind == "weather" and self.weather != payload[0]:
                    self._ability_label(u)
                    self.set_weather(payload[0], 30.0)
        return True

    GMAX_SIZE, GMAX_TIME = 1.9, 22.0

    def gmax_allowed(self, u):
        """One Gigantamax at a time per team."""
        return not any(x.alive and x.team == u.team and x.mon.gmaxed for x in self.units)

    def try_gmax(self, u):
        if not u.mon.can_gmax or not self.gmax_allowed(u):
            return False
        form = u.mon.gigantamax()
        u.r *= self.GMAX_SIZE
        u.gmax_t = self.GMAX_TIME
        u.stun = max(u.stun, 1.2)
        u.shield = max(u.shield, 1.2)
        name, mtype = u.mon.gmax_move()
        self.emit("gmax", u.uid, form["id"], form["name"], name, mtype)
        return True

    def end_gmax(self, u):
        if not u.mon.gmaxed:
            return
        u.mon.end_gmax()
        u.r /= self.GMAX_SIZE
        u.gmax_t = 0.0
        if u.alive:
            self.emit("gmax_end", u.uid, u.mon.entry["id"])

    def set_weather(self, w, dur=20.0):
        self.weather = w
        self.weather_t = dur
        self.emit("weather", w)

    # ------------------------------------------------------------------ main loop
    def step(self, dt=TICK):
        if self.over or self.paused:
            return
        if not self.started:
            self._battle_start()
        self.tick += 1
        self.t += dt
        if self.weather and self.weather_t < 9000:
            self.weather_t -= dt
            if self.weather_t <= 0:
                self.weather = None
                self.emit("weather", None)
        ramp_at = self.opts.get("time_ramp", 75)
        self.ramp = 1.0 + max(0.0, self.t - ramp_at) / 15.0
        alive = [u for u in self.units if u.alive and u.uid not in self.bench]
        grid = self._grid(alive)
        for u in alive:
            self._update_unit(u, dt, grid)
        self._separate(alive, grid)
        self._update_projectiles(dt)
        self._update_blasts(dt)
        self._update_env(dt)
        self._update_zone(dt)
        teams = self.alive_teams()
        if len(teams) <= 1:
            self.over = True
            self.winner = teams[0] if teams else None
            self.emit("end", self.winner)

    def _grid(self, alive):
        g = {}
        for u in alive:
            g.setdefault((int(u.x // 64), int(u.y // 64)), []).append(u)
        return g

    def _near(self, grid, x, y, rad):
        cx, cy = int(x // 64), int(y // 64)
        n = int(rad // 64) + 1
        for gx in range(cx - n, cx + n + 1):
            for gy in range(cy - n, cy + n + 1):
                yield from grid.get((gx, gy), ())

    def _separate(self, alive, grid):
        for u in alive:
            for o in self._near(grid, u.x, u.y, u.r * 2):
                if o is u or o.uid < u.uid:
                    continue
                dx, dy = o.x - u.x, o.y - u.y
                d2 = dx * dx + dy * dy
                min_d = (u.r + o.r) * 0.8
                if d2 < min_d * min_d:
                    d = math.sqrt(d2) or 0.01
                    push = (min_d - d) * 0.5
                    nx, ny = (dx / d, dy / d) if d > 0.011 else (self.rng.uniform(-1, 1), self.rng.uniform(-1, 1))
                    wu = 0.3 if u.boss and not o.boss else 0.5
                    wo = 1 - wu
                    u.x -= nx * push * wu * 2
                    u.y -= ny * push * wu * 2
                    o.x += nx * push * wo * 2
                    o.y += ny * push * wo * 2
        for u in alive:
            u.x = min(max(u.x, self.arena[0] + u.r * 0.6), self.arena[2] - u.r * 0.6)
            u.y = min(max(u.y, self.arena[1] + u.r * 0.6), self.arena[3] - u.r * 0.4)

    # ------------------------------------------------------------------ unit AI
    def _ai(self, u):
        return self.opts.get("ai", {}).get(u.team, "normal")

    def _pick_target(self, u, grid):
        if u.focus:
            f = self.by_id.get(u.focus)
            if f and f.alive:
                return f
            u.focus = None
        level = self._ai(u)
        best, best_s = None, 1e18
        for e in self.units:
            if not e.alive or e.team == u.team or e.uid in self.bench:
                continue
            d = math.hypot(e.x - u.x, e.y - u.y)
            s = d
            if level in ("hard", "insane"):
                # prefer low HP targets and ones we hit super effectively
                bestm = max((self._move_value(u, m, e) for m in u.mon.moves), default=1)
                s = d * (0.6 + e.mon.hp_frac()) / max(0.3, bestm / 80)
            elif level == "easy":
                s = d * self.rng.uniform(0.5, 2.5)
            else:
                s = d * self.rng.uniform(0.85, 1.25)
            if s < best_s:
                best, best_s = e, s
        return best

    def _move_value(self, u, m, tgt):
        from .types import effectiveness
        if m["power"] <= 0:
            return 0
        v = m["power"] * (sum(m["hits"]) / 2) * min(m["acc"], 100) / 100
        if m["type"] in u.mon.types:
            v *= 1.5
        v *= effectiveness(m["type"], tgt.mon.types)
        atk = u.mon.stat("atk" if m["cls"] == "phys" else "spa")
        return v * atk / 100

    def _choose_move(self, u, tgt):
        mon = u.mon
        if mon.choice_lock is not None:
            return mon.choice_lock
        level = self._ai(u)
        if level == "easy":
            return self.rng.randrange(len(mon.moves))
        scores = []
        for i, (m, k) in enumerate(zip(mon.moves, u.kinds)):
            if k == "heal":
                s = 160 if mon.hp_frac() < 0.45 else 0
            elif k == "buff":
                boosts = sum(v for v in m["stats"].values() if v > 0)
                s = 90 * boosts if mon.hp_frac() > 0.6 and max(mon.stages.values()) < 2 else 0
            elif k == "protect":
                s = 60 if mon.hp_frac() < 0.3 and self.rng.random() < 0.3 else 0
            elif k == "field":
                s = 70 if (m["key"] in WEATHER_MOVES and self.weather != WEATHER_MOVES[m["key"]]) \
                    or (m["key"] in HAZARDS and self.rng.random() < 0.25) else 0
            elif k == "boom":
                near = sum(1 for e in self.enemies(u) if math.hypot(e.x - u.x, e.y - u.y) < 110)
                s = 150 if (near >= 3 or mon.hp_frac() < 0.25) else 0
            elif m["power"] <= 0:
                st = AILMENT_TO_STATUS.get(m["ailment"])
                s = 80 if st and tgt.mon.can_status(st, self.weather) else 0
            else:
                s = self._move_value(u, m, tgt)
                if "charge" in m["flags"] and not (m["key"] == "solar-beam" and self.weather == "sun"):
                    s *= 0.6
                if "recharge" in m["flags"]:
                    s *= 0.7
            if level == "normal":
                s *= self.rng.uniform(0.6, 1.4)
            elif level == "hard":
                s *= self.rng.uniform(0.9, 1.1)
            scores.append(s)
        if max(scores) <= 0:
            return self.rng.randrange(len(mon.moves))
        if level in ("hard", "insane"):
            return max(range(len(scores)), key=scores.__getitem__)
        # normal: weighted pick among decent options for variety (big battles look better)
        total = sum(max(0, s) ** 2 for s in scores)
        r = self.rng.random() * total
        for i, s in enumerate(scores):
            r -= max(0, s) ** 2
            if r <= 0:
                return i
        return 0

    def _update_unit(self, u, dt, grid):
        mon = u.mon
        u.anim = max(0.0, u.anim - dt)
        u.shield = max(0.0, u.shield - dt)
        u.spawn_t += dt
        # status ticks
        if mon.status in ("brn", "psn", "tox"):
            u.status_t += dt
            if u.status_t >= 3.0:
                u.status_t = 0
                if mon.ability == "poison-heal" and mon.status != "brn":
                    if mon.heal(mon.maxhp / 8):
                        self.emit("heal", u.uid, 0)
                else:
                    if mon.status == "tox":
                        mon.toxic_n = min(mon.toxic_n + 1, 15)
                        frac = mon.toxic_n / 16
                    else:
                        frac = 1 / 16
                    self._hurt(u, mon.maxhp * frac * u.dmg_scale, None, chip=True)
                if not u.alive:
                    return
        if mon.status in ("slp", "frz"):
            u.status_t += dt
            if u.status_t >= 1.0:
                u.status_t = 0
                mon.status_turns -= 1
                if mon.status_turns < 0 or (mon.status == "frz" and self.rng.random() < 0.3):
                    mon.status = None
                    self.emit("status", u.uid, "cure")
            return
        # items over time
        u.item_t += dt
        if u.item_t >= 3.0:
            u.item_t = 0
            if mon.item == "leftovers" or (mon.item == "black-sludge" and "poison" in mon.types):
                if mon.heal(mon.maxhp / 16):
                    self.emit("heal", u.uid, 0)
            elif mon.item == "black-sludge":
                self._hurt(u, mon.maxhp / 8 * u.dmg_scale, None, chip=True)
            if self.weather == "sand" and not any(t in mon.types for t in ("rock", "ground", "steel")) \
                    and mon.ability not in ("sand-force", "sand-rush", "sand-veil", "overcoat"):
                self._hurt(u, mon.maxhp / 16 * u.dmg_scale, None, chip=True)
            for kind, val, msg in AB.end_of_turn(mon, self.weather, self.rng):
                if kind == "boost":
                    if mon.apply_stages(val):
                        self.emit("boost", u.uid, 1)
                elif kind == "heal" and mon.heal(mon.maxhp * val):
                    self.emit("heal", u.uid, 0)
                elif kind == "damage":
                    self._hurt(u, mon.maxhp * val * u.dmg_scale, None, chip=True)
                elif kind == "cure":
                    mon.status = None
                    self.emit("status", u.uid, "cure")
        if not u.alive:
            return
        if u.stun > 0:
            u.stun -= dt
            return
        if u.gmax_t > 0:
            u.gmax_t -= dt
            if u.gmax_t <= 0:
                self.end_gmax(u)
        if u.gmax_at is not None and (self.t >= u.gmax_at or mon.hp_frac() < 0.55):
            u.gmax_at = None
            if self.try_gmax(u):
                return
        if u.mega_at is not None and (self.t >= u.mega_at or mon.hp_frac() < 0.6):
            u.mega_at = None
            self.try_mega(u)
            return
        if u.charging > 0:
            u.charging -= dt
            if u.charging <= 0 and u.target and u.target.alive:
                self._execute(u, u.charge_move, u.target, grid, charged=True)
            return
        # battle royale: run back inside the storm circle
        if self.zone and not u.goto:
            zx, zy, zr = self.zone
            d = math.hypot(u.x - zx, u.y - zy)
            if d > zr * 0.92:
                k = zr * 0.55 / max(d, 1)
                u.goto = (zx + (u.x - zx) * k, zy + (u.y - zy) * k)
                u.goto_t = 1.2
        # target
        u.retarget -= dt
        if u.target is None or not u.target.alive or u.retarget <= 0:
            u.target = self._pick_target(u, grid)
            u.retarget = self.rng.uniform(0.8, 1.6)
        tgt = u.target
        if tgt is None:
            return
        dx, dy = tgt.x - u.x, tgt.y - u.y
        dist = math.hypot(dx, dy) or 0.01
        if abs(dx) > 2:
            u.face = 1 if dx > 0 else -1
        speed = 40 + u.norm_speed() * 0.65
        if u.goto and u.goto_t > 0:
            u.goto_t -= dt
            gx, gy = u.goto[0] - u.x, u.goto[1] - u.y
            gd = math.hypot(gx, gy)
            if gd > 6:
                u.x += gx / gd * speed * 1.3 * dt
                u.y += gy / gd * speed * 1.3 * dt
            else:
                u.goto = None
            u.cd -= dt
            return
        u.cd -= dt
        slot = self._peek_slot(u, tgt)
        kind = u.kinds[slot]
        rng_ = RANGES[kind] or (u.r + tgt.r + 8)
        if kind in ("heal", "buff", "protect"):
            rng_ = 1e9
        if dist > rng_ * 0.92:
            wob = math.sin(self.t * 3 + u.uid) * 0.35
            nx, ny = dx / dist, dy / dist
            u.x += (nx - ny * wob) * speed * dt
            u.y += (ny + nx * wob) * speed * dt
        elif u.cd <= 0:
            slot = self._take_slot(u, tgt, slot)
            move = mon.moves[slot]
            if mon.status == "par" and self.rng.random() < 0.25:
                self.emit("label", u.uid, "PARALYZED", "electric")
            elif "charge" in move["flags"] and not (move["key"] in ("solar-beam", "solar-blade")
                                                     and self.weather == "sun"):
                u.charging = 0.9
                u.charge_move = move
                self.emit("charge", u.uid, move["name"], move["type"])
            else:
                self._execute(u, move, tgt, grid)
            if mon.item in ("choice-band", "choice-specs", "choice-scarf") and mon.choice_lock is None:
                mon.choice_lock = slot
            base_cd = min(2.6, max(0.75, 2.5 - u.norm_speed() / 110))
            u.cd = base_cd * self.rng.uniform(0.85, 1.15) * (1.6 if u.boss else 1.0)
            if "recharge" in move["flags"]:
                u.stun = 1.2

    def _peek_slot(self, u, tgt):
        """The move this unit plans to use next (chosen once per attack so range checks stay stable)."""
        if u.queued is not None:
            return u.queued
        if u.plan is None or u.plan[0] != tgt.uid:
            u.plan = (tgt.uid, self._choose_move(u, tgt))
        return u.plan[1]

    def _take_slot(self, u, tgt, slot):
        u.plan = None
        if u.queued is not None:
            slot, u.queued = u.queued, None
        return slot

    # ------------------------------------------------------------------ actions
    def _execute(self, u, move, tgt, grid, charged=False):
        kind = move_kind(move)
        mon = u.mon
        mtype = move_type_and_power(mon, move, self.weather)[0]
        name = move["name"]
        if mon.gmaxed and mtype == mon.gmax_move()[1]:
            name = "G-Max " + mon.gmax_move()[0]
        self.emit("use", u.uid, name, mtype, kind)
        if AB.protean(mon, mtype):
            self._ability_label(u)
        u.anim = 0.25
        key = move["key"]
        if kind == "melee":
            self.emit("melee", u.uid, tgt.uid)
            if not self._protected(tgt):
                self._hit(u, tgt, move)
            if "contact" in move["flags"] and tgt.mon.item == "rocky-helmet" and u.alive:
                self._hurt(u, mon.maxhp / 6 * u.dmg_scale, None, chip=True)
            if "contact" in move["flags"] and u.alive:
                reacts, aname = AB.contact_reactions(mon, tgt.mon, self.rng)
                for rk, val in reacts:
                    if rk == "status" and mon.can_status(val, self.weather):
                        self.emit("status", u.uid, mon.set_status(val, self.rng))
                    elif rk == "damage":
                        self._hurt(u, mon.maxhp * val * u.dmg_scale, None, chip=True)
            if key in PIVOT_MOVES and u.alive:
                self._pivot(u)
        elif kind == "projectile":
            hits = self.rng.randint(*move["hits"]) if move["hits"][1] > 1 else 1
            for h in range(hits):
                p = Projectile(u, tgt, move)
                p.x -= h * 14 * (tgt.x - u.x) / (abs(tgt.x - u.x) + abs(tgt.y - u.y) + 1)
                p.y -= h * 14 * (tgt.y - u.y) / (abs(tgt.x - u.x) + abs(tgt.y - u.y) + 1)
                self.projectiles.append(p)
            if key in PIVOT_MOVES:
                self._pivot(u)
        elif kind == "beam":
            self.emit("beam", u.uid, round(u.x), round(u.y - u.r * 0.3), round(tgt.x), round(tgt.y),
                      move["type"], 10 if move["power"] >= 100 else 6)
            if not self._protected(tgt):
                self._hit(u, tgt, move)
        elif kind == "aoe":
            rad = 70 + move["power"] * 0.25
            if self.opts.get("radius", 22) < 16:
                rad *= 0.8
            delay = 0.45
            self.blasts.append(Blast(u, move, tgt.x, tgt.y, rad, delay))
            self.emit("aoe", round(tgt.x), round(tgt.y), round(rad), move["type"], delay, move["key"])
        elif kind == "boom":
            rad = 120
            self.emit("boom", round(u.x), round(u.y), rad)
            self.emit("label", u.uid, "SACRIFICE", "fighting")
            for e in list(self._near(grid, u.x, u.y, rad)):
                if e.alive and e.team != u.team and math.hypot(e.x - u.x, e.y - u.y) < rad + e.r:
                    self._hit(u, e, move, spread=True)
            u.mon.hp = 0
            u.mon.fainted = True
            self._faint(u, None)
        elif kind == "heal":
            frac = (move["healing"] or 50) / 100
            if key in ("rest",):
                mon.status = "slp"
                mon.status_turns = 2
                frac = 1
            if mon.heal(mon.maxhp * frac):
                self.emit("heal", u.uid, 1)
        elif kind == "buff":
            ch = mon.apply_stages(move["stats"], from_foe=False)
            if key == "belly-drum":
                mon.hp = max(1, mon.hp - mon.maxhp // 2)
                mon.stages["atk"] = 6
            if ch or key == "belly-drum":
                self.emit("boost", u.uid, 1)
        elif kind == "protect":
            u.shield = 1.4
            self.emit("protect", u.uid)
        elif kind == "field":
            if key in WEATHER_MOVES:
                self.set_weather(WEATHER_MOVES[key])
            else:
                # hazards become a field of rocks/spikes around the enemy blob
                self.blasts.append(Blast(u, dict(move, power=40, cls="phys", type="rock" if key == "stealth-rock"
                                                 else move["type"]), tgt.x, tgt.y, 90, 0.5))
                self.emit("aoe", round(tgt.x), round(tgt.y), 90, "rock", 0.5, key)
        if mon.item == "life-orb" and move["power"] > 0 and u.alive and kind != "boom":
            self._hurt(u, mon.maxhp / 10 * u.dmg_scale, None, chip=True)

    def _pivot(self, u):
        # dash back towards our own side
        back = -1 if u.team == 0 else 1
        u.goto = (min(max(u.x + self.rng.uniform(-60, 60), self.arena[0] + 20), self.arena[2] - 20),
                  min(max(u.y + back * 140, self.arena[1] + 20), self.arena[3] - 20))
        u.goto_t = 0.6

    def _protected(self, tgt):
        if tgt.shield > 0:
            self.emit("label", tgt.uid, "PROTECTED", "normal")
            return True
        return False

    def _update_projectiles(self, dt):
        keep = []
        for p in self.projectiles:
            if p.tgt.alive:
                p.tx, p.ty = p.tgt.x, p.tgt.y
            dx, dy = p.tx - p.x, p.ty - p.y
            d = math.hypot(dx, dy)
            step = p.speed * dt
            if d <= step + 4:
                if p.tgt.alive:
                    if not self._protected(p.tgt):
                        self._hit(p.src, p.tgt, p.move)
                    self.emit("impact", round(p.tx), round(p.ty), p.move["type"])
                continue
            p.x += dx / d * step
            p.y += dy / d * step
            keep.append(p)
        self.projectiles = keep

    def _update_blasts(self, dt):
        if not self.blasts:
            return
        keep = []
        grid = None
        for b in self.blasts:
            b.t -= dt
            if b.t > 0:
                keep.append(b)
                continue
            if grid is None:
                grid = self._grid([u for u in self.units if u.alive])
            self.emit("blast", round(b.x), round(b.y), round(b.rad), b.move["type"])
            for e in list(self._near(grid, b.x, b.y, b.rad)):
                if e.alive and e.team != b.team and math.hypot(e.x - b.x, e.y - b.y) < b.rad + e.r * 0.5:
                    if not self._protected(e):
                        self._hit(b.src, e, b.move, spread=True)
        self.blasts = keep

    def _update_env(self, dt):
        keep = []
        for b in self.env_blasts:
            b[5] -= dt
            if b[5] > 0:
                keep.append(b)
                continue
            x, y, rad, frac, mtype, _ = b
            self.emit("blast", round(x), round(y), round(rad), mtype)
            for u in self.units:
                if u.alive and math.hypot(u.x - x, u.y - y) < rad + u.r * 0.5:
                    self._hurt(u, u.mon.maxhp * frac * (0.35 if u.boss else 1.0), None)
        self.env_blasts = keep

    # ------------------------------------------------------------------ damage
    def _hit(self, u, tgt, move, spread=False):
        if not tgt.alive:
            return
        mon, tmon = u.mon, tgt.mon
        mtype = move_type_and_power(mon, move, self.weather)[0]
        imm = AB.immunity(tmon, mon, move, mtype)
        if imm:
            verb, eff_ = imm
            self.emit("label", tgt.uid, verb, mtype)
            if eff_[0] == "heal" and tmon.heal(tmon.maxhp * eff_[1]):
                self.emit("heal", tgt.uid, 1)
            elif eff_[0] == "boost" and tmon.apply_stages(eff_[1]):
                self.emit("boost", tgt.uid, 1)
            elif eff_[0] == "flash_fire":
                tmon.flags["flash_fire"] = True
            return
        if move["power"] > 0 and ((self.domain == "sea" and mtype == "fire") or
                                  (self.domain == "land" and mtype == "water")):
            self.emit("label", tgt.uid, "EVAPORATED", mtype)
            return
        acc = move["acc"]
        accm = AB.accuracy(mon, tmon, move)
        if acc <= 100 and accm is not None:
            if self.weather == "rain" and move["key"] in ("thunder", "hurricane"):
                acc = 101
            elif self.rng.random() * 100 >= acc * accm * acc_mult(mon.stages["acc"] - tmon.stages["eva"]):
                self.emit("miss", tgt.uid)
                return
        if move["power"] > 0:
            dmg, eff, crit = damage(mon, tmon, move, self.rng, self.weather, spread=spread)
            if self.domain == "sky" and eff > 1 and "flying" in tmon.types:
                dmg, eff = dmg / 2, eff / 2  # Delta Stream: Flying types lose their weaknesses
            if eff == 0:
                self.emit("label", tgt.uid, "NO EFFECT", "normal")
                return
            dmg *= tgt.dmg_scale  # scaled by the *target's* bonus HP (bosses used to be scaled down by their own)
            if u.boss and not tgt.boss:  # legendaries tear through regular Pokemon
                dmg *= self.opts.get("boss_dmg", 3.0)
            dmg *= self.ramp
            if tmon.item == "air-balloon":
                tmon.lose_item()
            if AB.ab(tmon, mon) == "disguise" and not tmon.flags.get("busted"):
                tmon.flags["busted"] = True
                self._ability_label(tgt, "disguise")
                dmg = tmon.maxhp / 8 * tgt.dmg_scale
            dealt = self._hurt(tgt, dmg, u, eff=eff, crit=crit)
            hb = AB.on_hit(tmon, mtype, mon) if tgt.alive else None
            if hb and tmon.apply_stages(hb):
                self.emit("boost", tgt.uid, 1)
            if move["drain"] > 0 and u.alive:
                mon.heal(dealt * move["drain"] / 100)
            elif move["drain"] < 0 and u.alive and mon.ability != "rock-head":
                self._hurt(u, dealt * -move["drain"] / 100, None, chip=True)
            if eff > 1 and tmon.item == "weakness-policy" and tgt.alive:
                tmon.lose_item()
                tmon.apply_stages({"atk": 2, "spa": 2})
                self.emit("boost", tgt.uid, 1)
            if move["key"] == "knock-off" and tmon.item not in ("none", "mega-stone"):
                tmon.lose_item()
                self.emit("label", tgt.uid, "KNOCKED OFF", "dark")
            if tgt.alive and tmon.item == "sitrus-berry" and tmon.hp_frac() < 0.5:
                tmon.lose_item()
                tmon.heal(tmon.maxhp / 4)
                self.emit("heal", tgt.uid, 1)
            if not tgt.alive:
                return
        # secondary effects
        st = AILMENT_TO_STATUS.get(move["ailment"])
        if move["key"] == "toxic":
            st = "tox"
        sec = AB.secondary_mult(mon, move) if move["power"] > 0 else 1.0
        chance = (move["ail_chance"] * sec) or (100 if move["cls"] == "status" else 0)
        if st and self.rng.random() * 100 < chance and tmon.can_status(st, self.weather, mon):
            res = tmon.set_status(st, self.rng)
            tgt.status_t = 0
            if st in ("slp", "frz"):
                tmon.status_turns = self.rng.randint(2, 4)
            self.emit("status", tgt.uid, res)
        if move["stats"]:
            to_self = move["cat"] in ("damage-raise", "net-good-stats") or move["target"] == "user"
            chance = (move["stat_chance"] or 100) * (1 if to_self else sec)
            if self.rng.random() * 100 < chance:
                who = u if to_self else tgt
                if who.alive and who.mon.apply_stages(move["stats"], from_foe=not to_self):
                    self.emit("boost", who.uid, 1 if sum(move["stats"].values()) > 0 else 0)
        if move["flinch"] and self.rng.random() * 100 < move["flinch"] * sec and AB.ab(tmon, mon) != "inner-focus":
            tgt.stun = max(tgt.stun, 0.35)

    def _hurt(self, u, dmg, src, eff=1.0, crit=False, chip=False, guard=True):
        if not u.alive:
            return 0
        if chip and guard and AB.magic_guard(u.mon):
            return 0
        dealt = u.mon.take(dmg, from_full_ok=not chip, attacker=src.mon if src else None)
        if not chip:
            self.emit("hit", u.uid, round(dealt / u.mon.maxhp * 100, 1), eff, int(crit))
        if not u.alive:
            self._faint(u, src)
        return dealt

    def _faint(self, u, src):
        if src is not None:
            src.kills += 1
            kb = AB.on_ko(src.mon) if src.alive else None
            if kb and src.mon.apply_stages(kb):
                self._ability_label(src)
                self.emit("boost", src.uid, 1)
        self.emit("faint", u.uid, round(u.x), round(u.y), u.mon.entry["id"], src.uid if src else 0)

    # ------------------------------------------------------------------ output
    def snapshot(self):
        """Compact, JSON-friendly state for renderers / network clients. Drains the event queue."""
        units = []
        for u in self.units:
            if not u.alive:
                continue
            m = u.mon
            flags = (1 if u.boss else 0) | (2 if m.megaed else 0) | (4 if m.can_mega and self.mega_allowed(u) else 0) \
                | (8 if u.charging > 0 else 0) | (16 if u.shield > 0 else 0) | (32 if m.terastallized else 0) \
                | (64 if self.tera_allowed(u) else 0) | (128 if m.gmaxed else 0)
            units.append([u.uid, u.team, m.entry["id"], round(u.x, 1), round(u.y, 1), round(m.hp_frac(), 4),
                          round(u.r, 1), flags, m.status or "", u.face, round(u.anim, 2),
                          u.target.uid if u.target and u.target.alive else 0])
        ev, self.events = self.events, []
        return {"t": round(self.t, 2), "u": units,
                "p": [[round(p.x), round(p.y), p.move["type"]] for p in self.projectiles],
                "e": ev, "w": self.weather, "over": self.over, "win": self.winner,
                "z": [round(v, 1) for v in self.zone] if self.zone and not self.over else None}

    def roster(self):
        """Static info sent once (move names per unit etc.)."""
        return {u.uid: {"team": u.team, "name": u.mon.name, "moves": [m["name"] for m in u.mon.moves],
                        "types": [m["type"] for m in u.mon.moves], "item": u.mon.member.item_name(self.dex),
                        "boss": u.boss, "species": u.mon.base_entry["id"], "ability": AB.ability_name(u.mon.ability),
                        "tera": u.mon.tera_type} for u in self.units}
