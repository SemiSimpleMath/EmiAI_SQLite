import sys
import os
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
from colorama import Fore, Style


import logging
import queue
import threading
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
import platform

log_queue = queue.Queue()
log_listener = None
log_lock = threading.Lock()

# ========================
# 1. Define Custom Levels
# ========================
MODEL_SYSTEM_LEVEL = 25
MODEL_USER_LEVEL = 26
MODEL_OUTPUT_LEVEL = 27

logging.addLevelName(MODEL_SYSTEM_LEVEL, "MODEL_SYSTEM")
logging.addLevelName(MODEL_USER_LEVEL, "MODEL_USER")
logging.addLevelName(MODEL_OUTPUT_LEVEL, "MODEL_OUTPUT")

class SafeFormatter(logging.Formatter):
    def format(self, record):
        # If the record does not have 'parent_name', set it to a default value.
        if 'parent_name' not in record.__dict__:
            record.__dict__['parent_name'] = "N/A"
        return super().format(record)

def model_system(self, message, *args, **kwargs):
    if self.isEnabledFor(MODEL_SYSTEM_LEVEL):
        self._log(MODEL_SYSTEM_LEVEL, message, args, **kwargs)

def model_user(self, message, *args, **kwargs):
    if self.isEnabledFor(MODEL_USER_LEVEL):
        self._log(MODEL_USER_LEVEL, message, args, **kwargs)

def model_output(self, message, *args, **kwargs):
    if self.isEnabledFor(MODEL_OUTPUT_LEVEL):
        self._log(MODEL_OUTPUT_LEVEL, message, args, **kwargs)

logging.Logger.model_system = model_system
logging.Logger.model_user = model_user
logging.Logger.model_output = model_output

# ========================
# 2. Configure Logger
# ========================
GLOBAL_LOG_LEVEL = logging.DEBUG  # Debug level to see all error messages

# Use SafeFormatter to include %(parent_name)s in our format string.
LOG_FORMATTER = SafeFormatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(parent_name)s - %(message)s'
)

class UnicodeStreamHandler(logging.StreamHandler):
    """Custom StreamHandler that explicitly handles Unicode characters"""
    def __init__(self, stream=None):
        super().__init__(stream)
        self.encoding = 'utf-8'

    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            # Write the message in utf-8 encoding
            if hasattr(stream, 'buffer'):
                # For sys.stdout/stderr
                stream.buffer.write((msg + self.terminator).encode(self.encoding))
                stream.buffer.flush()
            else:
                # Fallback
                stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

def ensure_logs_directory():
    """Ensure the logs directory exists"""
    logs_dir = os.path.join(os.getcwd(), 'logs')
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    return logs_dir

def setup_logger(name, level=None, log_file="project.log"):
    global log_listener

    # Ensure logs directory exists and update log file path
    logs_dir = ensure_logs_directory()
    if not os.path.isabs(log_file):
        # Add process-specific suffix to avoid file locking conflicts when multiple processes run
        # e.g., emi_logs.log -> emi_logs_12345.log (where 12345 is the process ID)
        base_name, ext = os.path.splitext(log_file)
        process_id = os.getpid()
        log_file = os.path.join(logs_dir, f"{base_name}_{process_id}{ext}")

    logger = logging.getLogger(name)
    logger.setLevel(level if level is not None else GLOBAL_LOG_LEVEL)
    logger.propagate = False

    if not logger.handlers:
        queue_handler = QueueHandler(log_queue)
        logger.addHandler(queue_handler)

    with log_lock:
        if log_listener is None:
            # Use larger file size on Windows to avoid rotation issues
            if platform.system() == 'Windows':
                file_handler = RotatingFileHandler(log_file, maxBytes=10485760, backupCount=2, encoding='utf-8', delay=True)
            else:
                file_handler = RotatingFileHandler(log_file, maxBytes=1048576, backupCount=3, encoding='utf-8', delay=True)
            file_handler.setFormatter(LOG_FORMATTER)

            console_handler = UnicodeStreamHandler(sys.stdout)
            console_handler.setFormatter(LOG_FORMATTER)

            log_listener = QueueListener(log_queue, file_handler, console_handler)
            log_listener.start()
        elif not log_listener._thread.is_alive():
            log_listener.start()

    return logger


def get_logger(name: str, level=None, log_file="emi_logs.log"):
    """
    Returns a module-specific logger that adheres to the global configuration.
    All log files will be written to the /logs subfolder.
    """
    return setup_logger(name, level, log_file)


