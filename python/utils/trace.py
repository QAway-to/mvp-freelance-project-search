"""Crash-survivable trace log.

The in-memory /debug buffer is wiped when the process is OOM-killed and
restarted, so we never see what happened right before a crash. This appends
trace lines to a file on the (ephemeral but restart-surviving) container disk,
readable via /debug/offer-trace after the crash.
"""
import time

from utils.logger import log_agent_action

_TRACE_FILE = "/tmp/offer_trace.log"


def trace(msg: str) -> None:
    log_agent_action("Trace", msg)
    try:
        with open(_TRACE_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def reset_trace(header: str = "") -> None:
    try:
        with open(_TRACE_FILE, "w", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} === {header} ===\n")
    except Exception:
        pass


def read_trace(tail: int = 80) -> list:
    try:
        with open(_TRACE_FILE, encoding="utf-8") as f:
            return f.read().splitlines()[-tail:]
    except Exception:
        return []
