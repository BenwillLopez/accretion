"""Inspect old private staging uploads; --apply removes at most 100 per invocation.

Only metadata in the builds bucket is listed. Objects outside staging/ are never
eligible. The default is a dry-run; the minimum retention period is 48 hours.
"""

import argparse
import datetime as dt
import json
import re
from itertools import islice

from common import path
from copy_builds_to_s3 import Supabase, service_key
from supabase_setup import sql

MAX_LIST = 500
MAX_DELETE = 100
MIN_AGE_HOURS = 48


def old_staging(row, now, min_age_hours):
    name = row.get("name", "")
    if not isinstance(name, str) or not re.fullmatch(r"staging/[A-Za-z0-9._/-]+", name):
        return False
    if any(part in ("", ".", "..") for part in name.split("/")):
        return False
    try:
        timestamps = [
            dt.datetime.fromisoformat(row[field].replace("Z", "+00:00"))
            for field in ("created_at", "updated_at")
        ]
        if any(value.tzinfo is None for value in timestamps):
            return False
        latest = max(timestamps)
        return latest <= now - dt.timedelta(hours=min_age_hours)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def cleanup(
    storage, rows, *, now=None, apply=False, min_age_hours=MIN_AGE_HOURS, max_delete=MAX_DELETE, recheck=None
):
    if min_age_hours < MIN_AGE_HOURS or not 1 <= max_delete <= MAX_DELETE:
        raise ValueError("Keep at least 48 hours and remove at most 100 objects per run")
    if apply and (storage is None or recheck is None):
        raise ValueError("Apply requires storage access and a fresh metadata check")
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("The cleanup clock must include its time zone")
    inspected = list(islice(rows, MAX_LIST))
    names = list(dict.fromkeys(row["name"] for row in inspected if old_staging(row, now, min_age_hours)))
    removed = 0
    if apply and names:
        selected = names[:max_delete]
        # A recently refreshed upload must survive, even if the original list said it was old.
        fresh = {row["name"] for row in recheck(selected) if old_staging(row, now, min_age_hours)}
        for name in selected:
            if name in fresh:
                storage.remove(name)
                removed += 1
    return {"inspected": len(inspected), "eligible": len(names), "removed": removed}


def metadata(ref, names=None):
    restriction = ""
    if names is not None:
        if not names:
            return []
        if len(names) > MAX_DELETE or any(
            not re.fullmatch(r"staging/[A-Za-z0-9._/-]+", name) for name in names
        ):
            raise ValueError("Invalid staging metadata selection")
        restriction = " and name in (" + ",".join("'" + name + "'" for name in names) + ")"
    return (
        sql(
            ref,
            "select name, created_at, updated_at from storage.objects "
            "where bucket_id = 'builds' and name like 'staging/%'"
            + restriction
            + f" order by updated_at asc nulls last, name limit {MAX_LIST}",
        )
        or []
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Delete eligible staging objects (default: inspect only)"
    )
    parser.add_argument("--min-age-hours", type=int, default=MIN_AGE_HOURS)
    parser.add_argument("--max-delete", type=int, default=MAX_DELETE)
    args = parser.parse_args()
    if args.min_age_hours < MIN_AGE_HOURS or not 1 <= args.max_delete <= MAX_DELETE:
        parser.error("Keep at least 48 hours; --max-delete must be between 1 and 100")
    with open(path("supabase/project.json"), encoding="utf-8") as file:
        url = json.load(file)["url"].rstrip("/")
    ref = url.split("//", 1)[1].split(".", 1)[0]
    rows = metadata(ref)
    storage = Supabase(url, service_key(ref)) if args.apply else None
    report = cleanup(
        storage,
        rows,
        apply=args.apply,
        min_age_hours=args.min_age_hours,
        max_delete=args.max_delete,
        recheck=lambda names: metadata(ref, names),
    )
    mode = "Apply" if args.apply else "Dry-run"
    print(
        f"{mode}: {report['inspected']} staging metadata records inspected; "
        f"{report['eligible']} at least {args.min_age_hours} hours old; {report['removed']} removed."
    )


if __name__ == "__main__":
    main()
