"""Build the Accretion web store into _site/ for GitHub Pages.

Copies the static storefront from site/ and adds data generated from the build:
  data/index.json       one compact row per app, everything the grid and search need
  data/apps/NNN.json    full details, split into SHARDS files so a phone only loads
                        the slice that holds the app it opens
  data/stats.json       the numbers merge.py collected
  source.json, curated.json and the card images, so the store has short links too
  app/<bundle id>/      a tiny page per app with link-preview tags (Discord, iMessage,
                        forums) that forwards to the app's page in the store
  sitemap.xml           when SITE_URL is set (the workflow sets it from GitHub Pages)

Run after merge.py. Reads _build/origins.json for where each app came from.
"""

import html
import json
import os
import re
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


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_]*$")


def share_pages(apps):
    """One small page per app so shared links show a name, icon and description."""
    for a in apps:
        bid = a["bundleIdentifier"]
        if not SAFE_ID.match(bid):
            continue
        latest = a["versions"][0]
        title = html.escape(f"{a['name']} {latest['version']}")
        desc = html.escape(
            (a.get("subtitle") or a.get("localizedDescription") or "")[:180].replace("\n", " ")
        )
        icon = html.escape(a["iconURL"])
        target = f"../../#/app/{bid}"
        page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Accretion</title>
<meta name="description" content="{desc}">
<meta property="og:site_name" content="Accretion">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{icon}">
<meta name="twitter:card" content="summary">
<meta name="theme-color" content="#07070D">
<meta http-equiv="refresh" content="0; url={target}">
<link rel="icon" href="../../icon-192.png">
</head><body style="background:#07070D;color:#ECEAFF;font-family:system-ui,sans-serif;padding:24px">
<script>location.replace({json.dumps(target)})</script>
<p><a style="color:#22D3EE" href="{target}">Open {html.escape(a["name"])} in Accretion</a></p>
</body></html>
"""
        folder = os.path.join(OUT, "app", bid)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "index.html"), "w") as f:
            f.write(page)


def sitemap(site_url, apps):
    urls = [f"{site_url}/"] + [
        f"{site_url}/app/{a['bundleIdentifier']}/" for a in apps if SAFE_ID.match(a["bundleIdentifier"])
    ]
    with open(os.path.join(OUT, "sitemap.xml"), "w") as f:
        f.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        )
        f.writelines(f"<url><loc>{html.escape(u)}</loc></url>\n" for u in urls)
        f.write("</urlset>\n")
    with open(os.path.join(OUT, "robots.txt"), "w") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {site_url}/sitemap.xml\n")


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
                "m": latest.get("minOSVersion", ""),
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
    # community features: public Supabase settings (the anon key is meant to be public)
    url, key = os.environ.get("SUPABASE_URL", "").strip(), os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if not (url and key):  # written by the "Set up community" workflow
        project = load_json("supabase/project.json", {})
        url, key = project.get("url", ""), project.get("anonKey", "")
    if url and key:
        with open(os.path.join(OUT, "config.js"), "w") as f:
            f.write(f"window.ACCRETION_CONFIG = {json.dumps({'supabaseUrl': url, 'supabaseKey': key})};\n")

    share_pages(source["apps"])
    site_url = os.environ.get("SITE_URL", "").rstrip("/")
    if site_url:
        sitemap(site_url, source["apps"])

    # the store used to live at /Accretion/: send old links and saved home screen icons home
    legacy = os.path.join(OUT, "Accretion")
    os.makedirs(legacy, exist_ok=True)
    with open(os.path.join(legacy, "index.html"), "w") as f:
        f.write(
            '<!doctype html><meta charset="utf-8"><title>Accretion</title>'
            '<meta name="robots" content="noindex"><link rel="canonical" href="../">'
            "<script>location.replace('../' + location.hash)</script>"
            '<a href="../">Accretion has moved</a>\n'
        )
    for name in ("source.json", "curated.json"):
        shutil.copy(path(name), os.path.join(legacy, name))

    # GitHub Pages: serve files as-is (no Jekyll processing)
    open(os.path.join(OUT, ".nojekyll"), "w").close()

    size = os.path.getsize(os.path.join(OUT, "data/index.json"))
    print(f"_site: {len(rows)} apps, index {size // 1024} KB, {SHARDS} detail files")


if __name__ == "__main__":
    main()
