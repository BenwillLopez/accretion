import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/checked_push.py"


class CheckedPush(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = None
        if SCRIPT.exists():
            spec = importlib.util.spec_from_file_location("checked_push", SCRIPT)
            cls.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)

    def setUp(self):
        self.assertIsNotNone(
            self.module, "Generated commits need exact-SHA validation before main publication"
        )
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.repo = self.root / "checkout"
        self.repo.mkdir()
        self.git("init", "--bare", "--initial-branch=main", str(self.remote), cwd=self.root)
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.test")
        self.git("remote", "add", "origin", str(self.remote))
        (self.repo / "base.txt").write_text("base")
        self.git("add", ".")
        self.git("commit", "-m", "Base")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.git("push", "origin", "HEAD:main")
        (self.repo / "generated.txt").write_text("generated")
        self.git("add", ".")
        self.git("commit", "-m", "Generated")
        self.sha = self.git("rev-parse", "HEAD").strip()
        self.dispatched = []
        self.failure = False
        self.bad_sha = False
        self.race = False
        self.push_race = False
        self.queued = False
        self.missing_job = False
        self.statuses = []
        self.status_api_error = False
        self.failed_workflow = ""
        self.delete_error = False

    def git(self, *args, cwd=None):
        return subprocess.check_output(
            ["git", *args], cwd=cwd or self.repo, text=True, stderr=subprocess.DEVNULL
        )

    def remote_main(self):
        return self.git("--git-dir", str(self.remote), "rev-parse", "main").strip()

    def advance_remote(self):
        commit = self.git(
            "commit-tree", self.base + "^{tree}", "-p", self.base, "-m", "Concurrent update"
        ).strip()
        self.git("push", "origin", commit + ":main")
        return commit

    def transport(self, args, **kwargs):
        if args[0] == "git":
            if self.push_race and args[1] == "push" and args[-1].endswith(":refs/heads/main"):
                self.push_race = False
                self.advance_remote()
            if self.delete_error and args[1] == "push" and "--delete" in args:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="fictional denied")
            return subprocess.run(args, **kwargs)
        self.assertEqual(args[0], "gh")
        if args[1:3] == ["workflow", "run"]:
            self.dispatched.append((args[3], args[args.index("--ref") + 1]))
            data = ""
        elif args[1:3] == ["run", "list"]:
            workflow = args[args.index("--workflow") + 1]
            identifier = next(i + 1 for i, item in enumerate(self.dispatched) if item[0] == workflow)
            data = json.dumps([{"databaseId": identifier, "headSha": self.sha}])
        elif args[1:3] == ["run", "view"]:
            identifier = int(args[3])
            workflow, branch = self.dispatched[identifier - 1]
            required = self.module.PROFILES[self.profile][workflow]
            if self.missing_job:
                required = set()
            data = json.dumps(
                {
                    "databaseId": identifier,
                    "headSha": "0" * 40 if self.bad_sha else self.sha,
                    "headBranch": branch,
                    "event": "workflow_dispatch",
                    "status": "in_progress" if self.queued else "completed",
                    "conclusion": "failure"
                    if self.failure or workflow == self.failed_workflow
                    else "success",
                    "jobs": [
                        {"name": name, "status": "completed", "conclusion": "success"} for name in required
                    ],
                }
            )
            if self.race:
                self.race = False
                self.advance_remote()
        elif args[1] == "api":
            self.assertNotIn("-R", args)
            fields = dict(args[index + 1].split("=", 1) for index, value in enumerate(args) if value == "-f")
            self.statuses.append((args[4], fields))
            if self.status_api_error:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="fictional denied")
            data = "{}"
        else:
            self.fail(f"Unexpected gh operation: {args[1:3]}")
        return subprocess.CompletedProcess(args, 0, stdout=data, stderr="")

    def publish(self, profile="store"):
        self.profile = profile
        with mock.patch.dict(os.environ, {"GH_TOKEN": "FICTIONAL_GH_TOKEN"}):
            return self.module.publish(
                profile, repo="Example/project", cwd=self.repo, runner=self.transport, timeout=0.2, poll=0.01
            )

    def assert_retained(self):
        branches = self.git(
            "--git-dir", str(self.remote), "for-each-ref", "--format=%(objectname)", "refs/heads/automation/"
        )
        self.assertIn(self.sha, branches)

    def test_all_profiles_require_actual_successful_validation_then_fast_forward(self):
        self.publish()
        self.assertEqual(self.remote_main(), self.sha)
        self.assertEqual([wf for wf, _ in self.dispatched], ["ci.yml"])

    def automation_branches(self):
        return self.git(
            "--git-dir", str(self.remote), "for-each-ref", "--format=%(refname)", "refs/heads/automation/"
        )

    def test_successful_publication_deletes_its_validation_branch(self):
        self.publish()
        self.assertEqual(self.remote_main(), self.sha)
        self.assertEqual(self.automation_branches().strip(), "")

    def test_failed_branch_cleanup_never_fails_a_publication(self):
        self.delete_error = True
        self.publish()
        self.assertEqual(self.remote_main(), self.sha)
        self.assert_retained()

    def test_failed_checks_do_not_change_main_and_retain_generated_branch(self):
        self.failure = True
        with self.assertRaises(RuntimeError):
            self.publish()
        self.assertEqual(self.remote_main(), self.base)
        self.assert_retained()
        self.assertEqual(self.statuses, [])

    def test_sha_mismatch_fails_before_main_push(self):
        self.bad_sha = True
        with self.assertRaises(RuntimeError):
            self.publish()
        self.assertEqual(self.remote_main(), self.base)
        self.assertEqual(self.statuses, [])

    def test_successful_run_with_missing_required_jobs_does_not_publish(self):
        self.missing_job = True
        with self.assertRaises(RuntimeError):
            self.publish()
        self.assertEqual(self.remote_main(), self.base)
        self.assertEqual(self.statuses, [])

    def test_remote_main_race_during_checks_does_not_rebase_or_overwrite(self):
        self.race = True
        with self.assertRaises(RuntimeError):
            self.publish()
        self.assertNotEqual(self.remote_main(), self.sha)
        self.assert_retained()

    def test_race_between_final_fetch_and_push_is_rejected_by_git(self):
        self.push_race = True
        with self.assertRaises(RuntimeError):
            self.publish()
        self.assertNotEqual(self.remote_main(), self.sha)

    def test_stale_initial_commit_is_retained_without_dispatch(self):
        raced = self.advance_remote()
        with self.assertRaises(RuntimeError):
            self.publish()
        self.assertEqual(self.remote_main(), raced)
        self.assertEqual(self.dispatched, [])
        self.assert_retained()

    def test_incomplete_validation_times_out_without_main_push(self):
        self.queued = True
        with self.assertRaises(RuntimeError):
            self.publish()
        self.assertEqual(self.remote_main(), self.base)

    def test_app_validates_both_workflows(self):
        self.publish("app")
        self.assertEqual(self.remote_main(), self.sha)
        self.assertEqual([wf for wf, _ in self.dispatched], ["release.yml", "tests.yml"])
        links = {fields["context"]: fields["target_url"] for _, fields in self.statuses}
        self.assertEqual(
            links,
            {
                "build": "https://github.com/Example/project/actions/runs/1",
                "core": "https://github.com/Example/project/actions/runs/2",
                "scripts": "https://github.com/Example/project/actions/runs/2",
            },
        )

    def test_mods_validates_its_ci_workflow(self):
        self.publish("mods")
        self.assertEqual(self.remote_main(), self.sha)
        self.assertEqual([fields["context"] for _, fields in self.statuses], ["check"])

    def test_verified_results_are_reported_as_commit_statuses_for_exact_sha(self):
        self.publish()
        self.assertEqual({fields["context"] for _, fields in self.statuses}, {"test", "database", "edge"})
        for endpoint, fields in self.statuses:
            self.assertEqual(endpoint, f"repos/Example/project/statuses/{self.sha}")
            self.assertEqual(fields["state"], "success")
            self.assertEqual(fields["target_url"], "https://github.com/Example/project/actions/runs/1")
            self.assertIn("ci.yml run 1", fields["description"])

    def test_status_api_failure_prevents_main_publication(self):
        self.status_api_error = True
        with self.assertRaises(RuntimeError):
            self.publish()
        self.assertEqual(self.remote_main(), self.base)
        self.assertEqual(len(self.statuses), 1)
        self.assert_retained()

    def test_no_statuses_are_reported_if_later_app_validation_fails(self):
        self.failed_workflow = "tests.yml"
        with self.assertRaises(RuntimeError):
            self.publish("app")
        self.assertEqual(self.statuses, [])
        self.assertEqual(self.remote_main(), self.base)


if __name__ == "__main__":
    unittest.main()
