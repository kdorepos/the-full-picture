#!/usr/bin/env bash
# Permanent RSS watcher for The Full Picture. Install as a system cron (see below).
# Checks the feed for episodes newer than what's on the site; if any, invokes a
# headless Claude Code session to run the full pipeline and publish them.
#
# Install (checks daily at 14:37; needs the `claude` CLI on PATH + authenticated):
#   (crontab -l 2>/dev/null; echo "37 14 * * * /srv/the-full-picture/pipeline/watch_and_ingest.sh >> /tmp/tfp-watch.log 2>&1") | crontab -
set -uo pipefail
cd /srv/the-full-picture || exit 1
# cron runs with a minimal PATH: add both node20 (build) and ~/.local/bin (the `claude` CLI).
export PATH="$HOME/.local/bin:$HOME/.local/node20/bin:$PATH"
set -a; . ./.env; set +a
FEED_URL="https://feeds.megaphone.fm/the-big-picture"

new_json=$(python3 pipeline/watch.py --json); rc=$?
[ "$rc" -eq 0 ] && { echo "$(date -u +%FT%TZ) no new episodes"; exit 0; }
[ "$rc" -ne 10 ] && { echo "$(date -u +%FT%TZ) watch.py error (rc=$rc)"; exit 1; }

echo "$(date -u +%FT%TZ) new episode(s) found — ingesting"
# Transcribe + auto-publish each new episode. The pipeline's --publish flag runs steps 4-6 via
# pipeline/publish_episode.sh (a headless Claude session) — one source of truth for the publish
# step, shared with manual/backlog runs. Pin each episode by its enclosure URL and resolve its
# live --item just before processing, so a new drop mid-run can't shift indices onto the wrong
# episode (see memory: item-index-feed-drift).
echo "$new_json" | python3 -c 'import sys,json; [print(e["url"]) for e in json.load(sys.stdin)]' \
  | while read -r url; do
      idx=$(python3 - "$url" <<'PY'
import sys; sys.path.insert(0, "pipeline")
from watch import feed_items, FEED
print(next((i["index"] for i in feed_items(FEED) if i["url"] == sys.argv[1]), -1))
PY
)
      [ "$idx" -ge 0 ] || { echo "$(date -u +%FT%TZ) url no longer in feed: $url"; continue; }
      echo "$(date -u +%FT%TZ) ingesting --item $idx  ($url)"
      python3 pipeline/the_full_picture.py "$FEED_URL" --item "$idx" --publish \
        || echo "$(date -u +%FT%TZ) ingest failed: $url"
    done
