# Copyright (c) 2026, Quad4 (quad4.io)
"""Allow running as python -m opip."""

import sys

from opip.cli import main

if __name__ == "__main__":
    sys.exit(main())
