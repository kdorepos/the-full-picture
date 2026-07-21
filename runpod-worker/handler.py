#!/usr/bin/env python3
# RunPod serverless worker for The Full Picture: transcribe one episode's mp3 with faster-whisper
# (medium.en, baked into the image) and return plain + timestamped segments. Invoked per new episode
# (~2-3/week); scales to zero between jobs. The box's transcribe_serverless.py POSTs {input:{audio}}
# and writes the returned segments to out/<slug>/transcript.txt + .timestamped.txt.
import os, time, tempfile, urllib.request
from urllib.parse import urlparse
import runpod
from faster_whisper import WhisperModel, BatchedInferencePipeline

# medium.en is baked into the image (Dockerfile) and loaded ONCE per warm worker. If a different
# model is ever wanted, the Dockerfile bake step + this constant change together (a rebuild) — so
# there's no env-var knob (it would only ever be a footgun that silently triggers a runtime download).
MODEL = "medium.en"
_model = WhisperModel(MODEL, device="cuda", compute_type="float16")
_batched = BatchedInferencePipeline(model=_model)
UA = "Mozilla/5.0 (tfp-runpod-worker)"
MAX_BYTES = 600 * 1024 * 1024   # ~6x a normal episode mp3 — cap so a bad/leaked call can't fetch huge

def _download(url, path, tries=4):
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError("only http/https audio URLs allowed")
    for i in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})  # follows 302 → signed CDN
            total = 0
            with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValueError("audio exceeds size cap")
                    f.write(chunk)
            if os.path.getsize(path) < 10000:
                raise ValueError(f"download too small ({os.path.getsize(path)}B) — likely not audio")
            return
        except Exception:
            if i == tries:
                raise
            time.sleep(5 * i)

def handler(job):
    inp = job.get("input") or {}
    url = inp.get("audio")
    if not url:
        return {"error": "missing 'audio' URL in input"}
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as f:
        _download(url, f.name)
        segments, info = _batched.transcribe(f.name, batch_size=16, language="en", beam_size=5)
        segs = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segments]
    if not segs:
        return {"error": "transcription produced no segments (bad/empty audio?)"}
    return {
        "model": MODEL,
        "duration": round(info.duration, 1),
        "text": "\n".join(s["text"] for s in segs),
        "segments": segs,
    }

runpod.serverless.start({"handler": handler})
