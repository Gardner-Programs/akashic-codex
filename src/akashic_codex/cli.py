# ruff: noqa: E402, F403, F405
"""
Deprecated: use living_library.cli instead.
This module re-exports from living_library.cli with a deprecation warning.
"""

import warnings

warnings.warn(
    "The 'akashic_codex.cli' module has been moved to 'living_library.cli'. "
    'Please update your imports. The old module will be removed in a future release.',
    DeprecationWarning,
    stacklevel=2,
)

from living_library.cli import *

if __name__ == '__main__':
    main()
