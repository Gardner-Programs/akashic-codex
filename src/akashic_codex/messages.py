"""Old name: alias of living_library.messages."""
import sys

from living_library import messages as _module

sys.modules[__name__] = _module
