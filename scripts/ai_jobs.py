"""Jobs that use the free language models (scripts/llm.py). Run: python scripts/ai_jobs.py <job>

  listings --limit N   clean store text (subtitle, description, features, category, tags) -> ai/listings.json
  moderate --limit N   flag unsafe community posts for the moderators (never hides or deletes a post)
  sources  --limit N   sort newly found source URLs into real app sources and junk -> ai/sources.json
  models               test the free models on ai/eval/listings.json and keep the best four in ai/models.json

Keys: GEMINI_API_KEY, OPENROUTER_API_KEY; moderate also needs SUPABASE_ACCESS_TOKEN. Every job saves
as it goes, so a timeout keeps the progress made.
"""

import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

import llm
from common import path
from sanitize import CATEGORIES, MAX_DESCRIPTION, src_hash, text

SAVE_EVERY = 25
LISTING_SYSTEM = (
    "You write clean store listings for iOS apps from messy source data. Facts only: use what the text "
    "states and never invent features. Remove site names, domains, download-site ads, emojis and hype. "
    "Plain words, no markdown."
)
LISTING_SCHEMA = {
    "subtitle": "str",
    "description": "str",
    "features": "list",
    "category": sorted(CATEGORIES),
    "tags": "list",
}
DOMAIN_RE = re.compile(
    r"\b[a-z0-9-]+\.(?:com|net|org|io|app|xyz|me|co|top|site|cc|to|ws|dev)\b", re.IGNORECASE
)
MARGIN = 0.1  # a model must beat the current first by this much (of a 0 to 1 score) to replace it


