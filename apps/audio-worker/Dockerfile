FROM python:3.12-slim

WORKDIR /app

COPY apps/audio-worker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY packages /app/packages
COPY apps/audio-worker/src /app/src

ENV PYTHONPATH=/app/src:/app/packages/contracts/python

CMD ["uvicorn", "audio_worker.main:app", "--host", "0.0.0.0", "--port", "8020"]

