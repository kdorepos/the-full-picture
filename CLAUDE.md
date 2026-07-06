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
For every candidate, confirm it's a real film and attach correct title + year — this
fixes Whisper proper-noun mishears and title collisions.
```
GET https://api.themoviedb.org/3/search/movie?query=<title>&api_key=$TMDB_KEY
```
Top result → title + release year. No match usually = mishear or a too-new indie (list
those with hand-noted year + director). Real catches: "Mariama"→Mārama, "Is God It Is"→
Is God Is, "Skin and Marink"→Skinamarink, "Mirroir"→Miroirs No. 3, "Gladys"→Gladiator II,
rejected a bad Jaws collision. TMDb key in `.env` (gitignored).

### 6. Deliver
Clean markdown: header (title/show/runtime) + sections above. Save transcript AND movie
list; send the list to the user; push-notify on completion (long jobs, user is usually away).

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
