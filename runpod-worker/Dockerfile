# RunPod serverless worker image — faster-whisper (medium.en) for The Full Picture.
# medium.en is BAKED IN at build time (the download step below) so cold-starts don't pull ~1.5GB
# from the network — the whole point of paying for the image build.
FROM runpod/base:0.6.2-cuda12.1.0

RUN pip install --no-cache-dir faster-whisper==1.2.1 runpod

# Bake the model into the image: run one tiny load so CTranslate2 downloads + caches medium.en now.
RUN python3 -c "from faster_whisper import WhisperModel; WhisperModel('medium.en', device='cpu', compute_type='int8')"

COPY handler.py /handler.py
CMD ["python3", "-u", "/handler.py"]
