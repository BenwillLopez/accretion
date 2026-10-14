"""Weekly digest of the app's install reports (the "Send Report" button in install diagnostics).

Reads the last 7 days of public.install_reports through the Supabase Management API, asks an
OpenRouter model to group them by likely cause, and prints Markdown (the workflow puts it in the
job summary and a GitHub issue). Only the report fields go to the model: app version, iOS version,
install mode, stage, the app's bundle ID and the diagnostic text. Never the reporter's account ID.

Needs SUPABASE_ACCESS_TOKEN, and GEMINI_API_KEY (free, tried first; GEMINI_MODEL picks the model) or
OPENROUTER_API_KEY (DIGEST_MODEL picks the model).
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

from common import path
from supabase_setup import sql

MODEL = os.environ.get("DIGEST_MODEL", "google/gemini-2.5-flash")


def gemini(system, user, max_tokens):
    """Google Gemini (free tier, GEMINI_API_KEY): the text, or None when there's no key or it fails"""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        # the model reasons before answering, and that counts against the limit
        "generationConfig": {"maxOutputTokens": max_tokens * 4},
    }
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    for attempt in range(2):  # one retry: the free tier answers 503 when busy
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                parts = json.loads(r.read())["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip() or None
        except urllib.error.HTTPError as e:
            if e.code != 503 or attempt:
                return None
            time.sleep(10)
        except (urllib.error.URLError, KeyError, IndexError, ValueError):
            return None
    return None


MODES = {0: "Fully Local", 1: "Semi Local", 2: "Offline"}
PROMPT = """You review install problem reports from Accretion, an iOS sideloading app.
Each report has the Accretion version, iOS version, install mode, the stage the install stopped at,
the app being installed and the diagnostic text the user saw.

Write a short Markdown digest for the developer:
1. One line: how many reports, and the overall picture.
2. "Likely causes": group the reports by probable cause (for example "no network at all", "certificate
   not trusted", "iOS never connected"), with a count, the iOS/Accretion versions involved and one
   short quoted detail as evidence. Most common first.
3. "Worth checking": at most three concrete suggestions for the developer.
Plain words, no speculation beyond the evidence, under 250 words."""


def ask(reports):
    text = gemini(PROMPT, json.dumps(reports, ensure_ascii=False)[:60000], 900)
    if text:
        return text
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        return "_No AI key worked (GEMINI_API_KEY, OPENROUTER_API_KEY), so no summary. Raw counts below._"
    body = {
        "model": MODEL,
        "max_tokens": 900,
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps(reports, ensure_ascii=False)[:60000]},
        ],
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        return f"_The AI summary failed ({e.code}: {detail}). Raw counts below._"


def main():
    with open(path("supabase/project.json"), encoding="utf-8") as f:
        url = json.load(f)["url"]
    ref = url.split("//", 1)[1].split(".", 1)[0]
    rows = (
        sql(
            ref,
            "select app_version, ios, mode, stage, bundle_id, details, created_at"
            " from public.install_reports where created_at > now() - interval '7 days'"
            " order by created_at desc limit 300",
        )
        or []
    )
    print("## Install reports, last 7 days\n")
    if not rows:
        print("No reports this week.")
        return 0
    reports = [{**r, "mode": MODES.get(r["mode"], r["mode"])} for r in rows]
    print(ask(reports))
    counts = {}
    for r in reports:
        key = (r["mode"], r["stage"])
        counts[key] = counts.get(key, 0) + 1
    print("\n### Raw counts\n\n| Mode | Stage | Reports |\n|---|---|---|")
    for (mode, stage), n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"| {mode} | {stage} | {n} |")
    print(f"\n_{len(rows)} report(s); summary by `{MODEL}` via OpenRouter._")
    return 0


if __name__ == "__main__":
    sys.exit(main())
