# tfp-runpod-worker

RunPod **serverless** worker for [The Full Picture](https://thefullpicture.app): transcribe one
podcast episode's mp3 with faster-whisper (`medium.en`, baked into the image) and return plain +
timestamped segments. Scales to zero between jobs; invoked ~2–3×/week when a new episode drops.

## Contract
**Input** — `{"input": {"audio": "<mp3 url>"}}`

**Output** — `{"model", "duration", "text", "segments": [{"start","end","text"}, ...]}`
The box turns `text` into `transcript.txt` and `segments` into `transcript.timestamped.txt`.

## Deploy (one-time, via RunPod GitHub integration)
1. RunPod console → Serverless → **New Endpoint → GitHub Repo** → authorize GitHub, pick this repo.
2. Set the Dockerfile path to `runpod-worker/Dockerfile`, GPU to an L4-class card, **max workers 1–2**,
   idle timeout low (scale to zero). Create.
3. RunPod builds the image (bakes `medium.en`) and gives an **endpoint ID** — put it in the box's
   `.env` as `RUNPOD_ENDPOINT_ID`. The box's `pipeline/transcribe_serverless.py` calls it.

Updates deploy on a new GitHub **release** (not just a push).
