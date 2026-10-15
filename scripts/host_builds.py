"""Copy Accretion's own builds into the private Supabase "builds" bucket.

For every app in the Accretion Mods source and the Accretion app's source, download the newest
.ipa, upload it to builds/<bundle id>/<version>-<sha256>.ipa and record it in hosted_builds. Versions
already hosted are skipped. The download and source functions then serve them to account holders.

Only a build whose source entry publishes its "sha256" is copied, over https, at most MAX_BYTES, and
only if the downloaded file matches that fingerprint; nothing is ever overwritten. Releases normally
go through the upload function (hash-checked, secret key) instead, and both sources already link to
the download function, so this copier is a manual fallback (handbook issue #27).

Needs SUPABASE_ACCESS_TOKEN (the same token "Store: set up backend" uses); the service key is fetched
with it at run time and never stored. Usage: python scripts/host_builds.py
"""

import hashlib
import json
import os
import re
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
MAX_BYTES = 1536 * 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def copyable(app):
    """(bundle, version, url, sha256) for a build this copier may take, else (None, reason)"""
    bundle = app.get("bundleIdentifier")
    newest = (app.get("versions") or [{}])[0]
    version = newest.get("version") or app.get("version")
    url = newest.get("downloadURL") or app.get("downloadURL") or ""
    digest = str(newest.get("sha256") or "").lower()
    if not (bundle and version and url):
        return None, "incomplete entry"
    if "/functions/v1/download" in url:
        return None, "already served by the download function"
    if not url.startswith("https://"):
        return None, "not https"
    if not SHA256.match(digest):
        return None, "no published sha256"
    return (bundle, version, url, digest), None


def fetch_checked(url, digest, out):
    """stream url into out (an open binary file); True when size and sha256 are right"""
    h, n = hashlib.sha256(), 0
    req = urllib.request.Request(url, headers={"User-Agent": "accretion-host-builds"})
    with urllib.request.urlopen(req, timeout=900) as r:
        while chunk := r.read(1 << 20):
            n += len(chunk)
            if n > MAX_BYTES:
                return False
            h.update(chunk)
            out.write(chunk)
    return h.hexdigest() == digest


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
    keys = http(
        "GET",
        f"https://api.supabase.com/v1/projects/{ref}/api-keys",
        {"Authorization": f"Bearer {TOKEN}", "User-Agent": "accretion-host-builds"},
    )
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
            entry, reason = copyable(app)
            if not entry:
                if reason != "already served by the download function":
                    print(f"skipped {app.get('bundleIdentifier')}: {reason}")
                continue
            bundle, version, url, digest = entry
            if (bundle, version) in have:
                continue
            with tempfile.NamedTemporaryFile(suffix=".ipa") as tmp:
                if not fetch_checked(url, digest, tmp):
                    print(f"skipped {bundle} {version}: file too big or doesn't match its sha256")
                    continue
                tmp.flush()
                size = os.path.getsize(tmp.name)
                object_path = f"{bundle}/{version}-{digest}.ipa"
                upload = {**auth, "Content-Type": "application/octet-stream"}  # never overwrite
                with open(tmp.name, "rb") as f:
                    http(
                        "POST",
                        f"{base}/storage/v1/object/builds/{urllib.parse.quote(object_path)}",
                        upload,
                        f.read(),
                        timeout=900,
                    )
            row = {
                "bundle_id": bundle,
                "version": version,
                "path": object_path,
                "size": size,
                "sha256": digest,
            }
            http(
                "POST",
                f"{base}/rest/v1/hosted_builds",
                {**auth, "Content-Type": "application/json", "Prefer": "return=minimal"},
                json.dumps(row).encode(),
            )
            print(f"hosted {bundle} {version} ({size // 1024} KB)")
            added += 1
    print(f"{added} new builds hosted, {len(have)} already there")


if __name__ == "__main__":
    main()
