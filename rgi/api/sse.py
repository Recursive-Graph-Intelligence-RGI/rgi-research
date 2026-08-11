"""Server-Sent Events helper for streaming JSON events."""
import json
from typing import Any, AsyncGenerator

from aiohttp import web


async def event_stream(
    request: web.Request, generator: AsyncGenerator[dict[str, Any], None]
) -> web.StreamResponse:
    """Stream JSON events to the client using SSE.

    Each yielded dict is serialized and sent as ``data: <json>\\n\\n``.
    A final ``data: [DONE]\\n\\n`` marker is written when the generator ends.
    """
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await response.prepare(request)
    async for event in generator:
        payload = json.dumps(event)
        await response.write(f"data: {payload}\n\n".encode("utf-8"))
    await response.write("data: [DONE]\n\n".encode("utf-8"))
    await response.write_eof()
    return response
