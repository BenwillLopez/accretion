import json
import os
import sys
import unittest
from unittest import mock

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

    def test_apps_with_only_dead_links_are_recorded_as_gone(self):
        def src(url, link):
            app = {
                "name": "Lost App",
                "bundleIdentifier": "com.lost.app",
                "developerName": "Dev",
                "iconURL": "https://x.io/i.png",
                "versions": [{"version": "1.0", "date": "2026-01-01", "downloadURL": link, "size": 10}],
            }
            return url, {"name": "S", "apps": [app]}, "ok", 0

        dead = {"https://dead.io/x.ipa"}
        gone = {}
        best, *_ = merge.pick([src("a", "https://dead.io/x.ipa")], dead, gone)
        self.assertNotIn("com.lost.app", best)
        self.assertEqual(gone["com.lost.app"]["n"], "Lost App")
        gone = {}
        best, *_ = merge.pick(
            [src("a", "https://dead.io/x.ipa"), src("b", "https://ok.io/x.ipa")], dead, gone
        )
        self.assertIn("com.lost.app", best)  # a working copy elsewhere wins
        self.assertEqual(gone, {})

    def test_placeholder_dates_get_a_real_one(self):
        import sanitize
        from common import date_from_url, plausible_day

        self.assertFalse(plausible_day("2000-01-01"))
        self.assertFalse(plausible_day("1970-01-01"))
        self.assertFalse(plausible_day("2999-01-01"))
        self.assertTrue(plausible_day("2024-05-01T10:00:00Z"))
        self.assertEqual(date_from_url("https://x.io/AR.Translator._3.10_1737138371.ipa"), "2025-01-17")
        self.assertIsNone(date_from_url("https://x.io/App_v4_14_0.ipa"))

        sanitize.KNOWN_DATES = {
            "https://x.io/b.ipa": {"modified": "2024-03-02"},
            "https://x.io/c.ipa": {"seen": "2026-10-01"},
        }
        sanitize.UNDATED.clear()
        try:
            v = {"version": "1", "downloadURL": "https://x.io/a_1737138371.ipa", "date": "1970-01-01"}
            self.assertEqual(sanitize.clean_version(v)["date"], "2025-01-17")  # timestamp in the link
            v = {"version": "1", "downloadURL": "https://x.io/b.ipa", "date": "2000-01-01"}
            self.assertEqual(sanitize.clean_version(v)["date"], "2024-03-02")  # file's upload day
            v = {"version": "1", "downloadURL": "https://x.io/c.ipa", "date": "2000-01-01"}
            self.assertEqual(sanitize.clean_version(v)["date"], "2026-10-01")  # first seen, flagged
            self.assertEqual(sanitize.UNDATED, {"https://x.io/c.ipa"})
            v = {"version": "1", "downloadURL": "https://x.io/d.ipa", "date": "2023-06-01"}
            self.assertEqual(sanitize.clean_version(v)["date"], "2023-06-01")  # real dates untouched
        finally:
            sanitize.KNOWN_DATES = {}
            sanitize.UNDATED.clear()
            sanitize.REDATED.clear()

    def test_upload_day_from_last_modified(self):
        import check_links

        self.assertEqual(
            check_links.upload_day({"Last-Modified": "Wed, 12 Mar 2025 08:00:00 GMT"}), "2025-03-12"
        )
        self.assertIsNone(check_links.upload_day({}))

    def test_every_app_gets_a_real_subtitle(self):
        from sanitize import make_subtitle

        desc = (
            "from @riftysIPAlibrary |\n----------------\n📱 Lake: Coloring Book for Adults\n🆔 Bundle ID: x"
        )
        self.assertEqual(make_subtitle(desc, "Lake", "lifestyle", "Dev"), "Lake: Coloring Book for Adults")
        self.assertEqual(
            make_subtitle("Watch anime anywhere. Free!", "X", "entertainment", "Dev"), "Watch anime anywhere."
        )
        self.assertEqual(make_subtitle("", "AAI", "games", "Unknown developer"), "Game")
        self.assertEqual(make_subtitle("AAI", "AAI", "utilities", "Acme"), "Utility by Acme")

    def test_dead_icons_are_replaced(self):
        best = {
            "a": (0, {"iconURL": "https://dead.io/i.png"}, "s1"),
            "b": (0, {"iconURL": "https://dead.io/j.png"}, "s1"),
        }
        icons = {"a": ["https://dead.io/i.png", "https://ok.io/i.png"], "b": ["https://dead.io/j.png"]}
        dead = {"https://dead.io/i.png", "https://dead.io/j.png"}
        self.assertEqual(merge.fix_icons(best, icons, dead), 2)
        self.assertEqual(best["a"][1]["iconURL"], "https://ok.io/i.png")  # another source's icon
        self.assertEqual(best["b"][1]["iconURL"], merge.PLACEHOLDER_ICON)

    def test_links_ending_on_plain_http_count_as_dead(self):
        from unittest import mock

        import check_links

        class Resp:
            def __init__(self, url):
                self.url = url
                self.headers = {}

            def geturl(self):
                return self.url

            def read(self, n):
                return b"x"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with mock.patch.object(
            check_links.urllib.request, "urlopen", lambda req, timeout: Resp("http://cdn.io/a.png")
        ):
            self.assertEqual(check_links.status("https://cdn.io/a.png"), "dead")
        with mock.patch.object(
            check_links.urllib.request, "urlopen", lambda req, timeout: Resp("https://cdn.io/a.png")
        ):
            self.assertEqual(check_links.status("https://cdn.io/a.png"), "alive")

        def page(req, timeout):  # an error or landing page instead of the file
            r = Resp("https://host.io/404")
            r.headers = {"Content-Type": "text/html; charset=utf-8"}
            return r

        with mock.patch.object(check_links.urllib.request, "urlopen", page):
            self.assertEqual(check_links.status("https://host.io/download/1"), "dead")

    def test_icons_are_hosted_by_accretion(self):
        import io
        import tempfile
        from unittest import mock

        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed")
        import icons

        png = io.BytesIO()
        Image.new("RGBA", (512, 400), (200, 30, 30, 128)).save(png, "PNG")
        jpeg = icons.shrink(png.getvalue())
        with Image.open(io.BytesIO(jpeg)) as im:
            self.assertEqual((im.format, im.size), ("JPEG", (180, 180)))

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(icons, "DIR", tmp):
            answers = {
                "https://a.io/ok.png": ("ok", jpeg),
                "https://a.io/gone.png": ("gone", None),
                "https://a.io/flaky.png": ("error", None),
            }
            with mock.patch.object(icons, "fetch", lambda url: answers[url]):
                self.assertEqual(
                    icons.mirror("https://a.io/ok.png")[1], icons.mirror_url(icons.key("https://a.io/ok.png"))
                )
                self.assertEqual(icons.mirror("https://a.io/gone.png")[1], icons.PLACEHOLDER_ICON)
                self.assertIsNone(icons.mirror("https://a.io/flaky.png")[1])  # keep the original link
            with mock.patch.object(
                icons, "fetch", lambda url: self.fail("cached icons are not fetched again")
            ):
                self.assertTrue(icons.mirror("https://a.io/ok.png")[1].startswith(icons.SITE + "/icons/"))

    def test_fallback_links_are_checked_before_publishing(self):
        def src(url, link, version):
            app = {
                "name": "App",
                "bundleIdentifier": "com.x.app",
                "developerName": "Dev",
                "iconURL": "https://x.io/i.png",
                "versions": [{"version": version, "date": "2026-01-01", "downloadURL": link, "size": 1}],
            }
            return url, {"name": "S", "apps": [app]}, "ok", 0

        # hand-picked source first (Core); its new copy was never checked and is dead
        loaded = [src("core", "https://gone.io/new.ipa", "2.0"), src("other", "https://ok.io/old.ipa", "1.0")]
        checked = {"https://ok.io/old.ipa": "alive"}
        asked = []

        def check_many(urls):
            asked.append(set(urls))
            return {u: "dead" if "gone.io" in u else "alive" for u in urls}

        dead, links = set(), {}
        full, core, _, _ = merge.pick_checked(loaded, 1, dead, checked, check_many, links)
        self.assertEqual(asked[0], {"https://gone.io/new.ipa"})  # only the unchecked link
        self.assertEqual(full[0]["com.x.app"][1]["versions"][0]["downloadURL"], "https://ok.io/old.ipa")
        self.assertNotIn("com.x.app", core[0])  # no working hand-picked copy: out of Core
        self.assertIn("https://gone.io/new.ipa", links)  # retested on later builds
        full, core, _, _ = merge.pick_checked(loaded, 1, set(), None, check_many, {})
        self.assertEqual(len(asked), 1)  # no link check this build: nothing extra tested

        # dead links found in the last allowed round are still left out
        asked.clear()
        fresh = {"https://ok.io/old.ipa": "alive"}
        full, core, _, _ = merge.pick_checked(loaded, 1, set(), fresh, check_many, {}, rounds=1)
        self.assertNotIn("com.x.app", core[0])
        self.assertEqual(full[0]["com.x.app"][1]["versions"][0]["downloadURL"], "https://ok.io/old.ipa")

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

    def test_accretion_ids_only_from_accretion_sources(self):
        owner = merge.RESERVED["io.github.getaccretion."]
        self.assertTrue(
            merge.reserved_by_other("io.github.getaccretion.Accretion", "https://evil.example/s.json")
        )
        self.assertFalse(merge.reserved_by_other("io.github.getaccretion.Accretion", owner))
        self.assertTrue(merge.reserved_by_other("io.github.accretionmods.x", owner))
        self.assertFalse(merge.reserved_by_other("com.example.app", "https://evil.example/s.json"))

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

    def run_check(self, source_urls, state, results, dead_hosts=(), curated=None):
        import tempfile
        from unittest import mock

        import check_links

        source = {"apps": [{"versions": [{"downloadURL": u} for u in source_urls]}]}
        files = {"source.json": source, "dead_links.json": state}
        if curated is not None:
            files["curated.json"] = curated
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.multiple(
                check_links,
                load_json=lambda name, default: files.get(name, default),
                read_list=lambda name: list(dead_hosts) if name == "dead_hosts.txt" else [],
                path=lambda name: os.path.join(tmp, name),
                check=lambda url: (url, results[url]),
            ),
        ):
            check_links.main()
            with open(os.path.join(tmp, "dead_links.json")) as f:
                return json.load(f)

    def test_dropped_links_are_retested_until_they_work(self):
        old = {"fails": 3, "first": "2026-10-01", "last": "2026-10-09"}
        state = {"https://a.io/back.ipa": old, "https://a.io/still.ipa": old, "https://a.io/flaky.ipa": old}
        out = self.run_check(
            ["https://a.io/ok.ipa"],  # dropped links are no longer in source.json, still retested
            state,
            {
                "https://a.io/ok.ipa": "alive",
                "https://a.io/back.ipa": "alive",
                "https://a.io/still.ipa": "dead",
                "https://a.io/flaky.ipa": "unknown",
            },
        )
        self.assertNotIn("https://a.io/back.ipa", out)  # works again: reinstated on this build
        self.assertEqual(out["https://a.io/still.ipa"]["fails"], 4)  # still broken: kept, retried
        self.assertEqual(out["https://a.io/flaky.ipa"], old)  # no clear answer: unchanged

    def test_confirmed_dead_hosts_need_a_real_file_to_come_back(self):
        urls = ["https://gone.io/a.ipa", "https://gone.io/b.ipa", "https://ok.io/c.ipa"]
        res = {
            "https://gone.io/a.ipa": "unknown",
            "https://gone.io/b.ipa": "alive",
            "https://ok.io/c.ipa": "unknown",
        }
        out = self.run_check(urls, {}, res, dead_hosts=["gone.io"])
        self.assertIn("https://gone.io/a.ipa", out)  # no clear answer from a confirmed-dead host
        self.assertNotIn("https://gone.io/b.ipa", out)  # a real file again: reinstated
        self.assertNotIn("https://ok.io/c.ipa", out)  # elsewhere, no clear answer changes nothing

    def test_core_list_links_and_icons_are_checked_too(self):
        core = {
            "apps": [
                {
                    "iconURL": "https://gone.io/icon.png",
                    "versions": [{"downloadURL": "https://gone.io/a.ipa"}],
                }
            ]
        }
        out = self.run_check(
            ["https://ok.io/x.ipa"],
            {},
            {
                "https://ok.io/x.ipa": "alive",
                "https://gone.io/icon.png": "dead",
                "https://gone.io/a.ipa": "dead",
            },
            curated=core,
        )
        self.assertIn("https://gone.io/icon.png", out)
        self.assertIn("https://gone.io/a.ipa", out)

    def test_confirmed_dead_hosts_skip_the_host_wide_grace(self):
        urls = [f"https://{h}/{i}.ipa" for h in ("down.io", "gone.io") for i in range(60)]
        out = self.run_check(urls, {}, dict.fromkeys(urls, "dead"), dead_hosts=["Gone.io"])
        self.assertTrue(out["https://down.io/0.ipa"]["host_wide"])  # one more check first
        self.assertFalse(out["https://gone.io/0.ipa"]["host_wide"])  # confirmed: dropped now


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


