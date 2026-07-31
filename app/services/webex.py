"""
Webex Bot Notification Service.

Sends formatted Markdown alert notifications to Cisco Webex Teams rooms
using the Webex Bot REST API. Uses urllib.request (stdlib) for zero-dependency
HTTP execution.

Runs asynchronously in a thread pool so Webex API latency never blocks
the NOC collection loop.
"""

import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from app.config import settings
from app.utils.logger import get_logger

log = get_logger("services.webex")

_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="webex_worker")


def send_webex_message(
    markdown_text: str,
    target: Literal["test", "it", "both"] | None = None,
) -> None:
    """
    Queue a Webex Markdown message to be sent in the background.

    Args:
        markdown_text: Formatted Markdown text of the message.
        target: Target room ("test", "it", or "both"). Defaults to settings.webex_room_default.
    """
    if not settings.webex_bot_token:
        return

    dest = target or settings.webex_room_default or "both"
    room_ids: list[str] = []

    if dest in ("test", "both") and settings.webex_room_test_id:
        room_ids.append(settings.webex_room_test_id)
    if dest in ("it", "both") and settings.webex_room_it_id:
        room_ids.append(settings.webex_room_it_id)

    if not room_ids:
        return

    for room_id in room_ids:
        _executor.submit(_post_webex_request, room_id, markdown_text)


def _post_webex_request(room_id: str, markdown_text: str) -> bool:
    """Execute standard POST to Webex Teams REST API."""
    url = "https://webexapis.com/v1/messages"
    headers = {
        "Authorization": f"Bearer {settings.webex_bot_token.strip()}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {
        "roomId": room_id,
        "markdown": markdown_text,
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status in (200, 201):
                log.info("Webex notification sent to room %s...", room_id[:15])
                return True
    except Exception as e:
        log.warning("Webex notification failed for room %s...: %s", room_id[:15], e)

    return False
