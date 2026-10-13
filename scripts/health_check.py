"""Daily health check for Accretion's hosting, for the Health workflow.

1. Each download source answers for the newest Accretion build, the way the download function signs
   it: CloudFront (signed link), the Supabase copy (signed link) and the Oracle copy (nginx secure_link).
2. Supabase free-plan room: storage and database size against the free limits.
3. Dates to act on: the AWS free plan's end date.

Prints Markdown. Lines that need action start with "FAIL" or "WARN"; the workflow opens or updates
one issue when there are any.

Needs SUPABASE_ACCESS_TOKEN, CDN_DOMAIN, CDN_KEY_PAIR_ID, CDN_PRIVATE_KEY, OCI_BUILDS_HOST,
OCI_LINK_SECRET.
"""

import base64
import datetime
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from botocore.signers import CloudFrontSigner
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from common import path, version_key
from copy_builds_to_s3 import service_key
from supabase_setup import sql

ACCRETION = "io.github.getaccretion.Accretion"
STORAGE_LIMIT_MB = 1000  # Supabase free plan
DATABASE_LIMIT_MB = 500
WARN_AT = 0.7
AWS_FREE_PLAN_ENDS = datetime.date(2027, 4, 12)
WARN_DAYS = 30


def env(name):
    return os.environ.get(name, "").strip()


def quoted(p):
    return "/".join(urllib.parse.quote(part) for part in p.split("/"))


def answers(url):
    """HTTP status of a HEAD request (0 when unreachable)"""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 0


def cloudfront_link(p):
    key = serialization.load_pem_private_key(env("CDN_PRIVATE_KEY").replace("\\n", "\n").encode(), None)
    # CloudFront signed URLs use RSA with SHA-1
    signer = CloudFrontSigner(
        env("CDN_KEY_PAIR_ID"), lambda m: key.sign(m, padding.PKCS1v15(), hashes.SHA1())
    )
    expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
    return signer.generate_presigned_url(f"https://{env('CDN_DOMAIN')}/{quoted(p)}", date_less_than=expires)


def oracle_link(p):
    expires = int(time.time()) + 300
    uri = f"/builds/{p}"
    # nginx secure_link: base64url(md5("<expires><uri> <secret>")), unpadded
    raw = hashlib.md5(f"{expires}{uri} {env('OCI_LINK_SECRET')}".encode()).digest()
    digest = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"https://{env('OCI_BUILDS_HOST')}/builds/{quoted(p)}?md5={digest}&expires={expires}"


def supabase_link(url, key, p):
    req = urllib.request.Request(
        f"{url}/storage/v1/object/sign/builds/{quoted(p)}",
        method="POST",
        data=json.dumps({"expiresIn": 300}).encode(),
        headers={"Authorization": f"Bearer {key}", "apikey": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return f"{url}/storage/v1{json.load(r)['signedURL']}"


def main():
    with open(path("supabase/project.json"), encoding="utf-8") as f:
        url = json.load(f)["url"].rstrip("/")
    ref = url.split("//", 1)[1].split(".", 1)[0]
    lines = []

    rows = sql(ref, f"select version, path from public.hosted_builds where bundle_id = '{ACCRETION}'") or []
    if not rows:
        lines.append("FAIL: no hosted Accretion builds found")
    else:
        newest = max(rows, key=lambda r: version_key(r["version"]))
        p = newest["path"]
        lines.append(f"Newest Accretion build: {newest['version']} (`{p}`)\n")
        sources = []
        if env("CDN_DOMAIN") and env("CDN_PRIVATE_KEY"):
            sources.append(("CloudFront", lambda: cloudfront_link(p)))
        sources.append(("Supabase copy", lambda: supabase_link(url, service_key(ref), p)))
        if env("OCI_BUILDS_HOST") and env("OCI_LINK_SECRET"):
            sources.append(("Oracle copy", lambda: oracle_link(p)))
        for name, link in sources:
            try:
                status = answers(link())
            except Exception as e:
                status, note = 0, f" ({type(e).__name__})"
            else:
                note = ""
            ok = status == 200
            lines.append(f"{'- ok' if ok else 'FAIL'}: {name} answered {status or 'nothing'}{note}")

    usage = sql(
        ref,
        "select coalesce(round(sum((metadata->>'size')::bigint) / 1e6, 1), 0) as storage_mb,"
        " round(pg_database_size(current_database()) / 1e6, 1) as database_mb from storage.objects",
    )[0]
    for label, used, limit in (
        ("Supabase storage", float(usage["storage_mb"]), STORAGE_LIMIT_MB),
        ("Supabase database", float(usage["database_mb"]), DATABASE_LIMIT_MB),
    ):
        level = "WARN" if used >= WARN_AT * limit else "- ok"
        lines.append(f"{level}: {label} {used:.0f} MB of {limit} MB ({used / limit:.0%})")

    left = (AWS_FREE_PLAN_ENDS - datetime.datetime.now(datetime.timezone.utc).date()).days
    level = "WARN" if left <= WARN_DAYS else "- ok"
    lines.append(
        f"{level}: AWS free plan ends {AWS_FREE_PLAN_ENDS} ({left} days): upgrade or move downloads first"
    )

    print("## Accretion health\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
