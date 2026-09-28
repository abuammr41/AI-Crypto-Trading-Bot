"""
channel_monitor.py
-------------------
Binance ke OFFICIAL Telegram announcement channel
(t.me/binance_api_announcements) ko ROZ EK BAAR check karta hai —
taake API mein koi naya change/update ho (jaisa OCO wala), turant
pata chal jaye, bina kisi surprise error ke.

Telegram ka PUBLIC PREVIEW page use karte hain (t.me/s/channelname) —
isके liye koi bot token, login, ya API key nahi chahiye, bilkul free.
"""

import re
import requests

CHANNEL_URL = "https://t.me/s/binance_api_announcements"
REQUEST_TIMEOUT = 25


def fetch_latest_announcements(limit=5):
    """
    Channel ke recent posts leta hai (sirf text, naye se purane).
    Return: list of strings, ya khali list agar fetch fail ho.
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(CHANNEL_URL, timeout=REQUEST_TIMEOUT, headers=headers)
        if response.status_code != 200:
            print(f"[WARN] Binance announcements fetch: status {response.status_code}")
            return []

        html = response.text
        raw_messages = re.findall(
            r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
            html, re.DOTALL,
        )

        cleaned = []
        for msg in raw_messages:
            text = re.sub(r'<br\s*/?>', '\n', msg)   # line-breaks preserve karo
            text = re.sub(r'<[^>]+>', '', text)        # baaki HTML tags hatao
            text = (
                text.replace("&amp;", "&").replace("&lt;", "<")
                .replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"')
            )
            text = text.strip()
            if text:
                cleaned.append(text)

        # Naye se purane order (page mein purane upar, naye neeche hote hain)
        cleaned.reverse()
        return cleaned[:limit]

    except requests.RequestException as e:
        print(f"[WARN] Binance announcements fetch failed: {e}")
        return []


def get_new_announcements(state):
    """
    State mein "last_seen_announcement" compare karke sirf NAYE posts
    deta hai (jo pehle kabhi nahi dikhaye). Pehli baar (state khali ho)
    to sirf latest 1 post "baseline" ke tor par note kar leta hai,
    poori purani history spam nahi karta.

    Return: list of new announcement texts (khali agar kuch naya nahi).
    """
    latest = fetch_latest_announcements(limit=5)
    if not latest:
        return []

    last_seen = state.get("last_seen_announcement")

    if last_seen is None:
        # Pehli baar — sirf baseline set karo, kuch bhejo mat
        state["last_seen_announcement"] = latest[0]
        return []

    if last_seen == latest[0]:
        return []  # kuch naya nahi hai

    # Jitne bhi posts "last_seen" se pehle hain (naye), sab collect karo
    new_ones = []
    for msg in latest:
        if msg == last_seen:
            break
        new_ones.append(msg)

    state["last_seen_announcement"] = latest[0]
    return new_ones
