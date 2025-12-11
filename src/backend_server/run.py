#!/usr/bin/env python3
# ./run D:\Lucas College\Purdue\Y4\ECE461\ECE-461-Project1-CLI\urls.txt
# ./run test
# ./run install
import sys
import subprocess
import time
from src.backend_server.utils.run_tests import run_testsuite
import logging
from src.backend_server.utils.logger import setup_logging
from src.frontend_server.model.cloudwatch_publisher import CloudWatchPublisher

logger = logging.getLogger(__name__)
cli_metrics = CloudWatchPublisher("api_gateway")

def publish_cli_metrics(operation: str, success: bool, latency_ms: float):
    """
    Publish CLI operation metrics to CloudWatch.
    
    Args:
        operation: Operation type (e.g., 'url_processing', 'install', 'test')
        success: Whether operation succeeded
        latency_ms: Time taken in milliseconds
    """
    if not cli_metrics:
        return
    
    try:
        cli_metrics.publish_batch([
            {'name': 'RequestCount', 'value': 1, 'unit': 'Count'},
            {'name': 'Latency', 'value': latency_ms, 'unit': 'Milliseconds'},
            {'name': f'{operation}Success', 'value': 1 if success else 0, 'unit': 'Count'}
        ])
        logger.debug(f"Published CloudWatch metrics for {operation}: "
                    f"success={success}, latency={latency_ms:.2f}ms")
    except Exception as e:
        logger.warning(f"Failed to publish CloudWatch metrics: {e}")

def main():
    setup_logging()
    start_time = time.time()
    operation_success = True
    
    if len(sys.argv) < 2:
        print("Usage: ./run [install|test|URL_FILE]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "install":
        logger.info("Installing dependencies...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            logger.info("Dependencies installed successfully")
            operation_success = True
        except Exception as e:
            logger.warning(f"Installation failed with exception: {e}")
            operation_success = False
        finally:
            elapsed_ms = (time.time() - start_time) * 1000
            publish_cli_metrics("install", operation_success, elapsed_ms)
            logging.shutdown()
            sys.exit(0 if operation_success else 1)
           
    elif command == "test":
        logger.info("Running tests...")
        test_args = sys.argv[2:]
        sys.argv = [sys.argv[0]] + test_args
        try:
            code = run_testsuite()
            logger.info(f"Tests completed with exit code: {code}")
            operation_success = (code == 0)
        except Exception as e:
            logger.warning(f"Tests failed with exception: {e}")
            code = 1
            operation_success = False
        finally:
            elapsed_ms = (time.time() - start_time) * 1000
            publish_cli_metrics("test", operation_success, elapsed_ms)
            logging.shutdown()
            sys.exit(code)

    else:
        from src.backend_server.utils.check_url import checkURL
        from src.backend_server.classes.ScoreCard import ScoreCard

        url_file = command
        urls_processed = 0
        urls_failed = 0
        try:
            urls = []
            with open(url_file, "r") as f:
                for line in f:
                    line = line.strip()
                    url_list = line.split(",")
                    for url in url_list:
                        urls.append(url.strip())
        except FileNotFoundError as e:
            logger.warning(f"Error: could not find file '{url_file}'")
            operation_success = False
            elapsed_ms = (time.time() - start_time) * 1000
            publish_cli_metrics("url_processing", operation_success, elapsed_ms)
            logging.shutdown()
            sys.exit(1)

        recentGhURL = None
        recentDatasetURL = None
        for url in urls:
            if url and checkURL(url):
                url_start_time = time.time()
                url_success = True
                
                try:
                    modelScore = ScoreCard(url)
                   
                    if recentDatasetURL:
                        modelScore.setDatasetURL(recentDatasetURL)
                    if recentGhURL:
                        modelScore.setGithubURL(recentGhURL)

                    modelScore.setTotalScore()
                    modelScore.printScores()
                    
                    urls_processed += 1
                    logger.info(f"Successfully processed URL: {url}")

                except Exception as e:
                    error_record = {
                        "url": url,
                        "error": str(e)
                    }
                    logger.warning(f"Error processing URL '{url}': {e}")
                    urls_failed += 1
                    url_success = False
                    operation_success = False
                
                finally:
                    # Publish metrics for this URL processing
                    url_elapsed_ms = (time.time() - url_start_time) * 1000
                    if cli_metrics:
                        cli_metrics.publish_metric(
                            metric_name="URLProcessingTime",
                            value=url_elapsed_ms,
                            unit="Milliseconds",
                            dimensions={'Success': 'true' if url_success else 'false'}
                        )
            else:
                if "dataset" in url:
                    recentDatasetURL = url
                elif "github" in url:
                    recentGhURL = url
        
        logger.info(f"URL processing complete: {urls_processed} successful, {urls_failed} failed")
        
        # Publish final summary metrics
        elapsed_ms = (time.time() - start_time) * 1000
        publish_cli_metrics("url_processing", operation_success, elapsed_ms)
        
        # Also publish batch processing summary if CloudWatch is enabled
        if cli_metrics:
            try:
                cli_metrics.publish_batch([
                    {"name": "URLsProcessed", "value": urls_processed, "unit": "Count"},
                    {"name": "URLsFailed", "value": urls_failed, "unit": "Count"},
                    {"name": "BatchProcessingTime", "value": elapsed_ms, "unit": "Milliseconds"}
                ])
            except Exception as e:
                logger.warning(f"Failed to publish batch summary: {e}")
        
        logger.info("All URLs processed successfully")
        logging.shutdown()
        sys.exit(0 if operation_success else 1)

if __name__ == "__main__":
    main()