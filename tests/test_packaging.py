import pytest

from scripts.package_source import ROOT_FILES, source_files


def release_tree(tmp_path):
    for name in ROOT_FILES:
        (tmp_path / name).write_text("BOT_TOKEN=\n" if name == ".env.example" else "example\n")
    return tmp_path


def test_release_excludes_credentials_runtime_data_and_caches(tmp_path):
    root = release_tree(tmp_path)
    (root / ".env").write_text("private token")
    for folder, name in [
        ("data", "settings.sqlite3"),
        (".venv", "python.exe"),
        ("dist", "old.zip"),
        ("tests/__pycache__", "test.py"),
    ]:
        path = root / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private")
    included = {str(path.relative_to(root)).replace("\\", "/") for path in source_files(root)}
    assert included == set(ROOT_FILES)


def test_release_rejects_token_in_source_without_printing_it(tmp_path):
    root = release_tree(tmp_path)
    fake_secret = "123456789" + ":" + "a" * 35
    (root / "main.py").write_text(fake_secret)
    with pytest.raises(ValueError, match="Possible credential") as failure:
        source_files(root)
    assert fake_secret not in str(failure.value)


def test_env_example_cannot_contain_a_token(tmp_path):
    root = release_tree(tmp_path)
    (root / ".env.example").write_text("BOT_TOKEN=not-empty\n")
    with pytest.raises(ValueError, match="empty BOT_TOKEN"):
        source_files(root)
