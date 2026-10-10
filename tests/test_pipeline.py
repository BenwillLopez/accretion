import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import discover
import merge
from common import date_key, version_key
from sanitize import category, clean_app, clean_news, https, permissions, screenshots, skip_reason, validate

ICON = "https://example.com/icon.png"


def app(bid="com.example.app", version="1.0", date="2025-01-01", url=None, **extra):
    return {
        "name": "Example",
        "bundleIdentifier": bid,
        "developerName": "Dev",
        "localizedDescription": "An app.",
        "iconURL": ICON,
        "versions": [
            {
                "version": version,
                "date": date,
                "size": 100,
                "downloadURL": url or f"https://example.com/{bid}-{version}.ipa",
            }
        ],
        **extra,
    }


def merged(*sources, dead=frozenset()):
    loaded = [
        (f"https://src{i}.example/apps.json", {"name": f"S{i}", "apps": apps}, "ok", 0)
        for i, apps in enumerate(sources)
    ]
    best, _, stats, news, _ = merge.pick(loaded, dead)
    return merge.build(best, news, merge.OUTPUTS["source.json"], stats)


class VersionOrdering(unittest.TestCase):
    def test_version_key(self):
        self.assertGreater(version_key("1.10.0"), version_key("1.9.9"))
        self.assertGreater(version_key("v2.0 (45)"), version_key("2.0 (44)"))
        self.assertEqual(version_key("Latest"), ())

    def test_date_key_formats(self):
        self.assertEqual(date_key("2024-3-5"), "2024-03-05T00:00")
        self.assertEqual(date_key("2024-03-05T10:20:30Z"), "2024-03-05T10:20:30")
        self.assertEqual(date_key("March 5"), "")

    def test_versions_of_reads_legacy_and_v2(self):
        raw = {
            "version": "1.0",
            "versionDate": "2024-01-01",
            "downloadURL": "https://a/1.ipa",
            "versions": [{"version": "2.0", "date": "2025-01-01", "downloadURL": "https://a/2.ipa"}],
        }
        self.assertEqual([v["version"] for v in merge.versions_of(raw)], ["2.0", "1.0"])

    def test_dead_links_are_skipped(self):
        raw = app(version="2.0")
        raw["versions"].append({"version": "1.0", "date": "2024-01-01", "downloadURL": "https://a/1.ipa"})
        dead = {raw["versions"][0]["downloadURL"]}
        self.assertEqual([v["version"] for v in merge.versions_of(raw, dead)], ["1.0"])


class Merging(unittest.TestCase):
    def test_highest_version_wins(self):
        out = merged([app(version="1.0")], [app(version="1.2")], [app(version="1.1")])
        self.assertEqual(out["apps"][0]["version"], "1.2")
        self.assertEqual(validate(out), [])

    def test_tie_goes_to_newer_date_then_first_source(self):
        out = merged([app(date="2025-01-01")], [app(date="2025-02-01", url="https://b/x.ipa")])
        self.assertEqual(out["apps"][0]["downloadURL"], "https://b/x.ipa")
        out = merged([app(url="https://a/x.ipa")], [app(url="https://b/x.ipa")])
        self.assertEqual(out["apps"][0]["downloadURL"], "https://a/x.ipa")

    def test_one_entry_per_bundle_id(self):
        out = merged([app(), app(bid="com.other")], [app(), app(bid="com.third")])
        self.assertEqual([a["bundleIdentifier"] for a in out["apps"]].count("com.example.app"), 1)
        self.assertEqual(len(out["apps"]), 3)

    def test_featured_apps_exist(self):
        out = merged([app(bid=f"com.app{i}", date=f"2025-01-{i + 1:02d}") for i in range(15)])
        self.assertEqual(len(out["featuredApps"]), merge.MAX_FEATURED)
        self.assertEqual(out["featuredApps"][0], "com.app14")
        self.assertEqual(validate(out), [])


