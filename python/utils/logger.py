import logging
import queue
import json
from collections import deque
from datetime import datetime
from typing import Dict, Any
from rich.console import Console
from rich.logging import RichHandler

# Global log queue for real-time streaming - increased size for detailed logging
log_queue: queue.Queue = queue.Queue(maxsize=5000)

# In-memory buffer for debug endpoint — keeps last 300 messages
log_buffer: deque = deque(maxlen=300)

class QueueHandler(logging.Handler):
    """Custom handler to send logs to queue and buffer"""

    def emit(self, record):
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "level": record.levelname,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName
            }
            serialized = json.dumps(log_entry)

            log_buffer.append(log_entry)

            for _ in range(3):
                try:
                    log_queue.put_nowait(serialized)
                    return
                except queue.Full:
                    try:
                        log_queue.get_nowait()  # drop one oldest
                    except queue.Empty:
                        return

        except Exception:
            pass

def setup_logging():
    """Setup logging. Idempotent — safe to call multiple times."""
    root = logging.getLogger()
    if root.handlers:
        return logging.getLogger("freelance_mvp")

    import os
    os.makedirs("logs", exist_ok=True)

    console = Console()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            RichHandler(console=console, rich_tracebacks=True),
            logging.FileHandler("logs/app.log", encoding="utf-8"),
            QueueHandler()
        ]
    )

    logger = logging.getLogger("freelance_mvp")
    logger.setLevel(logging.INFO)
    return logger

# Global logger instance
logger = setup_logging()

def log_agent_action(agent: str, action: str, details: Dict[str, Any] = None, level: str = "INFO"):
    """Log agent actions with structured data"""
    message = f"🤖 {agent}: {action}"

    if details:
        details_str = " | ".join(f"{k}: {v}" for k, v in details.items())
        message += f" | {details_str}"

    if level.upper() == "DEBUG":
        logger.debug(message)
    elif level.upper() == "WARNING":
        logger.warning(message)
    elif level.upper() == "ERROR":
        logger.error(message)
    else:
        logger.info(message)
