"""Draws PokeBrawl's icon (a ball) and saves it as an .ico (install.ps1's Windows shortcut) or an .icns (the Mac
app install.sh makes), and the game window uses it too:

    python -m pokebrawl.winicon OUT.ico
    python -m pokebrawl.winicon OUT.icns
"""
import io
import os
import struct
import sys

import pygame  # noqa: E402

INK = (24, 24, 32)


def draw(size=256):
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    r = size // 2
    w = max(2, size // 16)
    pygame.draw.circle(s, (232, 44, 44), (r, r), r - 2)
    pygame.draw.rect(s, (0, 0, 0, 0), (0, r, size, r))
    pygame.draw.circle(s, (248, 248, 248), (r, r), r - 2, draw_bottom_left=True, draw_bottom_right=True)
    pygame.draw.circle(s, (255, 120, 110), (int(r * 0.62), int(r * 0.55)), size // 12)   # shine
    pygame.draw.circle(s, INK, (r, r), r - 2, w)
    pygame.draw.rect(s, INK, (0, r - w // 2, size, w))
    pygame.draw.circle(s, (248, 248, 248), (r, r), size // 6)
    pygame.draw.circle(s, INK, (r, r), size // 6, w)
    pygame.draw.circle(s, INK, (r, r), size // 12, max(1, w // 2))
    return s


def save_ico(path, sizes=(256, 48, 32, 16)):
    """An .ico holding PNG images (Windows Vista and later read these)."""
    big = draw(256)
    pngs = []
    for n in sizes:
        buf = io.BytesIO()
        pygame.image.save(pygame.transform.smoothscale(big, (n, n)), buf, "png")
        pngs.append((n, buf.getvalue()))
    out = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    for n, data in pngs:
        out += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    with open(path, "wb") as f:
        f.write(out + b"".join(d for _, d in pngs))


def save_icns(path):
    """A Mac .icns holding PNG images from 1024 down to 128 pixels."""
    big = draw(1024)
    chunks = b""
    for kind, n in ((b"ic10", 1024), (b"ic09", 512), (b"ic08", 256), (b"ic07", 128)):
        buf = io.BytesIO()
        pygame.image.save(pygame.transform.smoothscale(big, (n, n)), buf, "png")
        data = buf.getvalue()
        chunks += kind + struct.pack(">I", 8 + len(data)) + data
    with open(path, "wb") as f:
        f.write(b"icns" + struct.pack(">I", 8 + len(chunks)) + chunks)


def ensure_mac_app_icon():
    """Older installs made ~/Applications/PokeBrawl.app without an icon: give it the ball (once). Updates come in
    without re-running the installer, so the game does this itself."""
    if sys.platform != "darwin":
        return
    app = os.path.join(os.path.expanduser("~"), "Applications", "PokeBrawl.app", "Contents")
    plist = os.path.join(app, "Info.plist")
    icns = os.path.join(app, "Resources", "PokeBrawl.icns")
    if not os.path.isfile(plist) or os.path.exists(icns):
        return
    try:
        os.makedirs(os.path.dirname(icns), exist_ok=True)
        save_icns(icns)
        with open(plist, encoding="utf-8") as f:
            text = f.read()
        if "CFBundleIconFile" not in text and "</dict>" in text:
            text = text.replace("</dict>", "  <key>CFBundleIconFile</key><string>PokeBrawl</string>\n</dict>", 1)
            with open(plist, "w", encoding="utf-8") as f:
                f.write(text)
        os.utime(os.path.dirname(app))   # so Finder notices
    except OSError:
        pass


if __name__ == "__main__":
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    (save_icns if sys.argv[1].endswith(".icns") else save_ico)(sys.argv[1])
