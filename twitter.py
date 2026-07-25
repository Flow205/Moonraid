"""Twitter/X API v2 client for fetching latest tweets from monitored accounts."""
from __future__ import annotations

import os
import httpx

BEARER_TOKEN: str = os.environ.get("TWITTER_BEARER_TOKEN", "")
BASE_URL = "https://api.twitter.com/2"
HEADERS = {"Authorization": f"Bearer {BEARER_TOKEN}"}


async def get_user_id(username: str) -> str | None:
    """Resolve a Twitter username to its numeric user ID."""
    clean = username.lstrip("@")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{BASE_URL}/users/by/username/{clean}",
                headers=HEADERS,
            )
            if r.status_code == 200:
                return r.json()["data"]["id"]
            return None
    except Exception:
        return None


async def get_latest_tweets(twitter_user_id: str, max_results: int = 10) -> list[dict]:
    """Fetch the latest original tweets (no retweets, no replies) from a user."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{BASE_URL}/users/{twitter_user_id}/tweets",
                headers=HEADERS,
                params={
                    "max_results": max_results,
                    "tweet.fields": "created_at,text",
                    "exclude": "retweets,replies",
                },
            )
            if r.status_code == 200:
                return r.json().get("data", [])
            return []
    except Exception:
        return []
