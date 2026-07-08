# the-full-picture

Podcast episode URL → local transcript → clean, TMDb-validated markdown list of every
movie mentioned. Transcription is fully local (faster-whisper on CPU); nothing leaves the
box except TMDb title lookups. Proven against The Ringer's "The Big Picture".

## Pipeline

Steps 1–3 are automated by `pipeline/the_full_picture.py`. Steps 4–6 are done by the Claude
session against the transcript — **do not** offload extraction to a small local LLM.

### 1–3 (the script)
- **Resolve audio**: fetch *raw* HTML (not the rendered page), grep the `<source src=...>`
  enclosure (Overcast embeds the real Megaphone CDN mp3). `<title>` gives the episode name.
- **Download + convert**: mp3 → 16kHz mono `pcm_s16le` wav (what Whisper wants).
- **Transcribe**: `faster_whisper` `BatchedInferencePipeline`, `medium.en`, int8, CPU.

### 4. Extract (Claude, not a local LLM)
- Read the FULL transcript (2.5hr ep ≈ 30k words). The show is **segmented** — a review,
  then a "Plus:" game, then a mailbag. Model the episode as an ordered list of `segments`,
  one per on-air section. Segment kinds + JSON schema per kind: **`web/src/data/episodes/TEMPLATES.md`**
  (review · discussion · ranking · topfive · halloffame · interview · list · draft · auction · awards).
- Exclude non-films (TV, YouTube/web series, video games, ad reads); list exclusions
  under episode-level `excluded` so the filtering is visible.

### 5. Validate + enrich against TMDb
Write the episode JSON (`web/src/data/episodes/<slug>.json`), then enrich:
```
TMDB_KEY=… ./pipeline/enrich_tmdb.py web/src/data/episodes/<slug>.json
```
Exact-title matching attaches `{id, poster, year}` per title and rejects collisions
(prefers null over a wrong link). It prints any UNMATCHED picks — usually a mishear.

### 5.5 Review — REQUIRED before publishing
Always run the **film-title-reviewer** agent (`.claude/agents/film-title-reviewer.md`)
on the episode. It grounds each pick in the transcript (stated director/cast/premise)
and confirms the TMDb match is *that* film — catching mishears (Nirvana→Nirvanna) and
wrong-but-same-title matches that enrichment can't. Apply its findings, then re-enrich.
This step is not optional; `enrich_tmdb.py` ends by reminding you to run it.

### 5.6 Humanize — public copy must read human
Run the **humanizer** agent (`.claude/agents/humanizer.md`) on the prose you wrote for the
episode (blurb + film notes) and any new site copy. It strips AI tells (em-dash overuse,
rule-of-three, "not just X, it's Y", promo adjectives) while preserving every fact, quote,
title, and year. Adapted from blader/humanizer. Voice: dry, specific, editorial — not promotional.

### 5.7 Spotify embed — every episode page must have one
Resolve it deterministically (the fuzzy app/MCP search won't surface plain-titled
back-catalog episodes):
```
./pipeline/spotify_id.py web/src/data/episodes/<slug>.json
```
It lists the show's episodes via the Spotify Web API and writes `spotifyEpisodeId` by
exact title+date match. Needs `SPOTIFY_CLIENT_ID`/`SPOTIFY_CLIENT_SECRET` in `.env`
(a free developer app, client-credentials only).

### 5.8 Release gates — REQUIRED before any commit/PR that touches code
Any change to `pipeline/`, `web/`, or the serverless endpoint must pass two agent gates
before it ships (episode-only JSON/transcript commits are exempt — they touch no code):
- **security-reviewer** (`.claude/agents/security-reviewer.md`) — leaked secrets, endpoint
  auth, injection, XSS, scoped to this project's threat model. Must return "safe to release".
- **yagni-reviewer** (`.claude/agents/yagni-reviewer.md`) — dead code, speculative abstraction,
  config-for-a-constant. Apply the safe deletions; simplifications are judgment calls.
Apply findings (or record why not), then commit. These run alongside the episode gates
(5.5 film-title-reviewer, 5.6 humanizer), not instead of them.

### 6. Deliver
Clean markdown: header (title/show/runtime) + sections above. Save transcript AND movie
list; send the list to the user; push-notify on completion (long jobs, user is usually away).

## Watch process (auto-ingest new episodes)
- `pipeline/watch.py` — reports feed episodes **newer** than the newest on the site
  (compares `published` dates), so it flags genuine new drops, not the skipped backlog.
  Exits 10 if there are new episodes, 0 if none. `--json` for machine use.
- `pipeline/watch_and_ingest.sh` — permanent watcher: runs `watch.py`, and on new
  episodes invokes a headless `claude -p` session to run the full pipeline (steps 4–6,
  review required) and open+merge a PR. Install as a system cron (line in the script).
  A session-scoped CronCreate job can cover the interim (auto-expires after 7 days).

## Live "now processing" panel
While the pipeline transcribes, `write_progress()` POSTs progress (phase · chunks · %)
to the site's **`web/api/progress.js`** serverless function, which stores it in Vercel KV.
The homepage polls `GET /api/progress` every 15s and shows a progress card; it auto-hides
when the run goes inactive or the slug is already published. Setup (one-time):
- Vercel dashboard → Storage → create a **KV** store, connect to the project (injects
  `KV_REST_API_URL` / `KV_REST_API_TOKEN`).
- Set `PROGRESS_TOKEN` (any secret) in Vercel project env **and** the box's `.env`.
- Box `.env` also needs `PROGRESS_URL=https://thefullpicture.app/api/progress`.
Without these the POST is skipped and the panel just stays hidden — nothing breaks.

## Transcription — local (faster-whisper on CPU), the only engine
- **BatchedInferencePipeline, not `model.transcribe()`.** Plain transcribe pins ~1 core
  (~0.5x realtime); batched VAD-chunks across cores.
- **Capped at 3 cores by default (`--cores`).** Using all cores + `batch_size=8` OOM-killed
  the 4-core box. `cpu_threads` and `batch_size` both track `--cores`. Leave one core for the
  OS; never go straight to `os.cpu_count()`.
- **`medium.en`** is the sweet spot for movie-title-heavy CPU audio (~1.6x realtime). `small.en`
  mangles proper nouns. For fewer title mishears at a speed cost, `--model large-v3-turbo`
  (the large model, faster decoder) or `distil-large-v3.5`; full `large-v3` is too slow CPU-only.
  `device="cuda"` if a GPU ever appears.
- Write transcript **incrementally** (plain + timestamped) so a crash keeps partial output.
  The script pings the "now processing" panel as the timeline advances (needs `PROGRESS_URL`/`_TOKEN`).
- Run transcription as a **harness-tracked background job** (`Bash run_in_background:true`,
  not nohup) → auto-notified on completion. ETA ≈ episode_minutes / 1.6.

## Setup
```
python3 -m venv venv && ./venv/bin/pip install faster-whisper
./venv/bin/python pipeline/the_full_picture.py <podcast-url>
```
First run downloads ~1.5GB `medium.en` into `~/.cache/huggingface` (cached after).

## Env
- Proven box: 4-core CPU, no GPU, ffmpeg 4.4, Python 3.10.
- `.gitignore`s all large/regenerable artifacts + `.env`. Never commit audio or the TMDb key.
