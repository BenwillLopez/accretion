"""Copy hosted builds from the Supabase "builds" bucket to the S3 bucket in aws/builds-cdn.yaml.

Run by community-setup.yml before the download functions switch to CloudFront, so every build in
hosted_builds is already in S3. Copies only files that aren't there yet; safe to run again.

Needs SUPABASE_ACCESS_TOKEN, BUILDS_BUCKET, BUILDS_REGION, BUILDS_AWS_KEY_ID, BUILDS_AWS_SECRET.
"""

import json
import os
import tempfile
import urllib.request

import boto3
from botocore.exceptions import ClientError

from common import path
from supabase_setup import call, sql


def env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} isn't set")
    return value


def service_key(ref):
    for k in call("GET", f"/projects/{ref}/api-keys?reveal=true") or []:
        if k.get("name") == "service_role" and k.get("api_key"):
            print(f"::add-mask::{k['api_key']}")
            return k["api_key"]
    raise SystemExit("Couldn't find the project's service_role key")


def main():
    with open(path("supabase/project.json"), encoding="utf-8") as f:
        project = json.load(f)
    url = project["url"].rstrip("/")
    ref = url.split("//", 1)[1].split(".", 1)[0]
    bucket = env("BUILDS_BUCKET")
    s3 = boto3.client(
        "s3",
        region_name=env("BUILDS_REGION"),
        aws_access_key_id=env("BUILDS_AWS_KEY_ID"),
        aws_secret_access_key=env("BUILDS_AWS_SECRET"),
    )
    key = service_key(ref)
    rows = sql(ref, "select path from public.hosted_builds order by created_at") or []
    copied = present = 0
    for row in rows:
        name = row["path"]
        try:
            s3.head_object(Bucket=bucket, Key=name)
            present += 1
            continue
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") not in ("404", "NoSuchKey", "NotFound"):
                raise
        req = urllib.request.Request(
            f"{url}/storage/v1/object/builds/{urllib.request.quote(name)}",
            headers={"Authorization": f"Bearer {key}", "apikey": key},
        )
        with tempfile.TemporaryFile() as tmp:
            with urllib.request.urlopen(req, timeout=600) as r:
                while chunk := r.read(1 << 20):
                    tmp.write(chunk)
            tmp.seek(0)
            s3.upload_fileobj(tmp, bucket, name)
        copied += 1
        print(f"Copied {name}")
    print(f"Builds in S3: {present} already there, {copied} copied, {len(rows)} total")


if __name__ == "__main__":
    main()
