"""Old name: alias of living_library.reembed."""
import sys

from living_library import reembed as _module

sys.modules[__name__] = _module
