"""Build an allowlisted source ZIP, excluding local credentials and runtime data."""

import hashlib
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent
ROOT_FILES = (
    ".env.example",
    ".gitignore",
    ".gitattributes",
    ".dockerignore",
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "PUBLISHING.md",
    "Dockerfile",
    "compose.yaml",
    "main.py",
    "start.cmd",
    "start.ps1",
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
)
TREES = ("emojigif", "tests", "scripts", ".github")
TEXT_SUFFIXES = {".py", ".yml", ".yaml", ".md", ".txt"}
SECRETS = (
    re.compile(rb"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
)


def source_files(root: Path = ROOT) -> list[Path]:
    files = [root / name for name in ROOT_FILES]
    for tree in TREES:
        files.extend(
            path
            for path in (root / tree).rglob("*")
            if path.is_file() and path.suffix in TEXT_SUFFIXES and "__pycache__" not in path.parts
        )
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Unexpected source path: {path.name}")
        payload = path.read_bytes()
        if path.name == ".env.example":
            token_line = re.search(rb"(?m)^BOT_TOKEN=(.*)$", payload)
            if not token_line or token_line.group(1).strip():
                raise ValueError(".env.example must have an empty BOT_TOKEN.")
        if any(pattern.search(payload) for pattern in SECRETS):
            raise ValueError(f"Possible credential in {path.relative_to(root)}; release stopped.")
    return sorted(set(files))


def main() -> None:
    files = source_files()
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    output = destination / "emoji-export-bot-source.zip"
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.relative_to(ROOT).as_posix())
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {path.relative_to(ROOT).as_posix() for path in files}
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (destination / "SHA256SUMS.txt").write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    print(f"Ready: {output.name} — {len(files)} files, {output.stat().st_size} bytes")


if __name__ == "__main__":
    main()
