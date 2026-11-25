"""Environment settings. LIVING_LIBRARY_<NAME> wins; the pre-rename AKASHIC_<NAME> still works."""
import os


def env(name, default=None):
    """Read LIVING_LIBRARY_<name>, falling back to the old AKASHIC_<name>, then default."""
    return os.environ.get(f"LIVING_LIBRARY_{name}", os.environ.get(f"AKASHIC_{name}", default))
