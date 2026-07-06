#!/usr/bin/env python3
"""the-full-picture: podcast episode/feed URL -> local transcript.txt

Steps 1-3 of the pipeline (resolve audio -> download -> 16kHz mono FLAC chunks ->
transcribe). Extraction + TMDb validation (steps 4-6) are done by hand afterwards
against the transcript. See CLAUDE.md.

Engines:
  groq  (default) - Groq whisper-large-v3-turbo. Best accuracy on proper nouns,
                    ~$0/episode on the free tier. Needs GROQ_KEY + curl.
                    Free tier caps audio at 7200s/hr; we PACE chunks to stay under it,
                    so a 2h+ episode spans >1hr wall-clock but never errors.
  local           - faster-whisper medium.en on CPU. No network, no rate limit.

Usage: ./venv/bin/python the_full_picture.py <url> [--engine groq|local]
"""
import os, re, sys, time, json, subprocess, urllib.request, argparse, unicodedata

UA = "Mozilla/5.0"
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
ASPH_LIMIT = 7200          # free-tier seconds-of-audio-per-hour
ASPH_SAFE = 7000           # leave margin so we never trip the cap
CHUNK_SECS = 600           # 10-min chunks -> ~19MB FLAC, under the 25MB free-tier upload cap


def sh(*cmd):
    subprocess.run(cmd, check=True)


def resolve_audio(url, item_index=0):
    """Return (audio_url, title). Handles RSS feeds (<enclosure>; item 0 is newest,
    item_index picks an older one) and Overcast-style episode pages (<source src=...>)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    body = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    # RSS feed: pick the Nth <item>'s enclosure (feeds are newest-first)
    if "<enclosure" in body:
        items = body.split("<item>")[1:]
        if 0 <= item_index < len(items):
            item = items[item_index].split("</item>", 1)[0]
            au = re.search(r'<enclosure[^>]+url="([^"]+)"', item, re.I)
            ti = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", item, re.S)
            if au:
                return au.group(1), (ti.group(1).strip() if ti else "episode")
    # Overcast page: raw HTML embeds the real Megaphone CDN enclosure as <source>
    m = re.search(r'<source[^>]+src="([^"]+)"', body, re.I)
    if not m:
        sys.exit("Could not find an <enclosure> (RSS) or <source> (page) audio URL.")
    t = re.search(r"<title>([^<]+)</title>", body, re.I)
    return m.group(1), (t.group(1).strip() if t else "episode")


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "episode"


def download(audio_url, mp3):
    print(f"Downloading -> {mp3}")
    req = urllib.request.Request(audio_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(mp3, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)


def duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path])
    return float(out.strip())


def chunk_flac(mp3, secs, chunkdir):
    """Cut mp3 into CHUNK_SECS 16kHz-mono FLAC pieces. We seek per-chunk with -ss/-t
    instead of `-f segment` because the segment muxer writes a bogus whole-file
    duration into the LAST FLAC's header, which Groq then rejects as too large."""
    os.makedirs(chunkdir, exist_ok=True)
    paths = []
    i, start = 0, 0.0
    while start < secs:
        p = os.path.join(chunkdir, f"c{i:03d}.flac")
        if not os.path.exists(p):
            sh("ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-t", str(CHUNK_SECS),
               "-i", mp3, "-ar", "16000", "-ac", "1", p)
        paths.append(p)
        i += 1
        start += CHUNK_SECS
    return paths


def groq_post(flac, key):
    """POST one chunk. Returns ('ok', (text, segments)) or ('retry', wait_seconds).
    An empty/non-JSON body (network hiccup, curl timeout) is retryable, not fatal."""
    out = subprocess.run(
        ["curl", "-sS", "--max-time", "300", GROQ_URL,
         "-H", f"Authorization: Bearer {key}",
         "-F", f"file=@{flac}", "-F", "model=whisper-large-v3-turbo",
         "-F", "language=en", "-F", "response_format=verbose_json"],
        capture_output=True, text=True).stdout.strip()
    if not out:
        return "retry", 30
    try:
        d = json.loads(out)
    except json.JSONDecodeError:
        return "retry", 30
    if "text" in d:
        return "ok", (d["text"].strip(), d.get("segments", []))
    err = d.get("error", {}).get("message", out[:200])
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", err)
    wait = int((int(m.group(1) or 0)) * 60 + float(m.group(2))) + 15 if m else 90
    return "retry", wait


