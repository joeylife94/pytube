Contributing
=============

Thank you for considering contributing! A few quick notes to get started:

- Create a topic branch from `main` for your change: `git checkout -b feat/your-feature`.
- Keep changes focused and add tests for new behavior where feasible.
- Run tests locally in the provided virtualenv before opening a PR:

```powershell
. .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
```

- For UI automation, use the `scripts/playwright_test.py` script. It is intended to be executed directly, not imported by pytest.
- If you add new long-running background tasks, consider adding progress file updates so the Streamlit UI can show progress to other sessions.

Thanks — maintainers will review PRs on main and provide feedback.