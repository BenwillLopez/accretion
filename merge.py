"""Merge many AltStore/SideStore sources into one source.json, newest versions only.

Sources come from sources.txt (yours, checked first) and discovered.txt
(found by discover.py). Anything matching blocklist.txt is skipped.

When several sources list the same app (same bundle ID), the copy with the
highest version wins; ties go to the newest release date, then to the source
listed first. Each source's last good copy is kept in cache/, so a source
that is down during a build keeps its apps. A summary is written to REPORT.md.
"""
import copy
import datetime as dt
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from common import date_key, fetch_source, is_blocked, path, read_list, version_key

OWNER = "benwilllopez"
REPO = "altsource"
MAX_VERSIONS = 3   # older versions kept per app; keeps source.json small enough for the app
MAX_NEWS = 100

SOURCE_INFO = {
    "name": "Ben's Merged Source",
    "identifier": f"io.github.{OWNER}.{REPO}",
    "subtitle": "Every source, newest versions, one link.",
    "sourceURL": f"https://raw.githubusercontent.com/{OWNER}/{REPO}/main/source.json",
    "website": f"https://github.com/{OWNER}/{REPO}",
    "tintColor": "#5B6CFF",
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


def versions_of(app):
    """All versions an app entry offers, newest first, in the v2 `versions` format."""
    out = [v for v in app.get("versions") or [] if isinstance(v, dict) and v.get("downloadURL")]
    if app.get("downloadURL"):  # legacy single-version format
        out.append({k2: app[k1] for k1, k2 in (("version", "version"), ("versionDate", "date"),
                    ("downloadURL", "downloadURL"), ("size", "size"),
                    ("versionDescription", "localizedDescription"),
                    ("minOSVersion", "minOSVersion"), ("buildVersion", "buildVersion"))
                    if app.get(k1) is not None})
    seen, uniq = set(), []
    for v in out:
        if v.get("downloadURL") not in seen:
            seen.add(v.get("downloadURL"))
            uniq.append(v)
    uniq.sort(key=lambda v: (version_key(v.get("version")), version_key(v.get("buildVersion")),
                             date_key(v.get("date"))), reverse=True)
    return uniq


def rank(versions, priority):
    v = versions[0]
    return (version_key(v.get("version")), version_key(v.get("buildVersion")),
            date_key(v.get("date")), -priority)


def normalise(app, versions):
    """Newest version first, in both the v2 and the legacy fields, so every client reads it."""
    app = copy.deepcopy(app)
    versions = versions[:MAX_VERSIONS]
    latest = versions[0]
    app["versions"] = versions
    app["version"] = latest.get("version", "")
    app["downloadURL"] = latest["downloadURL"]
    for k_new, k_old in (("date", "versionDate"), ("size", "size"),
                         ("localizedDescription", "versionDescription")):
        if latest.get(k_new) is not None:
            app[k_old] = latest[k_new]
    return app


def main():
    os.makedirs(CACHE, exist_ok=True)
    blocklist = read_list("blocklist.txt")
    urls, seen = [], set()
    for u in read_list("sources.txt") + read_list("discovered.txt"):
        if u not in seen and not is_blocked(u, blocklist):
            seen.add(u)
            urls.append(u)
    manual = set(read_list("sources.txt"))

    with ThreadPoolExecutor(16) as ex:
        loaded = list(ex.map(load, urls))

    best = {}        # bundle ID -> (rank, app, versions, source url)
    listings = {}    # bundle ID -> number of sources listing it
    stats = []
    news, news_ids = [], set()
    for priority, (url, data, status, size) in enumerate(loaded):
        st = {"url": url, "status": status, "size": size, "name": "", "apps": 0,
              "manual": url in manual, "newest": ""}
        stats.append(st)
        if not data:
            continue
        st["name"] = str(data.get("name", ""))[:60]
        seen_here = set()
        for app in data.get("apps", []):
            bid = app.get("bundleIdentifier") if isinstance(app, dict) else None
            if not bid:
                continue
            vers = versions_of(app)
            if not vers:
                continue
            st["apps"] += 1
            st["newest"] = max(st["newest"], date_key(vers[0].get("date")))
            if bid not in seen_here:
                seen_here.add(bid)
                listings[bid] = listings.get(bid, 0) + 1
            r = rank(vers, priority)
            if bid not in best or r > best[bid][0]:
                best[bid] = (r, app, vers, url)
        for item in data.get("news") or []:
            nid = item.get("identifier") if isinstance(item, dict) else None
            if nid and nid not in news_ids:
                news_ids.add(nid)
                news.append(item)

    if not best:
        sys.exit("No apps loaded; keeping the existing source.json.")

    apps = [normalise(app, vers) for _, app, vers, _ in
            sorted(best.values(), key=lambda b: (str(b[1].get("name", "")).lower(), b[1]["bundleIdentifier"]))]
    news.sort(key=lambda n: date_key(n.get("date")), reverse=True)
    out = dict(SOURCE_INFO, apps=apps, news=news[:MAX_NEWS])
    body = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    with open(path("source.json"), "w") as f:
        f.write(body)

    won = {}
    for _, _, _, url in best.values():
        won[url] = won.get(url, 0) + 1
    write_report(stats, won, best, listings, len(body))
    ok = sum(1 for s in stats if not s["status"].startswith("failed"))
    print(f"{len(apps)} apps (newest of each) from {ok}/{len(urls)} sources, "
          f"{len(body) // 1024} KB")


def write_report(stats, won, best, listings, size):
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ok = [s for s in stats if s["status"] == "ok"]
    cached = [s for s in stats if s["status"].startswith("cached")]
    failed = [s for s in stats if s["status"].startswith("failed")]
    total = sum(s["apps"] for s in stats)
    multi = sum(1 for n in listings.values() if n > 1)
    L = [
        "# Source report", "",
        f"Built {now}.", "",
        f"- **{len(best)} apps** in `source.json` ({size // 1024} KB), "
        f"picked from {total} listings",
        f"- **{multi} apps** were listed by more than one source; the newest version was kept",
        f"- **{len(stats)} sources**: {len(ok)} ok, {len(cached)} served from cache, "
        f"{len(failed)} failed", "",
        "## Sources", "",
        "Apps used = how many apps in the merged source came from this source "
        "(it had the newest version).", "",
        "| Source | Status | Apps listed | Apps used | Latest release | Type |",
        "|---|---|---:|---:|---|---|",
    ]
    for s in sorted(stats, key=lambda s: (-won.get(s["url"], 0), -s["apps"], s["url"])):
        name = s["name"] or s["url"].split("/")[2]
        status = s["status"].split(" (")[0]
        L.append(f"| [{name.replace('|', '/')}]({s['url']}) | {status} | {s['apps']} | "
                 f"{won.get(s['url'], 0)} | {s['newest'][:10]} | "
                 f"{'yours' if s['manual'] else 'discovered'} |")
    if failed or cached:
        L += ["", "## Problems", ""]
        L += [f"- {s['url']}: {s['status']}" for s in failed + cached]
    recent = sorted(best.values(), key=lambda b: date_key(b[2][0].get("date")), reverse=True)[:25]
    L += ["", "## Recently updated apps", "", "| App | Version | Date | From |", "|---|---|---|---|"]
    for _, app, vers, url in recent:
        L.append(f"| {str(app.get('name', ''))[:40].replace('|', '/')} | {vers[0].get('version', '')} | "
                 f"{date_key(vers[0].get('date'))[:10]} | {url.split('/')[2]} |")
    with open(path("REPORT.md"), "w") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
