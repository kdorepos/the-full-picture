#!/usr/bin/env bash
# Process an already-transcribed episode into a published PR via a headless Claude session.
# This is the "steps 4-6" half of the pipeline (extract -> enrich -> review -> humanize ->
# spotify -> build/test -> PR), the part CLAUDE.md says must be done by Claude, not a small
# local LLM. Reused by both `the_full_picture.py --publish` and the cron watcher.
#
# Usage: pipeline/publish_episode.sh <slug> [--no-merge]
#   <slug>       an episode whose transcript is at out/<slug>/transcript.txt
#   --no-merge   open the PR and stop (for a human to review) instead of auto-merging
#
# ponytail: no git-worktree isolation — the headless session owns the working tree while it
# runs, so don't run it concurrently with interactive git work. Add a worktree per episode if
# you ever need concurrent publishes.
set -uo pipefail
cd /srv/the-full-picture || exit 1
export PATH="$HOME/.local/bin:$HOME/.local/node20/bin:$PATH"
set -a; . ./.env; set +a
# Headless auth: CLAUDE_CODE_OAUTH_TOKEN (from .env, 1-yr subscription token via `claude setup-token`)
# is what `claude -p` should use. ANTHROPIC_API_KEY/AUTH_TOKEN outrank it in precedence and would
# silently switch to pay-as-you-go billing — unset them so the subscription token always wins.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN

slug="${1:?usage: publish_episode.sh <slug> [--no-merge]}"
[ "${2:-}" = "--no-merge" ] && merge=no || merge=yes
tx="/srv/the-full-picture/out/$slug/transcript.txt"
[ -f "$tx" ] || { echo "no transcript: $tx"; exit 1; }

# Resolve deterministic metadata so the LLM never has to guess it.
read -r DATE TITLE < <(python3 - "$slug" <<'PY'
import sys; sys.path.insert(0, "pipeline")
from watch import feed_items, FEED
it = next((i for i in feed_items(FEED) if i["slug"] == sys.argv[1]), None)
print(f"{it['date']} {it['title']}" if it else " ")
PY
)
RUNTIME=$(python3 - "$slug" <<'PY'
import sys
last = 0.0
try:
    for line in open(f"out/{sys.argv[1]}/transcript.timestamped.txt"):
        if line.startswith("["):
            last = float(line[1:line.index("]")])
except Exception:
    pass
print(round(last / 60))
PY
)
[ -n "${DATE// }" ] || { echo "could not resolve feed metadata for $slug"; exit 1; }
echo "$(date -u +%FT%TZ) publishing $slug  (date=$DATE runtime=${RUNTIME}m merge=$merge)"

if [ "$merge" = no ]; then
  STEP6="6. STOP after opening the PR. Do NOT merge — print the PR URL for a human to review."
else
  STEP6="6. gh pr merge <#> --merge --delete-branch, then: git checkout main && git pull --ff-only."
fi

claude -p --model claude-opus-4-8 --dangerously-skip-permissions "Process and publish one already-transcribed episode of The Big Picture for The Full Picture. Working dir /srv/the-full-picture. Follow CLAUDE.md steps 4-6 exactly; the film-title-reviewer and humanizer gates are REQUIRED, not optional.

FACTS (use verbatim, do NOT re-derive):
- slug: $slug
- transcript: $tx  (read it FULLY; out/$slug/transcript.timestamped.txt has timing)
- published date: $DATE
- episode title: $TITLE
- runtimeMin: $RUNTIME
- show: The Big Picture
- hosts: infer from the transcript intro (e.g. \"I'm X ... Y joins me\"); an interview guest is a host only if they co-host a segment.

STEPS:
1. Model the episode as an ordered list of segments per web/src/data/episodes/TEMPLATES.md, one per on-air section (a discussion, a review block, an interview, etc.). Extract EVERY film mentioned, with its year; TV / web-series / video games / ad reads -> episode-level \`excluded\`. Write web/src/data/episodes/$slug.json with the metadata above, a short dry blurb (\`format\`), and per-film notes where they add something.
2. Enrich + IDs: set -a; source .env; set +a && python3 pipeline/enrich_tmdb.py web/src/data/episodes/$slug.json && python3 pipeline/spotify_id.py web/src/data/episodes/$slug.json
3. REQUIRED: run the film-title-reviewer agent on the episode; apply its findings (add \`tmdbOverrides\` for confirmed same-title collisions), then re-run enrich_tmdb.py. Then run the humanizer agent on the blurb + film notes.
4. Build + test: cd web && export PATH=\"\$HOME/.local/node20/bin:\$PATH\" && npm run build && npx playwright test — fix any failure, then cd back to the repo root.
5. git checkout -b feat/episode-$slug && git add -A && git commit with the CLAUDE.md trailers, then git push -u origin feat/episode-$slug && gh pr create --fill.
$STEP6

Report a one-line summary (matched/total films, PR URL). On unrecoverable failure STOP and report — never publish a broken or half-matched episode."
