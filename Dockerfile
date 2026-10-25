FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ffmpeg: MP3 conversion and video+audio merging
# nodejs: JS runtime yt-dlp needs to solve YouTube's n-challenge (SABR-protected videos)
# tzdata: zone files so TZ (set in docker-compose.yml) takes effect instead of UTC
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first so code changes don't invalidate this layer
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN mkdir -p /app/downloads

# Ports: 8501 = Streamlit, 8000 = REST API
EXPOSE 8501 8000

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
