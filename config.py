import os

TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GROK_API_KEY: str = os.environ.get("GROK_API_KEY", "")
GROK_ENABLED: bool = bool(GROK_API_KEY)
TWITTER_BEARER_TOKEN: str = os.environ.get("TWITTER_BEARER_TOKEN", "")
GROK_MODEL: str = "llama-3.3-70b-versatile"
GROK_BASE_URL: str = "https://api.groq.com/openai/v1"

DB_PATH: str = "bot/community.db"

# Points awarded per action
POINTS_REGISTER: int = 10
POINTS_LINK_X: int = 5
POINTS_TASK: int = 5
POINTS_RAID: int = 20

LEADERBOARD_SIZE: int = 10
