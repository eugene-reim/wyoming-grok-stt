FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir \
    wyoming==1.5.4 \
    httpx

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Only copy what we need
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY main.py .

RUN useradd -l --create-home wyoming-grok-stt && \
    chown -R wyoming-grok-stt:wyoming-grok-stt /app

USER wyoming-grok-stt

EXPOSE 10300

# Real healthcheck – checks that the TCP server is listening
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import socket; socket.create_connection(('127.0.0.1', 10300), timeout=2)" || exit 1

CMD ["python", "main.py"]