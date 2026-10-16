"""Build the PokeBrawl app: the game compiled to a native program with Nuitka (no Python for players to install,
and no readable source code in what they download).

    python tools/build_app.py --tag v1.0.0

Makes, in dist/:
    Mac      PokeBrawl-mac-arm64.zip or PokeBrawl-mac-intel.zip   (PokeBrawl.app inside)
    Windows  PokeBrawl-windows/  (the game folder; the CI wraps it in PokeBrawl-windows-setup.exe)
    Linux    PokeBrawl-linux/    (for testing the build)
Needs: pip install nuitka ordered-set zstandard -r requirements.txt   (+ a C compiler)
"""
import argparse
import io
import os
import platform
import shutil
import struct
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
BUILD = os.path.join(ROOT, "build")
sys.path.insert(0, ROOT)


def write_build_info(tag):
    with open(os.path.join(ROOT, "pokebrawl", "_build.py"), "w", encoding="utf-8") as f:
        f.write(f"TAG = {tag!r}\nDATE = {time.strftime('%b %d')!r}\n")


def icons():
    """PokeBrawl's ball icon as .ico (Windows) and .icns (Mac)."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    from pokebrawl import winicon
    os.makedirs(BUILD, exist_ok=True)
    ico = os.path.join(BUILD, "PokeBrawl.ico")
    winicon.save_ico(ico)
    big = winicon.draw(1024)
    chunks = b""
    for kind, n in ((b"ic10", 1024), (b"ic09", 512), (b"ic08", 256), (b"ic07", 128)):
        buf = io.BytesIO()
        pygame.image.save(pygame.transform.smoothscale(big, (n, n)), buf, "png")
        data = buf.getvalue()
        chunks += kind + struct.pack(">I", 8 + len(data)) + data
    icns = os.path.join(BUILD, "PokeBrawl.icns")
    with open(icns, "wb") as f:
        f.write(b"icns" + struct.pack(">I", 8 + len(chunks)) + chunks)
    return ico, icns


def nuitka(tag, ico, icns):
    num = ".".join((tag.lstrip("v").split(".") + ["0", "0", "0"])[:3])
    cmd = [sys.executable, "-m", "nuitka", "--standalone", "--assume-yes-for-downloads",
           f"--output-dir={BUILD}", "--output-filename=PokeBrawl",
           "--include-package=pokebrawl",
           f"--include-data-dir={os.path.join(ROOT, 'pokebrawl', 'art')}=pokebrawl/art",
           f"--include-data-dir={os.path.join(ROOT, 'showcases')}=showcases",
           "--nofollow-import-to=numpy,tkinter,unittest,pydoc,test",
           "--company-name=PokeBrawl", "--product-name=PokeBrawl", f"--product-version={num}",
           f"--file-version={num}", "--file-description=PokeBrawl", "--remove-output"]
    if sys.platform == "darwin":
        cmd += ["--macos-create-app-bundle", "--macos-app-name=PokeBrawl", f"--macos-app-icon={icns}",
                f"--macos-app-version={num}", "--macos-signed-app-name=local.pokebrawl"]
    elif os.name == "nt":
        cmd += [f"--windows-icon-from-ico={ico}", "--windows-console-mode=disable"]
    cmd.append(os.path.join(ROOT, "tools", "app_main.py"))
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def package():
    os.makedirs(DIST, exist_ok=True)
    if sys.platform == "darwin":
        app = os.path.join(BUILD, "app_main.app")
        final = os.path.join(BUILD, "PokeBrawl.app")
        if os.path.isdir(app):
            shutil.rmtree(final, ignore_errors=True)
            os.rename(app, final)
        arch = "arm64" if platform.machine() == "arm64" else "intel"
        out = os.path.join(DIST, f"PokeBrawl-mac-{arch}.zip")
        if os.path.exists(out):
            os.remove(out)
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", final, out], check=True)
        return out
    name = "PokeBrawl-windows" if os.name == "nt" else "PokeBrawl-linux"
    out = os.path.join(DIST, name)
    shutil.rmtree(out, ignore_errors=True)
    shutil.move(os.path.join(BUILD, "app_main.dist"), out)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tag", required=True, help="release tag, e.g. v1.0.0")
    a = p.parse_args()
    write_build_info(a.tag)
    try:
        ico, icns = icons()
        nuitka(a.tag, ico, icns)
    finally:
        os.remove(os.path.join(ROOT, "pokebrawl", "_build.py"))
    print("built", package())


if __name__ == "__main__":
    main()
