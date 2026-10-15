"""Build the Accretion web store into _site/ for GitHub Pages.

Copies the static storefront from site/ and adds data generated from the build:
  data/store.json       one compact row per app, everything the grid and search need
  data/index.json       the same, listing only the Accretion app: what Accretion 1.0.4 and older
                        read, so their store only offers the update (app-config.json sets the
                        minimum version newer copies enforce themselves)
  data/apps/NNN.json    full details, split into SHARDS files so a phone only loads
                        the slice that holds the app it opens
  data/stats.json       the numbers merge.py collected
  source.json, curated.json and the card images, so the store has short links too
  app/<bundle id>/      a tiny page per app with link-preview tags (Discord, iMessage,
                        forums) that forwards to the app's page in the store
  sitemap.xml, robots.txt  every per-app page with its newest version date (SITE_URL, else the default)

Run after merge.py. Reads _build/origins.json for where each app came from.
"""

import html
import json
import os
import re
import shutil
import urllib.parse

from common import hide_nsfw_icons, load_json, nsfw_icon_keys, path, read_list
from merge import PLACEHOLDER_ICON

SHARDS = 128
ACCRETION_APP = "io.github.getaccretion.Accretion"
OUT = path("_site")


def private_links():
    """PRIVATE_LINKS (GitHub variable): publish download-server links instead of source URLs"""
    return os.environ.get("PRIVATE_LINKS", "").strip().lower() in ("1", "true", "yes", "on")


def supabase_settings():
    url, key = os.environ.get("SUPABASE_URL", "").strip(), os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if not (url and key):  # written by the "Store: set up backend" workflow
        project = load_json("supabase/project.json", {})
        url, key = project.get("url", ""), project.get("anonKey", "")
    return url.rstrip("/"), key


def server_link(base, bundle_id, version):
    """The download server's link for one version: it needs a login or personal key, checks it,
    then sends the file through the download proxy. The source's own URL is never published."""
    q = urllib.parse.urlencode({"app": bundle_id, "version": version})
    return f"{base}/functions/v1/download?{q}"


def private_source(source, base):
    """A copy of an AltStore source with every download pointed at the download server"""
    copy = json.loads(json.dumps(source))
    for app in copy.get("apps", []):
        bid = app.get("bundleIdentifier", "")
        versions = app.get("versions") or []
        for v in versions:
            v["downloadURL"] = server_link(base, bid, v.get("version", ""))
        if "downloadURL" in app:
            app["downloadURL"] = (
                versions[0]["downloadURL"] if versions else server_link(base, bid, app.get("version", ""))
            )
    return copy


# Apps from this source are built by Accretion: the store shows them with an "Accretion Mod" badge.
MODS_SOURCE = "https://raw.githubusercontent.com/AccretionMods/mods/main/mods.json"


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


def share_pages(apps, gone=None):
    """One small page per app so shared links show a name, icon and description. Apps with no
    working download left (gone) keep a page that opens the store's closest matches."""
    for bid, g in (gone or {}).items():
        if SAFE_ID.match(bid):
            write_share_page(
                bid,
                f"{g['n']} (unavailable)",
                "No working download right now. Open to see the closest apps that work.",
                g["ic"],
                g["n"],
            )
    for a in apps:
        bid = a["bundleIdentifier"]
        if not SAFE_ID.match(bid):
            continue
        latest = a["versions"][0]
        desc = (a.get("subtitle") or a.get("localizedDescription") or "")[:180].replace("\n", " ")
        write_share_page(bid, f"{a['name']} {latest['version']}", desc, a["iconURL"], a["name"])


