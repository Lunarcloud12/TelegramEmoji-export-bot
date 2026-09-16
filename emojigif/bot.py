"""Telegram handlers and temporary-file lifecycle."""

import asyncio
import contextlib
import io
import logging
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import httpx
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Sticker,
    Update,
)
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from emojigif.convert import MAX_FILE_BYTES, ConversionError, hidden_process_options
from emojigif.extract import extract_emojis, twemoji_names
from emojigif.network import RequestFailure, request_with_retry
from emojigif.settings import DEFAULT_SETTINGS, ExportSettings, SettingsStore
from emojigif.settings_ui import (
    accept_custom_size,
    cancel,
    current_settings,
    settings_callback,
    show_settings,
)

LOG = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
MAX_PER_MESSAGE = 5
TWEMOJI_BASE = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@17.0.3/assets/72x72"
HELP = (
    "Send me an emoji or sticker to export it as GIF, video, or PNG.\n\n"
    "📦 Default export: GIF, MP4, WEBM, MOV, and a first-frame PNG, "
    "at 128, 256, and 512 px, packed in a ZIP archive.\n"
    "MOV, WEBM, and PNG preserve transparency. MP4 uses a white background.\n\n"
    "⚙️ /settings — choose sizes, formats, PNG mode, delivery, "
    "frame rate, quality, and background.\n"
    "✨ Custom and premium emoji keep their original animation, when available.\n"
    "🧩 Stickers and TGS, WEBM, WEBP, or PNG files are supported.\n"
    "🙂 Standard Unicode emoji use static Twemoji artwork.\n\n"
    "Send up to 5 distinct emoji at a time. Each gets its own export set.\n"
    "Input limit: 10 MB. Animation limit: 10 seconds."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        markup = None
        if update.effective_user:
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⚙️ Export settings",
                            callback_data=f"cfg:{update.effective_user.id}:page:main",
                        )
                    ]
                ]
            )
        await update.effective_message.reply_text(HELP, reply_markup=markup)


async def download_telegram(context: ContextTypes.DEFAULT_TYPE, file_id: str, path: Path) -> None:
    remote = await request_with_retry("get_file", lambda: context.bot.get_file(file_id))
    if remote.file_size and remote.file_size > MAX_FILE_BYTES:
        raise ConversionError("The file exceeds 10 MB.")
    # Stream with an actual byte limit, even when Telegram omits file_size.
    if not remote.file_path:
        raise ConversionError("Telegram did not return a file.")
    if not await download_url(context.application.bot_data["http"], remote.file_path, path):
        raise ConversionError("The file is no longer available on Telegram. Send the emoji again.")


async def download_url(client: httpx.AsyncClient, url: str, path: Path) -> bool:
    return await request_with_retry("download", lambda: download_once(client, url, path))


async def download_once(client: httpx.AsyncClient, url: str, path: Path) -> bool:
    async with client.stream("GET", url) as response:
        if response.status_code == 404:
            return False
        response.raise_for_status()
        size = 0
        with path.open("wb") as output:
            async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise ConversionError("The file exceeds 10 MB.")
                output.write(chunk)
    return True


def run_conversion(source: Path, output: Path, settings: ExportSettings | None = None) -> None:
    worker_env = {key: value for key, value in os.environ.items() if key != "BOT_TOKEN"}
    worker_env["PYTHONIOENCODING"] = "utf-8"
    command = [sys.executable, "-m", "emojigif.convert", str(source), str(output)]
    if settings is not None:
        config = output.with_suffix(".settings.json")
        config.write_text(settings.to_json(), encoding="utf-8")
        command.extend(["--settings", str(config)])
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=worker_env,
            capture_output=True,
            timeout=240 if output.suffix.lower() == ".zip" else 55,
            **hidden_process_options(),
        )
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(
            "Processing took too long. Try another emoji or reduce the export settings."
        ) from exc
    if result.returncode:
        detail = result.stdout.decode("utf-8", errors="replace").strip()
        raise ConversionError(detail[:250] or "Could not convert this file.")


async def send_document(message: Message, data, filename: str, caption: str | None = None) -> None:
    async def upload():
        data.seek(0)
        await message.reply_document(
            document=data,
            filename=filename,
            caption=caption,
            disable_content_type_detection=True,
            do_quote=True,
            read_timeout=120,
            write_timeout=180,
            connect_timeout=20,
            pool_timeout=15,
        )

    await request_with_retry("send_document", upload, safe_to_repeat=False)


async def send_gif_archive(
    message: Message,
    source: Path,
    output: Path,
    settings: ExportSettings = DEFAULT_SETTINGS,
) -> None:
    archive_path = output.with_suffix(".zip")
    await asyncio.to_thread(run_conversion, source, archive_path, settings)
    formats = [fmt.upper() for fmt in settings.effective_formats]
    if settings.png != "none":
        formats.append("PNG")
    caption = (
        f"Ready: {', '.join(formats)}.\n"
        f"Sizes: {' / '.join(map(str, settings.sizes))} px. Use /settings to change export options."
    )
    if settings.delivery == "zip":
        with archive_path.open("rb") as document:
            await send_document(message, document, archive_path.name, caption)
    else:
        with ZipFile(archive_path) as archive:
            members = archive.namelist()
            for index, name in enumerate(members):
                if index:
                    await asyncio.sleep(1.1)
                filename = f"{output.stem}_{name.replace('/', '_')}"
                with io.BytesIO(archive.read(name)) as document:
                    await send_document(
                        message, document, filename, caption if index == 0 else None
                    )


