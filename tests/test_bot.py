import asyncio
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zipfile import ZipFile

import httpx
import pytest
from PIL import Image
from telegram import Sticker

from emojigif.bot import download_url, handle, send_gif_archive, sticker_suffix
from emojigif.convert import ConversionError
from emojigif.settings import ExportSettings


def test_send_media_bundle_in_zip_document(tmp_path):
    source, output = tmp_path / "source.png", tmp_path / "emoji.gif"
    Image.new("RGBA", (32, 32), "red").save(source)
    sent = []

    async def reply_document(**kwargs):
        sent.append(kwargs)
        with ZipFile(kwargs["document"]) as archive:
            expected = {
                f"{size}/{name}"
                for size in (128, 256, 512)
                for name in ("emoji.gif", "emoji.mp4", "emoji.webm", "emoji.mov", "first-frame.png")
            }
            assert set(archive.namelist()) == expected
            assert archive.testzip() is None
            for size in (128, 256, 512):
                with Image.open(io.BytesIO(archive.read(f"{size}/emoji.gif"))) as gif:
                    assert gif.format == "GIF"
                    assert gif.size == (size, size)
                with Image.open(io.BytesIO(archive.read(f"{size}/first-frame.png"))) as png:
                    assert png.format == "PNG"
                    assert png.size == (size, size)

    asyncio.run(send_gif_archive(SimpleNamespace(reply_document=reply_document), source, output))
    assert sent[0]["filename"] == "emoji.zip"
    assert sent[0]["disable_content_type_detection"] is True


def test_sticker_formats():
    for animated, video, suffix in [
        (True, False, ".tgs"),
        (False, True, ".webm"),
        (False, False, ".webp"),
    ]:
        sticker = Sticker("id", "unique", 100, 100, animated, video, "custom_emoji")
        assert sticker_suffix(sticker) == suffix


def test_bounded_download(tmp_path):
    async def run():
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 11))
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("emojigif.bot.MAX_FILE_BYTES", 10):
                with pytest.raises(ConversionError, match="10 MB"):
                    await download_url(client, "https://example.com/file", tmp_path / "file")

    asyncio.run(run())


def test_custom_download_failure_continues_with_next_emoji(tmp_path):
    message = SimpleNamespace(
        text="🔥🙂",
        caption=None,
        caption_entities=[],
        entities=[SimpleNamespace(type="custom_emoji", offset=0, length=2, custom_emoji_id="42")],
        document=None,
        sticker=None,
        reply_text=AsyncMock(),
        reply_chat_action=AsyncMock(),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(get_custom_emoji_stickers=AsyncMock(return_value=[])),
        application=SimpleNamespace(bot_data={"slots": asyncio.Semaphore(2), "http": None}),
    )

    async def download(client, url, path):
        Image.new("RGBA", (32, 32), "red").save(path)
        return True

    sent = AsyncMock()
    with patch("emojigif.bot.download_url", download), patch("emojigif.bot.send_gif_archive", sent):
        asyncio.run(handle(SimpleNamespace(effective_message=message), context))
    assert message.reply_text.await_count == 1
    assert sent.await_count == 1
    temporary_source: Path = sent.call_args.args[1]
    assert not temporary_source.exists()


def test_delivery_as_individual_png_files(tmp_path):
    source = tmp_path / "input.png"
    Image.new("RGBA", (32, 32), "red").save(source)
    settings = ExportSettings(sizes=(64, 96), png="only", delivery="files")
    sent = []

    async def reply_document(**kwargs):
        sent.append(kwargs["filename"])
        with Image.open(kwargs["document"]) as png:
            assert png.format == "PNG"

    with patch("emojigif.bot.asyncio.sleep", new_callable=AsyncMock):
        asyncio.run(
            send_gif_archive(
                SimpleNamespace(reply_document=reply_document),
                source,
                tmp_path / "emoji-2.gif",
                settings,
            )
        )
    assert sent == ["emoji-2_64_first-frame.png", "emoji-2_96_first-frame.png"]
