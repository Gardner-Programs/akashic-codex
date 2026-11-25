"""Old name: alias of living_library.api."""
import sys

from living_library import api as _module

sys.modules[__name__] = _module
