"""Find download links in source.json that no longer work.

A link counts as dead only on a clear answer: HTTP 404/410, or a host that no
longer exists. Timeouts, 403s and server errors are ignored, because they are
often temporary or caused by bot protection. merge.py drops a version once its
link has been dead on dead_after() checks in a row.

When nearly every link on one host fails at once, the host is more likely
blocking automated checks or briefly down than missing every file, so those
links are marked host_wide and get a much longer grace period.
"""

import json
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from common import USER_AGENT, load_json, path, today

DEAD_AFTER = 2
DEAD_AFTER_HOST_WIDE = 7
HOST_WIDE_MIN_LINKS = 50
HOST_WIDE_SHARE = 0.9
DEAD_STATUS = {404, 410}


def dead_after(entry):
    """Consecutive failed checks before a link is removed."""
    return DEAD_AFTER_HOST_WIDE if entry.get("host_wide") else DEAD_AFTER


def host(url):
    return urllib.parse.urlsplit(url).netloc.lower()


def status(url):
    """'alive', 'dead' or 'unknown' for one download URL."""
    for method, extra in (("HEAD", {}), ("GET", {"Range": "bytes=0-0"})):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT, **extra})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                r.read(1)
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


def main():
    source = load_json("source.json", None)
    if not source:
        sys.exit("source.json not built yet")
    state = load_json("dead_links.json", {})
    urls = sorted({v["downloadURL"] for a in source["apps"] for v in a.get("versions", [])} | set(state))
    now = today().isoformat()
    counts = {"alive": 0, "dead": 0, "unknown": 0}
    with ThreadPoolExecutor(32) as ex:
        results = dict(ex.map(check, urls))

    per_host = {}
    for url, s in results.items():
        counts[s] += 1
        h = per_host.setdefault(host(url), [0, 0])
        h[0] += 1
        h[1] += s == "dead"
    host_wide = {
        h
        for h, (total, dead) in per_host.items()
        if dead >= HOST_WIDE_MIN_LINKS and dead / total >= HOST_WIDE_SHARE
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
