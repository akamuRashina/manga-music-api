FROM node:22-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Clone & build bgutil server matching installed plugin version (gitlink has no .gitmodules)
RUN BGUTIL_VER=$(python -c "import importlib.metadata as m; print(m.version('bgutil-ytdlp-pot-provider'))") \
    && (git clone --depth 1 --branch "$BGUTIL_VER" https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /app/bgutil-ytdlp-pot-provider \
        || git clone --depth 1 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /app/bgutil-ytdlp-pot-provider) \
    && cd /app/bgutil-ytdlp-pot-provider/server \
    && npm ci && npx tsc && npm prune --omit=dev

COPY main.py .
COPY manga_api/ manga_api/
COPY music_api/ music_api/

EXPOSE 10000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
