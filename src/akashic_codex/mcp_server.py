"""Old name: alias of living_library.mcp_server; `-m akashic_codex.mcp_server` still works."""
import sys

from living_library import mcp_server as _module

if __name__ == "__main__":
    _module.run_mcp()
else:
    sys.modules[__name__] = _module
