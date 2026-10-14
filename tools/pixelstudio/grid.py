"""grid.py OUT.png SPRITE_DIR_OR_PNG [more...]   - sprites at 8x with a pixel grid and coordinates every 8 px,
for picking cut lines. A directory means a pokeemerald-style sprite folder (front frame 0)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

from pokebrawl import spritekit as K  # noqa: E402


def load(p):
    if os.path.isdir(p):
        f = os.path.join(p, "anim_front.png")
        if not os.path.exists(f):
            f = os.path.join(p, "front.png")
        return K.load_gba(f, os.path.join(p, "normal.pal")).to_surface()
    if p.endswith(":back"):
        d = p[:-5]
        return K.load_gba(os.path.join(d, "back.png"), os.path.join(d, "normal.pal")).to_surface()
    return pygame.image.load(p)


def main(out, paths, k=8):
    pygame.font.init()
    font = pygame.font.Font(None, 16)
    imgs = [load(p) for p in paths]
    W = sum(i.get_width() * k + 30 for i in imgs) + 10
    H = max(i.get_height() for i in imgs) * k + 30
    s = pygame.Surface((W, H))
    s.fill((200, 210, 200))
    x0 = 25
    for img in imgs:
        w, h = img.get_size()
        s.blit(pygame.transform.scale_by(img, k), (x0, 20))
        for x in range(w + 1):
            col = (90, 90, 120) if x % 8 == 0 else (175, 185, 175)
            pygame.draw.line(s, col, (x0 + x * k, 20), (x0 + x * k, 20 + h * k))
            if x % 8 == 0:
                s.blit(font.render(str(x), True, (0, 0, 0)), (x0 + x * k - 4, 4))
        for y in range(h + 1):
            col = (90, 90, 120) if y % 8 == 0 else (175, 185, 175)
            pygame.draw.line(s, col, (x0, 20 + y * k), (x0 + w * k, 20 + y * k))
            if y % 8 == 0:
                s.blit(font.render(str(y), True, (0, 0, 0)), (x0 - 22, 20 + y * k - 6))
        # redraw the sprite pixels on top so the grid is under them only on empty cells
        x0 += w * k + 30
    pygame.image.save(s, out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