class Sanitizing(unittest.TestCase):
    def test_https_only(self):
        self.assertIsNone(https("http://example.com/a.ipa"))
        self.assertIsNone(https("ftp://example.com/a.ipa"))
        self.assertEqual(https(" https://example.com/a.ipa "), "https://example.com/a.ipa")

    def test_rejects_unusable_apps(self):
        self.assertIsNone(clean_app(app(), []))
        self.assertIsNone(clean_app(app(iconURL="http://x/icon.png"), app()["versions"]))
        self.assertIsNone(clean_app(app(bid="bad id"), app()["versions"]))
        bad_date = [{**app()["versions"][0], "date": "soon"}]
        self.assertIsNone(clean_app(app(), bad_date))

    def test_fills_and_normalises_fields(self):
        raw = app(category="Emulators", tintColor="#ff00aa", developerName="")
        raw["versions"][0]["size"] = "2048"
        out = clean_app(raw, raw["versions"])
        self.assertEqual(out["category"], "games")
        self.assertEqual(out["tintColor"], "FF00AA")
        self.assertEqual(out["developerName"], "Unknown developer")
        self.assertEqual(out["size"], 2048)
        self.assertEqual(out["downloadURL"], out["versions"][0]["downloadURL"])

    def test_category_guessed_when_missing(self):
        self.assertEqual(category(None, "YouTube Plus com.google.ios.youtube"), "photo-video")
        self.assertEqual(category("", "Delta emulator"), "games")
        self.assertEqual(category(None, "TrollStore helper"), "developer")
        self.assertEqual(category("social", "game"), "social")  # a real category always wins
        self.assertEqual(category(None, "Mainspring IPA MOD"), "other")

    def test_unknown_category(self):
        self.assertEqual(category("Weird Stuff"), "other")
        self.assertEqual(category("photo-video"), "photo-video")

    def test_news_never_notifies(self):
        item = clean_news({"title": "Hi", "identifier": "n1", "date": "2025-01-01", "notify": True}, set())
        self.assertFalse(item["notify"])
        self.assertIsNone(clean_news({"title": "No id", "date": "2025-01-01"}, set()))

    def test_validate_catches_problems(self):
        out = merged([app()])
        out["apps"].append(dict(out["apps"][0]))
        out["apps"][0] = {**out["apps"][0], "category": "nope"}
        errors = validate(out)
        self.assertTrue(any("duplicate" in e for e in errors))
        self.assertTrue(any("category" in e for e in errors))


class LinkChecks(unittest.TestCase):
    def test_grace_periods(self):
        import check_links

        self.assertEqual(check_links.dead_after({"fails": 1}), check_links.DEAD_AFTER)
        self.assertEqual(check_links.dead_after({"host_wide": True}), check_links.DEAD_AFTER_HOST_WIDE)
        self.assertGreater(check_links.DEAD_AFTER_HOST_WIDE, check_links.DEAD_AFTER)


class Growth(unittest.TestCase):
    def test_timeline_from_first_release_dates(self):
        import datetime as dt

        now = dt.datetime(2026, 10, 10, tzinfo=dt.timezone.utc)
        firsts = {
            "a": "2020-01-01T00:00",
            "b": "2026-03-05T00:00",
            "c": "2026-10-01T00:00",
            "d": "2030-01-01T00:00",
        }
        out = merge.timeline(now, firsts)
        self.assertEqual(len(out["timeline"]), 24)
        self.assertEqual(out["timeline"][0], {"month": "2024-11", "apps": 1})
        self.assertEqual(out["timeline"][-1], {"month": "2026-10", "apps": 4})  # future date counts as today
        self.assertEqual(out["new_30d"], 2)
        self.assertEqual(out["new_12m"], 3)

    def test_earliest_date_across_sources(self):
        old = app(version="1.0", date="2021-05-01")
        new = app(version="2.0", date="2025-05-01")
        loaded = [
            ("https://a/x.json", {"name": "A", "apps": [new]}, "ok", 0),
            ("https://b/x.json", {"name": "B", "apps": [old]}, "ok", 0),
        ]
        _, _, _, _, firsts = merge.pick(loaded, frozenset())
        self.assertEqual(firsts["com.example.app"][:10], "2021-05-01")


class Cards(unittest.TestCase):
    def test_cards_are_valid_svg(self):
        import xml.etree.ElementTree as ET

        import card

        out = merged(
            [app(bid=f"com.app{i}", date=f"2025-01-{i + 1:02d}", category="games") for i in range(9)]
        )
        m = {
            "apps": 9,
            "curated_apps": 9,
            "sources": 1,
            "sources_total": 2,
            "sources_failed": 1,
            "sources_discovered": 1,
            "listings": 12,
            "duplicates": 3,
            "rejected": 1,
            "dead_links_removed": 0,
            "updated_7d": 2,
            "updated_30d": 5,
            "size_mb": 0.1,
            "curated_size_mb": 0.1,
            "updated": "2025-01-10 00:00 UTC",
            "categories": {"games": 9},
            "recent": [{"name": "A <&> B", "version": "1.0", "date": "2025-01-09"}],
        }
        for history in ([], [{"date": "2025-01-01", "apps": 5}, {"date": "2025-01-02", "apps": 9}]):
            for theme in card.THEMES.values():
                ET.fromstring(card.stats_card(m, history, theme))
                ET.fromstring(card.recent_card(m, theme))
        self.assertTrue(out["apps"])


