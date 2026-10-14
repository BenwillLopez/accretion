"""Weekly digest of the app's install reports (the "Send Report" button in install diagnostics).

Reads the last 7 days of public.install_reports through the Supabase Management API, asks a free
model (scripts/llm.py) to group them by likely cause, and prints Markdown (the workflow puts it in the
job summary and a GitHub issue). Only the report fields go to the model: app version, iOS version,
install mode, stage, the app's bundle ID and the diagnostic text. Never the reporter's account ID.

Needs SUPABASE_ACCESS_TOKEN, and GEMINI_API_KEY or OPENROUTER_API_KEY (the models are in ai/models.json).
"""

import json
import sys

import llm
from common import path
from supabase_setup import sql

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
    text = llm.ask("digest", PROMPT, json.dumps(reports, ensure_ascii=False)[:60000], max_tokens=900)
    return text or "_No AI key worked (GEMINI_API_KEY, OPENROUTER_API_KEY), so no summary. Raw counts below._"


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
    print(f"\n_{len(rows)} report(s); summary by `{llm.last_model or 'no model'}`._")
    return 0


if __name__ == "__main__":
    sys.exit(main())
