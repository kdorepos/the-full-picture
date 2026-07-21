#!/usr/bin/env python3
# Transcribe one episode via the RunPod SERVERLESS endpoint, writing out/<slug>/transcript.txt +
# transcript.timestamped.txt + .complete — the same files the local transcriber produces, so the
# publish driver picks it up identically. Falls back to LOCAL CPU transcription if serverless is
# unconfigured/unavailable/errors, so a new episode is never stranded.
#
# Usage: transcribe_serverless.py <slug> <mp3_url>
import os, sys, json, time, re, urllib.request

REPO = "/srv/the-full-picture"
def env(k):
    try:
        for line in open(f"{REPO}/.env"):
            if line.startswith(k + "="):
                return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return ""

API_KEY = env("RUNPOD_API_KEY")
ENDPOINT = env("RUNPOD_ENDPOINT_ID")

def _req(url, data=None):
    hdr = {"Authorization": f"Bearer {API_KEY}"}
    if data is not None:
        hdr["Content-Type"] = "application/json"
        data = json.dumps(data).encode()
    return json.load(urllib.request.urlopen(urllib.request.Request(url, data=data, headers=hdr), timeout=40))

def transcribe_serverless(mp3_url, timeout=1500):
    base = f"https://api.runpod.ai/v2/{ENDPOINT}"
    job = _req(f"{base}/run", {"input": {"audio": mp3_url}})
    jid = job.get("id")
    if not jid:
        raise RuntimeError(f"no job id from /run: {job}")
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = _req(f"{base}/status/{jid}")
        s = st.get("status")
        if s == "COMPLETED":
            return st.get("output") or {}
        if s in ("FAILED", "CANCELLED", "TIMED_OUT"):
            raise RuntimeError(f"runpod job {s}: {str(st)[:300]}")
        time.sleep(10)
    raise TimeoutError("runpod job did not complete within timeout")

def write_from_segments(slug, out):
    d = f"{REPO}/out/{slug}"; os.makedirs(d, exist_ok=True)
    segs = out.get("segments") or []
    if not segs:
        raise RuntimeError("no segments in serverless output")
    with open(f"{d}/transcript.txt", "w") as ft, open(f"{d}/transcript.timestamped.txt", "w") as fs:
        for seg in segs:
            ft.write(seg["text"].strip() + "\n")
            fs.write(f"[{seg['start']:8.1f}] {seg['text'].strip()}\n")
    open(f"{d}/.complete", "w").close()   # sentinel last: a crash mid-write never looks "done"

def local_fallback(slug, mp3_url):
    sys.path.insert(0, f"{REPO}/pipeline"); os.chdir(REPO)
    from the_full_picture import download, duration, transcribe_local, sh
    d = f"out/{slug}"; os.makedirs(d, exist_ok=True)
    mp3, wav, txt = f"{d}/{slug}.mp3", f"{d}/{slug}.wav", f"{d}/transcript.txt"
    try:
        download(mp3_url, mp3); secs = duration(mp3)
        sh("ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav)
        transcribe_local(wav, txt, "medium.en", secs, {"slug": slug, "title": slug, "runtimeMin": round(secs / 60)}, 3)
        open(f"{d}/.complete", "w").close()
    finally:
        for p in (mp3, wav):
            try: os.path.exists(p) and os.remove(p)
            except OSError: pass

def main():
    if len(sys.argv) < 3:
        sys.exit("usage: transcribe_serverless.py <slug> <mp3_url>")
    slug, mp3_url = sys.argv[1], sys.argv[2]
    if not re.fullmatch(r"[a-z0-9-]{1,60}", slug):   # matches the pipeline's slug() — no path traversal
        sys.exit(f"bad slug: {slug!r}")
    try:
        if not (API_KEY and ENDPOINT):
            raise RuntimeError("RunPod not configured (RUNPOD_API_KEY / RUNPOD_ENDPOINT_ID)")
        out = transcribe_serverless(mp3_url)
        if out.get("error"):
            raise RuntimeError(f"worker error: {out['error']}")
        write_from_segments(slug, out)
        print(f"serverless OK {slug} ({(out.get('duration') or 0)/60:.0f}m audio, {len(out['segments'])} segs)")
    except Exception as e:
        print(f"serverless path FAILED ({type(e).__name__}: {e}) — falling back to local CPU transcription")
        local_fallback(slug, mp3_url)
        print(f"local fallback OK {slug}")

if __name__ == "__main__":
    main()
