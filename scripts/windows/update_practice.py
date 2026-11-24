"""Fetch practice files only. Never execute downloaded code, SQL or deployments."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import time

EXPECTED_ORIGIN = "https://github.com/Moowses/python-release-practice.git"


class UpdateError(RuntimeError):
    pass


def git(repo, *args):
    try:
        result = subprocess.run(
            ["git", "--no-pager", *args], cwd=repo, capture_output=True, text=True,
            timeout=120, env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise UpdateError("Git is unavailable or the request timed out.") from error
    if result.returncode:
        raise UpdateError("Git " + args[0] + " failed. Check the practice checkout and network.")
    return result.stdout.strip()


def reject_filters(text):
    for line in text.splitlines():
        if not line.lstrip().startswith("#") and re.search(r"(?:^|\s)[-!]?filter(?:=|\s|$)", line):
            raise UpdateError("Git file filters are not supported by this practice updater.")


def check_tree(repo, commit):
    for entry in git(repo, "ls-tree", "-rz", "--full-tree", commit).split("\0"):
        if not entry:
            continue
        metadata, path = entry.split("\t", 1)
        mode = metadata.split()[0]
        if mode in ("120000", "160000") or path == ".gitmodules":
            raise UpdateError("Links and submodules are not supported by this practice updater.")
        if path.rsplit("/", 1)[-1] == ".gitattributes":
            reject_filters(git(repo, "show", commit + ":" + path))


def check_hooks(repo):
    hooks = Path(git(repo, "rev-parse", "--git-path", "hooks"))
    if not hooks.is_absolute():
        hooks = repo / hooks
    if hooks.is_dir() and any(p.is_file() and not p.name.endswith(".sample") for p in hooks.iterdir()):
        raise UpdateError("Active Git hooks require review. No update was attempted.")


def update_practice(repo):
    repo = Path(repo).resolve()
    if not (repo / ".git").is_dir() or (repo / ".git").is_symlink():
        raise UpdateError("Use a separate, normal clone of the practice repository.")
    if Path(git(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
        raise UpdateError("The practice checkout path is incorrect.")
    if git(repo, "remote", "get-url", "origin") != EXPECTED_ORIGIN:
        raise UpdateError("This is not the expected practice repository. No update was attempted.")
    if git(repo, "branch", "--show-current") != "main":
        raise UpdateError("Switch the practice checkout to main before updating.")
    if git(repo, "status", "--porcelain=v1", "--untracked-files=normal"):
        raise UpdateError("Local changes detected. Save them before updating.")

    check_hooks(repo)
    attributes = repo / ".git/info/attributes"
    if attributes.exists():
        reject_filters(attributes.read_text(encoding="utf-8"))

    before = git(repo, "rev-parse", "HEAD")
    check_tree(repo, before)
    git(repo, "fetch", "--no-tags", "--no-recurse-submodules", "origin",
        "refs/heads/main:refs/remotes/origin/main")
    target = git(repo, "rev-parse", "refs/remotes/origin/main^{commit}")
    if before == target:
        return "Already up to date."
    try:
        git(repo, "merge-base", "--is-ancestor", before, target)
    except UpdateError as error:
        raise UpdateError("Local history differs from GitHub. No files were replaced.") from error
    check_tree(repo, target)
    # Repeat guards in case a user edited files while the fetch was running.
    if (git(repo, "rev-parse", "HEAD") != before
            or git(repo, "branch", "--show-current") != "main"
            or git(repo, "status", "--porcelain=v1", "--untracked-files=normal")):
        raise UpdateError("The checkout changed during fetch. Update stopped.")
    check_hooks(repo)
    git(repo, "merge", "--ff-only", "--no-edit", target)
    return "Updated practice files to " + target[:7] + "."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true", help="Keep checking while this window stays open.")
    parser.add_argument("--interval-seconds", type=int, default=900, help="Watch interval; default 900 (15 minutes).")
    args = parser.parse_args()
    if args.interval_seconds < 60:
        parser.error("Use an interval of at least 60 seconds.")
    repo = Path(__file__).resolve().parents[2]
    try:
        while True:
            print(update_practice(repo), flush=True)
            if not args.watch:
                return 0
            time.sleep(args.interval_seconds)
    except (UpdateError, OSError) as error:
        print("Stopped: " + str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Practice updater stopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
