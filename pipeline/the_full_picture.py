#!/usr/bin/env python3
"""the-full-picture: podcast episode/feed URL -> local transcript.txt

Steps 1-3 of the pipeline: resolve audio -> download -> 16kHz mono WAV -> transcribe
locally with faster-whisper on CPU. Extraction + TMDb validation (steps 4-6) are done
by hand against the transcript. See CLAUDE.md. Transcription reaches no network and has
no rate limits.

Usage: ./venv/bin/python the_full_picture.py <rss-or-episode-url> [--model medium.en] [--item N]
"""
import os, re, sys, time, json, subprocess, urllib.request, argparse, unicodedata

UA = "Mozilla/5.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRESS = os.path.join(ROOT, "web", "public", "progress.json")  # site's "now processing" panel


def write_progress(**kw):
    """Best-effort progress ping for the homepage panel. Never fatal to transcription.
    Writes a local file (dev/telemetry) and, if PROGRESS_URL + PROGRESS_TOKEN are set,
    POSTs to the site's /api/progress so the deployed panel is live for visitors."""
    kw.setdefault("active", True)
    kw["updated"] = int(time.time())
    body = json.dumps(kw).encode()
    try:
        with open(PROGRESS, "wb") as f:
            f.write(body)
    except Exception:
        pass
    url, token = os.environ.get("PROGRESS_URL"), os.environ.get("PROGRESS_TOKEN")
    if url and token:
        try:
            req = urllib.request.Request(url, data=body, method="POST", headers={
                "Content-Type": "application/json", "Authorization": f"Bearer {token}"})
            urllib.request.urlopen(req, timeout=5).read()
        except Exception:
            pass


def sh(*cmd):
    subprocess.run(cmd, check=True)