class SitemapTest(unittest.TestCase):
    def load_site(self):
        import importlib.util

        # scripts/site.py shares its name with the stdlib "site" module, so load it by path
        spec = importlib.util.spec_from_file_location(
            "store_site", os.path.join(os.path.dirname(__file__), "..", "scripts", "site.py")
        )
        store = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(store)
        return store

    def test_lists_the_store_and_every_app_page_with_robots(self):
        import tempfile
        import xml.etree.ElementTree as ET

        store = self.load_site()
        apps = [
            {
                "bundleIdentifier": "com.a.one",
                "versions": [{"date": "2025-01-02T10:00:00"}, {"date": "2026-03-04"}],
            },
            {"bundleIdentifier": "com.b&two", "versions": [{"date": "bad"}]},
            {"bundleIdentifier": "com.c.three", "versions": []},
        ]
        with tempfile.TemporaryDirectory() as out:
            store.sitemap("https://getaccretion.github.io/", apps, out)
            ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            rows = ET.parse(os.path.join(out, "sitemap.xml")).getroot().findall("s:url", ns)
            urls = [r.find("s:loc", ns).text for r in rows]
            lastmod = {r.find("s:loc", ns).text: r.find("s:lastmod", ns) for r in rows}
            with open(os.path.join(out, "robots.txt")) as f:
                robots = f.read()
        self.assertEqual(
            urls,
            [
                "https://getaccretion.github.io/",
                "https://getaccretion.github.io/app/com.a.one/",
                "https://getaccretion.github.io/app/com.c.three/",
            ],  # com.b&two is not a safe page name, so it has no page
        )
        self.assertEqual(lastmod["https://getaccretion.github.io/app/com.a.one/"].text, "2026-03-04")
        self.assertIsNone(lastmod["https://getaccretion.github.io/app/com.c.three/"])
        self.assertEqual(
            robots, "User-agent: *\nAllow: /\nSitemap: https://getaccretion.github.io/sitemap.xml\n"
        )

    def test_splits_into_an_index_above_the_limit(self):
        import tempfile

        store = self.load_site()
        apps = [{"bundleIdentifier": f"com.a.app{i}", "versions": []} for i in range(5)]
        with tempfile.TemporaryDirectory() as out, mock.patch.object(store, "SITEMAP_LIMIT", 3):
            store.sitemap("https://x.example", apps, out)
            with open(os.path.join(out, "sitemap.xml")) as f:
                index = f.read()
            files = sorted(f for f in os.listdir(out) if f.startswith("sitemap-"))
        self.assertIn("<sitemapindex", index)
        self.assertEqual(files, ["sitemap-1.xml", "sitemap-2.xml"])


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
        self.assertIn(("CHECK", "https://oldref.supabase.co", "anon-key"), calls)  # public read verified
        self.assertTrue(any(isinstance(c[2], dict) and "ben_w" in c[2].get("query", "") for c in calls))

    def test_rejects_unsafe_admin_name(self):
        with self.assertRaises(SystemExit):
            self.run_setup(projects=[{"id": "r", "name": "accretion"}], admin="x'; drop table posts;--")


