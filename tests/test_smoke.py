"""Smoke tests. Expand these as you implement each module.

Run with:  pytest
"""

from akashic_codex import __version__


def test_package_imports():
    assert __version__


# TODO as you build:
#   test_init_db_creates_tables
#   test_save_then_search_roundtrip
#   test_search_returns_summaries_not_full_log
#   test_embedding_dimension_matches_schema
