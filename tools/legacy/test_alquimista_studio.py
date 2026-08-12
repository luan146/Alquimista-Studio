"""Legacy test launcher kept for compatibility.

Run ``python test_alquimista_studio.py`` or, preferably, ``pytest``.
"""

import pytest


if __name__ == "__main__":
    raise SystemExit(pytest.main(["-q"]))