def get_maintenance_logger(name: str, level=None):
    """
    Returns a logger specifically for maintenance tasks.
    Logs only to maintenance.log file (not to console) for cleaner terminal output.
    All maintenance logs will be written to the /logs subfolder.
    """
    logger = logging.getLogger(f"maintenance.{name}")
    logger.setLevel(level if level is not None else GLOBAL_LOG_LEVEL)
    logger.propagate = False
    
    # Only add handler if not already present
    if not logger.handlers:
        logs_dir = ensure_logs_directory()
        process_id = os.getpid()
        log_file = os.path.join(logs_dir, f"maintenance_{process_id}.log")
        
        # Create file handler - on Windows, use larger file size to avoid frequent rotation issues
        # Windows has aggressive file locking that prevents rotation when multiple threads are writing
        if platform.system() == 'Windows':
            # Use 10MB on Windows to reduce rotation frequency (file locking issues)
            file_handler = RotatingFileHandler(
                log_file, 
                maxBytes=10485760,  # 10MB (10x larger to avoid frequent rotation)
                backupCount=2,      # Keep fewer backups
                encoding='utf-8',
                delay=True
            )
        else:
            # Use 1MB on Unix-like systems (no file locking issues)
            file_handler = RotatingFileHandler(
                log_file, 
                maxBytes=1048576,  # 1MB
                backupCount=3, 
                encoding='utf-8',
                delay=True
            )
        file_handler.setFormatter(LOG_FORMATTER)
        logger.addHandler(file_handler)
    
    return logger

# ========================
# 3. Logging Configuration
# ========================
LOGGING_CONFIG = {
    "log_model_system": True,
    "log_model_user": True,
    "log_model_output": True,
    # Optionally, add other event types if needed.
}

# ========================
# 4. Custom Filters
# ========================
class CustomLevelFilter(logging.Filter):
    """
    Filters log records based on the custom logging configuration.
    """
    def __init__(self, config):
        super().__init__()
        self.config = config

    def filter(self, record):
        if record.levelno not in [MODEL_SYSTEM_LEVEL, MODEL_USER_LEVEL, MODEL_OUTPUT_LEVEL]:
            return True  # Allow normal logs
        key = f"log_{record.levelname.lower()}"
        return self.config.get(key, False)

class DefaultParentNameFilter(logging.Filter):
    """
    Ensures that every log record has a 'parent_name' attribute.
    """
    def filter(self, record):
        if not hasattr(record, 'parent_name'):
            record.parent_name = "N/A"
        return True

# ========================
# 5. Logger Adapter
# ========================
class ContextLoggerAdapter(logging.LoggerAdapter):
    """
    Extends LoggerAdapter to include additional context like parent_name and expose custom logging methods.
    """
    def __init__(self, logger, extra=None):
        if extra is None or not isinstance(extra, dict):
            extra = {}
        extra.setdefault('parent_name', 'N/A')
        super().__init__(logger, extra)

    def process(self, msg, kwargs):
        extra = kwargs.get('extra', {})
        if not isinstance(extra, dict):
            extra = {}
        extra.update(self.extra)
        kwargs['extra'] = extra
        return msg, kwargs

    def model_system(self, message, *args, **kwargs):
        message, kwargs = self.process(message, kwargs)
        self.logger.model_system(message, *args, **kwargs)

    def model_user(self, message, *args, **kwargs):
        message, kwargs = self.process(message, kwargs)
        self.logger.model_user(message, *args, **kwargs)

    def model_output(self, message, *args, **kwargs):
        message, kwargs = self.process(message, kwargs)
        self.logger.model_output(message, *args, **kwargs)



# ========================
# 7. Logging Functions
# ========================
def log_event(logger, event_type, message, extra_context=None):
    """
    Logs an event based on its type.
    """
    level_mapping = {
        "model_system": MODEL_SYSTEM_LEVEL,
        "model_user": MODEL_USER_LEVEL,
        "model_output": MODEL_OUTPUT_LEVEL,
    }
    if event_type in level_mapping:
        getattr(logger, event_type)(message, extra=extra_context)
    else:
        logger.info(message, extra=extra_context)

def log_standout_text(logger, content, title=None, color=Fore.LIGHTMAGENTA_EX):
    """
    Logs standout content with a custom level.
    """
    formatted_title = f"{color}{title}{Style.RESET_ALL}" if title else ""
    formatted_content = f"{color}{content}{Style.RESET_ALL}"
    message = f"{formatted_title}\n{formatted_content}" if title else formatted_content
    logger.model_output(message)

# ========================
# 8. Example Usage
# ========================
if __name__ == "__main__":
    # Initialize logger and listener *once*, in the correct place
    base_logger = setup_logger("MyProject")

    # Now that the logger has handlers, apply the filter
    custom_filter = CustomLevelFilter(LOGGING_CONFIG)
    for handler in base_logger.handlers:
        handler.addFilter(custom_filter)

    adapter = ContextLoggerAdapter(base_logger, {'parent_name': 'MainModule'})
    log_event(adapter, "model_system", "System level log for debugging.")
    log_event(adapter, "model_user", "User level log for tracking interactions.")
    log_event(adapter, "model_output", "Output level log for model responses.")
    log_standout_text(adapter, "This is standout output.", title="PlannerAgent Output")
    dummy_handler = "<dummy_handler>"
    adapter.info(f"📨 Dispatching message to handler {dummy_handler}")

    print("Logging test complete - Unicode emoji test: 📨 ✅ 🔍")
