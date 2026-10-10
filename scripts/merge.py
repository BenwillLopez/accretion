"""Merge many AltStore/SideStore sources into one source, newest versions only.

Inputs (repo root):
  sources.txt      your sources, always first
  discovered.txt   sources found by discover.py
  blocklist.txt    URLs or URL fragments that are never used
  dead_links.json  download links check_links.py found dead

Outputs:
  source.json   every source           (the main link)
  curated.json  only sources.txt       ("Accretion Core": smaller, faster to refresh)
  stats.json    numbers for the README badges
  REPORT.md     what every source contributed

When several sources list one bundle ID, the copy with the highest version
wins; ties go to the newest release date, then to the source listed first.
Each source's last good copy is kept in cache/ (restored by the workflow), so
a source that is down during a build keeps its apps. Nothing is written
unless the result passes sanitize.validate().
"""

import datetime as dt
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from common import date_key, fetch_source, is_blocked, load_json, path, read_list, version_key
from sanitize import clean_app, clean_news, validate

OWNER = "benwilllopez"
REPO = "accretion"
RAW = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/main"
MAX_NEWS = 50
MAX_FEATURED = 10
DEAD_AFTER = 2
MAX_BYTES = 30 * 1024 * 1024

SOURCE_INFO = {
    "name": "Accretion",
    "subtitle": "Every source, pulled into one. Always the newest.",
    "description": (
        "Like matter drawn into a star, Accretion pulls hundreds of public AltStore and "
        "SideStore sources into one. It is rebuilt every 6 hours and keeps only the newest "
        "version of each app.\n\n"
        "Apps come from third-party sources and are not reviewed. Install only what you trust.\n\n"
        f"Source list, report and issue tracker: https://github.com/{OWNER}/{REPO}"
    ),
    "iconURL": f"{RAW}/assets/icon.png",
    "headerURL": f"{RAW}/assets/header.png",
    "website": f"https://github.com/{OWNER}/{REPO}",
    "tintColor": "8B5CF6",
}
OUTPUTS = {
    "source.json": {"identifier": f"io.github.{OWNER}.{REPO}", "sourceURL": f"{RAW}/source.json"},
    "curated.json": {
        "identifier": f"io.github.{OWNER}.{REPO}.curated",
        "sourceURL": f"{RAW}/curated.json",
        "name": "Accretion Core",
        "subtitle": "The hand-picked core. Small and fast.",
    },
}

CACHE = path("cache")


def cache_file(url):
    return os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest()[:16] + ".json")


def load(url):
    try:
        data, _, size = fetch_source(url)
        with open(cache_file(url), "w") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        return url, data, "ok", size
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:70]}"
        if os.path.exists(cache_file(url)):
            with open(cache_file(url)) as f:
                return url, json.load(f), f"cached ({err})", 0
        return url, None, f"failed ({err})", 0


def versions_of(app, dead=frozenset()):
    """Every live version an app entry offers, newest first, in the v2 `versions` format."""
    out = [v for v in app.get("versions") or [] if isinstance(v, dict) and v.get("downloadURL")]
    if app.get("downloadURL"):  # legacy single-version format
        out.append(
            {
                k2: app[k1]
                for k1, k2 in (
                    ("version", "version"),
                    ("versionDate", "date"),
                    ("downloadURL", "downloadURL"),
                    ("size", "size"),
                    ("versionDescription", "localizedDescription"),
                    ("minOSVersion", "minOSVersion"),
                    ("buildVersion", "buildVersion"),
                )
                if app.get(k1) is not None
            }
        )
    seen, uniq = set(), []
    for v in out:
        url = v.get("downloadURL")
        if url not in seen and url not in dead:
            seen.add(url)
            uniq.append(v)
    uniq.sort(
        key=lambda v: (
            version_key(v.get("version")),
            version_key(v.get("buildVersion")),
            date_key(v.get("date")),
        ),
        reverse=True,
    )
    return uniq


def rank(app, priority):
    v = app["versions"][0]
    return (
        version_key(v.get("version")),
        version_key(v.get("buildVersion")),
        date_key(v.get("date")),
        -priority,
    )


def pick(loaded, dead):
    """Choose the newest clean copy of every app across the loaded sources."""
    best, listings, stats, news, news_ids = {}, {}, [], [], set()
    for priority, (url, data, status, size) in enumerate(loaded):
        st = {"url": url, "status": status, "size": size, "name": "", "apps": 0, "skipped": 0, "newest": ""}
        stats.append(st)
        if not data:
            continue
        st["name"] = str(data.get("name") or "")[:60]
        for raw in data.get("apps", []):
            if not isinstance(raw, dict):
                continue
            app = clean_app(raw, versions_of(raw, dead))
            if not app:
                st["skipped"] += 1
                continue
            st["apps"] += 1
            st["newest"] = max(st["newest"], date_key(app["versionDate"]))
            bid = app["bundleIdentifier"]
            listings.setdefault(bid, set()).add(url)
            r = rank(app, priority)
            if bid not in best or r > best[bid][0]:
                best[bid] = (r, app, url)
        for item in data.get("news") or []:
            if isinstance(item, dict) and item.get("identifier") not in news_ids:
                news_ids.add(item.get("identifier"))
                news.append(item)
    return best, listings, stats, news


