import os
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import ai_jobs
import llm
import sanitize
from common import hide_nsfw_icons, icon_key, nsfw_icon_keys
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
            raise http(503)

        def fake_group(specs, *_):
            seen.append(list(specs))
            if len(seen) == 2:
                raise http(429)
            return "hello", specs[-1]

        with mock.patch.object(llm, "call", fake), mock.patch.object(llm, "call_group", fake_group):
            self.assertIsNone(llm.ask("t", "s", "u"))
            self.assertEqual(llm.busy, {"gemini:g1", "openrouter:a/b:free", "openrouter:c/d:free"})
            llm.busy.discard("openrouter:c/d:free")
            llm.busy.add("openrouter:a/b:free")
            self.assertEqual(llm.ask("t", "s", "u"), None)  # c/d alone goes to call(), which is busy again
        self.assertEqual(
            seen, ["gemini:g1", ["openrouter:a/b:free", "openrouter:c/d:free"], "openrouter:c/d:free"]
        )

    def test_skips_providers_without_a_key(self):
        seen = []
        one = {"order": ["gemini:g1", "openrouter:a/b:free"], "moderation": ""}
        with (
            mock.patch.object(llm, "config", return_value=one),
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
            mock.patch.object(llm, "call_group", side_effect=AssertionError("paid model called")),
            mock.patch.object(llm, "post", side_effect=AssertionError("paid model called")),
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
        bad = '{"subtitle": "s", "category": "nope"}'
        with (
            mock.patch.object(llm, "call", return_value=bad) as call,
            mock.patch.object(llm, "call_group", side_effect=lambda specs, *_: (bad, specs[0])) as group,
        ):
            self.assertIsNone(llm.ask("t", "s", "u", SCHEMA))
        # gemini: 2 tries; group: 2 tries, then 2 more for the remaining model alone
        self.assertEqual(call.call_count, 2 + 2)
        self.assertEqual(group.call_count, 2)


class GroupTest(unittest.TestCase):
    def setUp(self):
        llm.busy.clear()
        mock.patch.object(llm, "config", return_value=ORDER).start()
        mock.patch.dict(os.environ, {**KEYS, "GEMINI_API_KEY": ""}).start()

    def tearDown(self):
        mock.patch.stopall()

    @staticmethod
    def reply(text, model="a/b:free"):
        return {"model": model, "choices": [{"message": {"content": text}}]}

    def test_two_openrouter_specs_go_out_as_one_request(self):
        bodies = []

        def fake(url, headers, body):
            bodies.append(body)
            return self.reply("hello")

        with mock.patch.object(llm, "post", fake):
            self.assertEqual(llm.ask("t", "s", "u"), "hello")
        self.assertEqual(len(bodies), 1)
        self.assertEqual(bodies[0]["models"], ["a/b:free", "c/d:free"])
        self.assertNotIn("model", bodies[0])

    def test_last_model_comes_from_the_response(self):
        with mock.patch.object(llm, "post", return_value=self.reply("hello", "c/d:free")):
            llm.ask("t", "s", "u")
        self.assertEqual(llm.last_model, "openrouter:c/d:free")
        with mock.patch.object(llm, "post", return_value=self.reply("hello", "other/x")):
            llm.ask("t", "s", "u")
        self.assertEqual(llm.last_model, "openrouter:other/x")

    def test_a_429_marks_every_model_in_the_group_busy(self):
        with mock.patch.object(llm, "post", side_effect=http(429)) as post:
            self.assertIsNone(llm.ask("t", "s", "u"))
            self.assertIsNone(llm.ask("t", "s", "u"))
        self.assertEqual(llm.busy, {"openrouter:a/b:free", "openrouter:c/d:free"})
        self.assertEqual(post.call_count, 1)

    def test_groups_hold_at_most_three_models(self):
        five = {"order": [f"openrouter:m{i}/x:free" for i in range(5)], "moderation": ""}
        bodies = []

        def fake(url, headers, body):
            bodies.append(body["models"])
            raise http(503)

        with mock.patch.object(llm, "config", return_value=five), mock.patch.object(llm, "post", fake):
            llm.ask("t", "s", "u")
        self.assertEqual([len(b) for b in bodies], [3, 2])

    def test_a_model_that_answers_badly_twice_is_dropped_from_the_group(self):
        bodies = []

        def fake(url, headers, body):
            bodies.append(body)
            if "models" in body:
                return self.reply('{"subtitle": "s", "category": "nope"}', "a/b:free")
            return self.reply(GOOD, "c/d:free")

        with mock.patch.object(llm, "post", fake):
            data = llm.ask("t", "s", "u", SCHEMA)
        self.assertEqual(data["category"], "games")
        self.assertEqual(len(bodies), 3)
        self.assertEqual(bodies[0]["models"], ["a/b:free", "c/d:free"])
        self.assertEqual(bodies[2]["model"], "c/d:free")
        self.assertNotIn("models", bodies[2])
        self.assertEqual(llm.last_model, "openrouter:c/d:free")

    def test_a_single_spec_order_sends_a_model_body(self):
        one = {"order": ["openrouter:a/b:free"], "moderation": ""}
        bodies = []

        def fake(url, headers, body):
            bodies.append(body)
            return self.reply("hello")

        with mock.patch.object(llm, "config", return_value=one), mock.patch.object(llm, "post", fake):
            self.assertEqual(llm.ask("t", "s", "u"), "hello")
        self.assertEqual(bodies[0]["model"], "a/b:free")
        self.assertNotIn("models", bodies[0])


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


class EmbedTest(unittest.TestCase):
    def setUp(self):
        mock.patch.dict(os.environ, KEYS).start()

    def tearDown(self):
        mock.patch.stopall()

    def test_batches_of_100_and_one_retry_on_429(self):
        calls = []

        def fake(url, headers, body):
            calls.append(len(body["requests"]))
            if len(calls) == 1:
                raise http(429)
            self.assertEqual(body["requests"][0]["outputDimensionality"], 4)
            return {"embeddings": [{"values": [1.0, 0, 0, 0]} for _ in body["requests"]]}

        with mock.patch.object(llm, "post", fake):
            out = llm.embed([f"t{i}" for i in range(150)], dims=4, pause=0)
        self.assertEqual(len(out), 150)
        self.assertEqual(calls, [100, 100, 50])

    def test_gives_up_after_a_second_busy_answer_or_without_a_key(self):
        with mock.patch.object(llm, "post", side_effect=http(503)):
            self.assertIsNone(llm.embed(["a"], pause=0))
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            self.assertIsNone(llm.embed(["a"]))

    def test_quantize_round_trip_and_top_k(self):
        vec = [0.5, -0.25, 0.125, 0.0, 1.0]
        scale, data = ai_jobs.quantize(vec)
        for a, b in zip(ai_jobs.dequantize(scale, data), vec, strict=True):
            self.assertAlmostEqual(a, b, delta=0.01)
        vectors = {
            "a": [1, 0, 0],
            "b": [0.9, 0.1, 0],
            "c": [0.8, 0.5, 0],
            "d": [0, 0, 1],
            "e": [1, 0, 0],
        }
        result, dups = ai_jobs.top_similar(vectors, k=2, duplicate_at=0.97)
        self.assertNotIn("a", result["a"])
        self.assertEqual(len(result["a"]), 2)
        self.assertEqual(result["a"][0], "e")  # the identical vector comes first
        for bid, others in result.items():
            self.assertNotIn(bid, others)
        self.assertEqual([(x, y) for x, y, _ in dups], [("a", "e"), ("a", "b"), ("b", "e")])
        self.assertTrue(all(x != y for x, y, _ in dups))

    def test_embed_text_prefers_a_matching_listing(self):
        app = {
            "bundleIdentifier": "x.y",
            "name": "N",
            "category": "games",
            "subtitle": "old",
            "localizedDescription": "d",
        }
        entry = {
            "src_hash": src_hash("N", "d", "games"),
            "subtitle": "new",
            "description": "clean",
            "category": "utilities",
        }
        self.assertEqual(ai_jobs.embed_text(app, {"x.y": entry}), "N. utilities. new. clean")
        entry["src_hash"] = "stale"
        self.assertEqual(ai_jobs.embed_text(app, {"x.y": entry}), "N. games. old. d")


class ImagesTest(unittest.TestCase):
    def setUp(self):
        llm.busy.clear()
        mock.patch.object(llm, "config", return_value={"order": ["openrouter:a/b:free", "gemini:g1"]}).start()
        mock.patch.dict(os.environ, KEYS).start()

    def tearDown(self):
        mock.patch.stopall()

    def test_only_gemini_models_see_images_and_status_is_validated(self):
        seen = []

        def fake(spec, *_):
            seen.append(spec)
            if len(seen) == 1:
                return '{"status": "weird", "note": "x"}'
            return '{"status": "nsfw", "note": "x"}'

        with mock.patch.object(llm, "call_image", fake):
            out = llm.ask_image("images", "s", "u", "image/png", b"x", ai_jobs.IMAGE_SCHEMA)
        self.assertEqual(out["status"], "nsfw")
        self.assertEqual(seen, ["gemini:g1", "gemini:g1"])  # a bad status gets one retry

    def test_download_failure_is_broken_without_a_model_call(self):
        with (
            mock.patch.object(ai_jobs, "fetch_image", return_value=(None, "download answered 404")),
            mock.patch.object(llm, "ask_image") as ask,
        ):
            entry = ai_jobs.check_image("https://x.example/i.png")
        self.assertEqual((entry["status"], entry["note"]), ("broken", "download answered 404"))
        ask.assert_not_called()

    def test_fetch_rejects_other_types_and_big_files(self):
        class Resp:
            def __init__(self, mime, size):
                self.headers = {"Content-Type": mime}
                self.size = size

            def read(self, n):
                return b"x" * min(n, self.size)

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        with mock.patch("urllib.request.urlopen", return_value=Resp("text/html; charset=utf-8", 5)):
            self.assertIsNone(ai_jobs.fetch_image("https://x.example/a")[0])
        with mock.patch("urllib.request.urlopen", return_value=Resp("image/png", 3 * 1024 * 1024)):
            self.assertIsNone(ai_jobs.fetch_image("https://x.example/a")[0])
        with mock.patch("urllib.request.urlopen", return_value=Resp("image/webp", 10)):
            self.assertEqual(ai_jobs.fetch_image("https://x.example/a")[0], "image/webp")

    def test_nsfw_icon_gets_the_placeholder_and_the_app_stays(self):
        ph = "https://s.example/assets/app-placeholder.png"
        apps = [
            {"bundleIdentifier": "a", "iconURL": "https://x.example/bad.png"},
            {"bundleIdentifier": "b", "iconURL": "https://x.example/fine.png"},
            {"bundleIdentifier": "c", "iconURL": "https://x.example/orig.png"},
        ]
        keys = {icon_key("https://x.example/bad.png"), icon_key("https://s.example/icons/c.jpg")}
        n = hide_nsfw_icons(apps, ph, keys, {"https://x.example/orig.png": "https://s.example/icons/c.jpg"})
        self.assertEqual(n, 2)
        self.assertEqual([a["iconURL"] for a in apps], [ph, "https://x.example/fine.png", ph])
        rows = {"k1": {"status": "nsfw"}, "k2": {"status": "ok"}, "k3": {"status": "broken"}}
        with mock.patch("common.load_json", return_value=rows):
            self.assertEqual(nsfw_icon_keys(), {"k1"})


if __name__ == "__main__":
    unittest.main()
