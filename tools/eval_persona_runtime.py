"""Compatibility wrapper for the formal persona eval suites."""

from __future__ import annotations

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from tests.evals.run_evals import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["--suite", "all"]))
