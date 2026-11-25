"""Old name: alias of living_library.migrations."""
import sys

from living_library import migrations as _module

sys.modules[__name__] = _module
