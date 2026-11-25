"""Old name: alias of living_library.cli; `python -m akashic_codex.cli` still works."""
import sys

from living_library import cli as _module

if __name__ == "__main__":
    _module.main()
else:
    sys.modules[__name__] = _module
