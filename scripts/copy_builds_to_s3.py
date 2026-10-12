"""Keep every hosted build in both stores: the Supabase "builds" bucket and the S3 bucket in
aws/builds-cdn.yaml.

Run by community-setup.yml before the download functions are deployed. Builds missing from S3 are
copied there (so CloudFront can serve them), and builds missing from Supabase are copied back (so
the download function can fall back to Supabase when AWS is unavailable). Copies only what's
missing; safe to run again.

Needs SUPABASE_ACCESS_TOKEN, BUILDS_BUCKET, BUILDS_REGION, BUILDS_AWS_KEY_ID, BUILDS_AWS_SECRET.
"""

import json
import os
import tempfile
import urllib.error
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


class Supabase:
    def __init__(self, url, key):
        self.url = url
        self.headers = {"Authorization": f"Bearer {key}", "apikey": key}

    def _object(self, name):
        return f"{self.url}/storage/v1/object/builds/{urllib.request.quote(name)}"

    def has(self, name):
        folder, _, file = name.rpartition("/")
        req = urllib.request.Request(
            f"{self.url}/storage/v1/object/list/builds",
            method="POST",
            data=json.dumps({"prefix": folder, "search": file, "limit": 100}).encode(),
            headers={**self.headers, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            return any(item.get("name") == file for item in json.load(r))

    def download(self, name, tmp):
        req = urllib.request.Request(self._object(name), headers=self.headers)
        with urllib.request.urlopen(req, timeout=600) as r:
            while chunk := r.read(1 << 20):
                tmp.write(chunk)

    def upload(self, name, tmp):
        req = urllib.request.Request(
            self._object(name),
            method="POST",
            data=tmp.read(),
            headers={**self.headers, "Content-Type": "application/octet-stream", "x-upsert": "true"},
        )
        try:
            with urllib.request.urlopen(req, timeout=600):
                pass
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise SystemExit(f"Supabase upload of {name} failed ({e.code}): {detail}") from None


def in_s3(s3, bucket, name):
    try:
        s3.head_object(Bucket=bucket, Key=name)
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


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
    supabase = Supabase(url, service_key(ref))
    rows = sql(ref, "select path from public.hosted_builds order by created_at") or []
    to_s3 = to_supabase = 0
    for row in rows:
        name = row["path"]
        there_s3, there_supabase = in_s3(s3, bucket, name), supabase.has(name)
        if there_s3 and there_supabase:
            continue
        if not there_s3 and not there_supabase:
            print(f"::warning::{name} is in neither store")
            continue
        with tempfile.TemporaryFile() as tmp:
            if there_supabase:
                supabase.download(name, tmp)
                tmp.seek(0)
                s3.upload_fileobj(tmp, bucket, name)
                to_s3 += 1
                print(f"Copied {name} to S3")
            else:
                s3.download_fileobj(bucket, name, tmp)
                tmp.seek(0)
                supabase.upload(name, tmp)
                to_supabase += 1
                print(f"Copied {name} to Supabase")
    print(f"Builds: {len(rows)} total, {to_s3} copied to S3, {to_supabase} copied to Supabase")


if __name__ == "__main__":
    main()