def transcribe_groq(chunks, key, txt):
    """Transcribe chunks via Groq, pacing submissions under the free-tier 7200s/hr cap.
    Each chunk's result is cached to <chunk>.json so a long paced run (or a crash) resumes
    instead of re-doing work. Transcripts are rebuilt from the cache at the end."""
    window = []
    for i, c in enumerate(chunks):
        j = os.path.splitext(c)[0] + ".json"
        if os.path.exists(j):
            try:
                if "text" in json.load(open(j)):
                    print(f"  chunk {i+1}/{len(chunks)} cached"); continue
            except Exception:
                pass
        need = duration(c)
        while True:  # pace: wait until this chunk fits the rolling-hour budget
            now = time.monotonic()
            window[:] = [(t, s) for t, s in window if now - t < 3600]
            used = sum(s for _, s in window)
            if used + need <= ASPH_SAFE:
                break
            sleep = min(3600 - (now - window[0][0]) + 1, 60)
            print(f"  pacing: {used:.0f}/{ASPH_LIMIT}s used this hr, sleeping {sleep:.0f}s")
            time.sleep(sleep)
        while True:  # submit, retrying transient errors + rate limits
            status, payload = groq_post(c, key)
            if status == "ok":
                break
            print(f"  retry in {payload}s ({os.path.basename(c)})")
            time.sleep(payload)
        text, segments = payload
        json.dump({"text": text, "segments": segments}, open(j, "w"))
        window.append((time.monotonic(), need))
        print(f"  chunk {i+1}/{len(chunks)} done ({need:.0f}s audio)")

    stamped = txt.replace(".txt", ".timestamped.txt")
    with open(txt, "w") as ft, open(stamped, "w") as fs:
        for i, c in enumerate(chunks):
            d = json.load(open(os.path.splitext(c)[0] + ".json"))
            off = i * CHUNK_SECS
            ft.write(d["text"].strip() + "\n")
            for s in d.get("segments", []):
                fs.write(f"[{s['start'] + off:8.1f}] {s['text'].strip()}\n")


def transcribe_local(wav, txt, model_name):
    from faster_whisper import WhisperModel, BatchedInferencePipeline
    cores = os.cpu_count() or 4
    print(f"Loading {model_name} (int8, {cores} threads)")
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=cores)
    batched = BatchedInferencePipeline(model=model)
    segments, _ = batched.transcribe(wav, batch_size=8, language="en", beam_size=5)
    stamped = txt.replace(".txt", ".timestamped.txt")
    with open(txt, "w") as ft, open(stamped, "w") as fs:
        for seg in segments:
            ft.write(seg.text.strip() + "\n"); ft.flush()
            fs.write(f"[{seg.start:8.1f}] {seg.text.strip()}\n"); fs.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--engine", choices=["groq", "local"], default="groq")
    ap.add_argument("--model", default="medium.en", help="local engine only")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--item", type=int, default=0, help="RSS feed item index (0 = newest)")
    ap.add_argument("--keep-audio", action="store_true")
    a = ap.parse_args()

    audio_url, title = resolve_audio(a.url, a.item)
    print(f"Episode: {title}")
    name = slug(title)
    d = os.path.join(a.outdir, name)
    os.makedirs(d, exist_ok=True)
    mp3, txt = os.path.join(d, f"{name}.mp3"), os.path.join(d, "transcript.txt")

    if not os.path.exists(mp3):
        download(audio_url, mp3)
    secs = duration(mp3)
    print(f"Runtime: {secs/60:.1f} min")

    if a.engine == "groq":
        key = os.environ.get("GROQ_KEY") or sys.exit("Set GROQ_KEY (see .env).")
        chunks = chunk_flac(mp3, secs, os.path.join(d, "chunks"))
        n = len(chunks)
        if secs > ASPH_LIMIT:
            print(f"Note: {secs/60:.0f} min > free-tier 120 min/hr cap; pacing will span "
                  f"~{secs/ASPH_SAFE:.1f}hr wall-clock.")
        transcribe_groq(chunks, key, txt)
    else:
        wav = os.path.join(d, f"{name}.wav")
        if not os.path.exists(wav):
            sh("ffmpeg", "-y", "-loglevel", "error", "-i", mp3,
               "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav)
        transcribe_local(wav, txt, a.model)
        a.keep_audio or (os.path.exists(wav) and os.remove(wav))

    if not a.keep_audio and os.path.exists(mp3):
        os.remove(mp3)
    print(f"\nTranscript: {txt}\nNow extract + TMDb-validate the movie list (steps 4-6).")


if __name__ == "__main__":
    main()
