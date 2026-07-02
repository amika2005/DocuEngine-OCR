"""Progress events: workers publish to one Redis channel; the API's SSE endpoint
fans out to browsers, filtered by the subscriber's company_id."""

import json
import uuid
from datetime import datetime, timezone

import redis

from app.config import get_settings

CHANNEL = "docuengine:events"

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(get_settings().redis_url)
    return _client


def publish_event(company_id: uuid.UUID, topic: str, data: dict) -> None:
    """Fire-and-forget: progress events must never fail the OCR pipeline."""
    payload = json.dumps(
        {
            "company_id": str(company_id),
            "topic": topic,
            "data": data,
            "ts": datetime.now(timezone.utc).isoformat(),
        },
        ensure_ascii=False,
    )
    try:
        _get_client().publish(CHANNEL, payload)
    except redis.RedisError:
        pass
