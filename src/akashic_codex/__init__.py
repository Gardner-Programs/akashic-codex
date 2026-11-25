"""Deprecated compatibility package for Akashic Codex."""

import warnings

warnings.warn(
    "The 'akashic_codex' package has been renamed to 'living_library'. "
    'Please update your imports. The old package will be removed after a release transition.',
    DeprecationWarning,
    stacklevel=2,
)

from living_library import __version__, db  # noqa: E402
from living_library.api import app as api_app  # noqa: E402
from living_library.cli import main as cli_main  # noqa: E402
from living_library.mcp_server import run_mcp  # noqa: E402

__all__ = ['__version__', 'api_app', 'cli_main', 'db', 'run_mcp']
