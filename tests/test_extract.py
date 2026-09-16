from datetime import UTC, datetime

import pytest
from telegram import Chat, Message, MessageEntity

from emojigif.extract import EmojiItem, extract_emojis, twemoji_names


def message(**kwargs):
    return Message(message_id=1, date=datetime.now(UTC), chat=Chat(1, "private"), **kwargs)


def test_custom_offsets_and_order():
    result = extract_emojis(
        message(
            text="😀 hello 🔥 ❤️ 😀",
            entities=[MessageEntity("custom_emoji", offset=9, length=2, custom_emoji_id="123")],
        )
    )
    assert result == [
        EmojiItem("unicode", "😀"),
        EmojiItem("custom", "123"),
        EmojiItem("unicode", "❤️"),
    ]


@pytest.mark.parametrize("value", ["👨‍👩‍👧‍👦", "👍🏽", "🇷🇴", "1️⃣", "🏳️‍🌈"])
def test_compound_emoji(value):
    assert extract_emojis(message(text=value)) == [EmojiItem("unicode", value)]


def test_caption_custom_emoji_is_not_duplicated():
    assert extract_emojis(
        message(
            caption="🔥🔥",
            caption_entities=[
                MessageEntity("custom_emoji", 0, 2, custom_emoji_id="42"),
                MessageEntity("custom_emoji", 2, 2, custom_emoji_id="42"),
            ],
        )
    ) == [EmojiItem("custom", "42")]


def test_plain_text():
    assert extract_emojis(message(text="Hello, 123")) == []


def test_twemoji_variation_selectors():
    assert twemoji_names("❤️")[0] == "2764"
    assert twemoji_names("1️⃣")[0] == "31-20e3"
    assert twemoji_names("🏳️‍🌈")[0] == "1f3f3-fe0f-200d-1f308"
