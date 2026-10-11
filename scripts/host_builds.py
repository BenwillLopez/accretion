"""Copy Accretion's own builds into the private Supabase "builds" bucket.

For every app in the Accretion Mods source and the Accretion app's source, download the newest
.ipa, upload it to builds/<bundle id>/<version>.ipa and record it in hosted_builds. Versions
already hosted are skipped. The download and source functions then serve them to account holders.

Needs SUPABASE_ACCESS_TOKEN (the same token "Set up community" uses); the service key is fetched
with it at run time and never stored. Usage: python scripts/host_builds.py
"""

import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request

from common import path

SOURCES = [
    "https://raw.githubusercontent.com/AccretionMods/mods/main/mods.json",
    "https://raw.githubusercontent.com/GETAccretion/accretion-app/main/app-repo.json",
]
TOKEN = os.environ.get("SUPABASE_ACCESS_TOKEN", "").strip()


def http(method, url, headers=None, body=None, timeout=300):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        return json.loads(data) if data and r.headers.get_content_type() == "application/json" else data


def main():
    if not TOKEN:
        sys.exit("SUPABASE_ACCESS_TOKEN is not set")
    with open(path("supabase/project.json"), encoding="utf-8") as f:
        base = json.load(f)["url"].rstrip("/")
    ref = urllib.parse.urlparse(base).hostname.split(".")[0]
    keys = http("GET", f"https://api.supabase.com/v1/projects/{ref}/api-keys",
                {"Authorization": f"Bearer {TOKEN}", "User-Agent": "accretion-host-builds"})
    service = next(k["api_key"] for k in keys if k.get("name") == "service_role")
    auth = {"apikey": service, "Authorization": f"Bearer {service}"}

    hosted = http("GET", f"{base}/rest/v1/hosted_builds?select=bundle_id,version", auth)
    have = {(row["bundle_id"], row["version"]) for row in hosted}

    added = 0
    for source_url in SOURCES:
        source = http("GET", source_url, {"User-Agent": "accretion-host-builds"})
        if isinstance(source, bytes):
            source = json.loads(source)
        for app in source.get("apps", []):
            bundle = app.get("bundleIdentifier")
            newest = (app.get("versions") or [{}])[0]
            version = newest.get("version") or app.get("version")
            url = newest.get("downloadURL") or app.get("downloadURL")
            if not (bundle and version and url) or (bundle, version) in have:
                continue
            if "/functions/v1/download" in url:
                continue  # already served by the function; nothing public to copy
            with tempfile.NamedTemporaryFile(suffix=".ipa") as tmp:
                tmp.write(http("GET", url, {"User-Agent": "accretion-host-builds"}, timeout=900))
                tmp.flush()
                size = os.path.getsize(tmp.name)
                object_path = f"{bundle}/{version}.ipa"
                with open(tmp.name, "rb") as f:
                    http("POST", f"{base}/storage/v1/object/builds/{urllib.parse.quote(object_path)}",
                         {**auth, "Content-Type": "application/octet-stream", "x-upsert": "true"}, f.read(), timeout=900)
            http("POST", f"{base}/rest/v1/hosted_builds",
                 {**auth, "Content-Type": "application/json", "Prefer": "return=minimal"},
                 json.dumps({"bundle_id": bundle, "version": version, "path": object_path, "size": size}).encode())
            print(f"hosted {bundle} {version} ({size // 1024} KB)")
            added += 1
    print(f"{added} new builds hosted, {len(have)} already there")


if __name__ == "__main__":
    main()
