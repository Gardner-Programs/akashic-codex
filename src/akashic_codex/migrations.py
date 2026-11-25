"""Deprecated alias for :mod:`living_library.migrations`."""

import warnings

warnings.warn(
    "The 'akashic_codex.migrations' module has moved to 'living_library.migrations'.",
    DeprecationWarning,
    stacklevel=2,
)

from living_library.migrations import *  # noqa: E402, F403
