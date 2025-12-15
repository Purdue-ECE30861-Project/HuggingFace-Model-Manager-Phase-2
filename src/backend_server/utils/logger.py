import logging
import json
import os
import sys
import datetime
from dotenv import load_dotenv
import boto3
from watchtower import CloudWatchLogHandler

# Load environment once
load_dotenv()

LOG_FILE = os.getenv("LOG_FILE", "run.log")
AWS_REGION = os.getenv("AWS_REGION", "us-east-2")
CLOUDWATCH_LOG_GROUP = os.getenv("CLOUDWATCH_LOG_GROUP", "/ece461/project")
CLOUDWATCH_LOG_STREAM = os.getenv("CLOUDWATCH_LOG_STREAM", f"run-logs-{datetime.datetime.now(datetime.UTC).strftime('%Y%m%d')}")

try:
    LOG_LEVEL = int(os.getenv("LOG_LEVEL", "1"))
except ValueError:
    LOG_LEVEL = 1

# Map custom LOG_LEVEL to Python logging levels
LEVEL_MAP = {
    0: logging.WARNING,
    1: logging.INFO,
    2: logging.DEBUG
}

class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    """
    
    def __init__(self, pretty=False):
        super().__init__()
        self.pretty = pretty
    
    def format(self, record):
        log_data = {
            "time": datetime.datetime.now(datetime.UTC).isoformat(timespec='seconds'),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["error_type"] = record.exc_info[0].__name__
            log_data["error_message"] = str(record.exc_info[1])
            log_data["traceback"] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        for key in ['url', 'filename', 'lineno', 'function', 'code']:
            if hasattr(record, key):
                log_data[key] = getattr(record, key)
        
        if self.pretty:
            # Pretty print with indentation and add separator
            return json.dumps(log_data, ensure_ascii=False, indent=2) + "\n" + "-" * 80
        else:
            # Single line JSON (better for log aggregation)
            return json.dumps(log_data, ensure_ascii=False)


def setup_logging():
    """
    Initialize logging handlers. Call once at application startup.
    """
    
    # Get root logger
    logging.getLogger("httpx").setLevel(logging.WARNING)
    root_logger = logging.getLogger()
    root_logger.setLevel(LEVEL_MAP.get(LOG_LEVEL, logging.INFO))
    
    root_logger.handlers.clear()
    
    # File handler
    file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding='utf-8')
    file_handler.setFormatter(JSONFormatter())
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    
    # CloudWatch handler
    try:
        cloudwatch_handler = CloudWatchLogHandler(
            log_group_name=CLOUDWATCH_LOG_GROUP,
            log_stream_name=CLOUDWATCH_LOG_STREAM,
            use_queues=True,
            create_log_group=True,
            boto3_client=boto3.client('logs', region_name=AWS_REGION)
        )
        cloudwatch_handler.setFormatter(JSONFormatter())
        cloudwatch_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(cloudwatch_handler)

    except Exception as e:
        root_logger.warning(f"Failed to set up CloudWatch logging: {e}. Local logging will continue.")
    
    # Console handler for errors
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.ERROR)
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    root_logger.addHandler(console_handler)