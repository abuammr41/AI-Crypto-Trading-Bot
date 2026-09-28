"""
telegram_helper.py
-------------------
Telegram par message bhejne ke liye. Agar internet/Telegram down ho,
error ko silently handle karta hai — poori script crash nahi hoti.
"""

import requests
import config


def send_message(text):
    """Telegram bot ke zariye message bhejta hai. Fail hone par sirf print karta hai, crash nahi hoti."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("[TELEGRAM] Token/Chat ID missing, skipping notification.")
        return

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(
            url,
            data={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
            timeout=25,
        )
    except requests.RequestException as e:
        print(f"[TELEGRAM] Failed to send message: {e}")
