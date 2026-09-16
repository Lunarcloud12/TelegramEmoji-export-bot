"""Extract custom emoji and Unicode sequences without losing UTF-16 offsets."""

from dataclasses import dataclass
from typing import Literal

import emoji
from telegram import Message, MessageEntity


@dataclass(frozen=True)
class EmojiItem:
    kind: Literal["custom", "unicode"]
    value: str


def extract_emojis(message: Message) -> list[EmojiItem]:
    text = message.text if message.text is not None else (message.caption or "")
    entities = message.entities if message.text is not None else message.caption_entities
    # Telegram offsets count UTF-16 code units, Python indexes count code points.
    offsets = [0]
    for char in text:
        offsets.append(offsets[-1] + (2 if ord(char) > 0xFFFF else 1))

    located: list[tuple[int, EmojiItem]] = []
    custom_ranges: list[tuple[int, int]] = []
    for entity in entities or ():
        if entity.type == MessageEntity.CUSTOM_EMOJI and entity.custom_emoji_id:
            custom_ranges.append((entity.offset, entity.offset + entity.length))
            located.append((entity.offset, EmojiItem("custom", entity.custom_emoji_id)))

    for match in emoji.emoji_list(text):
        start, end = offsets[match["match_start"]], offsets[match["match_end"]]
        if not any(start < right and end > left for left, right in custom_ranges):
            located.append((start, EmojiItem("unicode", match["emoji"])))

    # Preserve message order; don't send the same file repeatedly within one message.
    return list(dict.fromkeys(item for _, item in sorted(located, key=lambda row: row[0])))


def twemoji_names(value: str) -> list[str]:
    full = "-".join(f"{ord(char):x}" for char in value)
    stripped = "-".join(f"{ord(char):x}" for char in value if ord(char) != 0xFE0F)
    # Twemoji retains variation selectors in ZWJ sequences but strips standalone ones.
    return list(dict.fromkeys([full, stripped] if "\u200d" in value else [stripped, full]))
