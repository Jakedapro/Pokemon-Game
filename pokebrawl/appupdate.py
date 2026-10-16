"""Updates for the compiled PokeBrawl app (Mac .app / Windows .exe). New versions are GitHub releases on the
public PokeBrawl repo; the right download for this computer is fetched in the background and swapped in when
the game restarts:

    Mac      PokeBrawl-mac-arm64.zip / PokeBrawl-mac-intel.zip  (the .app, replaced in place)
    Windows  PokeBrawl-windows-setup.exe                         (run silently, then the game reopens)
"""
import json
import os
import platform
import shutil
import subprocess
import sys

from . import pokedex
from .version import BUILD_TAG

RELEASES = "https://api.github.com/repos/Jakedapro/PokeBrawl/releases/latest"
DIR = os.path.join(pokedex.HOME, "update")
READY = os.path.join(DIR, "ready.json")


def asset_name():
    if sys.platform == "darwin":
        return "PokeBrawl-mac-arm64.zip" if platform.machine() == "arm64" else "PokeBrawl-mac-intel.zip"
    if os.name == "nt":
        return "PokeBrawl-windows-setup.exe"
    return None


def bundle():
    """The PokeBrawl.app this is running from (Mac), or None."""
    p = os.path.abspath(sys.executable)
    for _ in range(4):
        if p.endswith(".app"):
            return p
        p = os.path.dirname(p)
    return None


def supported():
    if not BUILD_TAG or not asset_name():
        return False
    if sys.platform == "darwin":
        b = bundle()
        return bool(b) and os.access(os.path.dirname(b), os.W_OK)
    return True


def latest():
    """(tag, download url) of the newest release."""
    rel = json.loads(pokedex.fetch(RELEASES, timeout=15))
    want = asset_name()
    url = next((a["browser_download_url"] for a in rel.get("assets", []) if a["name"] == want), None)
    return rel.get("tag_name"), url


def ready_tag():
    try:
        with open(READY, encoding="utf-8") as f:
            info = json.load(f)
        return info["tag"] if os.path.exists(info["path"]) else None
    except (OSError, ValueError, KeyError):
        return None


def stage(tag, url):
    """Download release `tag` and mark it ready to install."""
    shutil.rmtree(DIR, ignore_errors=True)
    os.makedirs(DIR)
    data = pokedex.fetch(url, timeout=600)
    dl = os.path.join(DIR, asset_name())
    with open(dl, "wb") as f:
        f.write(data)
    path = dl
    if sys.platform == "darwin":   # unpack now so restarting is instant (ditto keeps permissions + signature)
        out = os.path.join(DIR, "new")
        subprocess.run(["ditto", "-x", "-k", dl, out], check=True)
        apps = [d for d in os.listdir(out) if d.endswith(".app")]
        if len(apps) != 1:
            raise ValueError("update download looks wrong")
        path = os.path.join(out, apps[0])
        os.remove(dl)
    with open(READY, "w", encoding="utf-8") as f:
        json.dump({"tag": tag, "path": path}, f)


def apply(log=print):
    """Install the staged update and reopen the game. Returns only if there's nothing to install."""
    tag = ready_tag()
    if not tag or tag == BUILD_TAG or not supported():
        if tag == BUILD_TAG:
            shutil.rmtree(DIR, ignore_errors=True)
        return
    with open(READY, encoding="utf-8") as f:
        path = json.load(f)["path"]
    log(f"[pokebrawl] installing {tag}...")
    if os.name == "nt":
        subprocess.Popen([path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                         creationflags=0x00000008 | 0x00000200)   # detached, own process group
    else:
        app = bundle()
        script = ('while kill -0 "$1" 2>/dev/null; do sleep 0.2; done\n'
                  'rm -rf "$2.old" && mv "$2" "$2.old" && mv "$3" "$2" && rm -rf "$2.old" "$4"\n'
                  'open "$2"\n')
        subprocess.Popen(["/bin/sh", "-c", script, "sh", str(os.getpid()), app, path, DIR],
                         start_new_session=True)
    _quit()


def _quit():
    try:
        import pygame
        pygame.quit()
    except Exception:  # noqa: BLE001
        pass
    os._exit(0)
