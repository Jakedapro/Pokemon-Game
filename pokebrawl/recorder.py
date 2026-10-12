"""Pipes frames into ffmpeg to make vertical MP4s (TikTok / Reels / Shorts ready)."""
import os
import shutil
import subprocess

import pygame


def ffmpeg_path():
    """ffmpeg comes from Homebrew, which needs Apple's Command Line Tools - so it may simply not be there.
    The .app launcher doesn't always have Homebrew on PATH, so look in its usual spots too."""
    exe = shutil.which("ffmpeg")
    for cand in (exe, "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def available():
    return ffmpeg_path() is not None


class Recorder:
    def __init__(self, path, w, h, fps=30):
        exe = ffmpeg_path()
        if not exe:
            raise RuntimeError("ffmpeg not found. On Mac: brew install ffmpeg")
        self.proc = subprocess.Popen(
            [exe, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
             "-r", str(fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
             "-crf", "18", "-movflags", "+faststart", path],
            stdin=subprocess.PIPE)

    def write(self, surface):
        self.proc.stdin.write(pygame.image.tobytes(surface, "RGB"))

    def close(self):
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.wait()
