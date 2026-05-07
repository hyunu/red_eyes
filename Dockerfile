FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/
COPY config/ config/

RUN mkdir -p data/events data/logs data/keyframes

VOLUME ["/app/data"]

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "red_eyes.cli"]