class SignInProviders(unittest.TestCase):
    def env(self, **values):
        from unittest import mock

        keys = [
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "GH_OAUTH_CLIENT_ID",
            "GH_OAUTH_CLIENT_SECRET",
            "DISCORD_CLIENT_ID",
            "DISCORD_CLIENT_SECRET",
            "APPLE_SERVICES_ID",
            "APPLE_TEAM_ID",
            "APPLE_KEY_ID",
            "APPLE_PRIVATE_KEY",
            "APPLE_SECRET",
            "GOOGLE_KEYS",
            "GIT_KEYS",
            "DISCORD_KEYS",
            "SMTP",
            "SMTP_USER",
            "SMTP_PASS",
            "SMTP_HOST",
            "SMTP_PORT",
        ]
        clean = dict.fromkeys(keys, "")
        clean.update(values)
        return mock.patch.dict(os.environ, clean)

    def test_only_providers_with_keys_are_switched_on(self):
        import supabase_setup as setup

        with self.env(GOOGLE_CLIENT_ID="g-id", GOOGLE_CLIENT_SECRET="g-secret", DISCORD_CLIENT_ID="d-id"):
            out = setup.provider_settings()
        self.assertEqual(out["external_google_client_id"], "g-id")
        self.assertTrue(out["external_google_enabled"])
        self.assertNotIn("external_discord_enabled", out)  # secret missing
        self.assertNotIn("external_apple_enabled", out)

    def test_one_secret_can_hold_both_keys(self):
        from unittest import mock

        import supabase_setup as setup

        gid, gsec = "123-abc.apps.googleusercontent.com", "GOCSPX-a1_b2-c3"
        hid, hsec = "Ov23liAbCdEf12345678", "0123456789abcdef0123456789abcdef01234567"
        did, dsec = "1558396810000000000", "A" * 16 + "b-c_" * 4
        with self.env(
            GOOGLE_KEYS=f"{gsec}\n{gid}\n",  # reversed, two lines
            GIT_KEYS=f"Client ID: {hid}\nClient secret: {hsec}",  # labelled
            DISCORD_KEYS=f"{did} {dsec}",
        ):
            out = setup.provider_settings()
        self.assertEqual((out["external_google_client_id"], out["external_google_secret"]), (gid, gsec))
        self.assertEqual((out["external_github_client_id"], out["external_github_secret"]), (hid, hsec))
        self.assertEqual((out["external_discord_client_id"], out["external_discord_secret"]), (did, dsec))
        with (
            self.env(DISCORD_KEYS=dsec),  # only the secret saved: ID comes from providers.json
            mock.patch.object(setup, "public_client_ids", return_value={"discord": did}),
        ):
            self.assertEqual(setup.provider_settings()["external_discord_client_id"], did)
        with self.env(DISCORD_KEYS=did), mock.patch.object(setup, "public_client_ids", return_value={}):
            self.assertNotIn("external_discord_enabled", setup.provider_settings())  # only half

    def test_mail_account_from_one_secret(self):
        import supabase_setup as setup

        with self.env():
            self.assertEqual(setup.smtp_settings(), {})  # none set: built-in sender
        with self.env(SMTP="getaccretion@gmail.com\nabcd efgh ijkl mnop"):
            out = setup.smtp_settings()
        self.assertEqual(out["smtp_user"], "getaccretion@gmail.com")
        self.assertEqual(out["smtp_pass"], "abcdefghijklmnop")  # Gmail's spaces dropped
        self.assertEqual((out["smtp_host"], out["smtp_port"]), ("smtp.gmail.com", "465"))
        self.assertIn("{{ .ConfirmationURL }}", out["mailer_templates_confirmation_content"])
        self.assertEqual(out["mailer_subjects_recovery"], "Reset your Accretion password")
        with self.env(SMTP_USER="a@b.io", SMTP_PASS="p w", SMTP_HOST="smtp.b.io", SMTP_PORT="587"):
            out = setup.smtp_settings()
        self.assertEqual((out["smtp_pass"], out["smtp_host"], out["smtp_port"]), ("p w", "smtp.b.io", "587"))

    def test_popularity_counts_sources_and_web_picks(self):
        import importlib.util

        # scripts/site.py shares its name with the stdlib "site" module, so load it by path
        spec = importlib.util.spec_from_file_location(
            "store_site", os.path.join(os.path.dirname(__file__), "..", "scripts", "site.py")
        )
        store = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(store)
        carriers = {"com.spotify.client": 18, "x.y": 2}
        picks = {"com.spotify.client", "com.rileytestut.Delta"}
        self.assertEqual(store.popularity("com.spotify.client", carriers, picks), 18 + store.WEB_PICK)
        self.assertEqual(store.popularity("com.rileytestut.Delta", carriers, picks), store.WEB_PICK)
        self.assertEqual(store.popularity("x.y", carriers, picks), 2)
        self.assertEqual(store.popularity("nobody", carriers, picks), 0)

    def test_apple_secret_is_a_signed_jwt(self):
        try:
            import jwt
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ec
        except ImportError:
            self.skipTest("pyjwt[crypto] not installed")
        import supabase_setup as setup

        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode()
        with self.env(
            APPLE_SERVICES_ID="io.accretion.signin",
            APPLE_TEAM_ID="TEAM123",
            APPLE_KEY_ID="KEY123",
            APPLE_PRIVATE_KEY=pem,
        ):
            out = setup.provider_settings()
        token = out["external_apple_secret"]
        claims = jwt.decode(
            token, key.public_key(), algorithms=["ES256"], audience="https://appleid.apple.com"
        )
        self.assertEqual(claims["iss"], "TEAM123")
        self.assertEqual(claims["sub"], "io.accretion.signin")
        self.assertLessEqual(claims["exp"] - claims["iat"], 180 * 86400)  # Apple's 6-month limit
        self.assertEqual(jwt.get_unverified_header(token)["kid"], "KEY123")


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

    def test_down_sources_are_kept_and_retried_until_they_work(self):
        import tempfile
        from unittest import mock

        ok = {"ok": True, "name": "Up", "apps": 3, "final_url": "u", "fingerprint": "f1", "size": 9}
        back = {**ok, "name": "Back", "final_url": "b", "fingerprint": "f2"}
        down = {"ok": False, "error": "HTTPError: 404"}
        long_ago = {"name": "Old", "apps": 5, "size": 1, "first_seen": "2025-01-01", "last_ok": "2025-01-02"}
        state = {
            "https://up.io/s.json": {**long_ago, "name": "Up"},
            "https://down.io/s.json": long_ago,  # down for months: still kept
            "https://back.io/s.json": {**long_ago, "down_since": "2026-01-01"},
        }
        results = {"https://up.io/s.json": ok, "https://down.io/s.json": down, "https://back.io/s.json": back}
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.multiple(
                discover,
                load_json=lambda name, default: state if name == "discovered.json" else default,
                read_list=lambda name: [],
                from_pages=lambda: set(),
                from_github=lambda: set(),
                check=lambda url: (url, results[url]),
                path=lambda name: os.path.join(tmp, name),
                log=lambda *a: None,
            ),
        ):
            discover.main()
            with open(os.path.join(tmp, "discovered.json")) as f:
                out = json.load(f)
            with open(os.path.join(tmp, "discovered.txt")) as f:
                listed = f.read()
        self.assertIn("https://down.io/s.json", out)
        self.assertTrue(out["https://down.io/s.json"]["down_since"])
        self.assertIn("https://down.io/s.json", listed)  # merge keeps retrying it every build
        self.assertNotIn("down_since", out["https://back.io/s.json"])  # working again: reinstated
        self.assertEqual(out["https://back.io/s.json"]["name"], "Back")


if __name__ == "__main__":
    unittest.main()
