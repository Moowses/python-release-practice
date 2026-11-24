"""Read-only release rehearsal: inspect committed Git objects, never a server/DB."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


class PlanError(ValueError):
    pass


def git(repo, *args):
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, check=False, timeout=30
    )
    if result.returncode:
        raise PlanError("Git could not verify the requested commit or history.")
    return result.stdout


def verify_commit(repo, value):
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise PlanError("Use a full, lowercase, 40-character Git commit SHA.")
    actual = git(repo, "rev-parse", "--verify", value + "^{commit}").decode().strip()
    if actual != value:
        raise PlanError("The commit did not resolve to the requested SHA.")
    return actual


def migration_inventory(repo, commit):
    entries = git(repo, "ls-tree", "-rz", "--full-tree", commit, "--", "supabase/migrations")
    inventory = {}
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, blob = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8")
        if not path.endswith(".sql"):
            continue
        match = re.fullmatch(r"supabase/migrations/([0-9]{14})_[a-z0-9_]+\.sql", path)
        if not match or kind != "blob" or mode not in ("100644", "100755"):
            raise PlanError("Migration names must be regular timestamped SQL files: " + path)
        version = match.group(1)
        if version in inventory:
            raise PlanError("Duplicate migration version: " + version)
        sql = git(repo, "cat-file", "blob", blob)
        inventory[version] = {
            "version": version,
            "path": path,
            "sha256": hashlib.sha256(sql).hexdigest(),
        }
    return inventory


def build_plan(repo, commit, previous_commit, target="practice"):
    if target not in ("practice", "staging"):
        raise PlanError("This rehearsal supports practice/staging plans only.")
    commit = verify_commit(repo, commit)
    previous_commit = verify_commit(repo, previous_commit)
    git(repo, "merge-base", "--is-ancestor", previous_commit, commit)
    previous = migration_inventory(repo, previous_commit)
    current = migration_inventory(repo, commit)
    for version, migration in previous.items():
        if current.get(version) != migration:
            raise PlanError("Previously committed migration was changed, renamed or removed: " + migration["path"])
    new = [current[version] for version in sorted(current) if version not in previous]
    if previous and new and new[0]["version"] <= max(previous):
        raise PlanError("A new migration predates the previous migration history; reconcile it explicitly.")
    changed = git(repo, "diff", "--name-only", "-z", previous_commit, commit, "--").split(b"\0")
    return {
        "contract": "release_practice.v1",
        "mode": "plan-only",
        "target": target,
        "commit": commit,
        "previous_commit": previous_commit,
        "git_tree": git(repo, "rev-parse", commit + "^{tree}").decode().strip(),
        "working_tree_has_uncommitted_changes": bool(git(repo, "status", "--porcelain=v1")),
        "source": "committed Git objects only; local changes are excluded",
        "changed_files": [value.decode("utf-8") for value in changed if value],
        "migration_inventory": [current[version] for version in sorted(current)],
        "new_migration_files": new,
        "database_history_verified": False,
        "running_release_baseline_verified": False,
        "application_build_tested": False,
        "sql_executed": False,
        "deployment_executed": False,
        "execution_authorized": False,
        "next_step": "Review this plan, verify the exact isolated staging target and its migration history, then obtain explicit approval before executing migrations or deployment.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--previous-commit", required=True)
    parser.add_argument("--target", choices=("practice", "staging"), default="practice")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        plan = build_plan(Path.cwd(), args.commit, args.previous_commit, args.target)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Existing evidence must never be silently overwritten.
        with args.output.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(plan, output, indent=2)
            output.write("\n")
    except (PlanError, OSError, subprocess.TimeoutExpired) as error:
        print("Release rehearsal stopped: " + str(error), file=sys.stderr)
        return 1
    print("Plan recorded for " + plan["commit"] + "; no database or deployment operations ran.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
