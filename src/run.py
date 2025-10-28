#!/usr/bin/env python3
# ./run D:\Lucas College\Purdue\Y4\ECE461\ECE-461-Project1-CLI\urls.txt
# ./run test
# ./run install
import sys
import json
import subprocess
from src.utils.run_tests import run_testsuite
import traceback
import os
import datetime
from dotenv import load_dotenv
import time
import boto3
import logging
from watchtower import CloudWatchLogHandler

# Read environment config
load_dotenv()
LOG_FILE = os.getenv("LOG_FILE", "run.log")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
CLOUDWATCH_LOG_GROUP = os.getenv("CLOUDWATCH_LOG_GROUP", "/ece461/project")
CLOUDWATCH_LOG_STREAM = os.getenv("CLOUDWATCH_LOG_STREAM", f"run-logs-{datetime.utcnow().strftime('%Y%m%d')}")
try:
    LOG_LEVEL = int(os.getenv("LOG_LEVEL", "0"))
except ValueError:
    LOG_LEVEL = 0  # fallback
    
# Initialize cloudwatch handler
cloudwatch_handler = None

def init_cloudwatch():
    """
    Initialize CloudWatch handler using Watchtower.
    """
    global cloudwatch_handler
    
    try:
        boto3_client = boto3.client('logs', region_name=AWS_REGION)
        
        cloudwatch_handler = CloudWatchLogHandler(
            log_group_name=CLOUDWATCH_LOG_GROUP,
            log_stream_name=CLOUDWATCH_LOG_STREAM,
            use_queues=True,
            create_log_group=True,
            boto3_client=boto3_client
        )
        
    except Exception as e:
        print(f"Failed to initialize CloudWatch logging: {e}. Using local logging only.", file=sys.stderr)
        cloudwatch_handler = None
        
def send_to_cloudwatch(message: str):
    """
    Send a log message to CloudWatch.
    """
    if not cloudwatch_handler:
        return
    
    try:
        record = logging.LogRecord(
            name="CloudWatchLogger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=message,
            args=(),
            exc_info=None
        )
        
        record.created = time.time()
        cloudwatch_handler.emit(record)
    
    except Exception as e:
        print(f"Failed to send log to CloudWatch: {e}", file=sys.stderr)
        
def flush_cloudwatch():
    """
    Flush any buffered CloudWatch logs.
    """
    if cloudwatch_handler:
        try:
            cloudwatch_handler.flush()
        except Exception as e:
            print(f"CloudWatch flush error: {e}", file=sys.stderr)

def print_full_exception(e):
    # Full formatted traceback string (multi-line)
    tb_str = "".join(traceback.TracebackException.from_exception(e).format())

    # Last frame (where it blew up)
    tb_frames = traceback.extract_tb(e.__traceback__)
    last = tb_frames[-1] if tb_frames else None

    error_record = {
        "error_type": e.__class__.__name__,
        "message": str(e),
        "filename": getattr(last, "filename", None),
        "lineno": getattr(last, "lineno", None),
        "function": getattr(last, "name", None),
        "code": getattr(last, "line", None),
    }
   
    error_record["traceback"] = tb_str
    print(json.dumps(error_record, ensure_ascii=False), file=sys.stderr)

def log(msg, level=1):
    """
    level=1 -> info, level=2 -> debug
    """
    if LOG_LEVEL >= level:
        ts = datetime.utcnow().isoformat()
        record = {"time": ts, "level": level, "msg": msg}
        log_message = json.dumps(record, ensure_ascii=False)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_message + "\n")
            
        send_to_cloudwatch(log_message)

def log_exception(e, url=None):
    tb_str = "".join(traceback.TracebackException.from_exception(e).format())
    tb_frames = traceback.extract_tb(e.__traceback__)
    last = tb_frames[-1] if tb_frames else None

    error_record = {
        "error_type": e.__class__.__name__,
        "message": str(e),
        "filename": getattr(last, "filename", None),
        "lineno": getattr(last, "lineno", None),
        "function": getattr(last, "name", None),
        "code": getattr(last, "line", None),
        "traceback": tb_str,
    }
    if url:
        error_record["url"] = url
    if LOG_LEVEL >= 1:  # errors show up if verbosity ≥ info
        log_message = json.dumps(error_record, ensure_ascii=False)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_message + "\n")
        
        send_to_cloudwatch(log_message)

def main():
    init_cloudwatch()
    
    if len(sys.argv) < 2:
        print("Usage: ./run [install|test|URL_FILE]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "install":
        log("Installing dependencies...", level=1)
        # print("Installing dependencies...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            log("Dependencies installed successfully", level=1)
            flush_cloudwatch()
            sys.exit(0)
        except Exception as e:
            log_exception(e)
            flush_cloudwatch()
            # print(f"[install] failed: {e}", file=sys.stderr)
            sys.exit(1)
           
    elif command == "test":
        log("Running tests...", level=1)
        test_args = sys.argv[2:]
        # forward args to your unittest runner
        sys.argv = [sys.argv[0]] + test_args
        try:
            code = run_testsuite()   # ← get the real exit code
            log(f"Tests completed with exit code: {code}", level=1)
        except Exception as e:
            log_exception(e)
            code = 1  # on exception, fail the run
            
        flush_cloudwatch()
        sys.exit(code)

    else:
        # assume it's a file with URLs
        from src.utils.check_url import checkURL
        from src.classes.ScoreCard import ScoreCard

        url_file = command
        try:
            urls = []
            with open(url_file, "r") as f:
                for line in f:
                    line = line.strip()
                    url_list = line.split(",")
                    for url in url_list:
                        urls.append(url.strip())
        except FileNotFoundError as e:
            log_exception(e)
            flush_cloudwatch()
            # print(f"Error: could not find file '{url_file}'", file=sys.stderr)
            sys.exit(1)

        recentGhURL = None
        recentDatasetURL = None
        for url in urls:
            if url and checkURL(url):
                try:
                    modelScore = ScoreCard(url)
                   
                    if recentDatasetURL:
                        modelScore.setDatasetURL(recentDatasetURL)
                    if recentGhURL:
                        modelScore.setGithubURL(recentGhURL)

                    modelScore.setTotalScore()
                    modelScore.printScores()

                except Exception as e:
                    error_record = {
                        "url": url,
                        "error": str(e)
                    }
                    log_exception(e)
                    flush_cloudwatch()
                    # print(json.dumps(error_record), file=sys.stderr)
                    # print_full_exception(e)
                    sys.exit(1)
            else:
                # Non-HF URLs (GitHub, etc.) handled later
                if "dataset" in url:
                    recentDatasetURL = url
                elif "github" in url:
                    recentGhURL = url
        log("All URLs processed successfully", level=1)
        flush_cloudwatch()
        sys.exit(0)

if __name__ == "__main__":
    main()