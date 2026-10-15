"""Copy every app version's file link from source.json into the private upstream_links table.

The download function reads that table to send other sources' apps through the download proxy
(workers/download-proxy), so the links don't have to be public for downloads to work. Run by
publish.yml after merge.py; needs SUPABASE_ACCESS_TOKEN. Without it, or on any API error, it says
so and exits 0: the store still publishes, downloads keep the previous links.

Rows the build no longer has (apps or versions that left the store) are removed, unless the new
list is much smaller than what is stored (a broken build must not wipe the table).
"""

import json
import os
import re
import secrets
import sys

from common import path

BUNDLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
BATCH = 2000
KEEP_IF_SHRINKS_BELOW = 0.5  # a list under half the stored size is treated as a broken build


def rows_from(source):
    seen, rows = set(), []
    for app in source.get("apps", []):
        bid = app.get("bundleIdentifier", "")
        if not BUNDLE.match(bid) or len(bid) > 200:
            continue
        for v in app.get("versions", []):
            version, url = str(v.get("version", ""))[:60], v.get("downloadURL", "")
            if not version or not isinstance(url, str) or not url.startswith("https://") or len(url) > 2000:
                continue
            if (bid, version) in seen:
                continue
            seen.add((bid, version))
            rows.append(
                {"bundle_id": bid, "version": version, "url": url, "name": (app.get("name") or "")[:200]}
            )
    return rows


def literal(data):
    """data as a dollar-quoted SQL string whose tag can't occur inside it"""
    text = json.dumps(data, ensure_ascii=False)
    while True:
        tag = f"$j{secrets.token_hex(4)}$"
        if tag not in text:
            return f"{tag}{text}{tag}"


def main():
    if not os.environ.get("SUPABASE_ACCESS_TOKEN", "").strip():
        print("SUPABASE_ACCESS_TOKEN is not set: private download links not updated")
        return 0
    from supabase_setup import sql  # reads the token at import

    with open(path("supabase/project.json"), encoding="utf-8") as f:
        ref = json.load(f)["url"].split("//", 1)[1].split(".", 1)[0]
    with open(path("source.json"), encoding="utf-8") as f:
        rows = rows_from(json.load(f))

    try:
        stored = (sql(ref, "select count(*) as n from public.upstream_links") or [{"n": 0}])[0]["n"]
        stamp = (sql(ref, "select now()::text as t") or [{}])[0]["t"]
        for i in range(0, len(rows), BATCH):
            sql(
                ref,
                "insert into public.upstream_links (bundle_id, version, url, name, seen_at) "
                f"select bundle_id, version, url, nullif(name, ''), '{stamp}'::timestamptz "
                f"from jsonb_to_recordset({literal(rows[i : i + BATCH])}::jsonb) "
                "as x(bundle_id text, version text, url text, name text) "
                "on conflict (bundle_id, version) do update "
                "set url = excluded.url, name = excluded.name, seen_at = excluded.seen_at",
            )
        removed = "skipped (the new list is much smaller than the stored one)"
        if rows and len(rows) >= stored * KEEP_IF_SHRINKS_BELOW:
            sql(ref, f"delete from public.upstream_links where seen_at < '{stamp}'::timestamptz")
            removed = "done"
    except SystemExit as e:  # supabase_setup reports API failures this way, without response bodies
        print(f"Private download links not updated: {e}")
        return 0
    print(f"Private download links: {len(rows)} versions saved (was {stored}); removing old ones: {removed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
