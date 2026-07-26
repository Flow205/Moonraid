"""Optional Grok AI replies via xAI's OpenAI-compatible API."""
from __future__ import annotations

from config import GROK_API_KEY, GROK_BASE_URL, GROK_ENABLED, GROK_MODEL

_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import AsyncOpenAI
        _client = AsyncOpenAI(api_key=GROK_API_KEY, base_url=GROK_BASE_URL)
    return _client


async def generate_raid_reply(tweet_content: str, account_username: str) -> str:
    """Generate a genuine, value-adding reply suggestion for a raid tweet."""
    if not GROK_ENABLED:
        return "Great point! Really appreciate you sharing this perspective."
    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model=GROK_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write short, genuine Twitter/X replies that add real value to the conversation. "
                        "Rules: no pitch, no promotion, no hashtags, no emojis. "
                        "Sound like a knowledgeable human, not a bot. "
                        "Max 2 sentences. Be insightful and specific to the tweet content."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Write a reply to this tweet by @{account_username}:\n\n{tweet_content}",
                },
            ],
            max_tokens=120,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "Really interesting take — this is exactly the kind of nuance the market tends to miss."


async def ask_grok(user_message: str, user_name: str = "user") -> str | None:
    """Send a message to Grok and return its reply, or None if AI is disabled."""
    if not GROK_ENABLED:
        return None
    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model=GROK_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful, friendly community bot assistant. "
                        "Keep replies concise (2-4 sentences). "
                        "You help community members stay engaged and motivated."
                    ),
                },
                {"role": "user", "content": f"{user_name}: {user_message}"},
            ],
            max_tokens=300,
        )
        return response.choices[0].message.content
    except Exception as exc:
        return f"⚠️ AI error: {exc}"