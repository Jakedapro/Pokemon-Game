"""Which version is installed, and whether a newer one is on GitHub (works with or without git)."""
import os
import subprocess

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMITS_API = "https://api.github.com/repos/jamalmusialla81-hub/Pokemon-Game/commits/HEAD"


def _git(*args, timeout=8):
    return subprocess.run(["git", "-C", APP_DIR, *args], capture_output=True, text=True,
                          timeout=timeout).stdout.strip()


def _version_file():
    try:
        with open(os.path.join(APP_DIR, "VERSION")) as f:
            parts = f.read().split(None, 1)
        return parts[0], (parts[1].strip() if len(parts) > 1 else "")
    except (OSError, IndexError):
        return None


def _is_git():
    return os.path.isdir(os.path.join(APP_DIR, ".git"))


def current():
    """('0395c8e', 'Oct 12'), or ('dev', '') when unknown."""
    if _is_git():
        try:
            h = _git("rev-parse", "--short", "HEAD")
            d = _git("log", "-1", "--format=%cd", "--date=format:%b %d")
            if h:
                return h, d
        except (OSError, subprocess.SubprocessError):
            pass
    vf = _version_file()
    if vf and vf[0] != "unknown":
        return vf[0][:7], vf[1]
    return "dev", ""
