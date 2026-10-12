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
    sub.add_parser("update", help="update the game")
    args = p.parse_args(argv)

    if args.cmd == "relay":
        from .net import run_relay
        try:
            run_relay(args.port)
        except KeyboardInterrupt:
            pass
        return
    if args.cmd == "download":
        from .pokedex import download_all
        download_all()
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
