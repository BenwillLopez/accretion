"""Copy Accretion's own builds into the private Supabase "builds" bucket.

A manual fallback for a build the release workflows failed to upload. For every app in the
Accretion Mods source and the Accretion app's source, download the newest .ipa, check it against
the sha256 and size the source declares, upload it to builds/<bundle id>/<version>-<sha256>.ipa and
record it in hosted_builds with that fingerprint, so the app can verify what it downloads, exactly
as the upload function does. Versions already hosted are skipped. So is a listing without a
sha256, with a link that isn't https, or whose file doesn't match: a build nobody fingerprinted is
never served as Accretion's own.

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
SHA256 = re.compile(r"^[0-9a-f]{64}$")
BUNDLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,199}$")
VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")


def http(method, url, headers=None, body=None, timeout=300):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        return json.loads(data) if data and r.headers.get_content_type() == "application/json" else data


def listing(app):
    """The newest version of an app as (build, reason): build is a dict with bundle, version, url,
    sha256 and size when the listing can be hosted, else None and the reason it can't."""
    bundle = app.get("bundleIdentifier")
    newest = (app.get("versions") or [{}])[0]
    version = newest.get("version") or app.get("version")
    url = newest.get("downloadURL") or app.get("downloadURL")
    sha256 = str(newest.get("sha256") or app.get("sha256") or "").lower()
    size = newest.get("size") if "size" in newest else app.get("size")
    if not (isinstance(bundle, str) and BUNDLE.match(bundle)):
        return None, "no usable bundle id"
    if not (isinstance(version, str) and VERSION.match(version)):
        return None, "no usable version"
    if not isinstance(url, str) or urllib.parse.urlparse(url).scheme != "https":
        return None, "download link isn't https"
    if "/functions/v1/download" in url:
        return None, "already served by the download function"
    if not SHA256.match(sha256):
        return None, "no sha256 in the source; a build nobody fingerprinted is not hosted"
    if size is not None and (not isinstance(size, int) or isinstance(size, bool) or size <= 0):
        return None, "size isn't a positive number"
    return {"bundle": bundle, "version": version, "url": url, "sha256": sha256, "size": size}, ""


def verify(data, build):
    """The data's fingerprint, if it is the build the source declared; raises otherwise."""
    if build["size"] is not None and len(data) != build["size"]:
        raise ValueError(f"downloaded {len(data)} bytes, the source says {build['size']}")
    actual = hashlib.sha256(data).hexdigest()
    if actual != build["sha256"]:
        raise ValueError("downloaded file doesn't match the sha256 the source declares")
    return actual


def object_path(build):
    return f"{build['bundle']}/{build['version']}-{build['sha256']}.ipa"


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
    skipped = 0
    for source_url in SOURCES:
        source = http("GET", source_url, {"User-Agent": "accretion-host-builds"})
        if isinstance(source, bytes):
            source = json.loads(source)
        for app in source.get("apps", []):
            build, reason = listing(app)
            if build is None:
                if reason != "already served by the download function":
                    print(f"skipped {app.get('bundleIdentifier')}: {reason}")
                    skipped += 1
                continue
            if (build["bundle"], build["version"]) in have:
                continue
            with tempfile.NamedTemporaryFile(suffix=".ipa") as tmp:
                data = http("GET", build["url"], {"User-Agent": "accretion-host-builds"}, timeout=900)
                try:
                    verify(data, build)
                except ValueError as error:
                    print(f"skipped {build['bundle']} {build['version']}: {error}")
                    skipped += 1
                    continue
                tmp.write(data)
                tmp.flush()
                size = os.path.getsize(tmp.name)
                # the same name the upload function gives a finished build; never overwrite one
                upload = {**auth, "Content-Type": "application/octet-stream"}
                with open(tmp.name, "rb") as f:
                    http(
                        "POST",
                        f"{base}/storage/v1/object/builds/{urllib.parse.quote(object_path(build))}",
                        upload,
                        f.read(),
                        timeout=900,
                    )
            row = {
                "bundle_id": build["bundle"],
                "version": build["version"],
                "path": object_path(build),
                "size": size,
                "sha256": build["sha256"],
            }
            http(
                "POST",
                f"{base}/rest/v1/hosted_builds",
                {**auth, "Content-Type": "application/json", "Prefer": "return=minimal"},
                json.dumps(row).encode(),
            )
            print(f"hosted {build['bundle']} {build['version']} ({size // 1024} KB)")
            added += 1
    print(f"{added} new builds hosted, {skipped} skipped, {len(have)} already there")


if __name__ == "__main__":
    main()
