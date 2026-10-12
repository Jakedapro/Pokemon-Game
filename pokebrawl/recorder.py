"""Pipes frames into ffmpeg to make vertical MP4s (TikTok / Reels / Shorts ready)."""
import shutil
import subprocess

import pygame


class Recorder:
    def __init__(self, path, w, h, fps=30):
        exe = shutil.which("ffmpeg")
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
