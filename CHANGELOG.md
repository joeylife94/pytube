# Changelog

All notable changes to this project are documented here.

## Unreleased (2025-10-16)

- Fix: Normalize YouTube URLs (convert `youtu.be` and `/shorts/` to standard `watch?v=`) to reduce pytube innertube HTTP 400 errors.
- Fix: Add `yt-dlp` fallback for metadata extraction and downloads when pytube fails.
- Improvement: Cache fetched streams in `st.session_state` to keep download UI visible across Streamlit reruns.
- Improvement: Default output folder set to `downloads/` (created automatically when blank).
- Feature: Add Playwright automation scripts (`scripts/playwright_test.py`, `scripts/playwright_debug.py`) to reproduce UI interactions and capture screenshots for debugging.
- Misc: Move existing downloaded media into `downloads/` during cleanup.


## Previous

- Initial project scaffolding and Streamlit GUI for pytube-based downloads.
