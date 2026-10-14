"""PokeBrawl pixel studio: builds GBA-style (FireRed/LeafGreen) battle sprites from small 3D models.

A sprite is modelled out of simple 3D parts - ellipsoids, tubes swept along curves (limbs, tails, horns, spikes) and
slabs (wings, fins, flames, plates) - posed in 3/4 view like the handheld sprites. The renderer then does what a
sprite artist does by hand:

  * hard pixel silhouette at 64x64 (supersampled, majority vote per pixel so curves stay clean)
  * cel shading with 3-4 tone hue-shifted ramps (shadows lean cool, highlights lean warm), light from the top-left
  * cast shadow under overlapping parts
  * selective outlines: a dark, tinted outline round the outside (lighter on the lit top-left side, nearly black on
    the bottom-right) and contour lines where one part passes in front of another
  * pixel-perfect cleanup (no doubled corners in the outline)
  * a final hand-placed pixel pass (eyes, mouths, markings) in pixel coordinates

The same model renders the back sprite (turned round, closer, cropped at the bottom like the GBA back sprites), so
front and back always match.

Coordinates: x right, y down, z toward the viewer, in front-sprite pixels (0..64). Needs numpy + pygame (dev only:
the game itself just loads the PNGs this makes).
"""
import colorsys
import math
import os

import numpy as np

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

LIGHT = np.array([-0.55, -0.8, 0.75])
LIGHT = LIGHT / np.linalg.norm(LIGHT)
SS = 4   # supersampling per pixel


# ---------------------------------------------------------------------------------------------------- colour ramps
def _hsv(rgb):
    return colorsys.rgb_to_hsv(*(c / 255 for c in rgb))


def _rgb(h, s, v):
    return tuple(int(round(max(0, min(1, c)) * 255)) for c in colorsys.hsv_to_rgb(h % 1.0, s, v))


def _toward(h, target, amount):
    """Turn hue h (0..1) toward target hue by amount (0..1 of a full turn), the short way round."""
    d = ((target - h + 0.5) % 1.0) - 0.5
    step = math.copysign(min(abs(d), amount), d)
    return h + step


def ramp(base, n=4, shift=1.0, spread=1.0):
    """Hue-shifted ramp, darkest first. Index 1 is the base colour for n=4 (shadow, base, light, highlight);
    n=3 gives shadow, base, light. Shadows turn toward blue-violet and get richer, lights toward yellow and paler."""
    h, s, v = _hsv(base)
    out = []
    steps = {3: (-1, 0, 1), 4: (-1, 0, 1, 2), 5: (-2, -1, 0, 1, 2)}[n]
    for k in steps:
        if k < 0:
            hh = _toward(h, 0.70, 0.035 * -k * shift)
            ss = min(1.0, s * (1 + 0.16 * -k * spread) + 0.04 * -k)
            vv = v * (1 - 0.24 * -k * spread)
        elif k > 0:
            hh = _toward(h, 0.15, 0.025 * k * shift)
            ss = s * (1 - 0.22 * k * spread)
            vv = min(1.0, v * (1 + 0.16 * k * spread) + 0.03 * k)
        else:
            hh, ss, vv = h, s, v
        out.append(_rgb(hh, ss, vv))
    return out


def line_color(base, k=0.42):
    """Dark tinted outline colour for a material (selout)."""
    h, s, v = _hsv(base)
    return _rgb(_toward(h, 0.70, 0.04), min(1.0, s * 1.1 + 0.15), v * k)


class Mat:
    def __init__(self, base, tones=4, gloss=False, line=None, dark_line=None, flat=False, shift=1.0, spread=1.0,
                 colors=None, bands=None, glow=False):
        self.colors = list(colors) if colors else ramp(base, tones, shift, spread)
        self.base_index = 1 if len(self.colors) >= 3 else 0
        self.gloss = gloss          # allow the brightest tone (highlight) at all
        self.line = line or line_color(base)
        self.dark_line = dark_line or line_color(base, 0.22)
        self.flat = flat            # one tone only (eyes, glowing bits)
        self.glow = glow            # glowing: brighter tones, no cast shadow
        self.bands = bands          # custom shading thresholds (len = tones - 1)


# ---------------------------------------------------------------------------------------------------- geometry
def _catmull(points, step=0.35):
    """Smooth curve through points (each (x, y, z, r)), sampled about every `step` pixels."""
    pts = [np.array(p, float) for p in points]
    if len(pts) == 1:
        return pts
    ext = [pts[0] * 2 - pts[1]] + pts + [pts[-1] * 2 - pts[-2]]
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        n = max(2, int(np.linalg.norm(p2[:3] - p1[:3]) / step) + 1)
        for j in range(n):
            t = j / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(pts[-1])
    return out