def write_share_page(bid, title, desc, icon, name):
    title = html.escape(title)
    desc = html.escape(desc)
    icon = html.escape(icon)
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
<p><a style="color:#22D3EE" href="{target}">Open {html.escape(name)} in Accretion</a></p>
</body></html>
"""
    folder = os.path.join(OUT, "app", bid)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "index.html"), "w") as f:
        f.write(page)


SITE_URL = "https://getaccretion.app"  # used for the sitemap when SITE_URL is not set
SITEMAP_LIMIT = 50000  # most URLs one sitemap file may list
STATIC_PAGES = ["install-without-computer.html"]  # crawlable guide pages in site/ that belong in the sitemap


def newest_date(app):
    """YYYY-MM-DD of the app's newest version, or '' when no version has a usable date"""
    dates = [str(v.get("date") or "")[:10] for v in app.get("versions", [])]
    return max((d for d in dates if re.match(r"^\d{4}-\d{2}-\d{2}$", d)), default="")


def sitemap(site_url, apps, out=None):
    """sitemap.xml (a sitemap index plus sitemap-N.xml files above 50,000 URLs) and robots.txt.
    Lists the store, the guide pages and every per-app page; nothing public is blocked."""
    out = out or OUT
    site_url = site_url.rstrip("/")
    entries = (
        [(f"{site_url}/", "")]
        + [(f"{site_url}/{page}", "") for page in STATIC_PAGES]
        + [
            (f"{site_url}/app/{a['bundleIdentifier']}/", newest_date(a))
            for a in apps
            if SAFE_ID.match(a["bundleIdentifier"])
        ]
    )
    head = '<?xml version="1.0" encoding="UTF-8"?>\n'
    ns = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'

    def urlset(items):
        body = "".join(
            f"<url><loc>{html.escape(u)}</loc>" + (f"<lastmod>{d}</lastmod>" if d else "") + "</url>\n"
            for u, d in items
        )
        return f"{head}<urlset {ns}>\n{body}</urlset>\n"

    def write(name, data):
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(data)

    if len(entries) <= SITEMAP_LIMIT:
        write("sitemap.xml", urlset(entries))
    else:
        parts = [entries[i : i + SITEMAP_LIMIT] for i in range(0, len(entries), SITEMAP_LIMIT)]
        for n, part in enumerate(parts, 1):
            write(f"sitemap-{n}.xml", urlset(part))
        refs = "".join(
            f"<sitemap><loc>{html.escape(f'{site_url}/sitemap-{n}.xml')}</loc></sitemap>\n"
            for n in range(1, len(parts) + 1)
        )
        write("sitemap.xml", f"{head}<sitemapindex {ns}>\n{refs}</sitemapindex>\n")
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {site_url}/sitemap.xml\n")


WEB_PICK = 8  # an app in popular.txt counts like 8 more sources carrying it


def popularity(bid, carriers, picks):
    """How wanted an app is before anyone searches the store: sources carrying it, plus a boost
    for the apps guides and communities name most (popular.txt)."""
    return carriers.get(bid, 0) + (WEB_PICK if bid in picks else 0)


def publish_source(name, dest, private, base):
    """source.json / curated.json as published: as built, or with download-server links"""
    if not private:
        shutil.copy(path(name), dest)
        return
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(
            private_source(load_json(name, {"apps": []}), base), f, ensure_ascii=False, separators=(",", ":")
        )