class AltStoreSpec(unittest.TestCase):
    """Rules from https://faq.altstore.io/developers/make-a-source"""

    def test_source_level_fields(self):
        out = merged([app(bid=f"com.app{i}") for i in range(8)])
        self.assertIs(out["nsfw"], False)
        self.assertEqual(len(out["featuredApps"]), 5)
        self.assertEqual(validate(out), [])

    def test_nsfw_inherited_from_sources(self):
        loaded = [("https://a/x.json", {"name": "A", "nsfw": True, "apps": [app()]}, "ok", 0)]
        best, _, stats, news, _ = merge.pick(loaded, frozenset())
        self.assertIs(merge.build(best, news, merge.OUTPUTS["source.json"], stats)["nsfw"], True)

    def test_patreon_and_pal_apps_are_excluded(self):
        self.assertEqual(skip_reason(app(patreon={"pledge": 3})), "patreon")
        self.assertEqual(skip_reason(app(marketplaceID="123")), "pal")
        pal = app(url="https://x.example/app/manifest.json")
        self.assertEqual(skip_reason(pal), "pal")
        self.assertIsNone(skip_reason(app()))
        out = merged([app(bid="com.paid", patreon={}), app(bid="com.free")])
        self.assertEqual([a["bundleIdentifier"] for a in out["apps"]], ["com.free"])

    def test_screenshots_current_format(self):
        shots = screenshots(
            {
                "screenshots": {
                    "iphone": [
                        "https://x/1.png",
                        {"imageURL": "https://x/2.png", "width": 2556, "height": 1179},
                    ],
                    "ipad": [
                        {"imageURL": "https://x/3.png"},
                        {"imageURL": "https://x/4.png", "width": 1, "height": 2},
                    ],
                }
            }
        )
        self.assertEqual(shots["iphone"][0], "https://x/1.png")
        self.assertEqual(shots["ipad"], [{"imageURL": "https://x/4.png", "width": 1, "height": 2}])
        self.assertEqual(
            screenshots({"screenshotURLs": ["https://x/a.png", "http://x/b.png"]}), ["https://x/a.png"]
        )
        out = clean_app(app(screenshots=["https://x/1.png"]), app()["versions"])
        self.assertEqual(out["screenshots"], ["https://x/1.png"])
        self.assertEqual(out["screenshotURLs"], ["https://x/1.png"])

    def test_permissions_are_cleaned_not_guessed(self):
        self.assertEqual(
            permissions(
                {"entitlements": ["b", "a", 3], "privacy": {"NSCameraUsageDescription": "cam", "x": 1}}
            ),
            {"entitlements": ["a", "b"], "privacy": {"NSCameraUsageDescription": "cam"}},
        )
        self.assertEqual(
            permissions({"privacy": [{"name": "NSMicrophoneUsageDescription", "usageDescription": "mic"}]}),
            {"privacy": {"NSMicrophoneUsageDescription": "mic"}},
        )
        self.assertIsNone(permissions([{"type": "photos"}]))  # legacy 1.x list: dropped

    def test_news_caption_required(self):
        item = clean_news({"title": "Hi", "identifier": "n1", "date": "2025-01-01"}, set())
        self.assertEqual(item["caption"], "Hi")


class WebStore(unittest.TestCase):
    def test_shard_hash_matches_the_browser(self):
        import importlib.util

        # scripts/site.py shares its name with the stdlib "site" module, so load it by path
        spec = importlib.util.spec_from_file_location(
            "store_site", os.path.join(os.path.dirname(__file__), "..", "scripts", "site.py")
        )
        store = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(store)
        # Known FNV-1a 32-bit value; site/app.js implements the same function.
        self.assertEqual(store.fnv1a("a"), 0xE40C292C)
        self.assertLess(store.shard_of("com.example.app"), store.SHARDS)


