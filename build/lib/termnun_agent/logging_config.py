from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def default_log_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    if base:
        root = Path(base)
    else:
        root = Path.home() / ".local" / "state"
    d = root / "termnun"
    d.mkdir(parents=True, exist_ok=True)
    return d / "agent.log"


def setup_logging(*, level: str | None = None, log_file: Path | str | None = None, foreground: bool) -> None:
    """Configure root logging for CLI and daemon modes."""
    lvl_name = (level or os.environ.get("TERMNU_LOG_LEVEL") or "INFO").upper()
    lvl = getattr(logging, lvl_name, logging.INFO)

    handlers: list[logging.Handler] = []

    log_path_raw = log_file or os.environ.get("TERMNU_LOG_FILE")
    log_path = Path(log_path_raw) if log_path_raw else default_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(lvl)
    fh.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z")
    )
    handlers.append(fh)

    if foreground or os.environ.get("TERMNU_LOG_CONSOLE", "").lower() in ("1", "true", "yes"):
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(lvl)
        sh.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        handlers.append(sh)

    logging.basicConfig(level=lvl, handlers=handlers, force=True)
    logging.captureWarnings(True)
