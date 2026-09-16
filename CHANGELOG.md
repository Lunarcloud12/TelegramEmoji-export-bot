# Changelog

## Unreleased

- Removed README.txt from Telegram export archives; archives now contain only selected media files grouped by size.

## 0.2.2 — 2026-09-15

- Increased Telegram API, download, and upload timeouts for slower connections.
- Added up to three attempts for transient metadata and download failures, with backoff.
- Retry uploads only after connection failures before sending or short Telegram rate limits; explain unconfirmed delivery without automatically duplicating files.
- Include the failing operation and transport error type in logs without exposing URLs or tokens.
- Added offline tests for interrupted downloads, retry limits, rate limits, and uncertain delivery.

## 0.2.1 — 2026-09-15

- Switched bot messages, settings, validation errors, launcher prompts, and documentation to English.
- Removed the informational bot command; retained artwork attribution in documentation and generated archives.
- Updated GitHub issue and pull request templates for an English-speaking audience.

## 0.2.0 — 2026-09-15

- Added `/settings` for sizes, formats, PNG mode, delivery, frame rate, quality, background, and still-image video duration.
- Persisted per-user settings in SQLite across restarts.
- Added custom sizes from 32 to 512 px, with up to four sizes per export.
- Added PNG modes: include, omit, or export only the first frame.
- Added ZIP or individual document delivery.
- Switched MOV output to ProRes 4444 with an alpha channel.
- Fixed TGS duration so the final boundary no longer adds extra frames.
- Added tests for settings, button ownership, codecs, transparency, and file delivery.
- Added persistent Docker storage, Windows/Linux CI, and a source archive builder.

## 0.1.0

- Converted standard/custom emoji and TGS, WEBM, WEBP, and PNG stickers or files.
- Exported GIF, MP4, WEBM, MOV, and PNG sets in ZIP archives at 128/256/512 px.
