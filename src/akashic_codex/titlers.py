"""Old name: alias of living_library.titlers."""
import sys

from living_library import titlers as _module

sys.modules[__name__] = _module
