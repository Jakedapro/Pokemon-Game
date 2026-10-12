"""Clipboard helpers (macOS pbcopy/pbpaste, with fallbacks)."""
import shutil
import subprocess


def copy(text):
    for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text.encode(), check=True, timeout=3)
                return True
            except (OSError, subprocess.SubprocessError):
                pass
    return False


def paste():
    for cmd in (["pbpaste"], ["wl-paste"], ["xclip", "-selection", "clipboard", "-o"]):
        if shutil.which(cmd[0]):
            try:
                return subprocess.run(cmd, capture_output=True, check=True, timeout=3).stdout.decode("utf-8", "ignore")
            except (OSError, subprocess.SubprocessError):
                pass
    return ""
