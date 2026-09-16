"""Validated export preferences and persistent per-user storage."""

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path

FORMATS = ("gif", "mp4", "webm", "mov")
SIZES = (64, 128, 256, 512)


@dataclass(frozen=True)
class ExportSettings:
    sizes: tuple[int, ...] = (128, 256, 512)
    formats: tuple[str, ...] = FORMATS
    png: str = "include"
    delivery: str = "zip"
    fps: int = 25
    quality: str = "high"
    background: str = "transparent"
    still_seconds: int = 1

    def __post_init__(self):
        if not self.sizes or len(self.sizes) > 4 or len(set(self.sizes)) != len(self.sizes):
            raise ValueError("Choose between 1 and 4 distinct sizes.")
        if any(type(size) is not int or not 32 <= size <= 512 for size in self.sizes):
            raise ValueError("Each size must be a whole number between 32 and 512 pixels.")
        if any(fmt not in FORMATS for fmt in self.formats) or len(set(self.formats)) != len(
            self.formats
        ):
            raise ValueError("Unknown or duplicate format.")
        if self.png not in {"include", "none", "only"} or (not self.formats and self.png != "only"):
            raise ValueError("Choose at least one format or select PNG only.")
        if self.delivery not in {"zip", "files"}:
            raise ValueError("Unknown delivery method.")
        if type(self.fps) is not int or self.fps not in {10, 20, 25, 50}:
            raise ValueError("Choose 10, 20, 25, or 50 frames per second.")
        if self.quality not in {"small", "balanced", "high"}:
            raise ValueError("Unknown quality setting.")
        if self.background not in {"transparent", "white", "black"}:
            raise ValueError("Unknown background setting.")
        if type(self.still_seconds) is not int or self.still_seconds not in {1, 3, 5}:
            raise ValueError("Still-image videos can be 1, 3, or 5 seconds long.")

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, value: str):
        data = json.loads(value)
        if not isinstance(data, dict):
            raise ValueError("Invalid settings.")
        for field in ("sizes", "formats"):
            if field in data:
                data[field] = tuple(data[field])
        return cls(**data)

    @property
    def effective_formats(self) -> tuple[str, ...]:
        return () if self.png == "only" else self.formats


DEFAULT_SETTINGS = ExportSettings()


class SettingsStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS preferences "
                "(user_id INTEGER PRIMARY KEY, data TEXT NOT NULL)"
            )

    def get(self, user_id: int) -> ExportSettings:
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute(
                "SELECT data FROM preferences WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row:
            try:
                return ExportSettings.from_json(row[0])
            except (ValueError, TypeError):
                pass
        return ExportSettings()

    def save(self, user_id: int, settings: ExportSettings) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "INSERT INTO preferences VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET data=excluded.data",
                (user_id, settings.to_json()),
            )

    def delete(self, user_id: int) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM preferences WHERE user_id = ?", (user_id,))
