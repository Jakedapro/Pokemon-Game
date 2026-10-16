"""Auto-updater. While you're in the menu it checks GitHub, downloads the newest version in the background
(a plain tarball over HTTPS - no git or Apple Command Line Tools needed) and stages it next to the game.
The staged copy is swapped in the next time the game starts (or right away with the RESTART button).

Only touches real installs (~/.pokebrawl/app), never a developer checkout. Turn it off in Settings or with
POKEBRAWL_NO_AUTOUPDATE=1.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading

from . import pokedex
from .version import APP_DIR, COMMITS_API, _git, _is_git, _version_file

OWNER_REPO = "Jakedapro/Pokemon-Game"
TARBALL = "https://codeload.github.com/" + OWNER_REPO + "/tar.gz/{sha}"
STAGE = APP_DIR + ".new"
OLD = APP_DIR + ".old"
READY = os.path.join(STAGE, ".ready")


def installed():
    """True for an installer-made copy (safe to replace), False for a dev checkout."""
    if os.environ.get("POKEBRAWL_NO_AUTOUPDATE"):
        return False
    return os.path.realpath(APP_DIR) == os.path.realpath(os.path.join(pokedex.HOME, "app"))


def local_sha():
    if _is_git():
        try:
            return _git("rev-parse", "HEAD") or None
        except (OSError, subprocess.SubprocessError):
            return None
    vf = _version_file()
    return vf[0] if vf and vf[0] != "unknown" else None


def latest_sha():
    return json.loads(pokedex.fetch(COMMITS_API, timeout=15)).get("sha") or None


def _safe_extract(tar, dest):
    root = os.path.realpath(dest)
    for m in tar.getmembers():
        target = os.path.realpath(os.path.join(dest, m.name))
        if not (target == root or target.startswith(root + os.sep)) or m.issym() or m.islnk() or m.isdev():
            raise ValueError(f"unsafe path in update: {m.name}")
    if hasattr(tarfile, "data_filter"):
        tar.extractall(dest, filter="data")
    else:
        tar.extractall(dest)  # members were checked above


def stage(sha, date_text):
    """Download version `sha` into app.new (atomically marked ready when complete)."""
    data = pokedex.fetch(TARBALL.format(sha=sha), timeout=120)
    tmp = APP_DIR + ".download"
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(STAGE, ignore_errors=True)
    os.makedirs(tmp)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        _safe_extract(tar, tmp)
    tops = [d for d in os.listdir(tmp) if os.path.isdir(os.path.join(tmp, d))]
    if len(tops) != 1 or not os.path.isfile(os.path.join(tmp, tops[0], "pokebrawl", "__main__.py")):
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError("update download looks wrong")
    os.rename(os.path.join(tmp, tops[0]), STAGE)
    shutil.rmtree(tmp, ignore_errors=True)
    with open(os.path.join(STAGE, "VERSION"), "w") as f:
        f.write(f"{sha} {date_text}\n")
    with open(READY, "w") as f:
        f.write(sha)


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def apply_staged(log=print):
    """Called first thing at startup: swap in a downloaded update, then restart into it.
    Returns quietly when there's nothing to do; rolls back if anything goes wrong."""
    if not os.path.isfile(READY) or not installed():
        return
    shutil.rmtree(OLD, ignore_errors=True)
    try:
        os.rename(APP_DIR, OLD)
        os.rename(STAGE, APP_DIR)
    except OSError as e:
        log(f"[pokebrawl] couldn't install the update ({e}) - will try again next time")
        if not os.path.isdir(APP_DIR) and os.path.isdir(OLD):
            os.rename(OLD, APP_DIR)
        return
    # keep showcase files you made yourself
    old_sc, new_sc = os.path.join(OLD, "showcases"), os.path.join(APP_DIR, "showcases")
    if os.path.isdir(old_sc) and os.path.isdir(new_sc):
        for name in os.listdir(old_sc):
            if name.endswith(".json") and not os.path.exists(os.path.join(new_sc, name)):
                shutil.copy2(os.path.join(old_sc, name), new_sc)
    req = os.path.join(APP_DIR, "requirements.txt")
    if _read(req) != _read(os.path.join(OLD, "requirements.txt")):
        log("[pokebrawl] update needs new packages - installing...")
        res = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", "-r", req])
        if res.returncode != 0:  # roll back, keep the download for next time
            log("[pokebrawl] couldn't install packages for the update - keeping the old version for now")
            os.rename(APP_DIR, STAGE)
            os.rename(OLD, APP_DIR)
            return
    os.remove(os.path.join(APP_DIR, ".ready"))
    shutil.rmtree(OLD, ignore_errors=True)
    log(f"[pokebrawl] updated to {_read(os.path.join(APP_DIR, 'VERSION')).split()[0][:7]}")
    restart()


def restart():
    """Start the game again in this same process slot (picks up new code)."""
    try:
        import pygame
        pygame.quit()
    except Exception:  # noqa: BLE001
        pass
    sys.stdout.flush()
    if os.name == "nt":   # no real exec on Windows: run the new version, then leave with its exit code
        sys.exit(subprocess.call([sys.executable, "-X", "utf8", "-m", "pokebrawl", *sys.argv[1:]]))
    os.execv(sys.executable, [sys.executable, "-m", "pokebrawl", *sys.argv[1:]])


class AutoUpdater:
    """Background check (+ download when `auto` is on). state: checking, current, available, downloading,
    ready, error, off."""

    def __init__(self, auto=True):
        self.auto = auto
        self.state = "checking"
        self.error = None
        threading.Thread(target=self._run, daemon=True).start()

    @property
    def available(self):
        return self.state in ("available", "downloading", "ready", "error")

    def _run(self):
        try:
            if os.path.isfile(READY):
                self.state = "ready"
                return
            mine = local_sha()
            latest = latest_sha()
            if not latest or latest == mine:
                self.state = "current"
                return
            if not (self.auto and installed()):
                self.state = "available"
                return
            self.state = "downloading"
            import time
            stage(latest, time.strftime("%b %d"))
            self.state = "ready"
        except Exception as e:  # noqa: BLE001 - offline, rate limited...: just try again next launch
            self.error = str(e)
            self.state = "error" if self.state == "downloading" else "current"
