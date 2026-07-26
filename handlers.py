"""Command and message handlers for the community bot."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import re
from datetime import datetime, timezone
from urllib.parse import quote

import database as db
from config import (
    GROK_ENABLED,
    LEADERBOARD_SIZE,
    POINTS_LINK_X,
    POINTS_RAID,
    POINTS_REGISTER,
    POINTS_TASK,
)
from grok import ask_grok, generate_raid_reply
from twitter import get_user_info, get_latest_tweets


def _time_ago(created_at_str: str) -> str:
    try:
        created = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - created
        minutes = int(diff.total_seconds() / 60)
        if minutes < 60:
            return f"{minutes}min ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        return f"{hours // 24}d ago"
    except Exception:
        return "recently"


def _extract_username(text: str) -> str | None:
    """Extract username from @user or https://x.com/user"""
    text = text.strip()
    if text.startswith("@"):
        return text.lstrip("@")
    match = re.search(r"(?:x\.com|twitter\.com)/([A-Za-z0-9_]+)", text)
    if match:
        return match.group(1)
    if re.match(r"^[A-Za-z0-9_]+$", text):
        return text
    return None


def _display_name(row) -> str:
    if row["username"]:
        return f"@{row['username']}"
    return row["first_name"] or "Unknown"


# ---------------------------------------------------------------------------
# /start  &  /register
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return

    existing = db.get_user(user.id)
    if existing:
        await update.message.reply_text(
            f"👋 Welcome back, <b>{user.first_name}</b>!\n"
            f"You have <b>{existing['points']} points</b>.\n\n"
            "Use /help to see what you can do.",
            parse_mode=ParseMode.HTML,
        )
        return

    success = db.register_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        bonus_points=POINTS_REGISTER,
    )
    if success:
        await update.message.reply_text(
            f"🎉 Welcome to the community, <b>{user.first_name}</b>!\n"
            f"You've been registered and earned <b>{POINTS_REGISTER} points</b> to start.\n\n"
            "📌 What's next?\n"
            f"• Link your X account: /linkx &lt;username&gt; (+{POINTS_LINK_X} pts)\n"
            f"• Log a task: /task &lt;description&gt; (+{POINTS_TASK} pts)\n"
            "• Check the /leaderboard",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text("Something went wrong. Please try again.")


# ---------------------------------------------------------------------------
# /linkx
# ---------------------------------------------------------------------------

async def cmd_linkx(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return

    if not db.get_user(user.id):
        await update.message.reply_text("Please /start first to register.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /linkx &lt;your_x_username&gt;\nExample: /linkx elonmusk",
            parse_mode=ParseMode.HTML,
        )
        return

    x_username = context.args[0].lstrip("@")
    db.link_x_username(user.id, x_username, POINTS_LINK_X)
    await update.message.reply_text(
        f"✅ Linked <b>@{x_username}</b> on X to your profile!\n"
        f"You earned <b>+{POINTS_LINK_X} points</b>.",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# /task
# ---------------------------------------------------------------------------

async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return

    if not db.get_user(user.id):
        await update.message.reply_text("Please /start first to register.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /task &lt;description of what you did&gt;\nExample: /task Shared the project on X",
            parse_mode=ParseMode.HTML,
        )
        return

    description = " ".join(context.args)
    db.log_task(user.id, description, POINTS_TASK)
    await update.message.reply_text(
        f"📝 Task logged: <i>{description}</i>\n"
        f"You earned <b>+{POINTS_TASK} points</b>! Keep it up 🚀",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# /points
# ---------------------------------------------------------------------------

async def cmd_points(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return

    row = db.get_user(user.id)
    if not row:
        await update.message.reply_text("Please /start first to register.")
        return

    tasks = db.get_user_tasks(user.id, limit=5)
    x_line = f"🐦 X: @{row['x_username']}\n" if row["x_username"] else ""
    tasks_section = ""
    if tasks:
        task_lines = "\n".join(
            f"  • {t['description']} (+{t['points_earned']} pts)" for t in tasks
        )
        tasks_section = f"\n\n📋 Recent tasks:\n{task_lines}"

    await update.message.reply_text(
        f"👤 <b>{user.first_name}</b>\n"
        f"{x_line}"
        f"⭐ Points: <b>{row['points']}</b>"
        f"{tasks_section}",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# /leaderboard
# ---------------------------------------------------------------------------

async def cmd_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = db.get_leaderboard(LEADERBOARD_SIZE)
    if not rows:
        await update.message.reply_text("No members yet. Be the first to /start!")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, row in enumerate(rows):
        medal = medals[i] if i < 3 else f"{i + 1}."
        name = _display_name(row)
        x_tag = f" 🐦@{row['x_username']}" if row["x_username"] else ""
        lines.append(f"{medal} {name}{x_tag} — <b>{row['points']} pts</b>")

    await update.message.reply_text(
        "🏆 <b>Community Leaderboard</b>\n\n" + "\n".join(lines),
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# /add  (add X account to track)
# ---------------------------------------------------------------------------

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return

    if not db.get_user(user.id):
        await update.message.reply_text("Please /start first to register.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /add &lt;username or profile link&gt;\n\n"
            "Examples:\n"
            "<code>/add OnchainDataNerd</code>\n"
            "<code>/add @OnchainDataNerd</code>\n"
            "<code>/add https://x.com/OnchainDataNerd</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    raw = " ".join(context.args)
    username = _extract_username(raw)
    if not username:
        await update.message.reply_text("❌ Could not understand that username or link.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    info = await get_user_info(username)
    if not info:
        await update.message.reply_text(
            f"❌ Could not find @{username} on X.\n"
            "Make sure the username is correct and that TWITTER_BEARER_TOKEN is set."
        )
        return

    followers = info["followers_count"]
    followers_str = f"{followers:,}" if followers >= 1000 else str(followers)

    success = db.add_monitored_account(
        username=info["username"],
        followers_count=followers_str,
        added_by=user.id,
    )

    if not success:
        await update.message.reply_text(f"ℹ️ @{info['username']} is already being tracked.")
        return

    # Store the twitter user id
    db.update_twitter_user_id(info["username"], info["id"])

    await update.message.reply_text(
        f"✅ added <b>@{info['username']}</b>\n"
        f"now tracking · {followers_str} followers",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# /find  (show latest post from tracked accounts)
# ---------------------------------------------------------------------------

async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return

    if not db.get_user(user.id):
        await update.message.reply_text("Please /start first to register.")
        return

    accounts = db.get_monitored_accounts()
    if not accounts:
        await update.message.reply_text(
            "No accounts are being tracked yet.\n"
            "Use /add @username to start tracking influencers."
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Look for a fresh tweet the user hasn't seen yet
    chosen = None
    for acc in accounts:
        if not acc["twitter_user_id"]:
            continue

        tweets = await get_latest_tweets(acc["twitter_user_id"], max_results=5)
        for tw in tweets:
            tweet_id = tw["id"]
            if db.is_tweet_seen(tweet_id, user.id):
                continue

            # Found a new one
            tweet_url = f"https://x.com/{acc['username']}/status/{tweet_id}"
            db.mark_tweet_seen(
                tweet_id=tweet_id,
                tweet_content=tw["text"],
                tweet_url=tweet_url,
                account_username=acc["username"],
                followers_count=acc["followers_count"],
                telegram_id=user.id,
            )
            chosen = {
                "tweet_id": tweet_id,
                "text": tw["text"],
                "url": tweet_url,
                "username": acc["username"],
                "followers": acc["followers_count"],
                "created_at": tw.get("created_at", ""),
            }
            break
        if chosen:
            break

    if not chosen:
        await update.message.reply_text(
            "✅ No new posts available right now.\n"
            "Check back later or add more accounts with /add"
        )
        return

    # Generate AI reply suggestion
    reply_suggestion = await generate_raid_reply(chosen["text"], chosen["username"])

    prefilled_url = (
        f"https://x.com/intent/tweet"
        f"?in_reply_to={chosen['tweet_id']}"
        f"&text={quote(reply_suggestion)}"
    )
    time_ago = _time_ago(chosen["created_at"])

    await update.message.reply_text(
        f"🎯 raid — reply to @{chosen['username']} ({chosen['followers']} followers):\n"
        f"{chosen['text']}\n\n"
        f"{chosen['url']}\n"
        f"🕒 {time_ago}\n\n"
        f"💬 genuine reply (no pitch — just add value; the points come later):\n"
        f"<i>{reply_suggestion}</i>\n"
        f'👉 <a href="{prefilled_url}">Reply on X (pre-filled)</a>\n\n'
        f"after posting, send /done &lt;link to your reply&gt; to score · /find for the next one",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


# ---------------------------------------------------------------------------
# /done  (submit raid completion)
# ---------------------------------------------------------------------------

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return

    if not db.get_user(user.id):
        await update.message.reply_text("Please /start first to register.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /done &lt;link to your X reply&gt;\n"
            "Example: /done https://x.com/yourname/status/123456",
            parse_mode=ParseMode.HTML,
        )
        return

    reply_url = context.args[0]
    if not reply_url.startswith("http"):
        await update.message.reply_text("Please provide a valid URL to your X reply.")
        return

    pending = db.get_pending_tweet(user.id)
    if not pending:
        await update.message.reply_text(
            "⚠️ No open raid found for you.\n"
            "Use /find to get a new one first!"
        )
        return

    success = db.complete_tweet(
        tweet_id=pending["tweet_id"],
        telegram_id=user.id,
        reply_url=reply_url,
        points=POINTS_RAID,
    )

    if not success:
        await update.message.reply_text(
            "⚠️ Looks like you already submitted this one. Use /find for the next."
        )
        return

    updated = db.get_user(user.id)
    await update.message.reply_text(
        f"🎉 Raid complete! You earned <b>+{POINTS_RAID} points</b>!\n"
        f"⭐ Total: <b>{updated['points']} points</b>\n\n"
        f"🔍 Use /find for the next raid.",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ai_note = (
        "\n🤖 <b>AI replies</b> — Mention me or message me in private for AI responses."
        if GROK_ENABLED
        else ""
    )
    await update.message.reply_text(
        "📖 <b>Community Bot Commands</b>\n\n"
        "/start — Register and join the community\n"
        "/linkx &lt;username&gt; — Link your X (Twitter) account\n"
        "/task &lt;description&gt; — Log a completed task\n"
        "/add &lt;username or link&gt; — Start tracking an X account\n"
        "/find — Get the latest post from tracked accounts + AI reply\n"
        "/done &lt;reply_url&gt; — Submit your reply to earn points\n"
        "/points — Check your points and recent tasks\n"
        "/leaderboard — See the top members\n"
        "/help — Show this message"
        f"{ai_note}",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# Message handler (AI chat)
# ---------------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    if user is None:
        return

    reply = await ask_grok(update.message.text, user.first_name or "user")
    if reply:
        await update.message.reply_text(reply)