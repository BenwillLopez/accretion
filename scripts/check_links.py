"""Find download links in source.json that no longer work.

A link counts as dead only on a clear answer: HTTP 404/410, or a host that no
longer exists. Timeouts, 403s and server errors are ignored, because they are
often temporary or caused by bot protection. merge.py drops a version once its
link has been dead on DEAD_AFTER checks in a row.
"""

import json
import socket
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from common import USER_AGENT, load_json, path, today

DEAD_AFTER = 2
DEAD_STATUS = {404, 410}


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
    new_state = {}
    with ThreadPoolExecutor(32) as ex:
        for url, s in ex.map(check, urls):
            counts[s] += 1
            old = state.get(url, {})
            if s == "dead":
                new_state[url] = {
                    "fails": old.get("fails", 0) + 1,
                    "first": old.get("first", now),
                    "last": now,
                }
            elif s == "unknown" and old:
                new_state[url] = old  # no clear answer: keep the old count, do not add to it
    with open(path("dead_links.json"), "w") as f:
        json.dump(dict(sorted(new_state.items())), f, indent=1)
    removed = sum(1 for v in new_state.values() if v["fails"] >= DEAD_AFTER)
    print(
        f"{len(urls)} links: {counts['alive']} alive, {counts['dead']} dead, "
        f"{counts['unknown']} no clear answer; {removed} will be removed"
    )


if __name__ == "__main__":
    main()
