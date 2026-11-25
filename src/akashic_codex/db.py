"""Old name: alias of living_library.db."""
import sys

from living_library import db as _module

sys.modules[__name__] = _module
