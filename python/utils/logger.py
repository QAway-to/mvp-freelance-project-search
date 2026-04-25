import logging
import asyncio
import json
from collections import deque
from datetime import datetime
from typing import Dict, Any
from rich.console import Console
from rich.logging import RichHandler

# Global log queue for real-time streaming - increased size for detailed logging
log_queue = asyncio.Queue(maxsize=5000)

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

            try:
                log_queue.put_nowait(serialized)
            except asyncio.QueueFull:
                removed = 0
                while removed < 50 and not log_queue.empty():
                    try:
                        log_queue.get_nowait()
                        removed += 1
                    except:
                        break
                try:
                    log_queue.put_nowait(serialized)
                except:
                    pass

        except Exception:
            pass

def setup_logging():
    """Setup logging with Rich console and queue handler"""
    # Create console for Rich output
    console = Console()

    # Ensure logs directory exists
    log_dir = "logs"
    import os
    os.makedirs(log_dir, exist_ok=True)
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            RichHandler(console=console, rich_tracebacks=True),
            logging.FileHandler(f"{log_dir}/app.log", encoding="utf-8"),
            QueueHandler()
        ]
    )

    # Create logger
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
