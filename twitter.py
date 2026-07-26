"""Twitter/X API v2 client for fetching latest tweets from monitored accounts."""
from __future__ import annotations

import os
import httpx

BEARER_TOKEN: str = os.environ.get("TWITTER_BEARER_TOKEN", "")
BASE_URL = "https://api.twitter.com/2"
HEADERS = {"Authorization": f"Bearer {BEARER_TOKEN}"}


async def get_user_info(username: str) -> dict | None:
    """Resolve a Twitter username → id + followers_count."""
    clean = username.lstrip("@")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{BASE_URL}/users/by/username/{clean}",
                headers=HEADERS,
                params={"user.fields": "public_metrics"},
            )
            if r.status_code == 200:
                data = r.json()["data"]
                followers = data.get("public_metrics", {}).get("followers_count", 0)
                return {
                    "id": data["id"],
                    "username": data["username"],
                    "followers_count": followers,
                }
            return None
    except Exception:
        return None


async def get_latest_tweets(twitter_user_id: str, max_results: int = 5) -> list[dict]:
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