def _rot(rx=0.0, ry=0.0, rz=0.0):
    """Rotation matrix from angles in degrees (x: tilt toward viewer, y: turn, z: roll in the picture)."""
    rx, ry, rz = (math.radians(a) for a in (rx, ry, rz))
    X = np.array([[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]])
    Y = np.array([[math.cos(ry), 0, math.sin(ry)], [0, 1, 0], [-math.sin(ry), 0, math.cos(ry)]])
    Z = np.array([[math.cos(rz), -math.sin(rz), 0], [math.sin(rz), math.cos(rz), 0], [0, 0, 1]])
    return Z @ Y @ X


class Part:
    """A rendered layer: depth, normal, material and group per supersampled pixel."""

    def __init__(self, mat, group, outline=True):
        self.mat, self.group, self.outline = mat, group, outline


class Ellipsoid(Part):
    def __init__(self, c, radii, rot, mat, group, outline=True):
        super().__init__(mat, group, outline)
        self.c = np.array(c, float)
        self.r = np.array(radii, float)
        self.R = _rot(*rot)

    def transformed(self, f):
        e = Ellipsoid((0, 0, 0), self.r, (0, 0, 0), self.mat, self.group, self.outline)
        e.c, e.R, e.r = f.point(self.c), f.M @ self.R, self.r * f.scale
        return e

    def render(self, X, Y):
        M = self.R @ np.diag(1 / self.r ** 2) @ self.R.T
        ux, uy = X - self.c[0], Y - self.c[1]
        A = M[2, 2]
        B = M[2, 0] * ux + M[2, 1] * uy
        C = M[0, 0] * ux * ux + 2 * M[0, 1] * ux * uy + M[1, 1] * uy * uy - 1
        disc = B * B - A * C
        hit = disc >= 0
        t = np.where(hit, (-B + np.sqrt(np.maximum(disc, 0))) / A, -1e9)
        z = self.c[2] + t
        q = np.stack([ux, uy, t], -1)
        n = q @ M.T
        n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9
        return hit, np.where(hit, z, -1e9), n


class Tube(Part):
    """Spheres swept along a smooth curve through (x, y, z, radius) points - limbs, tails, horns, spikes."""

    def __init__(self, points, mat, group, outline=True, flat_z=1.0):
        super().__init__(mat, group, outline)
        self.points = [tuple(p) for p in points]
        self.flat_z = flat_z    # <1 squashes the tube's depth (flatter shading)

    def transformed(self, f):
        pts = []
        for x, y, z, r in self.points:
            p = f.point(np.array([x, y, z], float))
            pts.append((p[0], p[1], p[2], r * f.scale))
        return Tube(pts, self.mat, self.group, self.outline, self.flat_z)

    def render(self, X, Y):
        hit = np.zeros(X.shape, bool)
        z = np.full(X.shape, -1e9)
        n = np.zeros(X.shape + (3,))
        for cx, cy, cz, r in _catmull(self.points):
            r = max(r, 0.25)
            x0, x1 = cx - r, cx + r
            y0, y1 = cy - r, cy + r
            sel = (X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)
            if not sel.any():
                continue
            dx, dy = X[sel] - cx, Y[sel] - cy
            d2 = r * r - dx * dx - dy * dy
            ok = d2 >= 0
            h = np.sqrt(np.maximum(d2, 0)) * self.flat_z
            zz = np.where(ok, cz + h, -1e9)
            cur = z[sel]
            better = ok & (zz > cur)
            idx = np.where(sel)
            bi = (idx[0][better], idx[1][better])
            z[bi] = zz[better]
            hit[bi] = True
            nn = np.stack([dx[better], dy[better], h[better] / max(self.flat_z, 1e-3)], -1)
            nn /= np.linalg.norm(nn, axis=-1, keepdims=True) + 1e-9
            n[bi] = nn
        return hit, z, n


