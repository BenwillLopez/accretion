import os
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import llm
import sanitize
from sanitize import clean_app, src_hash

ORDER = {
    "order": ["gemini:g1", "openrouter:a/b:free", "openrouter:c/d:free"],
    "moderation": "openrouter:m/safety:free",
}
KEYS = {"GEMINI_API_KEY": "x", "OPENROUTER_API_KEY": "y"}
GOOD = '{"subtitle": "s", "category": "games"}'
SCHEMA = {"subtitle": "str", "category": sorted(sanitize.CATEGORIES)}


def http(code):
    return urllib.error.HTTPError("https://x.example", code, "err", {}, None)


class RouterTest(unittest.TestCase):
    def setUp(self):
        llm.busy.clear()
        mock.patch.object(llm, "config", return_value=ORDER).start()
        mock.patch.dict(os.environ, KEYS).start()

    def tearDown(self):
        mock.patch.stopall()

    def test_falls_back_in_order_and_remembers_busy(self):
        seen = []

        def fake(spec, *_):
            seen.append(spec)
            if spec == "gemini:g1":
                raise http(503)
            if spec == "openrouter:a/b:free":
                raise http(429)
            return "hello"

        with mock.patch.object(llm, "call", fake):
            self.assertEqual(llm.ask("t", "s", "u"), "hello")
            self.assertEqual(llm.last_model, "openrouter:c/d:free")
            self.assertEqual(llm.ask("t", "s", "u"), "hello")
        self.assertEqual(
            seen, ["gemini:g1", "openrouter:a/b:free", "openrouter:c/d:free", "openrouter:c/d:free"]
        )

    def test_skips_providers_without_a_key(self):
        seen = []
        with (
            mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}),
            mock.patch.object(llm, "call", lambda spec, *_: seen.append(spec) or "ok"),
        ):
            llm.ask("t", "s", "u")
        self.assertEqual(seen, ["openrouter:a/b:free"])

    def test_never_calls_a_paid_openrouter_model(self):
        paid = {"order": ["openrouter:a/b"], "moderation": ""}
        with (
            mock.patch.object(llm, "config", return_value=paid),
            mock.patch.object(llm, "call", side_effect=AssertionError("paid model called")),
        ):
            self.assertIsNone(llm.ask("t", "s", "u"))

    def test_schema_rejects_a_bad_category_then_retries_once(self):
        replies = iter(['{"subtitle": "s", "category": "nonsense"}', "```json\n" + GOOD + "\n```"])
        prompts = []

        def fake(spec, system, user, _):
            prompts.append(user)
            return next(replies)

        with mock.patch.object(llm, "call", fake):
            data = llm.ask("t", "s", "u", SCHEMA)
        self.assertEqual(data["category"], "games")
        self.assertIn("rejected", prompts[1])

    def test_schema_gives_up_after_one_retry_per_model(self):
        with mock.patch.object(llm, "call", return_value='{"subtitle": "s", "category": "nope"}') as call:
            self.assertIsNone(llm.ask("t", "s", "u", SCHEMA))
        self.assertEqual(call.call_count, 2 * 3)


class OverlayTest(unittest.TestCase):
    def setUp(self):
        self.app = {
            "name": "Foo",
            "bundleIdentifier": "com.example.foo",
            "developerName": "Dev",
            "localizedDescription": "spam.com | Foo IPA (No Ads)",
            "category": "other",
            "iconURL": "https://example.com/i.png",
        }
        self.versions = [
            {"version": "1", "date": "2025-01-01", "size": 1, "downloadURL": "https://example.com/a.ipa"}
        ]
        plain = clean_app(self.app, self.versions)
        self.hash = src_hash(plain["name"], plain["localizedDescription"], plain["category"])

    def tearDown(self):
        sanitize.AI_LISTINGS = {}
        sanitize.AI_EXTRAS.clear()

    def entry(self, **extra):
        return {
            "src_hash": self.hash,
            "subtitle": "A foo game",
            "description": "Foo is a game.",
            "features": ["No Ads"],
            "category": "games",
            "tags": ["foo"],
            **extra,
        }

    def test_matching_hash_applies(self):
        sanitize.AI_LISTINGS = {"com.example.foo": self.entry()}
        out = clean_app(self.app, self.versions)
        self.assertEqual(out["subtitle"], "A foo game")
        self.assertEqual(out["localizedDescription"], "Foo is a game.")
        self.assertEqual(out["category"], "games")
        self.assertNotIn("features", out)
        self.assertEqual(sanitize.AI_EXTRAS["com.example.foo"]["features"], ["No Ads"])
        self.assertEqual(
            sanitize.validate({"name": "n", "identifier": "i", "nsfw": False, "apps": [out]}), []
        )

    def test_changed_source_ignores_the_listing(self):
        sanitize.AI_LISTINGS = {"com.example.foo": self.entry()}
        out = clean_app({**self.app, "localizedDescription": "New text"}, self.versions)
        self.assertEqual(out["localizedDescription"], "New text")
        self.assertNotIn("com.example.foo", sanitize.AI_EXTRAS)

    def test_bad_category_is_not_applied(self):
        sanitize.AI_LISTINGS = {"com.example.foo": self.entry(category="nonsense")}
        self.assertEqual(clean_app(self.app, self.versions)["category"], "other")


if __name__ == "__main__":
    unittest.main()
