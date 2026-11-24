# Python release practice

```text
GitHub
└── Start the workflow manually
    ├── Fetch the selected Git version
    ├── Python checks migration files
    └── Save a JSON release plan
```

Practice only. No SQL is executed and nothing is deployed.
The example SQL files describe a fictional notes table.

## Try it on GitHub

1. Open **Actions → Release practice → Run workflow**.
2. Select `main`. Leave `previous_commit` blank to compare with the parent commit.
3. Download the generated release-plan artifact after the run succeeds.

## Try it locally

Requires Python 3 and Git. No extra Python packages are needed.

```bash
python -B -m unittest discover -s tests/release_practice -p 'test_*.py' -v
git rev-parse HEAD
git rev-parse HEAD^
```

Use the two full commit hashes in this command:

```bash
python scripts/releases/plan_release.py --commit COMMIT_SHA --previous-commit PARENT_SHA --output artifacts/plan.json
```

The planner reads committed files only. It rejects changed or removed older
migrations, duplicate versions, backdated additions and production targets.
It does not verify a real database's migration history or authorize deployment.

## Windows Server (PowerShell)

Install Git and Python 3 with **Add to PATH** enabled. Use a separate practice folder:

```powershell
git clone https://github.com/Moowses/python-release-practice.git C:\Practice\python-release-practice
cd C:\Practice\python-release-practice
python scripts/windows/update_practice.py --watch
```

Checks GitHub every 15 minutes while the window stays open. Press **Ctrl+C** to stop.

For one update only:

```powershell
python scripts/windows/update_practice.py
```

It updates this practice clone only. Local edits or different history stop the update.
It never runs migrations, installs packages or restarts services.

**Simple explanation:** GitHub stores the latest files. This script downloads them
into a separate practice folder. Downloading files does not run them.

**Demo:** Commit a README change on GitHub. The Windows copy updates on the next check.
