"""Host every app icon on the store's own address.

Many sources keep their icons on slow or flaky hosts, some of which redirect to plain http,
which iOS refuses (App Transport Security): AltStore, SideStore and Feather then show blank
icons. After merge.py, this downloads each icon once, shrinks it to 180x180 JPEG, keeps it in
cache/icons/ (restored between builds) and points source.json and curated.json at
https://<site>/icons/<key>.jpg, which site.py publishes. An icon that can't be fetched keeps its
original link, or gets the neutral placeholder when its host says it is gone (404/410).

Needs Pillow (pip install pillow).
"""

import hashlib
import io
import os
import socket
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from common import USER_AGENT, hide_nsfw_icons, load_json, nsfw_icon_keys, path
from merge import PLACEHOLDER_ICON, SITE, write_json

DIR = path("cache/icons")
SIZE = 180  # what AltStore shows on a 3x screen
MAX_BYTES = 6 * 1024 * 1024


def key(url):
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def mirror_url(k):
    return f"{SITE}/icons/{k}.jpg"


def shrink(raw):
    """Square 180x180 JPEG from any image Pillow can read; transparency becomes white."""
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        im = ImageOps.fit(im.convert("RGB"), (SIZE, SIZE), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, "JPEG", quality=85, optimize=True, progressive=True)
        return out.getvalue()


def fetch(url):
    """('ok', jpeg bytes) | ('gone', None) on 404/410/no such host | ('error', None)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return "error", None
        return "ok", shrink(raw)
    except urllib.error.HTTPError as e:
        return ("gone" if e.code in (404, 410) else "error"), None
    except urllib.error.URLError as e:
        return ("gone" if isinstance(e.reason, socket.gaierror) else "error"), None
    except Exception:  # unreadable image, timeout, reset
        return "error", None


def mirror(url):
    """(url, new url or None to keep the original)."""
    k = key(url)
    file = os.path.join(DIR, f"{k}.jpg")
    if os.path.exists(file):
        return url, mirror_url(k)
    state, jpeg = fetch(url)
    if state == "ok":
        with open(file, "wb") as f:
            f.write(jpeg)
        return url, mirror_url(k)
    return url, PLACEHOLDER_ICON if state == "gone" else None


def main():
    os.makedirs(DIR, exist_ok=True)
    files = {name: load_json(name, None) for name in ("source.json", "curated.json")}
    files = {name: data for name, data in files.items() if data}
    urls = {
        a["iconURL"]
        for data in files.values()
        for a in data["apps"]
        if a.get("iconURL") and not a["iconURL"].startswith(SITE)
    }
    with ThreadPoolExecutor(24) as ex:
        new = {u: n for u, n in ex.map(mirror, sorted(urls)) if n}
    flagged = nsfw_icon_keys()  # icons ai/images.json marks nsfw get the placeholder
    hidden = 0
    for name, data in files.items():
        hidden += hide_nsfw_icons(data["apps"], PLACEHOLDER_ICON, flagged, new)
        for a in data["apps"]:
            a["iconURL"] = new.get(a["iconURL"], a["iconURL"])
        write_json(name, data)
    hosted = sum(1 for n in new.values() if n != PLACEHOLDER_ICON)
    gone = sum(1 for n in new.values() if n == PLACEHOLDER_ICON)
    kept = len(urls) - hosted - gone
    print(
        f"{len(urls)} icons: {hosted} hosted by Accretion, {gone} gone (placeholder), {kept} kept as is; "
        f"{hidden} flagged nsfw (placeholder)"
    )
    if not hosted and urls:
        sys.exit("No icon could be fetched; is Pillow installed?")


if __name__ == "__main__":
    main()
