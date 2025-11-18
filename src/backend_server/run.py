#!/usr/bin/env python3
# ./run D:\Lucas College\Purdue\Y4\ECE461\ECE-461-Project1-CLI\urls.txt
# ./run test
# ./run install
import sys
import subprocess
from src.utils.run_tests import run_testsuite
import logging
from src.utils.logger import setup_logging

logger = logging.getLogger(__name__)

def main():
    setup_logging()
    
    if len(sys.argv) < 2:
        print("Usage: ./run [install|test|URL_FILE]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "install":
        logger.info("Installing dependencies...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            logger.info("Dependencies installed successfully")
            logging.shutdown()
            sys.exit(0)
        except Exception as e:
            logger.warning(f"Installation failed with exception: {e}")
            logging.shutdown()
            # print(f"[install] failed: {e}", file=sys.stderr)
            sys.exit(1)
           
    elif command == "test":
        logger.info("Running tests...")
        test_args = sys.argv[2:]
        # forward args to your unittest runner
        sys.argv = [sys.argv[0]] + test_args
        try:
            code = run_testsuite()   # ← get the real exit code
            logger.info(f"Tests completed with exit code: {code}")
        except Exception as e:
            logger.warning(f"Tests failed with exception: {e}")
            code = 1  # on exception, fail the run
            
        logging.shutdown()
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
            logger.warning(f"Error: could not find file '{url_file}'")
            logging.shutdown()
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
                    logger.warning(f"Error processing URL '{url}': {e}")
                    logging.shutdown()
                    # print(json.dumps(error_record), file=sys.stderr)
                    # print_full_exception(e)
                    sys.exit(1)
            else:
                # Non-HF URLs (GitHub, etc.) handled later
                if "dataset" in url:
                    recentDatasetURL = url
                elif "github" in url:
                    recentGhURL = url
        logger.info("All URLs processed successfully")
        logging.shutdown()
        sys.exit(0)

if __name__ == "__main__":
    main()