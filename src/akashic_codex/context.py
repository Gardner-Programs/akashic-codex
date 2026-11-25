"""Old name: alias of living_library.context."""
import sys

from living_library import context as _module

sys.modules[__name__] = _module
