import importlib.util
import os
import sys
import unittest
import urllib.parse

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)

# scripts/site.py by path: "import site" would give Python's own site module
_spec = importlib.util.spec_from_file_location("store_site", os.path.join(SCRIPTS, "site.py"))
store_site = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(store_site)

BASE = "https://fixture.supabase.co"
SOURCE = {
    "name": "Fixture",
    "apps": [
        {
            "bundleIdentifier": "com.fixture.app",
            "name": "Fixture App",
            "downloadURL": "https://secret.invalid/files/app-2.0.ipa",
            "versions": [
                {"version": "2.0", "downloadURL": "https://secret.invalid/files/app-2.0.ipa"},
                {"version": "1.9 beta", "downloadURL": "https://secret.invalid/files/app-1.9.ipa"},
            ],
        },
        {
            "bundleIdentifier": "com.fixture.old",
            "version": "1.0",
            "downloadURL": "https://secret.invalid/old.ipa",
        },
    ],
}


class PrivateLinks(unittest.TestCase):
    def test_server_link_names_app_and_version(self):
        link = store_site.server_link(BASE, "com.fixture.app", "1.9 beta")
        parts = urllib.parse.urlsplit(link)
        self.assertEqual(f"{parts.scheme}://{parts.netloc}{parts.path}", f"{BASE}/functions/v1/download")
        self.assertEqual(
            urllib.parse.parse_qs(parts.query), {"app": ["com.fixture.app"], "version": ["1.9 beta"]}
        )

    def test_private_source_keeps_no_source_url(self):
        out = store_site.private_source(SOURCE, BASE)
        text = str(out)
        self.assertNotIn("secret.invalid", text)
        app = out["apps"][0]
        self.assertEqual(app["downloadURL"], app["versions"][0]["downloadURL"])
        self.assertIn("version=2.0", app["downloadURL"])
        self.assertIn("version=1.9+beta", app["versions"][1]["downloadURL"])
        self.assertIn("version=1.0", out["apps"][1]["downloadURL"])
        self.assertIn("secret.invalid", str(SOURCE), "the input is not changed")

    def test_config_values_are_all_text(self):
        # the app parses config.js as text only: a bool there breaks sign-in in every installed copy
        for private in (False, True):
            for proxy in ("", "https://dl.x.invalid/"):
                config = store_site.public_config("https://x.supabase.co", "anon", private, proxy)
                self.assertTrue(all(isinstance(v, str) for v in config.values()), config)
        on = store_site.public_config("https://x.supabase.co", "anon", True, "https://dl.x.invalid/")
        self.assertEqual((on["privateLinks"], on["downloadProxy"]), ("1", "1"))
        self.assertEqual(on["downloadOrigin"], "https://dl.x.invalid", "the site's download address")
        self.assertNotIn("downloadProxy", store_site.public_config("https://x.supabase.co", "anon"))

    def test_store_sources_keep_an_empty_url(self):
        # the app decodes store.json with a required "url" on every source
        out = store_site.private_sources(
            [{"name": "A", "url": "https://secret.invalid/a.json", "core": True}]
        )
        self.assertEqual(out, [{"name": "A", "url": "", "core": True}])

    def test_switch_reads_the_variable(self):
        for value, on in (("true", True), ("1", True), ("on", True), ("", False), ("false", False)):
            os.environ["PRIVATE_LINKS"] = value
            self.assertEqual(store_site.private_links(), on, value)
        os.environ.pop("PRIVATE_LINKS", None)


if __name__ == "__main__":
    unittest.main()
