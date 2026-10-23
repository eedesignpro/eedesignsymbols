"""Allows ``python -m eedesignsymbols.preview_tools``."""

from __future__ import annotations

import sys

from eedesignsymbols.preview_tools.cli import main

if __name__ == "__main__":
    sys.exit(main())