class Slab(Part):
    """A flat shape (wing, fin, flame, plate) - a polygon with a z per corner, gently rounded at the edges."""

    def __init__(self, points, mat, group, outline=True, bulge=0.5, smooth=False, both_sides=True):
        super().__init__(mat, group, outline)
        self.points = [tuple(p) for p in points]
        self.bulge = bulge
        self.smooth = smooth

    def transformed(self, f):
        pts = []
        for p in self.points:
            q = f.point(np.array(p[:3], float))
            pts.append(tuple(q))
        return Slab(pts, self.mat, self.group, self.outline, self.bulge, self.smooth)

    def _poly(self):
        pts = self.points
        if self.smooth:
            ring = pts + pts[:3]
            out = []
            for i in range(1, len(pts) + 1):
                p0, p1, p2, p3 = (np.array(ring[i - 1 + k], float) for k in range(4))
                for j in range(6):
                    t = j / 6
                    out.append(tuple(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                                            (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)))
            pts = out
        return np.array(pts, float)

    def render(self, X, Y):
        P = self._poly()
        xs, ys, zs = P[:, 0], P[:, 1], P[:, 2]
        # inside test (even-odd)
        inside = np.zeros(X.shape, bool)
        n = len(P)
        for i in range(n):
            x1, y1 = xs[i], ys[i]
            x2, y2 = xs[(i + 1) % n], ys[(i + 1) % n]
            cond = ((y1 > Y) != (y2 > Y))
            xint = (x2 - x1) * (Y - y1) / ((y2 - y1) + 1e-12) + x1
            inside ^= cond & (X < xint)
        # plane through the corners (least squares)
        A = np.stack([xs, ys, np.ones(n)], 1)
        (a, b, c), *_ = np.linalg.lstsq(A, zs, rcond=None)
        z = a * X + b * Y + c
        base_n = np.array([-a, -b, 1.0])
        base_n /= np.linalg.norm(base_n)
        # rounded edges: tilt the normal outward near the edge
        best = np.full(X.shape, 1e9)
        dirx = np.zeros(X.shape)
        diry = np.zeros(X.shape)
        for i in range(n):
            x1, y1 = xs[i], ys[i]
            x2, y2 = xs[(i + 1) % n], ys[(i + 1) % n]
            ex, ey = x2 - x1, y2 - y1
            L = ex * ex + ey * ey + 1e-12
            t = np.clip(((X - x1) * ex + (Y - y1) * ey) / L, 0, 1)
            px, py = x1 + t * ex, y1 + t * ey
            d = np.hypot(X - px, Y - py)
            closer = d < best
            best = np.where(closer, d, best)
            dirx = np.where(closer, X - px, dirx)
            diry = np.where(closer, Y - py, diry)
        k = self.bulge * np.exp(-best / 2.5)
        dl = np.hypot(dirx, diry) + 1e-9
        nx = base_n[0] - k * dirx / dl
        ny = base_n[1] - k * diry / dl
        nz = np.full(X.shape, base_n[2])
        nn = np.stack([nx, ny, nz], -1)
        nn /= np.linalg.norm(nn, axis=-1, keepdims=True)
        return inside, np.where(inside, z + (1 - np.exp(-best / 3)) * self.bulge * 2, -1e9), nn


class Frame:
    """A transform applied to a whole model: mirror/turn for the back view, scale and move."""

    def __init__(self, M=None, scale=1.0, pivot=(32, 32, 0), offset=(0, 0, 0)):
        self.M = np.eye(3) if M is None else M
        self.scale = scale
        self.pivot = np.array(pivot, float)
        self.offset = np.array(offset, float)

    def point(self, p):
        return self.M @ (np.asarray(p, float) - self.pivot) * self.scale + self.pivot + self.offset


