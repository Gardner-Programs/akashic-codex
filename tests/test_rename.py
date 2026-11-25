import importlib
import logging
from pathlib import Path

import pytest


def test_default_database_uses_legacy_directory_when_new_location_is_missing(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.delenv('LIVING_LIBRARY_DB_PATH', raising=False)
    monkeypatch.delenv('AKASHIC_DB_PATH', raising=False)
    legacy_dir = tmp_path / '.akashic'
    legacy_dir.mkdir()

    from living_library.db import get_default_db_path

    with caplog.at_level(logging.WARNING, logger='living_library.db'):
        path = get_default_db_path()

    assert path == legacy_dir / 'akashic.db'
    assert 'legacy database' in caplog.text
    assert str(tmp_path / '.living-library' / 'living-library.db') in caplog.text


def test_explicit_database_path_takes_precedence_over_legacy_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('LIVING_LIBRARY_DB_PATH', str(tmp_path / 'custom.db'))
    (tmp_path / '.akashic').mkdir()

    from living_library.db import get_default_db_path

    assert get_default_db_path() == tmp_path / 'custom.db'


def test_legacy_package_reexports_and_warns():
    import akashic_codex
    import living_library

    with pytest.warns(DeprecationWarning, match="renamed to 'living_library'"):
        legacy = importlib.reload(akashic_codex)

    assert legacy.__version__ == living_library.__version__
    assert legacy.db is living_library.db


def test_mcp_server_uses_living_library_name_and_instructions():
    from living_library.mcp_server import mcp

    assert mcp.name == 'living-library'
    assert 'Living Library' in mcp.instructions


def test_console_scripts_keep_new_and_legacy_commands():
    project_config = Path('pyproject.toml').read_text(encoding='utf-8')

    assert 'living-library = "living_library.cli:main"' in project_config
    assert 'akashic-codex = "akashic_codex.cli:main"' in project_config