class SupabaseSetup(unittest.TestCase):
    """The setup script against a fake Management API."""

    def run_setup(self, projects, admin="", statuses=("COMING_UP", "ACTIVE_HEALTHY"), admin_rows=None):
        import importlib
        import tempfile
        from unittest import mock

        import supabase_setup as setup

        importlib.reload(setup)
        calls = []
        status_iter = iter(statuses)

        def fake_call(method, route, body=None, timeout=120):
            calls.append((method, route, body))
            if route == "/projects" and method == "GET":
                return projects
            if route == "/organizations":
                return [{"id": "org-1", "name": "Ben"}]
            if route == "/projects" and method == "POST":
                return {"id": "newref"}
            if route.endswith("/api-keys"):
                return [
                    {"name": "service_role", "api_key": "SECRET"},
                    {"name": "anon", "api_key": "anon-key"},
                ]
            if route.endswith("/database/query"):
                return admin_rows if "update public.profiles" in body["query"] else []
            if method == "GET" and route.startswith("/projects/"):
                return {"status": next(status_iter, "ACTIVE_HEALTHY")}
            return {}

        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, "supabase"))
        with open(os.path.join(tmp, "supabase", "schema.sql"), "w") as f:
            f.write("select 1;")
        with (
            mock.patch.object(setup, "call", fake_call),
            mock.patch.object(setup, "TOKEN", "t"),
            mock.patch.object(setup, "SITE_URL", "https://x.github.io/accretion/"),
            mock.patch.object(setup, "ADMIN", admin),
            mock.patch.object(setup, "path", lambda n: os.path.join(tmp, n)),
            mock.patch.object(setup.time, "sleep", lambda s: None),
            mock.patch.object(setup, "check_public_api", lambda url, key: calls.append(("CHECK", url, key))),
        ):
            setup.main()
        with open(os.path.join(tmp, "supabase", "project.json")) as f:
            return calls, json.load(f)

    def test_creates_project_and_saves_public_settings(self):
        calls, saved = self.run_setup(projects=[])
        posted = next(c for c in calls if c[0] == "POST" and c[1] == "/projects")[2]
        self.assertEqual(posted["organization_id"], "org-1")
        self.assertGreaterEqual(len(posted["db_pass"]), 30)
        self.assertTrue(any(c[1] == "/projects/newref/database/query" for c in calls))
        auth = next(c for c in calls if c[1].endswith("/config/auth"))[2]
        self.assertEqual(auth["site_url"], "https://x.github.io/accretion/")
        self.assertEqual(
            saved, {"url": "https://newref.supabase.co", "anonKey": "anon-key"}
        )  # never the secret

    def test_reuses_existing_project_and_makes_admin(self):
        calls, saved = self.run_setup(
            projects=[{"id": "oldref", "name": "accretion"}],
            admin="ben_w",
            admin_rows=[{"username": "ben_w", "role": "admin"}],
        )
        self.assertFalse(any(c[0] == "POST" and c[1] == "/projects" for c in calls))
        self.assertEqual(saved["url"], "https://oldref.supabase.co")
        self.assertTrue(any("ben_w" in (c[2] or {}).get("query", "") for c in calls))

    def test_rejects_unsafe_admin_name(self):
        with self.assertRaises(SystemExit):
            self.run_setup(projects=[{"id": "r", "name": "accretion"}], admin="x'; drop table posts;--")


class Discovery(unittest.TestCase):
    def test_clean_url(self):
        self.assertEqual(
            discover.clean_url("github.com/a/b/blob/main/x.json"),
            "https://raw.githubusercontent.com/a/b/main/x.json",
        )
        self.assertEqual(
            discover.clean_url("https://github.com/a/b/raw/refs/heads/main/x.json)."),
            "https://raw.githubusercontent.com/a/b/main/x.json",
        )

    def test_plausible(self):
        self.assertTrue(discover.plausible("https://example.com/apps.json"))
        self.assertFalse(discover.plausible("https://reddit.com/r/AltStore"))
        self.assertFalse(discover.plausible("https://example.com/logo.png"))
        self.assertFalse(discover.plausible("https://github.com/a/b"))

    def test_urls_in_markdown(self):
        text = "[A](example.com/a.json) and https://b.example/b.json, see <https://c.example/c.json>"
        self.assertEqual(
            discover.urls_in_text(text),
            {"https://example.com/a.json", "https://b.example/b.json", "https://c.example/c.json"},
        )


if __name__ == "__main__":
    unittest.main()
