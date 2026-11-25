"""Old name: alias of living_library.adapters."""
import sys

from living_library import adapters as _module

sys.modules[__name__] = _module
