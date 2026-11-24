import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/windows/update_practice.py"
spec = importlib.util.spec_from_file_location("practice_updater", SCRIPT)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class PracticeUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.author = self.root / "author"
        self.checkout = self.root / "practice"
        self.git(self.root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.git(self.root, "init", "--initial-branch=main", str(self.author))
        self.identity(self.author)
        self.write(self.author, "README.md", "Synthetic practice files.\n")
        self.git(self.author, "add", ".")
        self.git(self.author, "commit", "-qm", "Synthetic initial version")
        self.git(self.author, "remote", "add", "origin", str(self.remote))
        self.git(self.author, "push", "-q", "origin", "main")
        self.git(self.root, "clone", "-q", str(self.remote), str(self.checkout))
        self.identity(self.checkout)
        self.origin_patch = patch.object(updater, "EXPECTED_ORIGIN", self.git(self.checkout, "remote", "get-url", "origin"))
        self.origin_patch.start()
        self.addCleanup(self.origin_patch.stop)
        self.before = self.git(self.checkout, "rev-parse", "HEAD")

    @staticmethod
    def git(repo, *args):
        return subprocess.check_output(["git", *args], cwd=repo, stderr=subprocess.DEVNULL, text=True).strip()

    def identity(self, repo):
        self.git(repo, "config", "user.name", "Synthetic update test")
        self.git(repo, "config", "user.email", "update-test@example.invalid")

    @staticmethod
    def write(repo, path, content):
        file = repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    def publish(self, path="README.md", content="Synthetic updated version.\n"):
        self.write(self.author, path, content)
        self.git(self.author, "add", ".")
        self.git(self.author, "commit", "-qm", "Synthetic update")
        self.git(self.author, "push", "-q", "origin", "main")
        return self.git(self.author, "rev-parse", "HEAD")

    def test_fast_forward_downloads_files_and_repeated_run_is_unchanged(self):
        target = self.publish("demo.sql", "-- Synthetic text only; never execute.\nselect 1;\n")
        updater.update_practice(self.checkout)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), target)
        self.assertEqual((self.checkout / "demo.sql").read_text(), "-- Synthetic text only; never execute.\nselect 1;\n")
        updater.update_practice(self.checkout)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), target)

    def test_wrong_origin_is_rejected_before_fetch(self):
        self.git(self.checkout, "remote", "set-url", "origin", "https://example.invalid/unrelated.git")
        with self.assertRaisesRegex(updater.UpdateError, "expected practice repository"):
            updater.update_practice(self.checkout)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), self.before)

    def test_other_branch_is_not_updated(self):
        self.git(self.checkout, "switch", "-qc", "local-work")
        with self.assertRaisesRegex(updater.UpdateError, "main"):
            updater.update_practice(self.checkout)
        self.assertEqual(self.git(self.checkout, "branch", "--show-current"), "local-work")

    def test_local_edits_and_untracked_files_are_preserved(self):
        self.publish()
        self.write(self.checkout, "README.md", "Local work.\n")
        with self.assertRaisesRegex(updater.UpdateError, "Local changes"):
            updater.update_practice(self.checkout)
        self.assertEqual((self.checkout / "README.md").read_text(), "Local work.\n")
        self.write(self.checkout, "README.md", "Synthetic practice files.\n")
        self.write(self.checkout, "local.txt", "Keep this file.")
        with self.assertRaisesRegex(updater.UpdateError, "Local changes"):
            updater.update_practice(self.checkout)
        self.assertEqual((self.checkout / "local.txt").read_text(), "Keep this file.")

    def test_local_commits_are_not_overwritten(self):
        self.publish()
        self.write(self.checkout, "local.txt", "Local committed work.")
        self.git(self.checkout, "add", ".")
        self.git(self.checkout, "commit", "-qm", "Synthetic local work")
        local = self.git(self.checkout, "rev-parse", "HEAD")
        with self.assertRaisesRegex(updater.UpdateError, "Local history"):
            updater.update_practice(self.checkout)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), local)

    def test_active_hooks_are_not_run(self):
        self.publish()
        hook = self.checkout / ".git/hooks/post-merge"
        hook.write_text("#!/bin/sh\necho unsafe > hook-ran.txt\n")
        hook.chmod(0o755)
        with self.assertRaisesRegex(updater.UpdateError, "Active Git hooks"):
            updater.update_practice(self.checkout)
        self.assertFalse((self.checkout / "hook-ran.txt").exists())
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), self.before)

    def test_downloaded_file_filters_are_not_activated(self):
        self.publish(".gitattributes", "*.txt filter=custom\n")
        with self.assertRaisesRegex(updater.UpdateError, "Git file filters"):
            updater.update_practice(self.checkout)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), self.before)
        self.assertFalse((self.checkout / ".gitattributes").exists())

    def test_edits_made_during_fetch_are_preserved(self):
        self.publish()
        real_git = updater.git

        def edit_during_fetch(repo, *args):
            result = real_git(repo, *args)
            if args[0] == "fetch":
                self.write(self.checkout, "README.md", "New local work.\n")
            return result

        with patch.object(updater, "git", side_effect=edit_during_fetch):
            with self.assertRaisesRegex(updater.UpdateError, "changed during fetch"):
                updater.update_practice(self.checkout)
        self.assertEqual((self.checkout / "README.md").read_text(), "New local work.\n")
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), self.before)

    def test_hooks_added_during_fetch_are_not_run(self):
        self.publish()
        real_git = updater.git

        def hook_during_fetch(repo, *args):
            result = real_git(repo, *args)
            if args[0] == "fetch":
                hook = self.checkout / ".git/hooks/post-merge"
                hook.write_text("#!/bin/sh\necho unsafe > hook-ran.txt\n")
                hook.chmod(0o755)
            return result

        with patch.object(updater, "git", side_effect=hook_during_fetch):
            with self.assertRaisesRegex(updater.UpdateError, "Active Git hooks"):
                updater.update_practice(self.checkout)
        self.assertFalse((self.checkout / "hook-ran.txt").exists())
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), self.before)


if __name__ == "__main__":
    unittest.main()
