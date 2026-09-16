import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.error import InvalidToken, NetworkError

from emojigif.bot import build_application


def main() -> None:
    load_dotenv(Path(__file__).with_name(".env"), encoding="utf-8-sig")
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set BOT_TOKEN in .env. Get a token from @BotFather using /newbot.")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Request URLs contain the bot token.
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    logging.getLogger("httpcore").setLevel(logging.CRITICAL)
    try:
        build_application(token).run_polling(
            allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY],
            drop_pending_updates=False,
        )
    except InvalidToken:
        raise SystemExit("Invalid BOT_TOKEN. Check the token from @BotFather in .env.") from None
    except NetworkError:
        raise SystemExit(
            "Cannot connect to Telegram. Check your internet connection and restart the bot."
        ) from None


if __name__ == "__main__":
    main()
