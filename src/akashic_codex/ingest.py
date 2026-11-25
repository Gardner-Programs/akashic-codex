"""Old name: alias of living_library.ingest."""
import sys

from living_library import ingest as _module

sys.modules[__name__] = _module
