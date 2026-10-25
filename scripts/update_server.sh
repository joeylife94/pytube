#!/usr/bin/env bash
# Update a Docker deployment: pull the latest code and rebuild the images so
# yt-dlp (and its YouTube fixes) is current, then restart.
#
# The pip layer is cached, so a plain `docker compose up --build` keeps an old
# yt-dlp; --no-cache forces a fresh install. Run weekly, e.g. from cron:
#   0 4 * * 1 /path/to/pytube/scripts/update_server.sh >> ~/pytube-update.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/.."
echo "== $(date '+%F %T') update"
git pull --ff-only
docker compose build --pull --no-cache
docker compose up -d
docker image prune -f
docker compose ps
