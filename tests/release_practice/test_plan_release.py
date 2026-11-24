import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/releases/plan_release.py"
spec = importlib.util.spec_from_file_location("release_plan", SCRIPT)
planner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planner)


class ReleasePlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic release test")
        self.git("config", "user.email", "release-test@example.invalid")
        self.write("supabase/migrations/20261101000000_initial.sql", "select 1;\n")
        self.before = self.commit()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, stderr=subprocess.DEVNULL).decode().strip()

    def write(self, path, content):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "Synthetic fixture")
        return self.git("rev-parse", "HEAD")

    def plan(self, after):
        return planner.build_plan(self.repo, after, self.before)

    def test_plan_pins_commit_and_new_sql_without_applying_it(self):
        self.write("supabase/migrations/20261102000000_practice.sql", "select 2;\n")
        after = self.commit()
        result = self.plan(after)
        self.assertEqual(result["commit"], after)
        self.assertEqual(len(result["new_migration_files"]), 1)
        self.assertEqual(len(result["new_migration_files"][0]["sha256"]), 64)
        for key in ["sql_executed", "deployment_executed", "execution_authorized", "database_history_verified"]:
            self.assertIs(result[key], False)

    def test_local_uncommitted_files_never_enter_the_release(self):
        self.write("supabase/migrations/20261102000000_unapproved.sql", "select 'not committed';\n")
        result = self.plan(self.before)
        self.assertTrue(result["working_tree_has_uncommitted_changes"])
        self.assertEqual(result["new_migration_files"], [])
        self.assertEqual(len(result["migration_inventory"]), 1)

    def test_existing_sql_changes_and_removals_are_rejected(self):
        file = "supabase/migrations/20261101000000_initial.sql"
        self.write(file, "select 'changed';\n")
        with self.assertRaises(planner.PlanError):
            self.plan(self.commit())
        (self.repo / file).unlink()
        with self.assertRaises(planner.PlanError):
            self.plan(self.commit())

    def test_duplicate_and_backdated_versions_are_rejected(self):
        duplicate = self.repo / "supabase/migrations/20261101000000_duplicate.sql"
        self.write(str(duplicate.relative_to(self.repo)), "select 2;\n")
        with self.assertRaises(planner.PlanError):
            self.plan(self.commit())
        duplicate.unlink()
        self.write("supabase/migrations/20261001000000_backdated.sql", "select 3;\n")
        with self.assertRaises(planner.PlanError):
            self.plan(self.commit())

    def test_mutable_refs_production_and_reversed_history_are_rejected(self):
        self.write("app.txt", "synthetic update")
        after = self.commit()
        for ref in ["main", "HEAD", "--help", after[:12]]:
            with self.assertRaises(planner.PlanError):
                planner.build_plan(self.repo, ref, self.before)
        with self.assertRaises(planner.PlanError):
            planner.build_plan(self.repo, after, self.before, "production")
        with self.assertRaises(planner.PlanError):
            planner.build_plan(self.repo, self.before, after)

    def test_cli_refuses_to_overwrite_previous_evidence(self):
        path = self.repo / "plan.json"
        args = ["--commit", self.before, "--previous-commit", self.before, "--output", str(path)]
        first = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.repo, capture_output=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        result = json.loads(path.read_text())
        self.assertEqual(result["mode"], "plan-only")
        before = path.read_bytes()
        second = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.repo, capture_output=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
