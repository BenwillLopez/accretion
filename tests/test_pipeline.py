import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import discover
import merge
from common import date_key, version_key
from sanitize import category, clean_app, clean_news, https, validate

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
    best, _, _, news = merge.pick(loaded, dead)
    return merge.build(best, news, merge.OUTPUTS["source.json"])


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
