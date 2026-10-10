"""Find download links and app icons in source.json that no longer work.

Runs with every build (every 6 hours). A link counts as dead only on a clear answer:
HTTP 404/410, a host that no longer exists, or a redirect to plain http (iOS refuses those
under App Transport Security). Timeouts, 403s and server errors are
ignored, because they are often temporary or caused by bot protection. merge.py drops a
version as soon as its link is dead, and the app falls back to an older working version or
another source; a link that works again comes back on the next build.

A link that returns a web page (text/html) instead of a file counts as dead too: installers
can't use it, and it's usually an error page behind a redirect.

When nearly every link on one host fails at once, the host may just be briefly down, so
those links are marked host_wide and get one more check before they are dropped. Hosts in
dead_hosts.txt (confirmed broken by hand) get no extra check, and their links only count again
once the check gets a real file from them; "no clear answer" isn't enough there.

Dropped links are never forgotten: they stay in dead_links.json, are tested again on every
build, and the version is reinstated as soon as its link works.
"""

import email.utils
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from common import USER_AGENT, load_json, path, plausible_day, read_list, today

DEAD_AFTER = 1
DEAD_AFTER_HOST_WIDE = 2
HOST_WIDE_MIN_LINKS = 50
HOST_WIDE_SHARE = 0.9
DEAD_STATUS = {404, 410}


def dead_after(entry):
    """Consecutive failed checks before a link is removed."""
    return DEAD_AFTER_HOST_WIDE if entry.get("host_wide") else DEAD_AFTER


def host(url):
    return urllib.parse.urlsplit(url).netloc.lower()


def upload_day(headers):
    """The file's Last-Modified day, used to date versions whose source date is a placeholder."""
    try:
        return email.utils.parsedate_to_datetime(headers.get("Last-Modified")).date().isoformat()
    except (TypeError, ValueError, AttributeError):
        return None


LAST_MODIFIED = {}  # url -> upload day, filled while checking


def status(url):
    """'alive', 'dead' or 'unknown' for one download URL."""
    for method, extra in (("HEAD", {}), ("GET", {"Range": "bytes=0-0"})):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT, **extra})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                r.read(1)
                if r.geturl().lower().startswith("http://"):
                    return "dead"  # ends on plain http: iOS refuses it (App Transport Security)
                if (r.headers.get("Content-Type") or "").lower().startswith("text/html"):
                    if method == "HEAD":
                        continue  # confirm with GET; some servers answer HEAD loosely
                    return "dead"  # a web page (error or landing page), not a file
                day = upload_day(r.headers)
                if day:
                    LAST_MODIFIED[url] = day
                return "alive"
        except urllib.error.HTTPError as e:
            if e.code in DEAD_STATUS:
                if method == "GET":
                    return "dead"
                continue  # some hosts answer HEAD with 404; confirm with GET
            if e.code in (405, 403, 501) and method == "HEAD":
                continue
            return "unknown"
        except urllib.error.URLError as e:
            if isinstance(e.reason, socket.gaierror):
                return "dead" if method == "GET" else "unknown_retry"
            return "unknown"
        except Exception:
            return "unknown"
    return "unknown"


def check(url):
    s = status(url)
    if s == "unknown_retry":
        s = status(url)
    return url, "unknown" if s == "unknown_retry" else s


def check_many(urls):
    """{url: 'alive' | 'dead' | 'unknown'}. On hosts in dead_hosts.txt only a real file counts."""
    confirmed = {h.lower() for h in read_list("dead_hosts.txt")}
    with ThreadPoolExecutor(32) as ex:
        results = dict(ex.map(check, sorted(urls)))
    for url, s in results.items():
        if s != "alive" and host(url) in confirmed:
            results[url] = "dead"
    return results


def main():
    source = load_json("source.json", None)
    if not source:
        sys.exit("source.json not built yet")
    state = load_json("dead_links.json", {})
    # both published lists: Accretion Core can pick a different copy of an app than the full list
    apps = source["apps"] + load_json("curated.json", {"apps": []})["apps"]
    downloads = {v["downloadURL"] for a in apps for v in a.get("versions", [])}
    own = source.get("website") or "https://getaccretion.github.io/"  # icons Accretion hosts itself
    icons = {a["iconURL"] for a in apps if a.get("iconURL") and not a["iconURL"].startswith(own)}
    urls = sorted(downloads | icons | set(state))
    now = today().isoformat()
    counts = {"alive": 0, "dead": 0, "unknown": 0}
    results = check_many(urls)
    # merge.py checks any link it is about to publish that isn't in here
    os.makedirs(path("_build"), exist_ok=True)
    with open(path("_build/checked.json"), "w") as f:
        json.dump(results, f)

    confirmed = {h.lower() for h in read_list("dead_hosts.txt")}  # no extra check for these
    per_host = {}
    for url, s in results.items():
        counts[s] += 1
        h = per_host.setdefault(host(url), [0, 0])
        h[0] += 1
        h[1] += s == "dead"
    host_wide = {
        h
        for h, (total, dead) in per_host.items()
        if dead >= HOST_WIDE_MIN_LINKS and dead / total >= HOST_WIDE_SHARE and h not in confirmed
    }

    new_state = {}
    for url, s in results.items():
        old = state.get(url, {})
        if s == "dead":
            new_state[url] = {
                "fails": old.get("fails", 0) + 1,
                "first": old.get("first", now),
                "last": now,
                "host_wide": host(url) in host_wide,
            }
        elif s == "unknown" and old:
            new_state[url] = old  # no clear answer: keep the old count, do not add to it
    with open(path("dead_links.json"), "w") as f:
        json.dump(dict(sorted(new_state.items())), f, indent=1)

    # upload days for versions whose source gives a placeholder date (see sanitize.real_date)
    dates = load_json("link_dates.json", {})
    for a in apps:
        for v in a.get("versions", []):
            if not plausible_day(v.get("date")):
                dates.setdefault(v["downloadURL"], {})
    for url, entry in dates.items():
        if url in LAST_MODIFIED and plausible_day(LAST_MODIFIED[url]):
            entry["modified"] = LAST_MODIFIED[url]
    with open(path("link_dates.json"), "w") as f:
        json.dump(dict(sorted(dates.items())), f, indent=1)

    removed = sum(1 for v in new_state.values() if v["fails"] >= dead_after(v))
    print(
        f"{len(urls)} links: {counts['alive']} alive, {counts['dead']} dead, "
        f"{counts['unknown']} no clear answer; {removed} will be removed"
    )
    for h in sorted(host_wide):
        total, dead = per_host[h]
        print(f"  host-wide failure, on hold for {DEAD_AFTER_HOST_WIDE} checks: {h} ({dead}/{total} links)")


if __name__ == "__main__":
    main()
