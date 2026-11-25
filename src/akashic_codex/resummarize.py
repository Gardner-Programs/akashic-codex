"""Old name: alias of living_library.resummarize."""
import sys

from living_library import resummarize as _module

sys.modules[__name__] = _module
