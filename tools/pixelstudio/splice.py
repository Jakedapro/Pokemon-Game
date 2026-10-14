"""splice.py OUTDIR PEX_GRAPHICS_DIR [names...]  - build Mega recipes from a local pokeemerald-expansion checkout and
write previews: NAME.png / NAME_back.png at 1x, NAME_preview.png at 4x next to the base, and NAME_grid.png."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

from pokebrawl import megas  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid  # noqa: E402


def main(out, root, names):
    os.makedirs(out, exist_ok=True)
    L = megas.local_loader(root)
    for name in names or list(megas.RECIPES):
        if name.endswith("_splice"):   # a dev design in designs/
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "designs"))
            import importlib
            front, back = importlib.import_module(name).build(L)
            name_base = name[:-7]
        else:
            front, back = megas.RECIPES[name](L)
            name_base = name
        fs, bs = front.to_surface(), back.to_surface()
        pygame.image.save(fs, os.path.join(out, f"{name}.png"))
        pygame.image.save(bs, os.path.join(out, f"{name}_back.png"))
        base = L(name_base).to_surface()
        k = 4
        s = pygame.Surface((64 * k * 3 + 40, 64 * k + 20))
        s.fill((236, 240, 222))
        for i, img in enumerate((base, fs, bs)):
            s.blit(pygame.transform.scale_by(img, k), (10 + i * (64 * k + 10), 10))
        pygame.image.save(s, os.path.join(out, f"{name}_preview.png"))
        grid.main(os.path.join(out, f"{name}_grid.png"), [os.path.join(out, f"{name}.png")])
        print(name, "colours:", len(front.colors()))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
