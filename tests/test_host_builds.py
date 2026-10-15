import hashlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import host_builds

GOOD = hashlib.sha256(b"IPA").hexdigest()


def app(url="https://files.invalid/a.ipa", digest=GOOD, version="1.0"):
    return {
        "bundleIdentifier": "com.fixture",
        "versions": [{"version": version, "downloadURL": url, "sha256": digest}],
    }


class Copyable(unittest.TestCase):
    def test_takes_only_https_with_a_published_fingerprint(self):
        self.assertEqual(
            host_builds.copyable(app())[0], ("com.fixture", "1.0", "https://files.invalid/a.ipa", GOOD)
        )
        self.assertEqual(host_builds.copyable(app(url="http://files.invalid/a.ipa")), (None, "not https"))
        self.assertEqual(host_builds.copyable(app(url="file:///etc/passwd")), (None, "not https"))
        self.assertEqual(host_builds.copyable(app(digest="")), (None, "no published sha256"))
        self.assertEqual(host_builds.copyable(app(digest="xyz")), (None, "no published sha256"))
        self.assertEqual(
            host_builds.copyable(app(url="https://x.supabase.co/functions/v1/download?app=a")),
            (None, "already served by the download function"),
        )
        self.assertEqual(
            host_builds.copyable({"bundleIdentifier": "com.fixture"}), (None, "incomplete entry")
        )


class FetchChecked(unittest.TestCase):
    def fetch(self, body, digest=GOOD, limit=None):
        response = mock.MagicMock()
        response.__enter__.return_value = io.BytesIO(body)
        out = io.BytesIO()
        with (
            mock.patch.object(host_builds.urllib.request, "urlopen", return_value=response),
            mock.patch.object(host_builds, "MAX_BYTES", limit or host_builds.MAX_BYTES),
        ):
            return host_builds.fetch_checked("https://files.invalid/a.ipa", digest, out)

    def test_matching_file_passes(self):
        self.assertTrue(self.fetch(b"IPA"))

    def test_changed_file_fails(self):
        self.assertFalse(self.fetch(b"TROJAN"))

    def test_oversized_file_stops(self):
        self.assertFalse(self.fetch(b"IPA" * 10, digest=hashlib.sha256(b"IPA" * 10).hexdigest(), limit=8))


if __name__ == "__main__":
    unittest.main()
