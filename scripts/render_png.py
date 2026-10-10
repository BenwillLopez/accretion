"""Render the dark stat cards to PNG for places that do not show SVG (forums, chats).

Needs rsvg-convert (apt: librsvg2-bin), which the publish workflow installs.
Writes assets/card-dark.png and assets/recent-dark.png at 2x with transparent corners.
"""

import os
import shutil
import subprocess
import sys

from common import path

CARDS = ("card-dark", "recent-dark")


def main():
    exe = shutil.which("rsvg-convert")
    if not exe:
        sys.exit("rsvg-convert not found (apt install librsvg2-bin)")
    for name in CARDS:
        out = path(f"assets/{name}.png")
        subprocess.run([exe, "-z", "2", "-o", out, path(f"assets/{name}.svg")], check=True, timeout=120)
        print(f"{out} ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main()
