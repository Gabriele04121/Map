from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


def setup_logging(level: str = "INFO", log_dir: Path | None = None) -> None:
    root = logging.getLogger("travelos")
    if root.handlers:
        return
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
    if log_dir:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(log_dir / "travelos.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError:  # read-only dir on locked-down machines: console logging is enough
            pass
