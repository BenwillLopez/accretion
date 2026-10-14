"""Keep the store domain's Cloudflare DNS equal to dns.json.

dns.json lists the wanted records. Every (name, type) pair it mentions is managed: records of that
pair that are not listed are removed, and listed ones are created. Names and types it doesn't mention
are never touched. The default is a check that exits 1 on drift; --apply makes the changes.
Records are DNS only (not proxied) unless a record says "proxied": true.

Needs CLOUDFLARE_API_TOKEN (Zone Read + DNS Edit on the zone). The token is never printed.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from common import path

API = "https://api.cloudflare.com/client/v4"
TYPES = {"A", "AAAA", "CNAME", "TXT", "MX", "CAA"}


class CloudflareError(RuntimeError):
    pass


def cloudflare(token):
    def call(method, route, body=None):
        request = urllib.request.Request(
            API + route,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)["result"]
        except urllib.error.HTTPError as error:
            try:
                errors = json.load(error).get("errors")
            except ValueError:
                errors = None
            raise CloudflareError(f"{method} {route.split('?')[0]}: HTTP {error.code} {errors}") from None

    return call


def fqdn(name, zone):
    return zone if name in ("@", "", zone) else f"{name.removesuffix('.' + zone)}.{zone}"


def key(record):
    content = record["content"]
    if record["type"] in ("CNAME", "MX"):
        content = content.rstrip(".").lower()
    elif record["type"] == "AAAA":
        content = content.lower()
    elif record["type"] == "TXT":
        content = content.strip('"')
    return (record["type"], record["name"].lower(), content, bool(record.get("proxied")))


def load(config_path):
    with open(config_path, encoding="utf-8") as handle:
        config = json.load(handle)
    zone = config["zone"].lower()
    wanted = []
    for record in config["records"]:
        if record["type"] not in TYPES:
            raise ValueError(f"unsupported record type {record['type']}")
        item = {
            "type": record["type"],
            "name": fqdn(record["name"].lower(), zone),
            "content": record["content"],
            "ttl": record.get("ttl", 1),
            "proxied": bool(record.get("proxied", False)),
        }
        if record["type"] == "MX":
            item["priority"] = record.get("priority", 10)
        wanted.append(item)
    return zone, wanted


def plan(wanted, current):
    """Return (remove, add) so that the managed (name, type) pairs match `wanted` exactly."""
    managed = {(w["name"], w["type"]) for w in wanted}
    todo = {key(w): w for w in wanted}
    remove = []
    for record in current:
        if (record["name"].lower(), record["type"]) not in managed:
            continue
        if todo.pop(key(record), None) is None:
            remove.append(record)
    return remove, list(todo.values())


def sync(call, zone, wanted, apply, log=print):
    zones = call("GET", f"/zones?name={zone}")
    if not zones:
        raise CloudflareError(f"zone {zone} is not visible to this token")
    zone_id = zones[0]["id"]
    current = call("GET", f"/zones/{zone_id}/dns_records?per_page=500")
    remove, add = plan(wanted, current)
    for record in remove:
        log(f"{'remove' if apply else 'extra '} {record['type']:5} {record['name']} -> {record['content']}")
        if apply:
            call("DELETE", f"/zones/{zone_id}/dns_records/{record['id']}")
    for record in add:
        log(f"{'add   ' if apply else 'missing'} {record['type']:5} {record['name']} -> {record['content']}")
        if apply:
            call("POST", f"/zones/{zone_id}/dns_records", record)
    if not remove and not add:
        log(f"{zone}: {len(wanted)} records match dns.json")
    return remove, add


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="create and remove records")
    parser.add_argument("--config", default=path("dns.json"))
    args = parser.parse_args(argv)
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not token:
        sys.exit("CLOUDFLARE_API_TOKEN is not set")
    zone, wanted = load(args.config)
    try:
        remove, add = sync(cloudflare(token), zone, wanted, args.apply)
    except CloudflareError as error:
        sys.exit(str(error))
    if (remove or add) and not args.apply:
        sys.exit("DNS differs from dns.json; run with --apply")


if __name__ == "__main__":
    main()