def resolve_audio(url, item_index=0):
    """Return (audio_url, title, date). Handles RSS feeds (<enclosure>; item 0 is newest,
    item_index picks an older one) and Overcast-style episode pages (<source src=...>).
    `date` (ISO, from the item's <pubDate>) disambiguates recurring titles; "" if unknown."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    body = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    # RSS feed: pick the Nth <item>'s enclosure (feeds are newest-first)
    if "<enclosure" in body:
        items = body.split("<item>")[1:]
        if 0 <= item_index < len(items):
            item = items[item_index].split("</item>", 1)[0]
            au = re.search(r'<enclosure[^>]+url="([^"]+)"', item, re.I)
            ti = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", item, re.S)
            pub = re.search(r"<pubDate>([^<]+)</pubDate>", item)
            date = ""
            if pub:
                try:
                    from email.utils import parsedate_to_datetime
                    date = parsedate_to_datetime(pub.group(1)).date().isoformat()
                except Exception:
                    date = ""
            if au:
                return au.group(1), (ti.group(1).strip() if ti else "episode"), date
    # Overcast page: raw HTML embeds the real Megaphone CDN enclosure as <source>
    m = re.search(r'<source[^>]+src="([^"]+)"', body, re.I)
    if not m:
        sys.exit("Could not find an <enclosure> (RSS) or <source> (page) audio URL.")
    t = re.search(r"<title>([^<]+)</title>", body, re.I)
    return m.group(1), (t.group(1).strip() if t else "episode"), ""


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "episode"


def unique_slug(title, date, existing):
    """slug(title), year-suffixed when the base already exists — so a recurring title
    ("The Summer Movie Mailbag", "The Epic Movie Draft") never overwrites last year's
    same-titled episode. Mirrors watch.py.unique_slug (kept self-contained, like slug())."""
    base = slug(title)
    if base not in existing:
        return base
    year = (date or "")[:4]
    return f"{base}-{year}" if year else base


def download(audio_url, mp3, tries=4):
    print(f"Downloading -> {mp3}")
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(audio_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r, open(mp3, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            return
        except Exception as e:  # transient CDN hiccups (504s) shouldn't kill a run
            if attempt == tries:
                raise
            print(f"  download failed ({e}); retry {attempt}/{tries} in {5 * attempt}s")
            time.sleep(5 * attempt)


def duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path])
    return float(out.strip())


def transcribe_local(wav, txt, model_name, secs, meta, cores):
    """faster-whisper on CPU. BatchedInferencePipeline VAD-chunks internally. Capped at
    `cores` threads (default 3) so it doesn't saturate the box and get OOM-killed; raise
    --cores on a beefier machine. Writes the transcript incrementally so a crash keeps
    partial output, and pings the progress panel as the timeline advances."""
    from faster_whisper import WhisperModel, BatchedInferencePipeline
    print(f"Loading {model_name} (int8, {cores} threads)")
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=cores)
    batched = BatchedInferencePipeline(model=model)
    segments, _ = batched.transcribe(wav, batch_size=cores, language="en", beam_size=5)
    stamped = txt.replace(".txt", ".timestamped.txt")
    last_pct = -1
    t0 = time.time()
    with open(txt, "w") as ft, open(stamped, "w") as fs:
        for seg in segments:
            ft.write(seg.text.strip() + "\n"); ft.flush()
            fs.write(f"[{seg.start:8.1f}] {seg.text.strip()}\n"); fs.flush()
            pct = min(99, int(seg.end / secs * 100)) if secs else 0
            if pct > last_pct:  # ping the panel at each 1% of the timeline
                last_pct = pct
                # ETA from observed throughput (self-calibrates to the actual core count),
                # not a hardcoded realtime factor: remaining_audio / (processed / elapsed).
                elapsed = time.time() - t0
                eta = max(0, round((secs - seg.end) * elapsed / seg.end)) if seg.end > 0 else None
                write_progress(phase="transcribing", pct=pct, etaSec=eta, **meta)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--model", default="medium.en",
                    help="faster-whisper model: medium.en (default), large-v3-turbo, distil-large-v3.5, ...")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--item", type=int, default=0, help="RSS feed item index (0 = newest)")
    ap.add_argument("--cores", type=int, default=3,
                    help="CPU threads / batch size (default 3; keep low to avoid killing the box)")
    ap.add_argument("--keep-audio", action="store_true")
    ap.add_argument("--publish", action="store_true",
                    help="after transcription, auto-process + publish the episode (headless Claude)")
    ap.add_argument("--no-merge", action="store_true",
                    help="with --publish, open the PR for human review instead of auto-merging")
    a = ap.parse_args()

    audio_url, title, date = resolve_audio(a.url, a.item)
    print(f"Episode: {title}")
    try:  # year-suffix a recurring title so it never overwrites last year's same-titled episode
        existing = {f[:-5] for f in os.listdir(os.path.join(ROOT, "web", "src", "data", "episodes"))
                    if f.endswith(".json")}
    except OSError:
        existing = set()
    name = unique_slug(title, date, existing)
    d = os.path.join(a.outdir, name)
    os.makedirs(d, exist_ok=True)
    mp3, txt = os.path.join(d, f"{name}.mp3"), os.path.join(d, "transcript.txt")
    meta = {"slug": name, "title": title}

    if not os.path.exists(mp3):
        write_progress(phase="downloading", pct=0, **meta)
        download(audio_url, mp3)
    secs = duration(mp3)
    print(f"Runtime: {secs/60:.1f} min  (local ETA ~{secs/60/1.6:.0f} min at ~1.6x realtime)")
    meta["runtimeMin"] = round(secs / 60)

    wav = os.path.join(d, f"{name}.wav")
    if not os.path.exists(wav):
        sh("ffmpeg", "-y", "-loglevel", "error", "-i", mp3,
           "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav)
    write_progress(phase="transcribing", pct=0, **meta)
    transcribe_local(wav, txt, a.model, secs, meta, a.cores)
    # Transcription done; still needs extraction/enrich/review before it's on the site.
    write_progress(phase="transcribed", pct=100, **meta)
    a.keep_audio or (os.path.exists(wav) and os.remove(wav))

    if not a.keep_audio and os.path.exists(mp3):
        os.remove(mp3)
    print(f"\nTranscript: {txt}\nNow extract + TMDb-validate the movie list (steps 4-6).")

    if a.publish:  # fire the "process + publish" half on a fresh (post-transcription) process
        cmd = [os.path.join(ROOT, "pipeline", "publish_episode.sh"), name]
        if a.no_merge:
            cmd.append("--no-merge")
        sh(*cmd)
        # Run fully done (PR opened/merged) — hide the "now processing" panel so it doesn't
        # linger as stale until the site redeploys with the episode.
        write_progress(phase="published", pct=100, active=False, **meta)


if __name__ == "__main__":
    main()
