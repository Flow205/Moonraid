"""Command and message handlers for the community bot."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import re
from datetime import datetime, timezone
from urllib.parse import quote

import database as db
from database import get_recent_posts, set_last_raid_id
from config import (
    GROK_ENABLED,
    LEADERBOARD_SIZE,
    POINTS_LINK_X,
    POINTS_RAID,
    POINTS_REGISTER,
    POINTS_TASK,
)
from grok import ask_grok, generate_raid_reply


def _time_ago(created_at_str: str) -> str:
    created = datetime.fromisoformat(created_at_str)
    diff = datetime.utcnow() - created
    minutes = int(diff.total_seconds() / 60)
    if minutes < 60:
        return f"{minutes}min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def _extract_tweet_id(url: str) -> str | None:
    match = re.search(r"/status/(\d+)", url)
    return match.group(1) if match else None


def _display_name(row) -> str:
    """Return a readable name for a leaderboard row."""
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
# /addraid  (add a raid target)
# ---------------------------------------------------------------------------

async def cmd_addraid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    if not db.get_user(user.id):
        await update.message.reply_text("Please /start first to register.")
        return

    # Usage: /addraid <tweet_url> @account <followers> <tweet content...>
    if not context.args or len(context.args) < 4:
        await update.message.reply_text(
            "Usage: /addraid &lt;tweet_url&gt; @account &lt;followers&gt; &lt;tweet content...&gt;\n\n"
            "Example:\n"
            "<code>/addraid https://x.com/CookerFlips/status/207... @CookerFlips 135k I don't care if you're bearish…</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    tweet_url = context.args[0]
    account = context.args[1].lstrip("@")
    followers = context.args[2]
    tweet_content = " ".join(context.args[3:])

    tweet_id = _extract_tweet_id(tweet_url)
    if not tweet_id:
        await update.message.reply_text(
            "❌ Couldn't extract tweet ID from that URL. Make sure it's a valid X/Twitter link."
        )
        return

    db.add_raid(tweet_url, tweet_id, account, followers, tweet_content, user.id)
    await update.message.reply_text(
        f"✅ Raid added!\n\n"
        f"🎯 Target: @{account} ({followers} followers)\n"
        f"📝 {tweet_content}\n\n"
        f"Members can now use /find to get this raid.",
    )


# ---------------------------------------------------------------------------
# /find  (show current raid with AI reply suggestion)
# ---------------------------------------------------------------------------

async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return

    if not db.get_user(user.id):
        await update.message.reply_text("Please /start first to register.")
        return

    raid = db.get_available_raid(user.id)
    if not raid:
        await update.message.reply_text(
            "✅ No tasks available right now.\nCheck back later for new raids!"
        )
        return

    # Advance cursor so next /find shows a different raid
    set_last_raid_id(user.id, raid["id"])

    # Generate AI reply suggestion
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply_suggestion = await generate_raid_reply(raid["tweet_content"], raid["account_username"])

    # Build pre-filled X reply link
    prefilled_url = (
        f"https://x.com/intent/tweet"
        f"?in_reply_to={raid['tweet_id']}"
        f"&text={quote(reply_suggestion)}"
    )
    time_ago = _time_ago(raid["created_at"])

    await update.message.reply_text(
        f"🎯 raid — reply to @{raid['account_username']} ({raid['followers_count']} followers):\n"
        f"{raid['tweet_content']}\n\n"
        f"{raid['tweet_url']}\n"
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

    # Find the most recent active raid the user hasn't completed yet
    raid = db.get_available_raid(user.id)
    if not raid:
        await update.message.reply_text(
            "⚠️ No open raid found for you. You may have already completed all active raids.\n"
            "Use /find to check for new ones!"
        )
        return

    success = db.complete_raid(raid["id"], user.id, reply_url, POINTS_RAID)
    if not success:
        await update.message.reply_text(
            "⚠️ Looks like you already submitted this raid. Use /find for the next one!"
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
        "/find — Get the current raid target + AI reply suggestion\n"
        "/done &lt;reply_url&gt; — Submit your raid reply to earn points\n"
        "/addraid &lt;url&gt; @account &lt;followers&gt; &lt;content&gt; — Add a raid target\n"
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