# ---------------------------------------------------------------------------------------------------- the model
class Model:
    def __init__(self, size=64):
        self.size = size
        self.parts = []
        self.paints = []   # (polygon, material, groups) - markings that follow the shading
        self.mats = {}
        self.front_pixels = []   # final hand pass: (x, y, colour or (mat, tone))
        self.back_pixels = []

    def mat(self, name, *a, **k):
        self.mats[name] = Mat(*a, **k)
        return name

    def ell(self, c, radii, mat, group=None, rot=(0, 0, 0), outline=True):
        self.parts.append(Ellipsoid(c, radii, rot, mat, group or mat, outline))

    def ball(self, c, r, mat, group=None, outline=True):
        self.ell(c, (r, r, r), mat, group, outline=outline)

    def tube(self, points, mat, group=None, outline=True, flat_z=1.0):
        self.parts.append(Tube(points, mat, group or mat, outline, flat_z))

    def slab(self, points, mat, group=None, bulge=0.5, smooth=False, outline=True):
        self.parts.append(Slab(points, mat, group or mat, outline, bulge, smooth))

    def paint(self, poly, mat, groups=None, smooth=False):
        """Recolour everything inside a picture-space polygon (keeping its shading) - stripes, spots, belly."""
        self.paints.append((poly, mat, groups, smooth))

    # ---------------------------------------------------------------- rendering
    def render(self, back=False, back_scale=1.18, back_drop=10):
        size = self.size
        S = size * SS
        g = (np.arange(S) + 0.5) / SS
        X, Y = np.meshgrid(g, g)
        if back:
            F = np.diag([-1.0, 1.0, -1.0])
            frame = Frame(F, back_scale, pivot=(size / 2, size, 0), offset=(0, back_drop, 0))
            parts = [p.transformed(frame) for p in self.parts]
        else:
            parts = self.parts
        zbuf = np.full((S, S), -1e9)
        nbuf = np.zeros((S, S, 3))
        pid = np.full((S, S), -1)
        for i, p in enumerate(parts):
            hit, z, n = p.render(X, Y)
            better = hit & (z > zbuf)
            zbuf[better] = z[better]
            nbuf[better] = n[better]
            pid[better] = i
        # down to real pixels: majority vote per pixel for which part shows, averaged normal/depth for it
        names = list(self.mats)
        mat_of = np.array([names.index(p.mat) for p in parts] + [-1])
        out_part = np.full((size, size), -1)
        out_z = np.full((size, size), -1e9)
        out_n = np.zeros((size, size, 3))
        blk = pid.reshape(size, SS, size, SS).transpose(0, 2, 1, 3).reshape(size, size, SS * SS)
        zb = zbuf.reshape(size, SS, size, SS).transpose(0, 2, 1, 3).reshape(size, size, SS * SS)
        nb = nbuf.reshape(size, SS, size, SS, 3).transpose(0, 2, 1, 3, 4).reshape(size, size, SS * SS, 3)
        for y in range(size):
            for x in range(size):
                ids = blk[y, x]
                vals, counts = np.unique(ids, return_counts=True)
                order = np.argsort(-counts)
                cov = counts[vals != -1].sum() if (vals != -1).any() else 0
                if cov * 2 < SS * SS:      # under half covered: empty
                    continue
                best = next(v for v in vals[order] if v != -1)
                sel = ids == best
                out_part[y, x] = best
                out_z[y, x] = zb[y, x][sel].mean()
                nn = nb[y, x][sel].mean(0)
                out_n[y, x] = nn / (np.linalg.norm(nn) + 1e-9)
        # markings painted on (keep each pixel's own shading, swap its material)
        mat_px = np.where(out_part >= 0, mat_of[out_part], -1)
        group_px = np.array([[parts[p].group if p >= 0 else None for p in row] for row in out_part], dtype=object)
        for poly, mat, groups, smooth in self.paints:
            if back:   # markings are drawn in the front picture; the back gets its own pixel pass
                continue
            P = Slab([(*q, 0) for q in poly], None, None, smooth=smooth)._poly()
            gx = np.arange(size) + 0.5
            GX, GY = np.meshgrid(gx, gx)
            inside = np.zeros((size, size), bool)
            n = len(P)
            for i in range(n):
                x1, y1 = P[i, 0], P[i, 1]
                x2, y2 = P[(i + 1) % n, 0], P[(i + 1) % n, 1]
                cond = ((y1 > GY) != (y2 > GY))
                xint = (x2 - x1) * (GY - y1) / ((y2 - y1) + 1e-12) + x1
                inside ^= cond & (GX < xint)
            ok = inside & (out_part >= 0)
            if groups:
                ok &= np.isin(group_px, groups)
            mat_px[ok] = names.index(mat)
        return self._shade(out_part, out_z, out_n, mat_px, parts, names, back)

    def _shade(self, part, z, n, mat_px, parts, names, back):
        size = self.size
        img = np.zeros((size, size, 4), np.uint8)
        filled = part >= 0
        tone = np.zeros((size, size), int)
        diff = np.einsum("ijk,k->ij", n, LIGHT)
        for y in range(size):
            for x in range(size):
                if not filled[y, x]:
                    continue
                m = self.mats[names[mat_px[y, x]]]
                cols = len(m.colors)
                if m.flat:
                    tone[y, x] = m.base_index
                    continue
                v = 0.5 + 0.5 * diff[y, x]
                bands = m.bands or ([0.36, 0.62, 0.9] if cols >= 4 else [0.4, 0.75])
                t = sum(v > b for b in bands[:cols - 1])
                if not m.gloss and cols >= 4:
                    t = min(t, cols - 2)
                if m.glow:
                    t = min(cols - 1, t + 1)
                tone[y, x] = t
        # cast shadow: something in front of this pixel just up-left of it
        cast = np.zeros((size, size), bool)
        for y in range(size):
            for x in range(size):
                if not filled[y, x] or self.mats[names[mat_px[y, x]]].glow:
                    continue
                for dx, dy in ((-1, -1), (0, -1), (-1, 0), (-2, -2), (0, -2), (-2, 0)):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < size and 0 <= yy < size and filled[yy, xx] and \
                            parts[part[yy, xx]].group != parts[part[y, x]].group and z[yy, xx] > z[y, x] + 2.5:
                        cast[y, x] = True
                        break
        tone = np.where(cast, np.maximum(tone - 1, 0), tone)
        # outlines
        line = np.zeros((size, size), int)   # 0 none, 1 selout (light side), 2 dark
        for y in range(size):
            for x in range(size):
                if not filled[y, x]:
                    continue
                me = parts[part[y, x]]
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    xx, yy = x + dx, y + dy
                    out = not (0 <= xx < size and 0 <= yy < size) or not filled[yy, xx]
                    if out:
                        if me.outline:
                            lit = (dx < 0 or dy < 0)
                            line[y, x] = max(line[y, x], 1 if lit else 2)
                        continue
                    other = parts[part[yy, xx]]
                    if other.group != me.group and z[yy, xx] > z[y, x] + 1.2 and me.outline and other.outline:
                        line[y, x] = max(line[y, x], 1 if (dx < 0 or dy < 0) else 2)
        line = self._pixel_perfect(line, filled)
        for y in range(size):
            for x in range(size):
                if not filled[y, x]:
                    continue
                m = self.mats[names[mat_px[y, x]]]
                if line[y, x] == 2:
                    c = m.dark_line
                elif line[y, x] == 1:
                    c = m.line
                else:
                    c = m.colors[tone[y, x]]
                img[y, x] = (*c, 255)
        surf = pygame.image.frombuffer(img.tobytes(), (size, size), "RGBA").copy()
        for x, y, c in (self.back_pixels if back else self.front_pixels):
            if c is None:
                surf.set_at((x, y), (0, 0, 0, 0))
                continue
            if isinstance(c, tuple) and len(c) == 2 and isinstance(c[0], str):
                mm = self.mats[c[0]]
                c = {"line": mm.line, "dark": mm.dark_line}.get(c[1], None) if isinstance(c[1], str) else mm.colors[c[1]]
            surf.set_at((x, y), c)
        return surf

    @staticmethod
    def _pixel_perfect(line, filled):
        """Thin the outside outline where it doubles up into an 'L' on a diagonal: an outline pixel whose two
        outside-facing neighbours are both empty and whose two inward neighbours are both outline pixels sits in
        the elbow of a staircase - make it a fill pixel."""
        size = line.shape[0]
        out = line.copy()
        for y in range(1, size - 1):
            for x in range(1, size - 1):
                if not out[y, x]:
                    continue
                for ox, oy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                    # outside corner direction (ox, oy): both neighbours that way are empty...
                    if filled[y, x + ox] or filled[y + oy, x]:
                        continue
                    # ...so this pixel already touches the outside twice - fine, it's a real corner
                    break
                else:
                    # inner elbow: the outline continues both left/right and up/down through diagonal neighbours
                    for ax, ay in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                        if out[y, x + ax] and out[y + ay, x] and not filled[y + ay, x + ax] and \
                                filled[y - ay, x] and filled[y, x - ax]:
                            out[y, x] = 0
                            break
        return out


# ---------------------------------------------------------------------------------------------------- previews
def colours_used(surf):
    w, h = surf.get_size()
    return len({tuple(surf.get_at((x, y))) for y in range(h) for x in range(w) if surf.get_at((x, y)).a})


def preview(path, images, scale=4, bg=(232, 240, 224)):
    """Side-by-side preview at `scale`x on a light battle-ish background."""
    w = sum(i.get_width() for i in images) * scale + 8 * (len(images) + 1)
    h = max(i.get_height() for i in images) * scale + 16
    s = pygame.Surface((w, h))
    s.fill(bg)
    x = 8
    for i in images:
        s.blit(pygame.transform.scale_by(i, scale), (x, 8))
        x += i.get_width() * scale + 8
    pygame.image.save(s, path)
