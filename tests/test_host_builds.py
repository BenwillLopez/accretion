import hashlib
import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/host_builds.py"

DATA = b"not really an ipa"
SHA = hashlib.sha256(DATA).hexdigest()


def app(**changes):
    version = {
        "version": "1.2.3",
        "downloadURL": "https://example.invalid/app.ipa",
        "sha256": SHA,
        "size": len(DATA),
    }
    version.update(changes)
    return {"bundleIdentifier": "com.fixture.app", "versions": [version]}


class HostBuilds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("host_builds", SCRIPT)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_fingerprinted_https_listing_is_hosted_under_its_sha256(self):
        build, reason = self.module.listing(app())
        self.assertEqual(reason, "")
        self.assertEqual(build["sha256"], SHA)
        self.assertEqual(self.module.object_path(build), f"com.fixture.app/1.2.3-{SHA}.ipa")
        self.assertEqual(self.module.verify(DATA, build), SHA)

    def test_listing_without_sha256_is_never_hosted(self):
        build, reason = self.module.listing(app(sha256=None))
        self.assertIsNone(build)
        self.assertIn("sha256", reason)
        build, reason = self.module.listing(app(sha256="not-hex"))
        self.assertIsNone(build)

    def test_plain_http_and_download_server_links_are_skipped(self):
        build, reason = self.module.listing(app(downloadURL="http://example.invalid/app.ipa"))
        self.assertIsNone(build)
        self.assertIn("https", reason)
        served = "https://fixture.supabase.co/functions/v1/download?app=com.fixture.app"
        build, reason = self.module.listing(app(downloadURL=served))
        self.assertIsNone(build)
        self.assertIn("download function", reason)

    def test_mismatching_file_is_refused(self):
        build, _ = self.module.listing(app())
        with self.assertRaises(ValueError):
            self.module.verify(DATA + b"!", build)
        build, _ = self.module.listing(app(sha256="0" * 64))
        with self.assertRaises(ValueError):
            self.module.verify(DATA, build)

    def test_size_is_optional_but_checked_when_given(self):
        build, _ = self.module.listing(app(size=None))
        self.assertIsNone(build["size"])
        self.assertEqual(self.module.verify(DATA, build), SHA)
        build, reason = self.module.listing(app(size="big"))
        self.assertIsNone(build)
        self.assertIn("size", reason)

    def test_bundle_and_version_must_look_like_the_upload_function_allows(self):
        bad = app()
        bad["bundleIdentifier"] = "../escape"
        self.assertIsNone(self.module.listing(bad)[0])
        self.assertIsNone(self.module.listing(app(version="1/2"))[0])


if __name__ == "__main__":
    unittest.main()