def sticker_suffix(sticker: Sticker) -> str:
    return ".tgs" if sticker.is_animated else ".webm" if sticker.is_video else ".webp"


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    if await accept_custom_size(update, context):
        return
    # Keep one snapshot for every emoji in this message, even if settings change mid-export.
    settings = current_settings(update, context)
    items = extract_emojis(message)
    document = message.document
    suffix = Path(document.file_name or "").suffix.lower() if document else ""
    supported_document = document and suffix in {".tgs", ".webm", ".webp", ".png"}
    if not message.sticker and not supported_document and not items:
        await message.reply_text(
            "Send an emoji, sticker, or TGS, WEBM, WEBP, or PNG file. Use /help for instructions."
        )
        return

    slots = context.application.bot_data["slots"]
    if slots.locked():
        await message.reply_text("I am processing other emoji right now. Please try again shortly.")
        return
    async with slots:
        # Typing/upload status is best-effort; its failure must not discard a request.
        with contextlib.suppress(TelegramError):
            await message.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)
        with TemporaryDirectory(prefix="emojigif-") as directory:
            folder = Path(directory)
            if message.sticker or supported_document:
                asset = message.sticker or document
                if message.sticker:
                    suffix = sticker_suffix(message.sticker)
                try:
                    if asset.file_size and asset.file_size > MAX_FILE_BYTES:
                        raise ConversionError("The file exceeds 10 MB.")
                    source = folder / f"source{suffix}"
                    await download_telegram(context, asset.file_id, source)
                    await send_gif_archive(message, source, folder / "emoji.gif", settings)
                except (ConversionError, RequestFailure, TelegramError, httpx.HTTPError) as exc:
                    await report_failure(message, exc)
                return

            if len(items) > MAX_PER_MESSAGE:
                await message.reply_text(
                    "I will export the first 5 distinct emoji. Send the remaining ones separately."
                )
            for index, item in enumerate(items[:MAX_PER_MESSAGE], start=1):
                try:
                    if item.kind == "custom":
                        stickers = await request_with_retry(
                            "get_custom_emoji_stickers",
                            lambda value=item.value: context.bot.get_custom_emoji_stickers([value]),
                        )
                        if not stickers:
                            raise ConversionError("This emoji is unavailable on Telegram.")
                        sticker = stickers[0]
                        source = folder / f"source-{index}{sticker_suffix(sticker)}"
                        await download_telegram(context, sticker.file_id, source)
                    else:
                        source = folder / f"source-{index}.png"
                        client = context.application.bot_data["http"]
                        for name in twemoji_names(item.value):
                            if await download_url(client, f"{TWEMOJI_BASE}/{name}.png", source):
                                break
                        else:
                            raise ConversionError(
                                "An image is not available for this Unicode emoji yet."
                            )
                    await send_gif_archive(message, source, folder / f"emoji-{index}.gif", settings)
                except (ConversionError, RequestFailure, TelegramError, httpx.HTTPError) as exc:
                    await report_failure(message, exc)


async def report_failure(message: Message, error: Exception) -> None:
    # HTTP/Telegram exceptions may contain token-bearing URLs. Never log their text.
    if isinstance(error, RequestFailure):
        LOG.warning(
            "Request failed at %s: %s (%s)",
            error.operation,
            type(error.error).__name__,
            type(error.error.__cause__).__name__
            if error.error.__cause__
            else "no transport detail",
        )
    else:
        LOG.warning("Request failed: %s", type(error).__name__)
    text = (
        str(error)
        if isinstance(error, ConversionError)
        else ("Could not download or send the file. Please try again in a few seconds.")
    )
    if isinstance(error, RequestFailure) and error.delivery_uncertain:
        text = (
            "Telegram did not confirm file delivery. Check the chat before sending the emoji "
            "again; the file may already have arrived. With individual files, the set may be "
            "incomplete. Use ZIP delivery in /settings to keep the set together."
        )
    with contextlib.suppress(TelegramError):
        await message.reply_text(text)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    LOG.error("Update failed: %s", type(context.error).__name__)
    if isinstance(update, Update) and update.effective_message:
        with contextlib.suppress(TelegramError):
            await update.effective_message.reply_text(
                "Could not process this message. Try another emoji."
            )


async def post_init(application: Application) -> None:
    data_dir = Path(os.getenv("DATA_DIR", str(ROOT / "data")))
    application.bot_data["settings_store"] = SettingsStore(data_dir / "settings.sqlite3")
    application.bot_data["http"] = httpx.AsyncClient(
        timeout=httpx.Timeout(60, connect=20, pool=15), follow_redirects=True
    )
    application.bot_data["slots"] = asyncio.Semaphore(2)
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Start"),
            BotCommand("help", "How to send emoji"),
            BotCommand("settings", "Export settings"),
            BotCommand("cancel", "Cancel custom size input"),
        ]
    )
    LOG.info("Bot is running. Open it in Telegram and send an emoji.")


async def post_shutdown(application: Application) -> None:
    if client := application.bot_data.get("http"):
        await client.aclose()


def build_application(token: str) -> Application:
    application = (
        Application.builder()
        .token(token)
        .connect_timeout(20)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(15)
        .get_updates_connect_timeout(20)
        .get_updates_read_timeout(30)
        .get_updates_pool_timeout(15)
        .concurrent_updates(8)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.add_handler(CommandHandler(["start", "help"], start))
    application.add_handler(CommandHandler("settings", show_settings))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(settings_callback, pattern=r"^cfg:"))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle))
    application.add_error_handler(error_handler)
    return application
