"""SSE progress stream. Browsers connect with ?token=<access JWT> (EventSource
cannot set headers); events are filtered to the subscriber's company."""

import asyncio
import json
import uuid

import jwt
from fastapi import APIRouter, HTTPException, Request, status
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.events.publisher import CHANNEL
from app.services.security import decode_token

router = APIRouter(tags=["events"])


@router.get("/events")
async def events(request: Request, token: str):
    try:
        payload = decode_token(token, "access")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    company_id = payload.get("company_id")
    is_super_admin = payload.get("role") == "super_admin"

    import redis.asyncio as aioredis

    client = aioredis.from_url(get_settings().redis_url)
    pubsub = client.pubsub()
    await pubsub.subscribe(CHANNEL)

    async def stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=15.0
                )
                if message is None:
                    # Heartbeat comment keeps proxies from closing the stream.
                    yield {"comment": "ping"}
                    continue
                event = json.loads(message["data"])
                if is_super_admin or event.get("company_id") == company_id:
                    # Unnamed SSE messages so EventSource.onmessage catches every
                    # topic — topics are dynamic (document.<id>.progress).
                    yield {"data": json.dumps(event, ensure_ascii=False)}
        finally:
            await pubsub.unsubscribe(CHANNEL)
            await client.aclose()

    return EventSourceResponse(stream())