def today():
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def load(name, default):
    try:
        with open(path(name), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save(name, data):
    os.makedirs(os.path.dirname(path(name)), exist_ok=True)
    with open(path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, sort_keys=True)  # ASCII only, so any default encoding reads it back
        f.write("\n")


def listing_prompt(app):
    return (
        "Write the store listing for this app.\n"
        "subtitle: at most 60 characters. description: plain text, facts only, at most 700 characters. "
        'features: at most 5 short chips such as "No Ads", "Cheat Menu", "Unlocked", only when the text '
        "says so. category: one of " + ", ".join(sorted(CATEGORIES)) + ". tags: at most 6 lowercase "
        "search words.\n\n"
        f"Name: {app['name']}\nDeveloper: {app.get('developerName', '')}\n"
        f"Category in source: {app['category']}\n"
        f"Description in source:\n{app.get('localizedDescription', '')[:2000]}"
    )


def short_list(values, n, lower=False):
    out = [str(w).strip()[:30] for w in values if str(w).strip()]
    return [w.lower() for w in out][:n] if lower else out[:n]


def make_listing(app):
    """The entry for ai/listings.json, or None when no model gave a valid answer"""
    data = llm.ask("listings", LISTING_SYSTEM, listing_prompt(app), LISTING_SCHEMA, max_tokens=700)
    if not data:
        return None
    return {
        "src_hash": src_hash(app["name"], app.get("localizedDescription", ""), app["category"]),
        "subtitle": text(data["subtitle"], 60),
        "description": text(data["description"], min(700, MAX_DESCRIPTION)),
        "features": short_list(data["features"], 5),
        "category": data["category"],
        "tags": short_list(data["tags"], 6, lower=True),
        "model": llm.last_model,
        "date": today(),
    }


def all_busy():
    return len(llm.busy) >= len([m for m in llm.config()["order"] if llm.usable(m)])


def listings(limit):
    apps = load("source.json", {"apps": []})["apps"]
    have = load("ai/listings.json", {})
    todo = []
    for app in apps:
        entry = have.get(app["bundleIdentifier"])
        if entry and (
            # written from this text, or already applied to the published app
            entry["src_hash"] == src_hash(app["name"], app.get("localizedDescription", ""), app["category"])
            or text(entry.get("description"), MAX_DESCRIPTION) == app.get("localizedDescription")
        ):
            continue
        todo.append(app)
    done = skipped = 0
    for app in todo[:limit]:
        entry = make_listing(app)
        if entry:
            have[app["bundleIdentifier"]] = entry
            done += 1
            if done % SAVE_EVERY == 0:
                save("ai/listings.json", have)
        else:
            skipped += 1
            if all_busy():
                break  # every usable model is busy: stop and keep what we have
    save("ai/listings.json", have)
    left = len(todo) - done - skipped
    print(f"listings: {done} done, {skipped} skipped, {left} left, {len(llm.busy)} model(s) busy")
    return 0


def rest(url, key, route, body=None, method="GET"):
    req = urllib.request.Request(
        f"{url}/rest/v1/{route}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def moderate(limit):
    from copy_builds_to_s3 import service_key  # needs boto3 installed; the workflow does that

    url = load("supabase/project.json", {})["url"]
    ref = url.split("//", 1)[1].split(".", 1)[0]
    key = service_key(ref)
    state = load("ai/state.json", {})
    last = int(state.get("moderate_last_id", 0))
    posts = rest(url, key, f"posts?id=gt.{last}&order=id.asc&limit={limit}&select=id,body,hidden") or []
    flagged = 0
    # NVIDIA's safety model answers in its own text format, not JSON: "User Safety: unsafe" and a
    # "Safety Categories: ..." line for unsafe posts, and an empty reply for safe ones. It doesn't
    # judge spam, so a second, ordinary model checks that.
    spam_system = (
        "You check posts in a community for an iOS app store. Spam means advertising unrelated "
        "products or services, follower or money schemes, repeated promotional links, or scam offers. "
        "Questions, bug reports, opinions and links to app sources or apps are not spam."
    )
    for post in posts:
        body = post["body"][:2000]
        verdict = llm.ask("moderate", "", body, max_tokens=120)
        if verdict is None and llm.busy:
            break  # the moderation model is busy: pick this post up on the next run
        label = ""
        if verdict and re.search(r"user safety:\s*unsafe", verdict, re.I):
            cats = re.search(r"safety categories:\s*(.+)", verdict, re.I)
            label = cats.group(1) if cats else "unsafe"
        else:
            spam = llm.ask("spam", spam_system, body, {"spam": "bool", "reason": "str"}, max_tokens=80)
            if spam and spam["spam"]:
                label = f"Spam: {spam['reason']}"
        last = post["id"]
        if label and not post.get("hidden"):
            label = re.sub(r"\s+", " ", label).strip()[:60]
            # the database function files one open report per post, with no human reporter
            rest(url, key, "rpc/ai_report", {"p_post_id": post["id"], "p_label": label}, "POST")
            flagged += 1
    state["moderate_last_id"] = last
    save("ai/state.json", state)
    print(f"moderate: {len(posts)} post(s) read, {flagged} flagged, last id {last}")
    return 0


def sources(limit):
    found = load("discovered.json", {})
    have = load("ai/sources.json", {})
    system = (
        "You decide whether a URL is a real AltStore or SideStore app source (a JSON catalogue of iOS apps "
        "from a developer or community) or junk (spam, a mirror farm, a repack or ad site, a single stray "
        "file, a site that is not an app source)."
    )
    done = 0
    for url, info in found.items():
        if url in have:
            continue
        if done >= limit:
            break
        user = f"URL: {url}\nName: {info.get('name')}\nApps listed: {info.get('apps')}"
        data = llm.ask("sources", system, user, {"real": "bool", "reason": "str"}, max_tokens=150)
        if data is None:
            if all_busy():
                break
            continue
        have[url] = {"real": data["real"], "reason": data["reason"][:200], "model": llm.last_model}
        done += 1
    save("ai/sources.json", have)
    real = sum(1 for v in have.values() if v["real"])
    print(f"sources: {done} classified, {real} real of {len(have)} (review ai/sources.json)")
    return 0


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def free_models():
    """Candidate model specs: free OpenRouter text models and Gemini flash/pro models"""
    out = []
    try:
        for m in get_json("https://openrouter.ai/api/v1/models")["data"]:
            price, arch = m.get("pricing", {}), m.get("architecture", {})
            if (
                str(price.get("prompt")) == "0"
                and str(price.get("completion")) == "0"
                and m["id"].endswith(":free")
                and "text" in arch.get("output_modalities", ["text"])
                and "safety" not in m["id"]
            ):
                out.append(f"openrouter:{m['id']}")
    except (urllib.error.URLError, ValueError, KeyError) as e:
        print(f"models: OpenRouter list failed ({type(e).__name__})", file=sys.stderr)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        try:
            listed = get_json(
                "https://generativelanguage.googleapis.com/v1beta/models", {"x-goog-api-key": key}
            )["models"]
            for m in listed:
                name = m["name"].removeprefix("models/")
                if ("flash" in name or "pro" in name) and "generateContent" in m.get(
                    "supportedGenerationMethods", []
                ):
                    out.append(f"gemini:{name}")
        except (urllib.error.URLError, ValueError, KeyError) as e:
            print(f"models: Gemini list failed ({type(e).__name__})", file=sys.stderr)
    return out


def score(spec, items):
    """0 to 1: per item, 1 point for valid JSON, 1 for the right category, 1 for no domain left"""
    points = 0
    llm.busy.clear()
    real_config = llm.config
    llm.config = lambda: {"order": [spec], "moderation": ""}
    try:
        for item in items:
            app = {
                "name": item["name"],
                "developerName": "",
                "category": "other",
                "localizedDescription": item["description"],
            }
            data = llm.ask("eval", LISTING_SYSTEM, listing_prompt(app), LISTING_SCHEMA, max_tokens=700)
            if data:
                points += 1 + (data["category"] == item["expected_category"])
                points += not DOMAIN_RE.search(data["description"])
    finally:
        llm.config = real_config
    return round(points / (3 * len(items)), 3)


def models():
    items = load("ai/eval/listings.json", [])
    if not items:
        raise SystemExit("ai/eval/listings.json is empty")
    cfg = llm.config()
    current = [m for m in cfg["order"] if llm.usable(m)]
    found = [m for m in free_models() if m not in current and llm.usable(m)]
    candidates = (current + found)[:8]
    ranking = {spec: score(spec, items) for spec in candidates}
    ordered = sorted(ranking, key=lambda s: -ranking[s])
    save("ai/models_ranking.json", {"date": today(), "scores": ranking})
    for spec in ordered:
        print(f"{ranking[spec]:.3f}  {spec}")
    first = cfg["order"][0] if cfg["order"] else None
    if (
        ordered
        and first in ranking
        and ordered[0] != first
        and ranking[ordered[0]] >= ranking[first] + MARGIN
    ):
        cfg["order"] = ordered[:4]
        save("ai/models.json", cfg)
        print(f"models: new order {cfg['order']}")
        print("CHANGED")
    else:
        print("models: order unchanged")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("job", choices=["listings", "moderate", "sources", "models"])
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    if args.job == "models":
        return models()
    default = {"listings": 150, "moderate": 200, "sources": 50}[args.job]
    return {"listings": listings, "moderate": moderate, "sources": sources}[args.job](args.limit or default)


if __name__ == "__main__":
    sys.exit(main())
