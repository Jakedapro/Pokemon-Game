"""Draws PokeBrawl's Windows shortcut icon (a ball) and saves it as an .ico. Used by install.ps1:

    python -m pokebrawl.winicon OUT.ico
"""
import io
import os
import struct
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

INK = (24, 24, 32)


def draw(size=256):
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    r = size // 2
    w = max(2, size // 16)
    pygame.draw.circle(s, (232, 44, 44), (r, r), r - 2)
    pygame.draw.rect(s, (0, 0, 0, 0), (0, r, size, r))
    pygame.draw.circle(s, (248, 248, 248), (r, r), r - 2, draw_bottom_left=True, draw_bottom_right=True)
    pygame.draw.circle(s, (255, 120, 110), (int(r * 0.62), int(r * 0.55)), size // 12)   # shine
    pygame.draw.circle(s, INK, (r, r), r - 2, w)
    pygame.draw.rect(s, INK, (0, r - w // 2, size, w))
    pygame.draw.circle(s, (248, 248, 248), (r, r), size // 6)
    pygame.draw.circle(s, INK, (r, r), size // 6, w)
    pygame.draw.circle(s, INK, (r, r), size // 12, max(1, w // 2))
    return s


def save_ico(path, sizes=(256, 48, 32, 16)):
    """An .ico holding PNG images (Windows Vista and later read these)."""
    big = draw(256)
    pngs = []
    for n in sizes:
        buf = io.BytesIO()
        pygame.image.save(pygame.transform.smoothscale(big, (n, n)), buf, "png")
        pngs.append((n, buf.getvalue()))
    out = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    for n, data in pngs:
        out += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    with open(path, "wb") as f:
        f.write(out + b"".join(d for _, d in pngs))


if __name__ == "__main__":
    save_ico(sys.argv[1])
