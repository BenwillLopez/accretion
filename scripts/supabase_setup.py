"""Create and configure the Accretion Supabase project through the Management API.

Run by .github/workflows/community-setup.yml. Needs SUPABASE_ACCESS_TOKEN, a personal access
token from supabase.com/dashboard/account/tokens. Safe to run again: it reuses the project,
re-applies supabase/schema.sql (which only updates what changed) and refreshes settings.

Steps:
  1. find or create the project (name PROJECT_NAME, region SUPABASE_REGION)
  2. wait until it is healthy
  3. apply supabase/schema.sql
  4. set auth URLs to the store's address, keep email confirmation on
  5. write the public URL and anon key to supabase/project.json (both are public)
  6. optionally make ADMIN_USERNAME an admin
"""

import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.request

from common import path

API = "https://api.supabase.com/v1"
TOKEN = os.environ.get("SUPABASE_ACCESS_TOKEN", "").strip()
NAME = os.environ.get("PROJECT_NAME", "accretion").strip() or "accretion"
REGION = os.environ.get("SUPABASE_REGION", "us-east-1").strip() or "us-east-1"
ORG = os.environ.get("SUPABASE_ORG", "").strip()
SITE_URL = os.environ.get("SITE_URL", "").strip()
ADMIN = os.environ.get("ADMIN_USERNAME", "").strip()


def call(method, route, body=None, timeout=120):
    req = urllib.request.Request(
        f"{API}{route}",
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "accretion-setup",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise SystemExit(f"Supabase API {method} {route} failed ({e.code}): {detail}") from None


def sql(ref, query):
    return call("POST", f"/projects/{ref}/database/query", {"query": query}, timeout=300)


def log(msg):
    print(msg, flush=True)


def find_or_create_project():
    projects = call("GET", "/projects") or []
    for p in projects:
        if p.get("name") == NAME:
            log(f"Using existing project '{NAME}' ({p['id']}, {p.get('region')})")
            return p["id"]
    orgs = call("GET", "/organizations") or []
    if not orgs:
        raise SystemExit("No Supabase organization found. Open supabase.com/dashboard once to create one.")
    org = (
        next((o for o in orgs if ORG in (o.get("id"), o.get("slug"), o.get("name"))), None)
        if ORG
        else orgs[0]
    )
    if not org:
        raise SystemExit(
            f"Organization '{ORG}' not found. Yours: {', '.join(o.get('name', '?') for o in orgs)}"
        )
    log(f"Creating project '{NAME}' in {REGION} under organization '{org.get('name')}'")
    created = call(
        "POST",
        "/projects",
        {
            "name": NAME,
            "organization_id": org["id"],
            "region": REGION,
            # never needed by the store; reset it in the dashboard if you ever want direct DB access
            "db_pass": secrets.token_urlsafe(32),
        },
    )
    return created["id"]


def wait_healthy(ref, minutes=15):
    deadline = time.time() + minutes * 60
    status = ""
    while time.time() < deadline:
        status = (call("GET", f"/projects/{ref}") or {}).get("status", "")
        if status == "ACTIVE_HEALTHY":
            log("Project is ready")
            return
        log(f"Waiting for project to start ({status or 'unknown'})…")
        time.sleep(15)
    raise SystemExit(f"Project did not become ready in {minutes} minutes (last status: {status})")


def anon_key(ref):
    keys = call("GET", f"/projects/{ref}/api-keys") or []
    for k in keys:
        if k.get("name") == "anon" and k.get("api_key"):
            return k["api_key"]
    for k in keys:  # newer projects: publishable keys replace anon
        if k.get("type") == "publishable" and k.get("api_key"):
            return k["api_key"]
    raise SystemExit("Couldn't find the project's anon/publishable key")


def main():
    if not TOKEN:
        raise SystemExit(
            "SUPABASE_ACCESS_TOKEN is not set. Create one at supabase.com/dashboard/account/tokens "
            "and add it as a repository secret."
        )
    ref = find_or_create_project()
    wait_healthy(ref)

    with open(path("supabase/schema.sql")) as f:
        sql(ref, f.read())
    log("Database tables, rules and functions are in place")

    if SITE_URL:
        call(
            "PATCH",
            f"/projects/{ref}/config/auth",
            {"site_url": SITE_URL, "uri_allow_list": f"{SITE_URL},{SITE_URL}**", "mailer_autoconfirm": False},
        )
        log(f"Sign-in links point to {SITE_URL}")

    url = f"https://{ref}.supabase.co"
    key = anon_key(ref)
    with open(path("supabase/project.json"), "w") as f:
        json.dump({"url": url, "anonKey": key}, f, indent=1)
        f.write("\n")
    log(f"Saved public settings for {url}")

    if ADMIN:
        if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", ADMIN):
            raise SystemExit("ADMIN_USERNAME must be 3-20 letters, numbers or underscores")
        rows = sql(
            ref,
            f"update public.profiles set role = 'admin' where username = '{ADMIN}' returning username, role;",
        )
        if rows:
            log(f"@{ADMIN} is now an admin")
        else:
            log(f"No account named @{ADMIN} yet. Sign up on the store first, then run this again.")
            sys.exit(1)


if __name__ == "__main__":
    main()
