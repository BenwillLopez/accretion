"""Find AltStore/SideStore sources automatically and write discovered.txt.

Candidates come from:
  * link lists and blog pages ("pages" in discover.json)
  * JSON files in known GitHub repos and repos tagged with source topics
  * GitHub code search (only when GH_SEARCH_TOKEN, a personal token, is set)

Every candidate is downloaded and kept only if it is a real source. Results
are remembered in discovered.json; a source that stops working is dropped
after `forget_after_days`.
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from common import fetch_bytes, fetch_source, is_blocked, path, read_list

CONFIG = json.load(open(path("discover.json")))
API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
SEARCH_TOKEN = os.environ.get("GH_SEARCH_TOKEN", "")

SKIP_HOSTS = ("reddit.com", "discord.", "twitter.com", "x.com", "t.me", "youtube.",
              "web.archive.org", "awesome.re", "apps.apple.com", "testflight.apple.com",
              "shields.io", "img.shields", "patreon.", "ko-fi.", "buymeacoffee.", "paypal.")
SKIP_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ipa", ".zip", ".deb",
            ".css", ".js", ".mp4", ".pdf", ".plist")
SKIP_FILES = ("package.json", "package-lock.json", "tsconfig", "composer.json", "manifest.json",
              "renovate.json", ".eslintrc", "vercel.json", "netlify.json", "firebase.json",
              "launch.json", "settings.json", "tasks.json", "appsettings", "contents.json",
              "info.json", "app.json5")


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def gh(url, token=TOKEN):
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    raw, _ = fetch_bytes(url, timeout=60, headers=headers)
    return json.loads(raw)


def clean_url(u):
    u = u.strip().strip("<>\"'`").rstrip(".,;:!?)]}*_")
    if not re.match(r"https?://", u):
        u = "https://" + u
    p = urllib.parse.urlsplit(u)
    host = p.netloc.lower()
    # github.com/owner/repo/blob|raw/branch/path -> raw.githubusercontent.com
    m = re.match(r"/([^/]+)/([^/]+)/(?:blob|raw)/(.+)", p.path)
    if host in ("github.com", "www.github.com") and m:
        owner, repo, rest = m.groups()
        rest = rest.replace("refs/heads/", "", 1)
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{rest}"
    return urllib.parse.urlunsplit((p.scheme, host, p.path, p.query, ""))


def plausible(u):
    p = urllib.parse.urlsplit(u)
    host, low = p.netloc, p.path.lower()
    if not host or "." not in host or any(h in host for h in SKIP_HOSTS):
        return False
    if low.endswith(SKIP_EXT):
        return False
    if host in ("github.com", "www.github.com", "gist.github.com"):
        return False  # repo pages, not files; JSON files there were rewritten to raw above
    return True


def urls_in_text(text):
    found = set(re.findall(r"https?://[^\s<>\"'`)\]]+", text))
    # markdown links without a scheme: [name](example.com/apps.json)
    found |= {t for t in re.findall(r"\]\(([^)\s]+)\)", text) if "." in t and not t.startswith("#")}
    return {clean_url(u) for u in found}


def from_pages():
    out = set()
    for page in CONFIG.get("pages", []):
        try:
            raw, _ = fetch_bytes(page, timeout=45)
            urls = {u for u in urls_in_text(raw.decode("utf-8", "replace")) if plausible(u)}
            log(f"page  {len(urls):4d} links  {page}")
            out |= urls
        except Exception as e:
            log(f"page  FAILED ({type(e).__name__})  {page}")
    return out


def json_files_in_repo(full_name, branch=None):
    try:
        if not branch:
            branch = gh(f"{API}/repos/{full_name}")["default_branch"]
        tree = gh(f"{API}/repos/{full_name}/git/trees/{urllib.parse.quote(branch)}?recursive=1")
    except Exception as e:
        log(f"repo  FAILED ({type(e).__name__})  {full_name}")
        return set()
    files = []
    for item in tree.get("tree", []):
        p = item.get("path", "")
        name = p.rsplit("/", 1)[-1].lower()
        if item.get("type") != "blob" or not name.endswith(".json"):
            continue
        if any(s in name for s in SKIP_FILES) or "node_modules/" in p or p.startswith(".vscode/"):
            continue
        if item.get("size", 0) < 200:
            continue
        # files that look like sources first
        score = sum(k in name for k in ("app", "source", "repo", "alt", "store", "side", "ipa"))
        files.append((-score, p.count("/"), p))
    files.sort()
    keep = files[: CONFIG.get("max_files_per_repo", 12)]
    return {f"https://raw.githubusercontent.com/{full_name}/{branch}/{urllib.parse.quote(p)}"
            for _, _, p in keep}


def from_github():
    repos = {}
    for full in CONFIG.get("github_repos", []):
        repos[full] = None
    for topic in CONFIG.get("github_topics", []):
        n = CONFIG.get("max_repos_per_topic", 100)
        try:
            res = gh(f"{API}/search/repositories?q=topic:{urllib.parse.quote(topic)}"
                     f"&sort=updated&order=desc&per_page={min(n, 100)}")
            items = res.get("items", [])
            log(f"topic {len(items):4d} repos  {topic}")
            for r in items:
                if not r.get("archived"):
                    repos[r["full_name"]] = r.get("default_branch")
        except Exception as e:
            log(f"topic FAILED ({type(e).__name__})  {topic}")
    out = set()
    if SEARCH_TOKEN:
        for q in CONFIG.get("github_code_queries", []):
            try:
                res = gh(f"{API}/search/code?q={urllib.parse.quote(q)}&per_page=100", SEARCH_TOKEN)
                items = res.get("items", [])
                log(f"code  {len(items):4d} files  {q}")
                for it in items:
                    # scan the whole repo on its branch, so we always read the latest file
                    repos.setdefault(it["repository"]["full_name"], None)
            except Exception as e:
                log(f"code  FAILED ({type(e).__name__})  {q}")
    else:
        log("code  skipped (set GH_SEARCH_TOKEN to enable GitHub code search)")
    with ThreadPoolExecutor(8) as ex:
        for files in ex.map(lambda kv: json_files_in_repo(*kv), repos.items()):
            out |= files
    return out


def check(url):
    try:
        data, final_url, size = fetch_source(url, timeout=45)
        apps = [a for a in data["apps"] if isinstance(a, dict) and a.get("bundleIdentifier")]
        digest = hashlib.sha1("\n".join(sorted(a["bundleIdentifier"] for a in apps)).encode()).hexdigest()
        return url, {"ok": True, "name": str(data.get("name", ""))[:80], "apps": len(apps),
                     "final_url": final_url, "fingerprint": digest, "size": size}
    except Exception as e:
        return url, {"ok": False, "error": f"{type(e).__name__}: {str(e)[:80]}"}


def main():
    blocklist = read_list("blocklist.txt")
    manual = set(read_list("sources.txt"))
    try:
        state = json.load(open(path("discovered.json")))
    except FileNotFoundError:
        state = {}

    candidates = from_pages() | from_github() | set(state)
    candidates = {u for u in candidates if u not in manual and not is_blocked(u, blocklist)}
    log(f"\nchecking {len(candidates)} candidates")

    with ThreadPoolExecutor(24) as ex:
        results = dict(ex.map(check, sorted(candidates)))

    today = dt.date.today().isoformat()
    forget = (dt.date.today() - dt.timedelta(days=CONFIG.get("forget_after_days", 30))).isoformat()
    # fingerprints of sources already covered, so mirrors and short links are not added twice
    seen_finals, seen_prints = set(manual), set()
    new_state = {}
    # bigger sources first, so a mirror loses to the original it copies
    order = sorted(results, key=lambda u: (-(results[u].get("apps") or 0), len(u), u))
    for u in order:
        r, old = results[u], state.get(u, {})
        if r["ok"]:
            if r["final_url"] in seen_finals or r["fingerprint"] in seen_prints:
                continue
            seen_finals.add(r["final_url"])
            seen_prints.add(r["fingerprint"])
            new_state[u] = {"name": r["name"], "apps": r["apps"], "size": r["size"],
                            "first_seen": old.get("first_seen", today), "last_ok": today}
        elif old and old.get("last_ok", "") >= forget:
            new_state[u] = {**old, "last_error": r["error"]}

    with open(path("discovered.json"), "w") as f:
        json.dump(dict(sorted(new_state.items())), f, indent=1, ensure_ascii=False)
    with open(path("discovered.txt"), "w") as f:
        f.write("# Written by discover.py. Edit sources.txt or blocklist.txt instead.\n")
        for u in sorted(new_state):
            f.write(f"{u}  # {new_state[u]['name'][:50]} ({new_state[u]['apps']} apps)\n")

    added = [u for u in new_state if u not in state]
    dropped = [u for u in state if u not in new_state]
    log(f"\n{len(new_state)} discovered sources ({len(added)} new, {len(dropped)} dropped)")
    for u in added:
        log(f"  + {u}")
    for u in dropped:
        log(f"  - {u}")


if __name__ == "__main__":
    main()
