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

import sanitize
from card import render_cards
from check_links import check_many, dead_after
from common import date_key, fetch_source, is_blocked, load_json, path, read_list, today, version_key
from sanitize import clean_app, clean_news, skip_reason, validate

OWNER = "GETAccretion"
REPO = "getaccretion.github.io"
SITE = "https://getaccretion.github.io"  # GitHub Pages serves the store, the sources and the assets
# AltStore refuses a source whose identifier changes, so these stay as first published
ID = "io.github.benwilllopez.accretion"
MAX_NEWS = 50
MAX_FEATURED = 5  # AltStore shows the first five
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
    "iconURL": f"{SITE}/assets/icon.png",
    "headerURL": f"{SITE}/assets/source-header.png",  # 3:2, as AltStore recommends
    "website": f"{SITE}/",
    "tintColor": "8B5CF6",
}
OUTPUTS = {
    "source.json": {"identifier": ID, "sourceURL": f"{SITE}/source.json"},
    "curated.json": {
        "identifier": f"{ID}.curated",
        "sourceURL": f"{SITE}/curated.json",
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


# Accretion's own bundle IDs may only come from Accretion's own sources, so no other source can
# replace the Accretion app or a mod by listing a higher version.
RESERVED = {
    "io.github.getaccretion.": "https://raw.githubusercontent.com/GETAccretion/accretion-app/main/app-repo.json",
    "io.github.accretionmods.": "https://raw.githubusercontent.com/AccretionMods/mods/main/mods.json",
}


def reserved_by_other(bid, url):
    """True when bid belongs to an Accretion prefix and url isn't the source that owns it."""
    return any(bid.startswith(prefix) and url != owner for prefix, owner in RESERVED.items())


def rank(app, priority):
    v = app["versions"][0]
    return (
        version_key(v.get("version")),
        version_key(v.get("buildVersion")),
        date_key(v.get("date")),
        -priority,
    )


PLACEHOLDER_ICON = f"{SITE}/assets/app-placeholder.png"


def fix_icons(best, icons, dead):
    """Replace dead icons with the same app's icon from another source, else a neutral one."""
    swapped = 0
    for bid, (_, app, _) in best.items():
        if app["iconURL"] in dead:
            app["iconURL"] = next((i for i in icons.get(bid, []) if i not in dead), PLACEHOLDER_ICON)
            swapped += 1
    return swapped


def published_links(*bests):
    return {v["downloadURL"] for best in bests for _, app, _ in best.values() for v in app["versions"]}


def pick_checked(loaded, n_manual, dead, checked, check_many, links, rounds=4):
    """Pick the full list and Core, then test every download link they'd publish that this
    build's link check hasn't seen (fallback copies chosen because another copy is dead).
    Dead ones are added to dead and to links (so later builds retest them), then pick again.
    checked is None when no link check ran: nothing extra is tested."""
    for round_ in range(rounds + 1):
        gone, icons = {}, {}
        full = pick(loaded, dead, gone, icons)
        core = pick(loaded[:n_manual], dead)
        if checked is None or round_ == rounds:
            break  # no check ran, or out of rounds: this last pick already skips every dead link
        new = published_links(full[0], core[0]) - set(checked) - dead
        if not new:
            break
        results = check_many(new)
        checked.update(results)
        newly = {u for u, s in results.items() if s == "dead"}
        print(f"checked {len(new)} links chosen as fallbacks: {len(newly)} dead")
        if not newly:
            break
        now = today().isoformat()
        for u in newly:
            links[u] = {"fails": 1, "first": now, "last": now, "host_wide": False}
        dead |= newly  # pick again without them
    return full, core, gone, icons


def pick(loaded, dead, gone=None, icons=None):
    """Choose the newest clean copy of every app across the loaded sources.

    gone, when given, collects apps whose every download is dead (name, developer, category),
    so the store can point people to the closest working app instead."""
    best, listings, stats, news, news_ids = {}, {}, [], [], set()
    firsts = {}  # bundle ID -> earliest release date seen in any source
    for priority, (url, data, status, size) in enumerate(loaded):
        st = {
            "url": url,
            "status": status,
            "size": size,
            "name": "",
            "apps": 0,
            "skipped": 0,
            "excluded": 0,
            "newest": "",
            "nsfw": False,
        }
        stats.append(st)
        if not data:
            continue
        st["name"] = str(data.get("name") or "")[:60]
        st["nsfw"] = data.get("nsfw") is True
        for raw in data.get("apps", []):
            if not isinstance(raw, dict):
                continue
            if skip_reason(raw):  # Patreon or AltStore PAL: cannot install from here
                st["excluded"] += 1
                continue
            versions = versions_of(raw, dead)
            app = clean_app(raw, versions)
            if not app:
                st["skipped"] += 1
                if gone is not None:
                    lost = clean_app(raw, versions_of(raw))  # usable apart from dead links?
                    if lost:
                        gone[lost["bundleIdentifier"]] = {
                            "n": lost["name"],
                            "d": lost["developerName"],
                            "c": lost["category"],
                            "ic": lost["iconURL"],
                        }
                continue
            bid = app["bundleIdentifier"]
            if reserved_by_other(bid, url):
                st["skipped"] += 1
                continue
            st["apps"] += 1
            st["newest"] = max(st["newest"], date_key(app["versionDate"]))
            listings.setdefault(bid, set()).add(url)
            if icons is not None:
                icons.setdefault(bid, []).append(app["iconURL"])
            dates = [d for d in (date_key(v.get("date")) for v in versions) if d]
            if dates:
                firsts[bid] = min(firsts.get(bid, dates[0]), *dates)
            r = rank(app, priority)
            if bid not in best or r > best[bid][0]:
                best[bid] = (r, app, url)
        for item in data.get("news") or []:
            if isinstance(item, dict) and item.get("identifier") not in news_ids:
                news_ids.add(item.get("identifier"))
                news.append(item)
    if gone is not None:
        for bid in [b for b in gone if b in best]:  # a working copy exists elsewhere
            del gone[bid]
    return best, listings, stats, news, firsts


def build(best, news, info, stats):
    apps = sorted((b[1] for b in best.values()), key=lambda a: (a["name"].lower(), a["bundleIdentifier"]))
    ids = {a["bundleIdentifier"] for a in apps}
    items = [n for n in (clean_news(n, ids) for n in news) if n]
    items.sort(key=lambda n: date_key(n["date"]), reverse=True)
    featured = sorted(apps, key=lambda a: date_key(a["versionDate"]), reverse=True)[:MAX_FEATURED]
    # adult content: true if any source that supplied an app says so
    used = {b[2] for b in best.values()}
    nsfw = any(s["nsfw"] for s in stats if s["url"] in used)
    return dict(
        SOURCE_INFO,
        **info,
        nsfw=nsfw,
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
    links = load_json("dead_links.json", {})
    # every dropped link stays in dead_links.json and is retested each build until it works
    dead = {u for u, v in links.items() if v.get("fails", 0) >= dead_after(v)}
    held = sum(1 for u, v in links.items() if u not in dead and v.get("host_wide"))

    with ThreadPoolExecutor(16) as ex:
        loaded = list(ex.map(load, manual + found))

    # real dates for versions whose source gives a placeholder (see sanitize.real_date)
    link_dates = load_json("link_dates.json", {})
    sanitize.KNOWN_DATES = link_dates
    sanitize.AI_LISTINGS = load_json("ai/listings.json", {})  # reviewed text, see scripts/ai_jobs.py
    checked = load_json("_build/checked.json", None)  # this build's link check
    before = len(links)
    full, core, gone, icons = pick_checked(loaded, len(manual), dead, checked, check_many, links)
    if len(links) > before:
        with open(path("dead_links.json"), "w") as f:
            json.dump(dict(sorted(links.items())), f, indent=1)
    best, listings, stats, news, firsts = full
    cur_best, _, cur_stats, cur_news, _ = core
    print(f"{fix_icons(best, icons, dead)} dead icons replaced")
    undated = {b for b, (_, app, _) in best.items() if app["versions"][0]["downloadURL"] in sanitize.UNDATED}
    first_seen = today().isoformat()
    link_dates = {
        u: {**link_dates.get(u, {}), "seen": link_dates.get(u, {}).get("seen") or first_seen}
        for u in sorted(sanitize.UNDATED | sanitize.REDATED)
    }
    with open(path("link_dates.json"), "w") as f:
        json.dump(link_dates, f, indent=1)
    if not best:
        sys.exit("No apps loaded; keeping the published files.")
    fix_icons(cur_best, icons, dead)

    sizes = {
        "source.json": write_json("source.json", build(best, news, OUTPUTS["source.json"], stats)),
        "curated.json": write_json(
            "curated.json", build(cur_best, cur_news, OUTPUTS["curated.json"], cur_stats)
        ),
    }
    ok = sum(1 for s in stats if not s["status"].startswith("failed"))
    now = dt.datetime.now(dt.timezone.utc)
    numbers = metrics(now, stats, best, listings, sizes, cur_best, len(found), len(dead), held)
    numbers.update(timeline(now, {b: firsts[b] for b in best if b in firsts}))
    write_build_info(stats, best, firsts, set(manual), listings, gone, undated)
    with open(path("stats.json"), "w") as f:
        json.dump(numbers, f, indent=1, ensure_ascii=False)
    history = update_history(numbers)
    render_cards(numbers, history)
    write_report(now, stats, best, listings, sizes, len(cur_best), set(manual), len(dead), held)
    print(
        f"{len(best)} apps from {ok}/{len(stats)} sources "
        f"(source.json {sizes['source.json'] // 1024} KB, "
        f"curated.json {len(cur_best)} apps, {sizes['curated.json'] // 1024} KB)"
    )


def metrics(now, stats, best, listings, sizes, cur_best, discovered, dead, held):
    """Every number worth showing, for stats.json, the README badges and the stat cards."""
    apps = [b[1] for b in best.values()]
    used = {}
    for _, _, url in best.values():
        used[url] = used.get(url, 0) + 1
    names = {s["url"]: s["name"] or s["url"].split("/")[2] for s in stats}
    categories = {}
    for a in apps:
        categories[a["category"]] = categories.get(a["category"], 0) + 1

    def updated_within(days):
        cutoff = (now - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")
        return sum(1 for a in apps if date_key(a["versionDate"]) >= cutoff)

    recent = sorted(best.values(), key=lambda b: date_key(b[1]["versionDate"]), reverse=True)[:8]
    return {
        # keys used by the README badges
        "apps": len(best),
        "curated_apps": len(cur_best),
        "sources": sum(1 for s in stats if not s["status"].startswith("failed")),
        "updated": now.strftime("%Y-%m-%d %H:%M UTC"),
        "size_mb": round(sizes["source.json"] / 1048576, 1),
        # the rest
        "built_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources_total": len(stats),
        "sources_cached": sum(1 for s in stats if s["status"].startswith("cached")),
        "sources_failed": sum(1 for s in stats if s["status"].startswith("failed")),
        "sources_discovered": discovered,
        "listings": sum(s["apps"] for s in stats),
        "duplicates": sum(1 for v in listings.values() if len(v) > 1),
        "rejected": sum(s["skipped"] for s in stats),
        "excluded": sum(s["excluded"] for s in stats),
        "dead_links_removed": dead,
        "links_on_hold": held,
        "developers": len({a["developerName"] for a in apps}),
        "updated_7d": updated_within(7),
        "updated_30d": updated_within(30),
        "curated_size_mb": round(sizes["curated.json"] / 1048576, 1),
        "categories": dict(sorted(categories.items(), key=lambda kv: -kv[1])),
        "top_sources": [
            {"name": names[u][:40], "apps": n} for u, n in sorted(used.items(), key=lambda kv: -kv[1])[:5]
        ],
        "recent": [
            {"name": a["name"][:40], "version": a["version"][:20], "date": a["versionDate"][:10]}
            for _, a, _ in recent
        ],
    }


def write_build_info(stats, best, firsts, manual=frozenset(), listings=None, gone=None, undated=()):
    """Where each app came from, when it first appeared and how many sources carry it, for the
    website (not committed). Source maintainers add what their users ask for, so an app carried
    by many independent sources is one people want."""
    names = [
        {"name": s["name"] or s["url"].split("/")[2], "url": s["url"], "core": s["url"] in manual}
        for s in stats
    ]
    index = {s["url"]: i for i, s in enumerate(stats)}
    info = {
        "sources": names,
        "origin": {bid: index[b[2]] for bid, b in best.items()},
        "first": {bid: d[:10] for bid, d in firsts.items() if bid in best},
        "carriers": {
            bid: len(urls) for bid, urls in (listings or {}).items() if bid in best and len(urls) > 1
        },
        "gone": gone or {},
        "undated": sorted(undated),  # release date unknown: not shown as new or fresh
    }
    os.makedirs(path("_build"), exist_ok=True)
    with open(path("_build/origins.json"), "w") as f:
        json.dump(info, f, ensure_ascii=False, separators=(",", ":"))
    extras = {b: v for b, v in sanitize.AI_EXTRAS.items() if b in best}
    with open(path("_build/ai_extras.json"), "w") as f:
        json.dump(extras, f, ensure_ascii=False, separators=(",", ":"))


def timeline(now, firsts, months=24):
    """Catalog growth from release dates: how many of today's apps existed at the end of each month.

    Each app counts from the earliest release date any source lists for it, so the
    curve shows how the catalog built up over time without waiting for daily history.
    """
    today = now.strftime("%Y-%m-%dT%H:%M")
    dates = sorted(min(d, today) for d in firsts.values())  # future dates from bad sources count as today
    ends, y, m = [], now.year, now.month
    for _ in range(months):
        ends.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    ends.reverse()
    points, i = [], 0
    for month in ends:
        while i < len(dates) and dates[i][:7] <= month:
            i += 1
        points.append({"month": month, "apps": i})

    def since(days):
        cutoff = (now - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")
        return sum(1 for d in dates if d >= cutoff)

    return {"timeline": points, "new_30d": since(30), "new_12m": since(365)}


def update_history(numbers, keep=365):
    """One point per day, so the stat card can draw growth over time."""
    history = load_json("history.json", [])
    point = {
        "date": numbers["built_at"][:10],
        "apps": numbers["apps"],
        "sources": numbers["sources"],
        "listings": numbers["listings"],
    }
    if history and history[-1]["date"] == point["date"]:
        history[-1] = point
    else:
        history.append(point)
    history = history[-keep:]
    with open(path("history.json"), "w") as f:
        json.dump(history, f, indent=0)
    return history


def write_report(now, stats, best, listings, sizes, curated_apps, manual, dead, held):
    won = {}
    for _, _, url in best.values():
        won[url] = won.get(url, 0) + 1
    failed = [s for s in stats if s["status"].startswith("failed")]
    cached = [s for s in stats if s["status"].startswith("cached")]
    total = sum(s["apps"] for s in stats)
    skipped = sum(s["skipped"] for s in stats)
    excluded = sum(s["excluded"] for s in stats)
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
        f"| Listings excluded (Patreon-only or AltStore PAL, cannot install here) | {excluded} |",
        f"| Dead download links held back (retested every build) | {dead} |",
        f"| Links on hold (whole host failing, kept for now) | {held} |",
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
            f"{won.get(s['url'], 0)} | {s['skipped'] + s['excluded']} | {s['newest'][:10]} | "
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
