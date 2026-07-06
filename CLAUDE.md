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
- Read the FULL transcript (2.5hr ep ≈ 30k words). Mirror the episode's structure:
  - Discussion ep → one flat grouped list.
  - Picks/countdown ep → a "Top N" section (who picked what) + a "Referenced" section
    grouped under the pick each reference was raised alongside, one-line note each.
- Exclude non-films (TV, YouTube/web series, video games, ad reads); list exclusions
  separately so the filtering is visible.

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

## Groq engine (default) — lessons
- `whisper-large-v3-turbo` beats local `medium.en` on proper nouns (movie titles) and is
  ~$0/episode. POST FLAC chunks to `/openai/v1/audio/transcriptions`.
- **Free tier caps audio at 7200 s/hr (ASPH), rolling.** A 149-min episode (8958 s) CANNOT be
  done inside one hour — max ~120 min/hr. The CLI paces uploads (~11 chunks/hr) to stay under it.
  The 429 message mislabels the rolling total as "Requested <N>"; it's account usage, not file size.
- **Chunk with `-ss/-t`, not `-f segment`.** The segment muxer writes the whole-file duration
  into the LAST FLAC's header; Groq reads that and rejects it as too large.
- Dev tier (100 MB files, higher ASPH, ~$0.10/episode) removes all of this — but self-serve
  upgrades have been unavailable since ~May 2026, so free-tier pacing is the current path.

## Lessons — local engine (do not relearn the hard way)
- **BatchedInferencePipeline, not `model.transcribe()`.** Plain transcribe pins ~1 core
  (~0.5x realtime); batched VAD-chunks and uses ~3/4 cores (~1.6–1.7x realtime).
- **`medium.en`** is the sweet spot for movie-title-heavy CPU audio. `small.en` mangles
  proper nouns; `large-v3` too slow CPU-only. `device="cuda"` if a GPU ever appears.
- Write transcript **incrementally** (plain + timestamped) so a crash keeps partial output.
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
