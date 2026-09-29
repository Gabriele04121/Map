#!/usr/bin/env python3
"""Start TravelOS:  python run.py   (Python 3.9+, no dependencies)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from travelos.server.app import main  # noqa: E402

if __name__ == "__main__":
    main()
