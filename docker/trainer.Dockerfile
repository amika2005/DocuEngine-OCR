FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/trainer

# Trainer imports the backend's models/config, so install backend first;
# pip then resolves trainer's `docuengine-backend` dep from the installed copy.
COPY backend /srv/backend
RUN pip install --no-cache-dir /srv/backend

COPY trainer/pyproject.toml trainer/README.md ./
COPY trainer/trainer ./trainer
RUN pip install --no-cache-dir .

RUN useradd -r -u 10001 docuengine
USER docuengine

CMD ["celery", "-A", "trainer.celery_app", "worker", "-Q", "training", "-c", "1", "--loglevel=info"]
