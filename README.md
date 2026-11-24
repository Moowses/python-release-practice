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

Install Git and Python 3 with **Add to PATH** enabled. Open PowerShell:

```powershell
git clone https://github.com/Moowses/python-release-practice.git
cd python-release-practice
$releaseCommit = (git rev-parse HEAD).Trim()
$previousCommit = (git rev-parse 'HEAD^').Trim()
python scripts/releases/plan_release.py --commit $releaseCommit --previous-commit $previousCommit --output artifacts/windows-plan.json
```

Use a new output filename for another run.
