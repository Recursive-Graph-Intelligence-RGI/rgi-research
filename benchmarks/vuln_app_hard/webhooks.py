"""Outbound webhooks: ping a URL the merchant configures."""
import urllib.request


def test_webhook(callback_url: str) -> int:
    """Fetch the merchant's callback URL to verify it responds."""
    with urllib.request.urlopen(callback_url) as resp:
        return resp.status


def send_event(callback_url: str, payload: bytes) -> int:
    req = urllib.request.Request(callback_url, data=payload)
    with urllib.request.urlopen(req) as resp:
        return resp.status
