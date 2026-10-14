import datetime as dt
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/staging_cleanup.py"


class Storage:
    def __init__(self):
        self.deleted = []

    def remove(self, name):
        self.deleted.append(name)


class StagingCleanup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = None
        if SCRIPT.exists():
            spec = importlib.util.spec_from_file_location("staging_cleanup", SCRIPT)
            cls.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)

    def setUp(self):
        self.assertIsNotNone(self.module, "Staging cleanup must provide a bounded dry-run")
        self.now = dt.datetime(2026, 10, 14, 12, tzinfo=dt.timezone.utc)
        self.storage = Storage()

    def row(self, name, age=72, updated_age=None):
        return {
            "name": name,
            "created_at": (self.now - dt.timedelta(hours=age)).isoformat(),
            "updated_at": (
                self.now - dt.timedelta(hours=age if updated_age is None else updated_age)
            ).isoformat(),
        }

    def run_cleanup(self, rows, **kwargs):
        options = {"now": self.now, "recheck": lambda names: [row for row in rows if row["name"] in names]}
        options.update(kwargs)
        return self.module.cleanup(self.storage, rows, **options)

    def test_default_dry_run_never_deletes(self):
        report = self.run_cleanup([self.row("staging/old/build.upload")])
        self.assertEqual(report["eligible"], 1)
        self.assertEqual(report["removed"], 0)
        self.assertEqual(self.storage.deleted, [])

    def test_only_old_staging_objects_can_be_removed(self):
        rows = [
            self.row("staging/old/build.upload"),
            self.row("staging/boundary/build.upload", 48),
            self.row("staging/recent/build.upload", 47),
            self.row("staging/updated/build.upload", updated_age=2),
            self.row("bases/private-input"),
            self.row("bundle/final.ipa"),
            self.row("staging-other/file"),
            self.row("staging/../bases/file"),
        ]
        report = self.run_cleanup(rows, apply=True)
        self.assertEqual(report["removed"], 2)
        self.assertEqual(self.storage.deleted, [rows[0]["name"], rows[1]["name"]])

    def test_invalid_dates_future_objects_and_naive_dates_are_retained(self):
        rows = [
            self.row("staging/bad/file"),
            self.row("staging/future/file", -2),
            self.row("staging/naive/file"),
        ]
        rows[0]["updated_at"] = "invalid"
        rows[2]["created_at"] = rows[2]["updated_at"] = "2026-10-01T12:00:00"
        self.assertEqual(self.run_cleanup(rows, apply=True)["removed"], 0)

    def test_apply_rechecks_metadata_and_deletion_count_is_bounded(self):
        rows = [self.row(f"staging/old/{i}.upload") for i in range(5)]
        fresh = [rows[0], self.row(rows[1]["name"], updated_age=0)]
        report = self.run_cleanup(rows, apply=True, max_delete=2, recheck=lambda _: fresh)
        self.assertEqual(report["removed"], 1)
        self.assertEqual(self.storage.deleted, [rows[0]["name"]])

    def test_apply_requires_recheck_and_cannot_lower_minimum_age(self):
        rows = [self.row("staging/old/file")]
        for options in ({"min_age_hours": 47}, {"max_delete": 101}, {"recheck": None}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.run_cleanup(rows, apply=True, **options)
        self.assertEqual(self.storage.deleted, [])

    def test_inspection_never_consumes_more_than_500_records(self):
        consumed = []

        def rows():
            for index in range(1000):
                consumed.append(index)
                yield self.row(f"staging/old/{index}.upload")

        self.module.cleanup(self.storage, rows(), now=self.now)
        self.assertEqual(len(consumed), 500)

    def test_failed_fresh_metadata_check_stops_before_any_deletion(self):
        rows = [self.row("staging/old/build.upload"), self.row("bases/final")]
        with (
            mock.patch.object(self.module, "metadata", side_effect=OSError("fictional unavailable")),
            self.assertRaises(OSError),
        ):
            self.run_cleanup(rows, apply=True, recheck=lambda names: self.module.metadata("example", names))
        self.assertEqual(self.storage.deleted, [])

    def test_metadata_query_is_scoped_and_limited(self):
        with mock.patch.object(self.module, "sql", return_value=[]) as sql:
            self.module.metadata("fictional")
        query = sql.call_args.args[1]
        self.assertIn("bucket_id = 'builds'", query)
        self.assertIn("name like 'staging/%'", query)
        self.assertIn("limit 500", query)


if __name__ == "__main__":
    unittest.main()
