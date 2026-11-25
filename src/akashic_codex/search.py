"""Old name: alias of living_library.search."""
import sys

from living_library import search as _module

sys.modules[__name__] = _module
