"""Clipboard helpers (macOS pbcopy/pbpaste, Windows PowerShell, with fallbacks)."""
import os
import shutil
import subprocess

WIN = os.name == "nt"
_PS = ["powershell", "-NoProfile", "-Command"]
COPY_CMDS = [_PS + ["$input | Set-Clipboard"]] if WIN else [["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"]]
PASTE_CMDS = [_PS + ["Get-Clipboard -Raw"]] if WIN else [["pbpaste"], ["wl-paste"],
                                                          ["xclip", "-selection", "clipboard", "-o"]]


def _sdl_clip(text=None):
    """SDL's own clipboard (fast, works once the game window is open). None if it can't be used."""
    try:
        import pygame
        if not pygame.display.get_surface():
            return None
        if text is None:
            return pygame.scrap.get_text() or None
        pygame.scrap.put_text(text)
        return True
    except Exception:  # noqa: BLE001
        return None


def copy(text):
    if WIN and _sdl_clip(text):
        return True
    for cmd in COPY_CMDS:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text.encode(), check=True, timeout=5)
                return True
            except (OSError, subprocess.SubprocessError):
                pass
    return False


def paste():
    if WIN:
        got = _sdl_clip()
        if got:
            return got
    for cmd in PASTE_CMDS:
        if shutil.which(cmd[0]):
            try:
                return subprocess.run(cmd, capture_output=True, check=True, timeout=5).stdout.decode("utf-8", "ignore")
            except (OSError, subprocess.SubprocessError):
                pass
    return ""
