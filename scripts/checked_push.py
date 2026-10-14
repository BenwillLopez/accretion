"""Validate a generated commit on its own branch before a normal main fast-forward.

Equivalent copies live in the store, app and mods repositories. Failed/raced
publications retain their unique automation branch; never rebase unchecked code.
"""

import argparse
import json
import os
import re
import subprocess
import time
import uuid

PROFILES = {
    "store": {"ci.yml": {"test", "database", "edge"}},
    "mods": {"ci.yml": {"check"}},
    "app": {"release.yml": {"build"}, "tests.yml": {"core", "scripts"}},
}


def publish(profile, *, repo, cwd=None, runner=subprocess.run, timeout=2400, poll=10):
    if profile not in PROFILES or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Choose a supported validation profile and repository")
    if timeout <= 0 or poll <= 0 or not os.environ.get("GH_TOKEN", "").strip():
        raise ValueError("A GitHub token and positive polling/timeout values are required")

    def command(*arguments):
        try:
            result = runner(
                list(arguments), cwd=cwd, capture_output=True, text=True, check=False, timeout=120
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(f"{arguments[0]} {arguments[1]} unavailable") from error
        if result.returncode:
            # Remote diagnostics can contain credential-bearing URLs; never echo their bodies.
            raise RuntimeError(f"{arguments[0]} {arguments[1]} failed")
        return result.stdout.strip()

    def git(*arguments):
        return command("git", *arguments)

    def gh(*arguments):
        return command("gh", *arguments, "-R", repo)

    sha = git("rev-parse", "--verify", "HEAD^{commit}")
    parents = git("rev-list", "--parents", "-n", "1", sha).split()
    if len(parents) != 2:
        raise RuntimeError("Expected exactly one generated commit with one parent")
    base = parents[1]
    branch = "automation/checked-" + uuid.uuid4().hex
    git("push", "origin", sha + ":refs/heads/" + branch)
    print(f"Generated commit retained on {branch}", flush=True)

    def current_main():
        git("fetch", "--quiet", "origin", "refs/heads/main:refs/remotes/origin/main")
        return git("rev-parse", "refs/remotes/origin/main")

    if current_main() != base:
        raise RuntimeError(
            f"Main changed before validation; recover {branch} and regenerate from current main"
        )
    deadline = time.monotonic() + timeout

    def wait():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(f"Validation timed out; retained {branch}")
        time.sleep(min(poll, remaining))

    for workflow in PROFILES[profile]:
        gh("workflow", "run", workflow, "--ref", branch)
    runs = {}
    for workflow in PROFILES[profile]:
        while True:
            listed = json.loads(
                gh(
                    "run",
                    "list",
                    "--workflow",
                    workflow,
                    "--branch",
                    branch,
                    "--event",
                    "workflow_dispatch",
                    "--limit",
                    "10",
                    "--json",
                    "databaseId,headSha",
                )
            )
            if listed:
                if len(listed) != 1 or listed[0].get("headSha") != sha:
                    raise RuntimeError(f"Ambiguous or mismatched validation run for {workflow}")
                identifier = listed[0].get("databaseId")
                if not isinstance(identifier, int) or isinstance(identifier, bool):
                    raise RuntimeError("Validation run has no usable identity")
                runs[workflow] = identifier
                break
            wait()

    for workflow, identifier in runs.items():
        while True:
            run = json.loads(
                gh(
                    "run",
                    "view",
                    str(identifier),
                    "--json",
                    "databaseId,headSha,headBranch,event,status,conclusion,jobs",
                )
            )
            if (
                run.get("databaseId") != identifier
                or run.get("headSha") != sha
                or run.get("headBranch") != branch
                or run.get("event") != "workflow_dispatch"
            ):
                raise RuntimeError("Validation identity or commit differs from the generated commit")
            if run.get("status") == "completed":
                jobs = {job["name"]: job for job in run.get("jobs", [])}
                if run.get("conclusion") != "success" or any(
                    jobs.get(name, {}).get("status") != "completed"
                    or jobs.get(name, {}).get("conclusion") != "success"
                    for name in PROFILES[profile][workflow]
                ):
                    raise RuntimeError(
                        f"Required validation failed or was missing: {workflow} run {identifier}"
                    )
                print(f"Validated {workflow} run {identifier} for {sha[:12]}", flush=True)
                break
            wait()
    if time.monotonic() > deadline:
        raise RuntimeError(f"Validation timed out; retained {branch}")
    if current_main() != base:
        raise RuntimeError(f"Main changed during validation; retained {branch}, no rebase performed")
    # A concurrent update after the fetch is still rejected by the ordinary fast-forward push.
    git("push", "origin", sha + ":refs/heads/main")
    print(f"Published validated commit {sha[:12]} to main", flush=True)
    return branch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=PROFILES)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--timeout", type=int, default=2400, help="Validation timeout in seconds")
    args = parser.parse_args()
    try:
        publish(args.profile, repo=args.repo, timeout=args.timeout)
    except (RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
