"""Inline export settings menu. Every panel belongs to its requesting user."""

from dataclasses import replace

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from emojigif.settings import FORMATS, SIZES, ExportSettings

LABELS = {
    "include": "Include PNG",
    "none": "No PNG",
    "only": "PNG only",
    "zip": "ZIP archive",
    "files": "Individual files",
    "transparent": "Transparent",
    "white": "White",
    "black": "Black",
    "small": "Compact",
    "balanced": "Balanced",
    "high": "High",
}


def current_settings(update, context) -> ExportSettings:
    user = getattr(update, "effective_user", None)
    store = context.application.bot_data.get("settings_store")
    return store.get(user.id) if user and store else ExportSettings()


def summary(settings: ExportSettings) -> str:
    formats = ", ".join(fmt.upper() for fmt in settings.effective_formats) or "—"
    return (
        "⚙️ Export settings\n\n"
        f"Sizes: {', '.join(map(str, settings.sizes))} px on the longest edge\n"
        f"Formats: {formats}\n"
        f"First frame: {LABELS[settings.png]}\n"
        f"Delivery: {LABELS[settings.delivery]}\n"
        f"Frame rate: {settings.fps} fps\n"
        f"Quality: {LABELS[settings.quality]}\n"
        f"Background: {LABELS[settings.background]}\n"
        f"Still-image video: {settings.still_seconds} s\n\n"
        "MOV uses ProRes 4444 with alpha. MP4 uses white for transparent areas.\n"
        "Changes are saved immediately and apply to your next emoji."
    )


def keyboard(user_id: int, settings: ExportSettings, section: str = "main"):
    def button(label, action, value):
        return InlineKeyboardButton(label, callback_data=f"cfg:{user_id}:{action}:{value}")

    rows = []
    if section == "main":
        for pair in [
            [("📏 Sizes", "sizes"), ("🎞 Formats", "formats")],
            [("🖼 First-frame PNG", "png"), ("📦 Delivery", "delivery")],
            [("⏱ Frame rate", "fps"), ("✨ Quality", "quality")],
            [("🎨 Background", "background"), ("⌛ Still-image duration", "still_seconds")],
        ]:
            rows.append([button(label, "page", value) for label, value in pair])
        rows += [[button("Reset", "reset", "all"), button("Done", "done", "all")]]
    else:
        choices = {
            "sizes": [(str(n), n) for n in sorted(set(SIZES) | set(settings.sizes))],
            "formats": [(fmt.upper(), fmt) for fmt in FORMATS],
            "png": [(LABELS[key], key) for key in ("include", "none", "only")],
            "delivery": [(LABELS[key], key) for key in ("zip", "files")],
            "fps": [(str(n), n) for n in (10, 20, 25, 50)],
            "quality": [(LABELS[key], key) for key in ("small", "balanced", "high")],
            "background": [(LABELS[key], key) for key in ("transparent", "white", "black")],
            "still_seconds": [(f"{n} s", n) for n in (1, 3, 5)],
        }
        for label, value in choices[section]:
            current = getattr(settings, section)
            active = value in current if isinstance(current, tuple) else value == current
            rows.append([button(f"{'✓ ' if active else ''}{label}", section, str(value))])
        if section == "sizes":
            rows.append([button("Enter custom sizes…", "custom", "sizes")])
        rows.append([button("← All settings", "page", "main")])
    return InlineKeyboardMarkup(rows)


