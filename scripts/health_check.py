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
import re
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


ADMOB_PUBLISHER = "pub-4500603236648893"


def admob_week():
    """AdMob totals for the last 7 days (requests, fill, impressions, earnings), read-only.
    Needs ADMOB_CLIENT_ID, ADMOB_CLIENT_SECRET and ADMOB_REFRESH_TOKEN (handbook INVENTORY.yaml)."""
    cid, secret, refresh = (env(n) for n in ("ADMOB_CLIENT_ID", "ADMOB_CLIENT_SECRET", "ADMOB_REFRESH_TOKEN"))
    if not (cid and secret and refresh):
        return "WARN: AdMob not checked (ADMOB_* configuration is incomplete)"
    try:
        grant = {"client_id": cid, "client_secret": secret, "refresh_token": refresh}
        body = urllib.parse.urlencode({**grant, "grant_type": "refresh_token"}).encode()
        with urllib.request.urlopen("https://oauth2.googleapis.com/token", data=body, timeout=30) as r:
            token = json.load(r)["access_token"]
        end = datetime.datetime.now(datetime.timezone.utc).date()
        start = end - datetime.timedelta(days=6)
        day = lambda d: {"year": d.year, "month": d.month, "day": d.day}  # noqa: E731
        spec = {
            "reportSpec": {
                "dateRange": {"startDate": day(start), "endDate": day(end)},
                "metrics": ["AD_REQUESTS", "MATCHED_REQUESTS", "IMPRESSIONS", "ESTIMATED_EARNINGS"],
            }
        }
        req = urllib.request.Request(
            f"https://admob.googleapis.com/v1/accounts/{ADMOB_PUBLISHER}/networkReport:generate",
            data=json.dumps(spec).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            parts = json.load(r)
    except (urllib.error.URLError, KeyError, ValueError, OSError) as e:
        # an expired or revoked refresh token shows here: redo the one-time consent (PLAYBOOK)
        return f"WARN: AdMob report failed ({type(e).__name__}); the AdMob sign-in may need renewing"
    values = {}
    for part in parts:
        for name, v in (part.get("row", {}).get("metricValues") or {}).items():
            values[name] = values.get(name, 0) + int(v.get("integerValue") or v.get("microsValue") or 0)
    requests_, matched = values.get("AD_REQUESTS", 0), values.get("MATCHED_REQUESTS", 0)
    fill = f"{matched / requests_:.0%}" if requests_ else "n/a"
    earnings = values.get("ESTIMATED_EARNINGS", 0) / 1e6
    return (
        f"- ok: AdMob last 7 days: {requests_} ad requests, {fill} filled, "
        f"{values.get('IMPRESSIONS', 0)} impressions, ${earnings:.2f} estimated"
    )


def google_sign_in(url):
    """Google sign-in reaches Google's account page (not "Access blocked", e.g. redirect_uri_mismatch
    when the OAuth client in Google Cloud loses Supabase's callback address)"""
    start = f"{url}/auth/v1/authorize?provider=google&redirect_to=https://getaccretion.github.io/"
    req = urllib.request.Request(start, headers={"User-Agent": "Mozilla/5.0 (accretion health check)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            final, body = r.geturl(), r.read(200000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        final, body = e.geturl() or "", e.read(200000).decode("utf-8", "replace")
    except OSError as e:
        return f"FAIL: Google sign-in unreachable ({type(e).__name__})"
    if "oauth/error" in final or "redirect_uri_mismatch" in body or "invalid_client" in body:
        return "FAIL: Google sign-in is blocked by Google (check the OAuth client's redirect URIs)"
    if "accounts.google.com" not in final:
        host = urllib.parse.urlsplit(final).netloc or "no answer"
        return f"FAIL: Google sign-in didn't reach Google ({host})"
    return "- ok: Google sign-in reaches Google's account page"


def main():
    with open(path("supabase/project.json"), encoding="utf-8") as f:
        url = json.load(f)["url"].rstrip("/")
    ref = url.split("//", 1)[1].split(".", 1)[0]
    lines = []

    rows = sql(ref, f"select version, path from public.hosted_builds where bundle_id = '{ACCRETION}'") or []
    rows = [row for row in rows if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", row["version"])]
    if not rows:
        lines.append("FAIL: no hosted Accretion builds found")
    else:
        newest = max(rows, key=lambda r: version_key(r["version"]))
        p = newest["path"]
        lines.append(f"Newest Accretion build: {newest['version']} (`{p}`)\n")
        sources = []
        if all(env(name) for name in ("CDN_DOMAIN", "CDN_KEY_PAIR_ID", "CDN_PRIVATE_KEY")):
            sources.append(("CloudFront", lambda: cloudfront_link(p)))
        else:
            lines.append("FAIL: CloudFront configuration is incomplete")
        sources.append(("Supabase copy", lambda: supabase_link(url, service_key(ref), p)))
        if env("OCI_BUILDS_HOST") and env("OCI_LINK_SECRET"):
            sources.append(("Oracle copy", lambda: oracle_link(p)))
        else:
            lines.append("FAIL: Oracle copy configuration is incomplete")
        for name, link in sources:
            try:
                status = answers(link())
            except (Exception, SystemExit) as e:
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

    lines.append(google_sign_in(url))
    lines.append(admob_week())

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
