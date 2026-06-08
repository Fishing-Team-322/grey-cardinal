FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

ENV PYTHONUNBUFFERED=1 \
    PULSE_SERVER=unix:/tmp/pulse/native \
    PYTHONPATH=/app/src

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg pulseaudio pulseaudio-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY apps/telemost-recorder/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY apps/telemost-recorder/src /app/src
COPY apps/telemost-recorder/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
