"""Optional smoke test against the real Twemoji CDN, without a bot token."""

import asyncio
import os

import httpx
import pytest
from PIL import Image

from emojigif.bot import TWEMOJI_BASE, download_url, run_conversion
from emojigif.extract import twemoji_names


@pytest.mark.skipif(os.getenv("RUN_NETWORK_TESTS") != "1", reason="Opt-in CDN test")
@pytest.mark.parametrize("value", ["😀", "❤️", "🏳️‍🌈"])
def test_real_twemoji_download(value, tmp_path):
    async def run():
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            source, output = tmp_path / "source.png", tmp_path / "emoji.gif"
            name = twemoji_names(value)[0]
            assert await download_url(client, f"{TWEMOJI_BASE}/{name}.png", source)
            run_conversion(source, output)
            with Image.open(output) as result:
                assert result.format == "GIF"
                assert result.size == (72, 72)

    asyncio.run(run())
