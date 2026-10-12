"""Which version is installed, and whether a newer one is on GitHub."""
import os
import subprocess
import threading

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _git(*args, timeout=8):
    return subprocess.run(["git", "-C", APP_DIR, *args], capture_output=True, text=True,
                          timeout=timeout).stdout.strip()


def current():
    """('0395c8e', 'Oct 12') or ('dev', '') when not a git install."""
    try:
        h = _git("rev-parse", "--short", "HEAD")
        d = _git("log", "-1", "--format=%cd", "--date=format:%b %d")
        return (h or "dev", d)
    except (OSError, subprocess.SubprocessError):
        return ("dev", "")


class UpdateCheck:
    """Asks GitHub (in the background) whether the default branch has moved past our commit."""

    def __init__(self):
        self.available = False
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            local = _git("rev-parse", "HEAD")
            remote = _git("ls-remote", "origin", "HEAD", timeout=15).split()
            self.available = bool(local and remote and remote[0] != local)
        except (OSError, subprocess.SubprocessError):
            pass
