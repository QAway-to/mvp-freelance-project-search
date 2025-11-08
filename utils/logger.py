import logging
import asyncio
import json
from datetime import datetime
from typing import Dict, Any
from rich.console import Console
from rich.logging import RichHandler

# Global log queue for real-time streaming
log_queue = asyncio.Queue(maxsize=1000)

class QueueHandler(logging.Handler):
    """Custom handler to send logs to queue"""

    def emit(self, record):
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "level": record.levelname,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName
            }

            # Simple, non-blocking queue insertion
            # If queue is full, remove oldest messages
            try:
                log_queue.put_nowait(json.dumps(log_entry))
            except asyncio.QueueFull:
                # Remove old messages to make room (keep queue size manageable)
                removed = 0
                while removed < 50 and not log_queue.empty():
                    try:
                        log_queue.get_nowait()
                        removed += 1
                    except:
                        break
                # Try to add new message
                try:
                    log_queue.put_nowait(json.dumps(log_entry))
                except:
                    pass  # If still full, skip this message

        except Exception:
            pass  # Don't let logging errors crash the app

def setup_logging():
    """Setup logging with Rich console and queue handler"""
    # Create console for Rich output
    console = Console()

    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[
            RichHandler(console=console, rich_tracebacks=True),
            QueueHandler()
        ]
    )

    # Create logger
    logger = logging.getLogger("freelance_mvp")
    logger.setLevel(logging.INFO)

    return logger

# Global logger instance
logger = setup_logging()

def log_agent_action(agent: str, action: str, details: Dict[str, Any] = None):
    """Log agent actions with structured data"""
    message = f"🤖 {agent}: {action}"

    if details:
        details_str = " | ".join(f"{k}: {v}" for k, v in details.items())
        message += f" | {details_str}"

    logger.info(message)
