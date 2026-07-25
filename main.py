"""Entry point for the Telegram community bot."""
import logging

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.config import TELEGRAM_BOT_TOKEN
from bot.database import init_db
from bot.handlers import (
    cmd_addraid,
    cmd_done,
    cmd_find,
    cmd_help,
    cmd_leaderboard,
    cmd_linkx,
    cmd_points,
    cmd_start,
    cmd_task,
    handle_message,
)

logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set.")

    logger.info("Initialising database …")
    init_db()

    logger.info("Starting bot …")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler(["start", "register"], cmd_start))
    app.add_handler(CommandHandler("linkx", cmd_linkx))
    app.add_handler(CommandHandler("task", cmd_task))
    app.add_handler(CommandHandler(["points", "mypoints"], cmd_points))
    app.add_handler(CommandHandler("leaderboard", cmd_leaderboard))
    app.add_handler(CommandHandler("addraid", cmd_addraid))
    app.add_handler(CommandHandler("find", cmd_find))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("help", cmd_help))

    # Catch-all for normal messages → Grok AI
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
