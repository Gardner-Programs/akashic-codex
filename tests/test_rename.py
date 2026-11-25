"""The project was renamed from akashic-codex; old names must keep working."""
import subprocess
import sys

from living_library import settings


def test_new_env_name_wins_over_legacy(monkeypatch):
    monkeypatch.setenv("AKASHIC_TITLER", "old")
    assert settings.env("TITLER", "d") == "old"
    monkeypatch.setenv("LIVING_LIBRARY_TITLER", "new")
    assert settings.env("TITLER", "d") == "new"
    monkeypatch.delenv("AKASHIC_TITLER")
    monkeypatch.delenv("LIVING_LIBRARY_TITLER")
    assert settings.env("TITLER", "d") == "d"


def test_legacy_imports_are_the_same_modules():
    import akashic_codex
    import living_library
    from akashic_codex import db as old_db
    from akashic_codex.ingest import save_session as old_save
    from living_library import db
    from living_library.ingest import save_session

    assert akashic_codex.__version__ == living_library.__version__
    assert old_db is db and old_save is save_session


def test_legacy_cli_module_still_runs():
    p = subprocess.run([sys.executable, "-m", "akashic_codex.cli", "--help"],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0 and "serve_mcp" in p.stdout
