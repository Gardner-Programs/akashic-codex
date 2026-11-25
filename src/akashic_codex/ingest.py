# ruff: noqa: E402, F403, F405
"""
Deprecated: use living_library.ingest instead.
This module re-exports from living_library.ingest with a deprecation warning.
"""

import warnings

warnings.warn(
    "The 'akashic_codex.ingest' module has been moved to 'living_library.ingest'. "
    'Please update your imports. The old module will be removed in a future release.',
    DeprecationWarning,
    stacklevel=2,
)

from living_library.ingest import *