def main():
    source = load_json("source.json", None)
    if not source:
        raise SystemExit("source.json not built yet")
    info = load_json("_build/origins.json", {"sources": [], "origin": {}, "first": {}})
    for s in info["sources"]:
        if s["url"] == MODS_SOURCE:
            s["mod"] = True
    carriers = info.get("carriers", {})
    undated = set(info.get("undated", []))
    picks = set(read_list("popular.txt"))
    stats = load_json("stats.json", {})
    extras = load_json("_build/ai_extras.json", {})  # features and tags from ai/listings.json
    similar = load_json("ai/similar.json", {})  # bundle id -> similar bundle ids (ai_jobs.py similar)
    known = {a["bundleIdentifier"] for a in source["apps"]}
    private = private_links()
    base, _ = supabase_settings()
    if private and not base:
        raise SystemExit("PRIVATE_LINKS is on but the Supabase URL is unknown")
    if private:  # source names stay public, their URLs don't
        info["sources"] = [{k: v for k, v in s.items() if k != "url"} for s in info["sources"]]
    # icons flagged nsfw by ai_jobs.py images show the placeholder (the app stays)
    hide_nsfw_icons(source["apps"], PLACEHOLDER_ICON, nsfw_icon_keys())

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
        if extras.get(bid, {}).get("tags"):
            rows[-1]["k"] = extras[bid]["tags"]
        pop = popularity(bid, carriers, picks)
        if pop:
            rows[-1]["p"] = pop
        if bid in undated:
            rows[-1]["u"] = 1  # release date unknown
        shards[shard_of(bid)].append(
            {
                "i": bid,
                "desc": a.get("localizedDescription", ""),
                "feat": extras.get(bid, {}).get("features", []),
                "sim": [b for b in similar.get(bid, []) if b in known and b != bid][:6],
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
                        "url": server_link(base, bid, v["version"]) if private else v["downloadURL"],
                    }
                    for v in a["versions"]
                ],
            }
        )

    def dump(rel, data):
        with open(os.path.join(OUT, rel), "w") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    dump("data/store.json", {"sources": info["sources"], "shards": SHARDS, "apps": rows})
    dump(
        "data/index.json",
        {"sources": info["sources"], "shards": SHARDS, "apps": [r for r in rows if r["i"] == ACCRETION_APP]},
    )
    for i, items in enumerate(shards):
        dump(f"data/apps/{i:03d}.json", {a["i"]: a for a in items})
    dump("data/stats.json", stats)
    for name in ("source.json", "curated.json"):
        publish_source(name, os.path.join(OUT, name), private, base)
    # app icons hosted by Accretion (scripts/icons.py keeps them in cache/icons)
    os.makedirs(os.path.join(OUT, "icons"), exist_ok=True)
    published = 0
    for name in ("source.json", "curated.json"):
        for a in load_json(name, {"apps": []})["apps"]:
            m = re.search(r"/icons/([0-9a-f]{16})\.jpg$", a.get("iconURL", ""))
            src = m and path(f"cache/icons/{m.group(1)}.jpg")
            if (
                src
                and os.path.exists(src)
                and not os.path.exists(os.path.join(OUT, "icons", f"{m.group(1)}.jpg"))
            ):
                shutil.copy(src, os.path.join(OUT, "icons", f"{m.group(1)}.jpg"))
                published += 1
    print(f"{published} icons published")
    # donation and certificate links shown on the store (empty parts stay hidden)
    support = load_json("support.json", {})
    with open(os.path.join(OUT, "support.json"), "w") as f:
        json.dump(support, f, ensure_ascii=False)
    for name in os.listdir(path("assets")):
        shutil.copy(path(f"assets/{name}"), os.path.join(OUT, "assets", name))
    # community features: public Supabase settings (the anon key is meant to be public)
    url, key = supabase_settings()
    if url and key:
        config = {"supabaseUrl": url, "supabaseKey": key}
        if private:
            config["privateLinks"] = True
        # "Download IPA" for other sources' apps goes through the download proxy once it is live
        # (GitHub variable DOWNLOAD_PROXY_ORIGIN, the same one the download function gets)
        if os.environ.get("DOWNLOAD_PROXY_ORIGIN", "").strip():
            config["downloadProxy"] = True
        with open(os.path.join(OUT, "config.js"), "w") as f:
            f.write(f"window.ACCRETION_CONFIG = {json.dumps(config)};\n")

    gone = {
        b: g
        for b, g in info.get("gone", {}).items()
        if b not in {a["bundleIdentifier"] for a in source["apps"]}
    }
    dump("data/gone.json", gone)
    share_pages(source["apps"], gone)
    sitemap(os.environ.get("SITE_URL", "").strip() or SITE_URL, source["apps"])

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
        publish_source(name, os.path.join(legacy, name), private, base)

    # GitHub Pages: serve files as-is (no Jekyll processing)
    open(os.path.join(OUT, ".nojekyll"), "w").close()

    size = os.path.getsize(os.path.join(OUT, "data/store.json"))
    print(f"_site: {len(rows)} apps, index {size // 1024} KB, {SHARDS} detail files")


if __name__ == "__main__":
    main()
