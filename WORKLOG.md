# Worklog — 2025-10-16 / 2025-10-17

This file summarizes the debugging and fixes performed, and lists next steps for follow-up work.

## Summary of work done

- Inspected project and ran unit tests locally.
- Reproduced pytube HTTP 400 error for some short/youtu.be URLs.
- Implemented URL normalization (`_normalize_video_url`) in `pytube_helper.py` to convert short/shorts URLs to `watch?v=` form.
- Added a yt-dlp fallback for metadata extraction and downloads when pytube fails.
- Improved `pytube_helper.py` logging and clearer error messages.
- Made Streamlit UI improvements in `app.py`:
  - Cache fetched streams in `st.session_state` so the download UI remains visible across reruns.
  - Add `show_live_progress` checkbox to optionally run yt-dlp inline so users see live progress in the UI.
  - Default output folder now `downloads/` and created if missing.
- Added Playwright automation scripts to reproduce UI flows and capture screenshots:
  - `scripts/playwright_test.py`
  - `scripts/playwright_debug.py`
- Installed `yt-dlp` and (local) ffmpeg for testing; reprocessed a downloaded file with ffmpeg to fix container issues.
- Moved existing downloaded media from repo root into `downloads/`.
- Cleaned repository: added `.gitignore` and untracked generated artifacts (screenshots, ffmpeg dir).
- Created `CHANGELOG.md` and updated `README.md` to cover new usage and notes.
- Added GitHub Actions workflow `.github/workflows/python-tests.yml` to run pytest on push.
- Ran full test suite: `2 passed, 1 warning`.
- Created and pushed tag `v0.1.0`.

## Files changed / added (high-level)

- Modified: `pytube_helper.py`, `app.py`, `tests/test_pytube_helper.py`, `README.md`
- Added: `CHANGELOG.md`, `WORKLOG.md`, `scripts/playwright_test.py`, `scripts/playwright_debug.py`, `.gitignore`, `.github/workflows/python-tests.yml`
- Created: `downloads/` folder and moved media files into it during cleanup

## Next steps / TODOs

1. Commit/verify CI workflow runs successfully on GitHub Actions (check run and logs).
2. Optional: add Playwright test job to CI (requires headless browser support and test failure handling).
3. Optional: implement server-side shared progress (file or websocket) so background downloads update any open UI session reliably.
4. Add `DEV_SETUP.md` / `CONTRIBUTING.md` with quick start (venv, pip install, playwright install steps).
5. If desired, create a GitHub Release from tag `v0.1.0` (CHANGELOG content can be used as release notes).

## Notes

- The project uses pytube but falls back to yt-dlp in cases where pytube fails; installing `yt-dlp` in your venv is recommended for robustness.
- Local ffmpeg was used for testing; avoid committing binaries to the repo. Use `.gitignore` to keep them out of version control.

---

If you want, I can also:
- Draft `DEV_SETUP.md` now (includes Playwright setup commands).
- Create a GitHub Release draft using the changelog text.
- Start implementing server-side progress updates (design + code).

Tell me which of those you'd like next, or we can wrap up for today.