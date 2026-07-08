#!/usr/bin/env bash
# Permanent RSS watcher for The Full Picture. Install as a system cron (see below).
# Checks the feed for episodes newer than what's on the site; if any, invokes a
# headless Claude Code session to run the full pipeline and publish them.
#
# Install (checks daily at 14:37; needs the `claude` CLI on PATH + authenticated):
#   (crontab -l 2>/dev/null; echo "37 14 * * * /srv/the-full-picture/pipeline/watch_and_ingest.sh >> /tmp/tfp-watch.log 2>&1") | crontab -
set -uo pipefail
cd /srv/the-full-picture || exit 1
export PATH="$HOME/.local/node20/bin:$PATH"
set -a; . ./.env; set +a

python3 pipeline/watch.py
rc=$?
[ "$rc" -eq 0 ] && { echo "$(date -u +%FT%TZ) no new episodes"; exit 0; }
[ "$rc" -ne 10 ] && { echo "$(date -u +%FT%TZ) watch.py error (rc=$rc)"; exit 1; }

echo "$(date -u +%FT%TZ) new episode(s) found — ingesting"
# ponytail: --dangerously-skip-permissions is required for unattended tool use; the box is trusted.
claude -p --dangerously-skip-permissions "$(cat <<'PROMPT'
Autonomous episode ingest for The Full Picture (fully automatic). Working dir /srv/the-full-picture.
1. Run: set -a; source .env; set +a && python3 pipeline/watch.py --json. If it prints [], stop.
2. For EACH new episode (by its `index`), run the full pipeline per CLAUDE.md (review is required):
   a. Transcribe (local, unattended, ETA ~episode_min/1.6; wait for it): python3 pipeline/the_full_picture.py https://feeds.megaphone.fm/the-big-picture --item <index>
   b. Read out/<slug>/transcript.txt; extract every film into web/src/data/episodes/<slug>.json per the schema and web/DESIGN.md. Set type (auction|list|draft|discussion) by the episode's real shape. Non-films -> excluded.
   c. python3 pipeline/enrich_tmdb.py web/src/data/episodes/<slug>.json && python3 pipeline/spotify_id.py web/src/data/episodes/<slug>.json
   d. REQUIRED: run the film-title-reviewer agent; apply findings; re-enrich.
   e. cd web && npm run build && npx playwright test — fix any failure.
   f. Branch, commit (CLAUDE.md trailers), push, gh pr create, gh pr merge --merge --delete-branch, sync main.
3. Report a one-line summary. On unrecoverable failure, stop and report — never publish a broken episode.
PROMPT
)"
