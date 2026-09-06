"""Telegram notification wrapper."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path


def notify_telegram(message: str, chat_id: str | None = None) -> bool:
    """Send message via Telegram Bot API.
    
    Returns True if sent, False if no token configured or send failed.
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return False
    if chat_id is None:
        chat_id = os.environ.get("OPENCODE_NOTIFICATION_TELEGRAM_CHAT_ID")
    if not chat_id:
        return False
    try:
        result = subprocess.run(
            [
                "curl", "-s", "-X", "POST",
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                "-d", f"chat_id={chat_id}",
                "-d", f"text={message}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False