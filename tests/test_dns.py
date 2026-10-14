import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dns

ROOT = Path(__file__).resolve().parents[1]


def record(rid, type_, name, content, proxied=False):
    return {"id": rid, "type": type_, "name": name, "content": content, "proxied": proxied}


class FakeCloudflare:
    def __init__(self, records, zones=None):
        self.records = records
        self.zones = [{"id": "z1"}] if zones is None else zones
        self.calls = []

    def __call__(self, method, route, body=None):
        self.calls.append((method, route.split("?")[0], body))
        if route.startswith("/zones?"):
            return self.zones
        if method == "GET":
            return list(self.records)
        return {}


class Dns(unittest.TestCase):
    def config(self, records, zone="example.app"):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        config = Path(folder.name) / "dns.json"
        config.write_text(json.dumps({"zone": zone, "records": records}), encoding="utf-8")
        return dns.load(config)

    def test_repo_config_loads_github_pages_records(self):
        zone, wanted = dns.load(ROOT / "dns.json")
        self.assertEqual(zone, "getaccretion.app")
        self.assertEqual(sum(w["type"] == "A" for w in wanted), 4)
        self.assertEqual(sum(w["type"] == "AAAA" for w in wanted), 4)
        self.assertTrue(all(not w["proxied"] for w in wanted))

    def test_matching_records_need_no_changes(self):
        _, wanted = self.config([{"type": "CNAME", "name": "www", "content": "a.github.io"}])
        current = [record("1", "CNAME", "www.example.app", "A.github.io.")]
        self.assertEqual(dns.plan(wanted, current), ([], []))

    def test_wrong_and_proxied_records_are_replaced(self):
        _, wanted = self.config([{"type": "A", "name": "@", "content": "1.1.1.1"}])
        current = [
            record("1", "A", "example.app", "9.9.9.9"),
            record("2", "A", "example.app", "1.1.1.1", proxied=True),
        ]
        remove, add = dns.plan(wanted, current)
        self.assertEqual([r["id"] for r in remove], ["1", "2"])
        self.assertEqual([a["content"] for a in add], ["1.1.1.1"])

    def test_unmanaged_names_and_types_are_never_touched(self):
        _, wanted = self.config([{"type": "A", "name": "@", "content": "1.1.1.1"}])
        current = [
            record("1", "A", "example.app", "1.1.1.1"),
            record("2", "TXT", "example.app", "google-site-verification=x"),
            record("3", "A", "mail.example.app", "2.2.2.2"),
        ]
        self.assertEqual(dns.plan(wanted, current), ([], []))

    def test_check_mode_reports_without_writing(self):
        zone, wanted = self.config([{"type": "A", "name": "@", "content": "1.1.1.1"}])
        fake = FakeCloudflare([record("1", "A", "example.app", "9.9.9.9")])
        remove, add = dns.sync(fake, zone, wanted, apply=False, log=lambda _: None)
        self.assertEqual((len(remove), len(add)), (1, 1))
        self.assertEqual({m for m, _, _ in fake.calls}, {"GET"})

    def test_apply_deletes_then_creates(self):
        zone, wanted = self.config([{"type": "A", "name": "@", "content": "1.1.1.1"}])
        fake = FakeCloudflare([record("1", "A", "example.app", "9.9.9.9")])
        dns.sync(fake, zone, wanted, apply=True, log=lambda _: None)
        writes = [(m, r) for m, r, _ in fake.calls if m != "GET"]
        self.assertEqual(writes, [("DELETE", "/zones/z1/dns_records/1"), ("POST", "/zones/z1/dns_records")])

    def test_missing_zone_is_an_error(self):
        zone, wanted = self.config([{"type": "A", "name": "@", "content": "1.1.1.1"}])
        with self.assertRaises(dns.CloudflareError):
            dns.sync(FakeCloudflare([], zones=[]), zone, wanted, apply=False, log=lambda _: None)

    def test_unsupported_type_is_rejected(self):
        with self.assertRaises(ValueError):
            self.config([{"type": "NS", "name": "@", "content": "x"}])


if __name__ == "__main__":
    unittest.main()
