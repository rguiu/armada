FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tmux \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY armada_ai/ armada_ai/

RUN pip install --no-cache-dir -e .

ENV ARMADA_HOST=0.0.0.0
ENV ARMADA_PORT=9100

EXPOSE 9100

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:9100/health || exit 1

ENTRYPOINT ["armada", "start", "--lan", "--no-browser", "--foreground"]
