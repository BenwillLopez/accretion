import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import copy_builds_to_s3 as copies
import health_check as health
import supabase_setup as setup


class ManagementRequests(unittest.TestCase):
    def response(self, data):
        result = mock.MagicMock()
        result.__enter__.return_value.read.return_value = json.dumps(data).encode()
        return result

    def failure(self, code):
        return urllib.error.HTTPError(
            "https://api.example.invalid", code, "unavailable", {}, io.BytesIO(b"fictional-private-value")
        )

    def test_transient_read_recovers_without_printing_response_body(self):
        output = io.StringIO()
        with (
            mock.patch.object(
                setup.urllib.request, "urlopen", side_effect=[self.failure(500), self.response([])]
            ) as request,
            mock.patch.object(setup.time, "sleep"),
            contextlib.redirect_stderr(output),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(setup.call("GET", "/projects"), [])
        self.assertEqual(request.call_count, 2)
        self.assertNotIn("fictional-private-value", output.getvalue())

    def test_write_is_not_retried_and_error_body_is_private(self):
        with (
            mock.patch.object(setup.urllib.request, "urlopen", side_effect=self.failure(500)) as request,
            self.assertRaises(SystemExit) as caught,
        ):
            setup.call("POST", "/projects", {"private": "fictional"})
        self.assertEqual(request.call_count, 1)
        self.assertNotIn("fictional-private-value", str(caught.exception))

    def test_read_retries_are_bounded_and_auth_failure_is_immediate(self):
        for code, attempts in [(503, 3), (401, 1), (429, 3)]:
            with (
                self.subTest(code=code),
                mock.patch.object(
                    setup.urllib.request,
                    "urlopen",
                    side_effect=self.failure(code),
                ) as request,
                mock.patch.object(setup.time, "sleep"),
                self.assertRaises(SystemExit),
            ):
                setup.call("GET", "/projects")
            self.assertEqual(request.call_count, attempts)


class HealthReport(unittest.TestCase):
    def test_fallback_keeps_latest_stable_when_betas_fill_the_retention_window(self):
        rows = [
            {"bundle_id": "io.github.getaccretion.Accretion", "version": version, "path": version}
            for version in ["1.0.29", "1.0.30", *[f"1.0.30.{i}" for i in range(1, 7)]]
        ]
        retained = copies.mirrored(rows, 5)
        self.assertIn("1.0.30", retained)
        self.assertNotIn("1.0.29", retained)
        self.assertIn("1.0.30.6", retained)

    def test_fetched_key_never_enters_report_stdout(self):
        public, commands = io.StringIO(), io.StringIO()
        fictional = "fictional-service-value-do-not-publish"
        with (
            mock.patch.object(copies, "call", return_value=[{"name": "service_role", "api_key": fictional}]),
            mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}),
            contextlib.redirect_stdout(public),
            contextlib.redirect_stderr(commands),
        ):
            self.assertEqual(copies.service_key("fictional"), fictional)
        self.assertNotIn(fictional, public.getvalue())
        self.assertIn("::add-mask::" + fictional, commands.getvalue())

    def test_local_key_lookup_does_not_print_a_runner_command(self):
        output = io.StringIO()
        with (
            mock.patch.object(
                copies, "call", return_value=[{"name": "service_role", "api_key": "fictional"}]
            ),
            mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
        ):
            self.assertEqual(copies.service_key("fixture"), "fictional")
        self.assertEqual(output.getvalue(), "")

    def run_health(self, builds, settings=None):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "project.json"
            config.write_text('{"url":"https://fictional.supabase.co"}', encoding="utf-8")
            usage = [{"storage_mb": 5, "database_mb": 10}]
            with (
                mock.patch.object(health, "path", return_value=config),
                mock.patch.object(health, "sql", side_effect=[builds, usage]),
                mock.patch.object(health, "service_key", return_value="fictional"),
                mock.patch.object(
                    health,
                    "supabase_link",
                    side_effect=lambda url, key, path: "https://example.invalid/" + path,
                ),
                mock.patch.object(
                    health, "cloudfront_link", side_effect=lambda path: "https://example.invalid/" + path
                ),
                mock.patch.object(
                    health, "oracle_link", side_effect=lambda path: "https://example.invalid/" + path
                ),
                mock.patch.object(health, "answers", return_value=200),
                mock.patch.object(
                    health,
                    "google_sign_in",
                    return_value="- ok: Google sign-in reaches Google's account page",
                ),
                mock.patch.object(health, "admob_week", return_value="- ok: AdMob checked"),
                mock.patch.dict(os.environ, settings or {}, clear=True),
                contextlib.redirect_stdout(output),
            ):
                health.main()
        return output.getvalue()

    def test_mirrors_check_stable_build_even_when_a_beta_is_newer(self):
        report = self.run_health(
            [
                {"version": "1.0.30", "path": "app/stable.ipa"},
                {"version": "1.0.30.1", "path": "app/beta.ipa"},
            ],
            {
                "CDN_DOMAIN": "example.invalid",
                "CDN_KEY_PAIR_ID": "fictional",
                "CDN_PRIVATE_KEY": "fictional",
                "OCI_BUILDS_HOST": "example.invalid",
                "OCI_LINK_SECRET": "fictional",
            },
        )
        self.assertIn("Newest Accretion build: 1.0.30 (`app/stable.ipa`)", report)
        self.assertNotIn("app/beta.ipa", report)

    def test_missing_mirror_configuration_is_actionable(self):
        report = self.run_health([{"version": "1.0.30", "path": "app/stable.ipa"}])
        self.assertIn("FAIL: CloudFront", report)
        self.assertIn("FAIL: Oracle", report)


if __name__ == "__main__":
    unittest.main()
