"""Build the Accretion web store into _site/ for GitHub Pages.

Copies the static storefront from site/ and adds data generated from the build:
  data/index.json       one compact row per app, everything the grid and search need
  data/apps/NNN.json    full details, split into SHARDS files so a phone only loads
                        the slice that holds the app it opens
  data/stats.json       the numbers merge.py collected
  source.json, curated.json and the card images, so the store has short links too

Run after merge.py. Reads _build/origins.json for where each app came from.
"""

import json
import os
import shutil

from common import load_json, path

SHARDS = 128
OUT = path("_site")


def fnv1a(text):
    """32-bit FNV-1a; site/app.js uses the same function to find an app's shard."""
    h = 0x811C9DC5
    for byte in text.encode("utf-8"):
        h ^= byte
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def shard_of(bundle_id):
    return fnv1a(bundle_id) % SHARDS


def screenshot_urls(app):
    shots = app.get("screenshots") or []
    if isinstance(shots, dict):
        shots = shots.get("iphone") or shots.get("ipad") or []
    return [s["imageURL"] if isinstance(s, dict) else s for s in shots]


def main():
    source = load_json("source.json", None)
    if not source:
        raise SystemExit("source.json not built yet")
    info = load_json("_build/origins.json", {"sources": [], "origin": {}, "first": {}})
    stats = load_json("stats.json", {})

    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(path("site"), OUT)
    os.makedirs(os.path.join(OUT, "data", "apps"))
    os.makedirs(os.path.join(OUT, "assets"))

    rows, shards = [], [[] for _ in range(SHARDS)]
    for a in source["apps"]:
        bid = a["bundleIdentifier"]
        latest = a["versions"][0]
        rows.append(
            {
                "i": bid,
                "n": a["name"],
                "d": a["developerName"],
                "s": (a.get("subtitle") or "")[:90],
                "c": a["category"],
                "v": latest["version"],
                "t": latest["date"][:10],
                "z": latest.get("size") or 0,
                "ic": a["iconURL"],
                "o": info["origin"].get(bid, -1),
                "f": info["first"].get(bid, latest["date"][:10]),
            }
        )
        shards[shard_of(bid)].append(
            {
                "i": bid,
                "desc": a.get("localizedDescription", ""),
                "tint": a.get("tintColor", ""),
                "shots": screenshot_urls(a)[:5],
                "perms": a.get("appPermissions", {}),
                "versions": [
                    {
                        "v": v["version"],
                        "b": v.get("buildVersion", ""),
                        "t": v["date"][:10],
                        "z": v.get("size") or 0,
                        "min": v.get("minOSVersion", ""),
                        "notes": v.get("localizedDescription", ""),
                        "url": v["downloadURL"],
                    }
                    for v in a["versions"]
                ],
            }
        )

    def dump(rel, data):
        with open(os.path.join(OUT, rel), "w") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    dump("data/index.json", {"sources": info["sources"], "shards": SHARDS, "apps": rows})
    for i, items in enumerate(shards):
        dump(f"data/apps/{i:03d}.json", {a["i"]: a for a in items})
    dump("data/stats.json", stats)
    for name in ("source.json", "curated.json"):
        shutil.copy(path(name), os.path.join(OUT, name))
    for name in os.listdir(path("assets")):
        shutil.copy(path(f"assets/{name}"), os.path.join(OUT, "assets", name))
    # GitHub Pages: serve files as-is (no Jekyll processing)
    open(os.path.join(OUT, ".nojekyll"), "w").close()

    size = os.path.getsize(os.path.join(OUT, "data/index.json"))
    print(f"_site: {len(rows)} apps, index {size // 1024} KB, {SHARDS} detail files")


if __name__ == "__main__":
    main()
