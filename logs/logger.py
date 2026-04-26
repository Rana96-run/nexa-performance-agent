"""
Nexa — centralised rotating logger.

Usage (in any script):
    from logs.logger import get_logger
    log = get_logger("main")
    log.info("Daily cadence started")
    log.warning("CPL threshold breached")
    log.error("Slack post failed: ...")

Writes to:
    D:/Nexa Performance Agent/logs/nexa_YYYY-MM-DD.log

Keeps 30 days of logs. Also prints to console so the CONTROL_PANEL
terminal window still shows live output.
"""
import logging
import os
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).parent        # logs/ folder
LOG_DIR.mkdir(exist_ok=True)

_loggers: dict[str, logging.Logger] = {}


def get_logger(name: str = "nexa") -> logging.Logger:
    """Return a named logger, creating it once and caching it."""
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # ASCII-only separator to stay safe on Windows cp1252 consoles.
    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── File handler: daily rotation, keep 30 days ────────────────────────
    today   = datetime.now().strftime("%Y-%m-%d")
    logfile = LOG_DIR / f"nexa_{today}.log"
    fh = TimedRotatingFileHandler(
        filename=logfile,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # ── Console handler ───────────────────────────────────────────────────
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    _loggers[name] = logger
    return logger


# Convenience: top-level logger named "nexa"
log = get_logger("nexa")


# ---------------------------------------------------------------------------
# Global stdout/stderr capture — run once at each entry point.
# ---------------------------------------------------------------------------

class _Tee:
    """Write-proxy that fans out to multiple streams. Keeps print() working
    on the console while also appending to the rotating log file."""
    def __init__(self, *streams):
        self.streams = [s for s in streams if s is not None]

    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
            except Exception:
                pass  # never let logging corruption crash the app

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass

    def isatty(self):
        # Preserve tty-awareness for libraries (e.g. tqdm) that check this.
        base = self.streams[0] if self.streams else None
        return getattr(base, "isatty", lambda: False)()


_setup_done = False


def setup_global_logging(name: str = "nexa") -> logging.Logger:
    """
    Call once at the top of any entry point (main.py, scheduler, listener, etc.)
    Redirects stdout/stderr through a tee so every `print()` anywhere in the
    codebase is also written to logs/nexa_YYYY-MM-DD.log — no need to refactor
    every collector.

    Idempotent: safe to call multiple times.
    """
    global _setup_done
    if _setup_done:
        return get_logger(name)

    # Force UTF-8 on the Windows console so unicode (arrows, em-dashes, Arabic)
    # in print() calls and log messages doesn't crash cp1252 encoders.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # older Python or non-standard streams — harmless

    logger = get_logger(name)
    today  = datetime.now().strftime("%Y-%m-%d")
    logfile = LOG_DIR / f"nexa_{today}.log"
    # Opened in append mode; the TimedRotatingFileHandler above owns rotation
    # for logger calls, and this raw file captures the print() stream.
    raw_log = open(logfile, "a", encoding="utf-8", buffering=1)

    sys.stdout = _Tee(sys.__stdout__, raw_log)
    sys.stderr = _Tee(sys.__stderr__, raw_log)

    # Route uncaught exceptions through the logger too.
    def _excepthook(exc_type, exc, tb):
        logger.error("UNCAUGHT EXCEPTION", exc_info=(exc_type, exc, tb))
    sys.excepthook = _excepthook

    _setup_done = True
    logger.info("Global logging initialised -> %s", logfile)
    return logger
