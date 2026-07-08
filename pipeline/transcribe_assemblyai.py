#!/usr/bin/env python3
"""Transcribe a podcast episode via AssemblyAI (async batch API) from its public audio URL.

Cloud alternative to the local faster-whisper engine, for one-time bulk backfill. AssemblyAI
accepts a remote `audio_url`, so we hand it the Megaphone enclosure URL directly — no upload.
Writes the same two files the local pipeline does: <prefix>.txt (plain) and
<prefix>.timestamped.txt. Needs ASSEMBLY_API_KEY in the environment.

Usage: transcribe_assemblyai.py <audio_url> <out_prefix>
"""
import json, os, sys, time, urllib.request

API = "https://api.assemblyai.com/v2"
KEY = os.environ["ASSEMBLY_API_KEY"]
HDR = {"Authorization": KEY, "Content-Type": "application/json"}


def _post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers=HDR, method="POST")
    return json.load(urllib.request.urlopen(req, timeout=30))


def _get(path):
    req = urllib.request.Request(API + path, headers=HDR)
    return json.load(urllib.request.urlopen(req, timeout=30))


def transcribe(audio_url, prefix):
    tid = _post("/transcript", {"audio_url": audio_url})["id"]
    print(f"submitted {tid} for {audio_url}", flush=True)
    while True:
        t = _get(f"/transcript/{tid}")
        st = t["status"]
        if st == "completed":
            break
        if st == "error":
            sys.exit(f"AssemblyAI error: {t.get('error')}")
        time.sleep(15)
    with open(prefix + ".txt", "w") as f:
        f.write(t["text"] + "\n")
    # timestamped, one line per sentence (start seconds) — mirrors the local timestamped file
    sents = _get(f"/transcript/{tid}/sentences").get("sentences", [])
    with open(prefix + ".timestamped.txt", "w") as f:
        for s in sents:
            f.write(f"[{s['start']/1000:8.1f}] {s['text'].strip()}\n")
    print(f"done -> {prefix}.txt ({len(t['text'].split())} words, {len(sents)} sentences)", flush=True)


if __name__ == "__main__":
    transcribe(sys.argv[1], sys.argv[2])