def build(best, news, info):
    apps = sorted((b[1] for b in best.values()), key=lambda a: (a["name"].lower(), a["bundleIdentifier"]))
    ids = {a["bundleIdentifier"] for a in apps}
    items = [n for n in (clean_news(n, ids) for n in news) if n]
    items.sort(key=lambda n: date_key(n["date"]), reverse=True)
    featured = sorted(apps, key=lambda a: date_key(a["versionDate"]), reverse=True)[:MAX_FEATURED]
    return dict(
        SOURCE_INFO,
        **info,
        featuredApps=[a["bundleIdentifier"] for a in featured],
        apps=apps,
        news=items[:MAX_NEWS],
    )


def write_json(name, data):
    errors = validate(data)
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if len(body) > MAX_BYTES:
        errors.append(f"{name} is {len(body) // 1024} KB, over the {MAX_BYTES // 1024} KB limit")
    if errors:
        print(f"{name} NOT written, {len(errors)} problems:", *errors[:20], sep="\n  ")
        sys.exit(1)
    tmp = path(name + ".tmp")
    with open(tmp, "w") as f:
        f.write(body)
    os.replace(tmp, path(name))
    return len(body)


def main():
    os.makedirs(CACHE, exist_ok=True)
    blocklist = read_list("blocklist.txt")
    manual = [u for u in dict.fromkeys(read_list("sources.txt")) if not is_blocked(u, blocklist)]
    found = [
        u
        for u in dict.fromkeys(read_list("discovered.txt"))
        if u not in manual and not is_blocked(u, blocklist)
    ]
    dead = {u for u, v in load_json("dead_links.json", {}).items() if v.get("fails", 0) >= DEAD_AFTER}

    with ThreadPoolExecutor(16) as ex:
        loaded = list(ex.map(load, manual + found))

    best, listings, stats, news = pick(loaded, dead)
    if not best:
        sys.exit("No apps loaded; keeping the published files.")
    cur_best, _, _, cur_news = pick(loaded[: len(manual)], dead)

    sizes = {
        "source.json": write_json("source.json", build(best, news, OUTPUTS["source.json"])),
        "curated.json": write_json("curated.json", build(cur_best, cur_news, OUTPUTS["curated.json"])),
    }
    ok = sum(1 for s in stats if not s["status"].startswith("failed"))
    now = dt.datetime.now(dt.timezone.utc)
    with open(path("stats.json"), "w") as f:
        json.dump(
            {
                "apps": len(best),
                "curated_apps": len(cur_best),
                "sources": ok,
                "updated": now.strftime("%Y-%m-%d %H:%M UTC"),
                "size_mb": round(sizes["source.json"] / 1048576, 1),
            },
            f,
            indent=1,
        )
    write_report(now, stats, best, listings, sizes, len(cur_best), set(manual), len(dead))
    print(
        f"{len(best)} apps from {ok}/{len(stats)} sources "
        f"(source.json {sizes['source.json'] // 1024} KB, "
        f"curated.json {len(cur_best)} apps, {sizes['curated.json'] // 1024} KB)"
    )


def write_report(now, stats, best, listings, sizes, curated_apps, manual, dead):
    won = {}
    for _, _, url in best.values():
        won[url] = won.get(url, 0) + 1
    failed = [s for s in stats if s["status"].startswith("failed")]
    cached = [s for s in stats if s["status"].startswith("cached")]
    total = sum(s["apps"] for s in stats)
    skipped = sum(s["skipped"] for s in stats)
    multi = sum(1 for v in listings.values() if len(v) > 1)
    L = [
        "# Source report",
        "",
        f"Built {now.strftime('%Y-%m-%d %H:%M UTC')}.",
        "",
        "| | |",
        "|---|---|",
        f"| Apps in `source.json` | **{len(best)}** ({sizes['source.json'] // 1024} KB) |",
        f"| Apps in `curated.json` | **{curated_apps}** ({sizes['curated.json'] // 1024} KB) |",
        f"| Listings read | {total} |",
        f"| Apps listed by more than one source (newest kept) | {multi} |",
        f"| Listings skipped (http-only, no icon, no date, bad bundle ID) | {skipped} |",
        f"| Dead download links removed | {dead} |",
        (
            f"| Sources | {len(stats)}: {len(stats) - len(failed) - len(cached)} ok, "
            f"{len(cached)} from cache, {len(failed)} failed |"
        ),
        "",
        "## Sources",
        "",
        ("*Used* is how many apps in `source.json` came from that source (it had the newest version)."),
        "",
        "| Source | Status | Listed | Used | Skipped | Latest release | List |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for s in sorted(stats, key=lambda s: (-won.get(s["url"], 0), -s["apps"], s["url"])):
        name = (s["name"] or s["url"].split("/")[2]).replace("|", "/")
        L.append(
            f"| [{name}]({s['url']}) | {s['status'].split(' (')[0]} | {s['apps']} | "
            f"{won.get(s['url'], 0)} | {s['skipped']} | {s['newest'][:10]} | "
            f"{'curated' if s['url'] in manual else 'discovered'} |"
        )
    if failed or cached:
        L += ["", "## Problems", ""]
        L += [f"- `{s['url']}`: {s['status']}" for s in failed + cached]
    recent = sorted(best.values(), key=lambda b: date_key(b[1]["versionDate"]), reverse=True)[:25]
    L += ["", "## Recently updated", "", "| App | Version | Date | From |", "|---|---|---|---|"]
    for _, app, url in recent:
        L.append(
            f"| {app['name'][:40].replace('|', '/')} | {app['version'][:24]} | "
            f"{app['versionDate'][:10]} | {url.split('/')[2]} |"
        )
    with open(path("REPORT.md"), "w") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
