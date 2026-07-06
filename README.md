# the-full-picture

Turn a movie podcast into a browsable, TMDb-validated index of every film mentioned —
one page per episode. Built and proven against The Ringer's *The Big Picture*.

Two components:

```
pipeline/   Python CLI: podcast URL -> local transcript (Groq or faster-whisper)
web/        Astro static site: renders one page per episode from JSON
```

The flow: **`pipeline/` transcribes → a Claude session extracts + TMDb-validates the movies
into `web/src/data/episodes/<slug>.json` → `web/` renders it.** The per-episode JSON is the
hand-off format between the two halves. See `CLAUDE.md` for the full pipeline + lessons.

## 1. Pipeline (transcription)

**Groq (default)** — best accuracy, ~$0/episode on the free tier. Needs `curl` + a `GROQ_KEY`.
```sh
echo "GROQ_KEY=..." >> .env && set -a && . ./.env && set +a
./venv/bin/python pipeline/the_full_picture.py <podcast-url-or-rss-feed>   # -> out/<slug>/transcript.txt
```
Accepts an RSS feed URL (transcribes the newest episode) or an Overcast episode page.
The free tier caps audio at 7200 s/hr, so the script **paces** chunk uploads to stay under it —
a 2h+ episode therefore spans >1 hr wall-clock but never errors. (Groq's paid Dev tier removes
the cap for ~$0.10/episode, but self-serve upgrades have been unavailable since ~May 2026.)

**Local** — no network, no rate limit; CPU-only.
```sh
python3 -m venv venv && ./venv/bin/pip install faster-whisper
./venv/bin/python pipeline/the_full_picture.py <podcast-url> --engine local   # medium.en, ~75-95 min for 2.5hr
```
First local run pulls the ~1.5GB `medium.en` model into `~/.cache/huggingface`.
Both engines write `transcript.txt` + `transcript.timestamped.txt`. Extraction + TMDb
validation (needs `TMDB_KEY` in `.env`) are done by a Claude session against the transcript.

Secrets (`GROQ_KEY`, `TMDB_KEY`) live in a gitignored `.env` at the repo root.

## 2. Web (the site)

Astro static site, Cinema Noir theme, mobile-first, Playwright-tested (desktop + mobile).
```sh
cd web
npm install
npm run dev        # local dev at http://localhost:4321
npm run build      # -> dist/ (static)
npm test           # Playwright usability suite on both viewports
```
Add an episode by dropping a `<slug>.json` into `src/data/episodes/`; pages generate automatically.

### Deploy (Vercel)
Import the repo on vercel.com and set **Root Directory = `web`** (auto-detects the Astro preset).
Every push redeploys. Or, from `web/`: `npx vercel --prod`.
