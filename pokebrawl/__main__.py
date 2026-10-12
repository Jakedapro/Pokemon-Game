"""pokebrawl command line.

    pokebrawl                         open the game
    pokebrawl showcase FILE.json      play a showcase file   (--record out.mp4 to render a video, --seed N)
    pokebrawl relay [--port 7778]     run a relay server so friends can play without port forwarding
    pokebrawl download                download every sprite now (the installer does this)
    pokebrawl update                  update to the latest version
"""
import argparse
import os
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    p = argparse.ArgumentParser(prog="pokebrawl", description="Pokemon arena battles: practice, showcase, PvP")
    sub = p.add_subparsers(dest="cmd")
    sc = sub.add_parser("showcase", help="play or record a showcase JSON file")
    sc.add_argument("file")
    sc.add_argument("--record", metavar="OUT.mp4")
    sc.add_argument("--seed", type=int)
    rl = sub.add_parser("relay", help="run a relay server")
    rl.add_argument("--port", type=int, default=7778)
    sub.add_parser("download", help="download all Pokemon data and sprites")
    sub.add_parser("spritetest", help="save a picture of sprite effects to your Desktop (for bug reports)")
    sub.add_parser("update", help="update the game")
    sub.add_parser("version", help="show the installed version")
    sub.add_parser("nettest", help="check that online rooms can work from this network")
    args = p.parse_args(argv)
    if args.cmd in (None, "showcase", "version"):
        from .updater import apply_staged
        apply_staged()  # swaps in a downloaded update and restarts (does nothing otherwise)

    if args.cmd == "relay":
        from .net import run_relay
        try:
            run_relay(args.port)
        except KeyboardInterrupt:
            pass
        return
    if args.cmd == "download":
        from .pokedex import download_all
        try:
            download_all()
        except Exception as e:  # noqa: BLE001
            print(f"\n[pokebrawl] download failed: {e}")
            print("[pokebrawl] check your internet connection; on school/work Wi-Fi try another network")
            sys.exit(1)
        return
    if args.cmd == "spritetest":
        _spritetest()
        return
    if args.cmd == "nettest":
        from .net import PROTO
        from .online import selftest
        from .version import current
        print(f"version {current()[0]}  protocol {PROTO}")
        selftest()
        return
    if args.cmd == "version":
        from .version import current
        h, d = current()
        print(f"PokeBrawl {h} ({d})")
        return
    if args.cmd == "update":
        if os.path.isdir(os.path.join(APP_DIR, ".git")):
            subprocess.call(["git", "-C", APP_DIR, "pull", "--ff-only"])
        else:
            print("Not a git install - rerun the install command to update.")
        return
    if args.cmd == "showcase":
        from .pokedex import load_dex
        from .showcase import load_config, record
        cfg = load_config(args.file)
        if args.seed is not None:
            cfg["seed"] = args.seed
        dex = load_dex()
        if args.record:
            record(dex, cfg, args.record)
            return
        from . import gfx
        from .app import App
        from .showcase_ui import ShowcaseLoad
        app = App()
        app.dex = dex

        class _Root:  # closing the showcase quits
            def handle(self, ev, pos):
                pass

            def update(self, dt):
                app.running = False

            def draw(self, surf):
                pass
        app.stack = [_Root(), ShowcaseLoad(app, cfg, record=False)]
        _loop(app, gfx)
        return
    from .app import App
    App().run()


def _spritetest():
    """Saves a picture testing every way sprites get drawn, plus version info, for bug reports."""
    import platform

    import pygame

    from . import gfx
    from .pokedex import load_dex
    from .render import ArenaRenderer
    disp = gfx.Display(headless=True)
    out = gfx.new_surface((720, 520))
    out.fill((166, 124, 92))

    def label(t, x, y):
        gfx.text(out, t, (x, y), 14, chunky=False, ow=1)
    row = [("plain", {}), ("hit flash", {"white": 0.7}), ("outline", {"outline": (230, 50, 50)}),
           ("outline+flash", {"outline": (230, 50, 50), "white": 0.7}), ("faint", {"white": 0.6, "flip": True})]
    for i, (name, kw) in enumerate(row):
        out.blit(gfx.SPRITES.get(150, 90, **kw), (15 + i * 140, 30))
        label(name, 60 + i * 140, 18)
    raw = pygame.image.load(gfx.pokedex.ensure_sprite(384))
    tests = [("raw file", raw), ("smoothscale", pygame.transform.smoothscale(raw.convert_alpha(), (120, 120))),
             ("scale", pygame.transform.scale(raw, (120, 120))), ("rescale", gfx.rescale(raw, (120, 120)))]
    for i, (name, img) in enumerate(tests):
        out.blit(img, (15 + i * 170, 160))
        label(name, 70 + i * 170, 150)
    r = ArenaRenderer(load_dex(), {}, mode="showcase")
    r.feed({"u": [[1, 0, 150, 300, 640, 1.0, 40, 1, "", 1, 0, 0], [2, 1, 384, 420, 640, 1.0, 40, 1, "", -1, 0, 0]],
            "p": [], "e": [], "w": None})
    for k, zoom in enumerate((1.0, 1.8)):
        r.cam = [360, 620, zoom]
        r.units[1].flash = 0.1 if k else 0
        r.draw(disp.canvas)
        out.blit(gfx.rescale(disp.canvas, (180, 320)).subsurface((0, 60, 180, 230)).copy(), (15 + k * 200, 290))
        label(f"arena zoom {zoom}", 105 + k * 200, 290)
    info = [f"pygame-ce {pygame.version.ver}  SDL {'.'.join(map(str, pygame.get_sdl_version()))}",
            f"python {platform.python_version()}  {platform.system()} {platform.machine()} {platform.mac_ver()[0]}",
            f"display bits {pygame.display.get_surface().get_bitsize()}"]
    for i, t in enumerate(info):
        gfx.text(out, t, (430, 330 + i * 26), 15, chunky=False, ow=1, anchor="topleft")
    desk = os.path.join(os.path.expanduser("~"), "Desktop")
    path = os.path.join(desk if os.path.isdir(desk) else os.getcwd(), "pokebrawl-spritetest.png")
    pygame.image.save(out, path)
    print(f"saved {path}")
    print("\n".join(info))


def _loop(app, gfx):
    import pygame
    while app.running and app.stack:
        dt = min(0.05, app.clock.tick(60) / 1000)
        scene = app.stack[-1]
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                app.running = False
            pos = app.display.to_canvas(ev.pos) if hasattr(ev, "pos") else app.display.to_canvas(
                pygame.mouse.get_pos())
            scene.handle(ev, pos)
        if not app.stack:
            break
        app.stack[-1].update(dt)
        if app.stack:
            app.stack[-1].draw(app.display.canvas)
            app.display.present()
    pygame.quit()


if __name__ == "__main__":
    main(sys.argv[1:])
