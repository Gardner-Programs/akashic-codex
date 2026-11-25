"""Old name: alias of living_library.summarizers."""
import sys

from living_library import summarizers as _module

sys.modules[__name__] = _module
