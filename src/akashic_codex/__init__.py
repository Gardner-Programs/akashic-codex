"""Old name of living_library, kept so existing hooks, MCP configs and imports keep working.

`import akashic_codex.X` returns the living_library.X module itself; `python -m akashic_codex.cli`
runs the living_library CLI. New code should import living_library.
"""
from living_library import *  # noqa: F401,F403
from living_library import __version__  # noqa: F401
