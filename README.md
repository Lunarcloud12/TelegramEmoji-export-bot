# Emoji Export Bot

A Telegram bot that exports emoji and stickers to **GIF, MP4, transparent WEBM/MOV, and PNG**. Choose sizes, formats, quality, and delivery options using `/settings`. Preferences are saved separately for each user.

## Quick start

You need **Python 3.12, 64-bit** and a bot token from [@BotFather](https://t.me/BotFather). Send `/newbot` to create a bot and get its token.

### Windows

1. Download and extract the source code.
2. Double-click `start.cmd`. Dependencies are installed automatically on the first run.
3. Paste your token when prompted and press Enter. Input is hidden; the token is saved in your local `.env` file.
4. Open your bot in Telegram, press **Start**, then **Export settings**, or send an emoji immediately.

Keep the launcher window open while the bot runs. Press Ctrl+C to stop. Restart the bot after updating the source code. Run only one instance per token.

Check the installation without connecting to Telegram:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File start.ps1 -Check
```

Normal startup automatically updates dependencies when `requirements.txt` changes.

### Linux / macOS

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Set BOT_TOKEN in .env.
.venv/bin/python main.py
```

FFmpeg and rlottie are included in platform-specific Python packages. A standard 64-bit system is recommended. Platforms without compatible binary packages may require additional dependency setup.

## Export settings

Open `/settings`. Changes are saved immediately and apply to your **next message**. An export already in progress keeps the settings it started with. In group chats, each user can change only their own settings panel.

| Setting | Options |
| --- | --- |
| Sizes | Presets: 64, 128, 256, 512 px. Custom values: 32–512 px. Select 1–4 sizes |
| Formats | Any combination of GIF, MP4, WEBM, and MOV |
| First frame | Include PNG / no PNG / **PNG only** |
| Delivery | ZIP archive or individual documents |
| Frame rate | 10, 20, 25, or 50 fps |
| Quality | Compact / balanced / high |
| Background | Transparent / white / black |
| Still-image video duration | 1, 3, or 5 seconds |

Size refers to the **longest edge**. Aspect ratios are preserved without cropping. Video output pads an odd shorter edge by one pixel. Small raster images are upscaled without adding new detail.

**PNG only** exports the first frame at each selected size without encoding GIF or video. Your format selections are retained so you can switch back later. **Reset** deletes your saved preferences and restores the defaults.

Defaults: 128/256/512 px, all four formats, PNG included, ZIP delivery, 25 fps, high quality, transparent background, and one-second still-image videos.

## Formats and transparency

| Format | Codec and behavior |
| --- | --- |
| GIF | Looping animation with up to 256 colors. Supports transparency, but not partial transparency |
| MP4 | H.264. Transparent areas become white; select a black background if preferred |
| WEBM | VP9 with alpha. High quality uses lossless encoding; transparency support depends on the player |
| MOV | **ProRes 4444 with a 16-bit alpha channel**, encoded directly from source frames. Suitable for video editing; typically larger than MP4 |
| PNG | The first frame before GIF compression, preserving transparency and partial transparency |

White or black backgrounds apply to every selected format. Higher quality produces larger files. Compact quality reduces the GIF palette and increases video compression. PNG remains lossless after resizing.

Example archive using the default settings:

```text
emoji-1.zip
├── 128/
│   ├── emoji.gif
│   ├── emoji.mp4
│   ├── emoji.webm
│   ├── emoji.mov
│   └── first-frame.png
├── 256/  (the same set of files)
└── 512/  (the same set of files)
```

Each emoji gets its own export set. Archives contain only the selected media files, grouped by size. Individual document names include the emoji number and size, such as `emoji-1_128_first-frame.png`. ZIP delivery keeps the entire set together. Telegram controls how individually sent GIF and video files are displayed.

## Supported inputs

- Custom and premium emoji, including emoji in message captions.
- Animated TGS stickers, WEBM video stickers using VP9, and static WEBP stickers.
- TGS, WEBM, WEBP, or PNG files.
- Standard Unicode emoji, including compound sequences, flags, and skin-tone variations.

Standard Unicode emoji arrive through the Bot API as text. They use static Twemoji artwork: Telegram's built-in client animation is not included in that text. Send a custom emoji or sticker to export a specific animation.

Send up to 5 distinct emoji per message, in their original order. Repeated emoji are exported once. An attached supported file or sticker takes priority over emoji in its caption.

Commands: `/start`, `/help`, `/settings`, and `/cancel` to cancel custom size input.

## Limits and storage

Input files are limited to 10 MB. Each output file and the ZIP archive are limited to 45 MB. Animated TGS/WEBP inputs longer than 10 seconds are rejected; WEBM is trimmed to the first 10 seconds. PNG-only exports decode only the first frame of raster and video inputs. Two requests can be processed concurrently, with a four-minute limit per export.

If a set is too large, the bot asks you to reduce sizes, frame rate, or the number of formats. Incomplete ZIP archives are not sent.

Preferences are stored in `data/settings.sqlite3` as a Telegram user ID and export settings. Set `DATA_DIR` to use a different directory. Messages and media are not stored in the database. Temporary media files are removed after processing. See [SECURITY.md](SECURITY.md) for details.

## Connection troubleshooting

`TimedOut` means a network request exceeded its waiting limit. Logs include the operation (`get_file`, `get_custom_emoji_stickers`, `download`, or `send_document`) and the underlying transport error type when available. Exception messages and file URLs are omitted to protect the bot token.

Temporary metadata and download failures are retried up to three attempts, with 1- and 2-second pauses. Interrupted downloads restart from the beginning. Telegram rate limits of up to 60 seconds are respected. API responses allow 30 seconds; downloads allow 60 seconds between chunks. File uploads allow 180 seconds between write operations and 120 seconds for the response.

Uploads are retried only when a connection could not be established, no connection was available, or Telegram explicitly requested a short wait. If a connection drops during upload or while waiting for confirmation, the file may already have arrived. The bot asks you to check the chat before sending the emoji again. Individual file delivery may leave an incomplete set; ZIP keeps the set together.

Persistent failures require checking the host's internet connection and HTTPS access to Telegram and the Twemoji CDN. Restart the bot after installing an update.

## Docker

Create `.env` with your bot token, then run:

```sh
docker compose up -d --build
docker compose logs -f
docker compose down
```

Preferences persist in the `bot-data` volume across container updates. `docker compose down -v` deletes this volume and its saved preferences. The bot uses long polling: no inbound ports or domain are needed. Outbound HTTPS access to Telegram and the Twemoji CDN is required.

## Testing and development

```sh
python -m pip install -r requirements-dev.txt
python -m emojigif.check
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python scripts/package_source.py
```

Use Python from your virtual environment. Tests run without a bot token. Generated videos are decoded to check dimensions, motion, duration, backgrounds, and MOV/WEBM alpha. Separate tests cover menus, user isolation, persistent preferences, and delivered files. Set `RUN_NETWORK_TESTS=1` to enable the optional Twemoji CDN tests.

GitHub Actions is configured for Python 3.12 on Windows/Linux and a Docker build. Local Windows checks do not replace the first CI run or a live conversation test with your bot.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development, [CHANGELOG.md](CHANGELOG.md) for release history, and [PUBLISHING.md](PUBLISHING.md) for GitHub publication instructions.

## License and attribution

The project code is licensed under [MIT](LICENSE). Standard emoji artwork comes from [Twemoji](https://github.com/jdecked/twemoji), copyright Twitter and contributors, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Artwork is resized and converted to other formats. Attribution is included in this documentation. Dependencies and binary codecs have their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
