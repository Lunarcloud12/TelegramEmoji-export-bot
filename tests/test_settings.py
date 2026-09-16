import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from emojigif.settings import ExportSettings, SettingsStore
from emojigif.settings_ui import (
    accept_custom_size,
    apply_change,
    keyboard,
    settings_callback,
    summary,
)


@pytest.mark.parametrize(
    "overrides",
    [
        {"sizes": ()},
        {"sizes": (0,)},
        {"sizes": (1024,)},
        {"sizes": (128, 128)},
        {"sizes": (True,)},
        {"sizes": (32, 64, 128, 256, 512)},
        {"formats": ()},
        {"formats": ("exe",)},
        {"formats": ("gif", "gif")},
        {"fps": 60},
        {"png": "bad"},
        {"delivery": "bad"},
        {"quality": "bad"},
        {"background": "bad"},
        {"still_seconds": 10},
    ],
)
def test_reject_invalid_settings(overrides):
    with pytest.raises(ValueError):
        ExportSettings(**overrides)


def test_settings_persist_and_users_are_isolated(tmp_path):
    path = tmp_path / "settings.sqlite3"
    store = SettingsStore(path)
    settings = ExportSettings(sizes=(96,), formats=(), png="only", delivery="files")
    store.save(101, settings)
    reopened = SettingsStore(path)
    assert reopened.get(101) == settings
    assert reopened.get(102) == ExportSettings()
    reopened.delete(101)
    assert reopened.get(101) == ExportSettings()


def test_toggle_and_png_only_transitions():
    settings = ExportSettings(sizes=(128,), formats=("gif",))
    with pytest.raises(ValueError):
        apply_change(settings, "sizes", "128")
    with pytest.raises(ValueError):
        apply_change(settings, "formats", "gif")
    only = apply_change(settings, "png", "only")
    assert only.effective_formats == ()
    assert apply_change(only, "png", "include").effective_formats == ("gif",)
    assert apply_change(settings, "sizes", "320").sizes == (128, 320)


def test_menus_are_telegram_sized_and_owner_scoped():
    settings = ExportSettings(sizes=(96, 128, 320, 512))
    assert len(summary(settings)) < 4096
    for section in (
        "main",
        "sizes",
        "formats",
        "png",
        "delivery",
        "fps",
        "quality",
        "background",
        "still_seconds",
    ):
        for row in keyboard(1234567890123, settings, section).inline_keyboard:
            for button in row:
                assert len(button.callback_data.encode()) <= 64
                assert button.callback_data.startswith("cfg:1234567890123:")


def context_and_update(tmp_path, data, user_id=10):
    store = SettingsStore(tmp_path / "preferences.sqlite3")
    query = SimpleNamespace(data=data, answer=AsyncMock(), edit_message_text=AsyncMock())
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id))
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"settings_store": store}), user_data={}
    )
    return context, update, store


def test_other_user_cannot_change_menu(tmp_path):
    context, update, store = context_and_update(tmp_path, "cfg:99:png:only")
    asyncio.run(settings_callback(update, context))
    assert update.callback_query.answer.call_args.kwargs["show_alert"] is True
    assert not update.callback_query.edit_message_text.called
    assert store.get(99) == ExportSettings()


def test_menu_changes_save_and_acknowledge_callback(tmp_path):
    context, update, store = context_and_update(tmp_path, "cfg:10:png:only")
    asyncio.run(settings_callback(update, context))
    assert store.get(10).png == "only"
    update.callback_query.answer.assert_awaited_once()
    assert "PNG only" in update.callback_query.edit_message_text.call_args.args[0]


def test_custom_size_flow(tmp_path):
    context, update, store = context_and_update(tmp_path, "cfg:10:custom:sizes")
    asyncio.run(settings_callback(update, context))
    assert context.user_data["custom_size"]
    update.effective_message = SimpleNamespace(text="96 320", reply_text=AsyncMock())
    assert asyncio.run(accept_custom_size(update, context))
    assert store.get(10).sizes == (96, 320)
    assert "custom_size" not in context.user_data


def test_corrupted_stored_preferences_fall_back(tmp_path):
    import sqlite3

    store = SettingsStore(tmp_path / "preferences.sqlite3")
    with sqlite3.connect(store.path) as db:
        db.execute("INSERT INTO preferences VALUES (?, ?)", (12, '{"sizes": []}'))
    assert store.get(12) == ExportSettings()


def test_round_trip_all_preferences():
    settings = replace(
        ExportSettings(),
        sizes=(32, 96),
        formats=("mov",),
        png="none",
        delivery="files",
        fps=50,
        quality="small",
        background="black",
        still_seconds=5,
    )
    assert ExportSettings.from_json(settings.to_json()) == settings
