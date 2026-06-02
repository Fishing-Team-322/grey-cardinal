FROM python:3.12-slim

WORKDIR /app

COPY apps/brain-api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY packages /app/packages
COPY apps/brain-api/src /app/src

ENV PYTHONPATH=/app/src:/app/packages/contracts/python

CMD ["uvicorn", "brain_api.main:app", "--host", "0.0.0.0", "--port", "8010"]