def panel_text(settings: ExportSettings, section: str) -> str:
    hints = {
        "sizes": "Select multiple sizes or enter custom values. The aspect ratio is preserved.",
        "formats": (
            "Select any combination of formats. "
            "In PNG-only mode, these formats are temporarily skipped."
        ),
        "png": "PNG only exports the first frame at each selected size, without GIF or video.",
        "delivery": (
            "ZIP includes the entire set in one archive. "
            "Individual delivery sends each result as a separate document."
        ),
        "fps": "More frames give smoother motion, but take longer and create larger files.",
        "quality": (
            "Compact produces smaller files. High preserves more detail at a larger file size. "
            "PNG compression is lossless."
        ),
        "background": (
            "MOV, WEBM, and PNG preserve transparency. "
            "GIF has no partial transparency; MP4 uses a white background."
        ),
        "still_seconds": (
            "Video duration for still images. This does not change animated emoji duration."
        ),
    }
    return summary(settings) + ("\n\n" + hints[section] if section in hints else "")


def apply_change(settings: ExportSettings, field: str, value: str) -> ExportSettings:
    if field == "sizes":
        number = int(value)
        sizes = set(settings.sizes)
        sizes.symmetric_difference_update({number})
        return replace(settings, sizes=tuple(sorted(sizes)))
    if field == "formats":
        if value not in FORMATS:
            raise ValueError("Unknown format.")
        formats = set(settings.formats)
        formats.symmetric_difference_update({value})
        return replace(settings, formats=tuple(fmt for fmt in FORMATS if fmt in formats))
    if field in {"fps", "still_seconds"}:
        return replace(settings, **{field: int(value)})
    if field in {"png", "delivery", "quality", "background"}:
        return replace(settings, **{field: value})
    raise ValueError("Unknown setting.")


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message and update.effective_user:
        context.user_data.pop("custom_size", None)
        settings = current_settings(update, context)
        await update.effective_message.reply_text(
            summary(settings),
            reply_markup=keyboard(update.effective_user.id, settings),
        )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not update.effective_user:
        return
    try:
        _, owner, action, value = query.data.split(":", 3)
        if int(owner) != update.effective_user.id:
            await query.answer(
                "These settings belong to another user. Open your own with /settings.",
                show_alert=True,
            )
            return
        settings = current_settings(update, context)
        store = context.application.bot_data["settings_store"]
        section = "main"
        context.user_data.pop("custom_size", None)
        if action == "done":
            await query.answer("Saved")
            await query.edit_message_text(
                "Settings saved. Send an emoji or sticker. Use /settings to change them."
            )
            return
        if action == "custom":
            context.user_data["custom_size"] = True
            await query.answer()
            await query.edit_message_text(
                "Send 1 to 4 sizes separated by spaces, for example: 96 320 512.\n"
                "Allowed range: 32–512 px on the longest edge. Use /cancel to cancel.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "← All settings",
                                callback_data=f"cfg:{owner}:page:main",
                            )
                        ]
                    ]
                ),
            )
            return
        if action == "page":
            section = value
        elif action == "reset":
            settings = ExportSettings()
            store.delete(update.effective_user.id)
        else:
            settings = apply_change(settings, action, value)
            store.save(update.effective_user.id, settings)
            section = action
        markup = keyboard(update.effective_user.id, settings, section)
        await query.answer()
        try:
            await query.edit_message_text(panel_text(settings, section), reply_markup=markup)
        except BadRequest as exc:
            if "Message is not modified" not in str(exc):
                raise
    except ValueError as exc:
        await query.answer(str(exc)[:180], show_alert=True)
    except (KeyError, TypeError):
        await query.answer("Reopen the settings with /settings.", show_alert=True)


async def accept_custom_size(update, context) -> bool:
    if not getattr(context, "user_data", None) or not context.user_data.get("custom_size"):
        return False
    try:
        values = tuple(sorted(set(int(n) for n in (update.effective_message.text or "").split())))
        settings = replace(current_settings(update, context), sizes=values)
    except ValueError:
        await update.effective_message.reply_text(
            "Enter 1 to 4 whole numbers separated by spaces (32–512). Use /cancel to cancel."
        )
        return True
    context.application.bot_data["settings_store"].save(update.effective_user.id, settings)
    await show_settings(update, context)
    return True


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("custom_size", None)
    await update.effective_message.reply_text("Input canceled. Send an emoji or open /settings.")
