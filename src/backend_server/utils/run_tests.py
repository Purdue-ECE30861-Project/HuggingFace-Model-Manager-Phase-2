# run_tests.py
#from __future__ import annotations

import argparse
import io
import sys
import unittest

def run_testsuite() -> int:
    parser = argparse.ArgumentParser(description="Run unittest suite with coverage.")
    parser.add_argument("--tests-dir", default="tests",
                        help="Directory containing tests (default: tests)")
    parser.add_argument("--pattern", default="test*.py",
                        help="Glob pattern to discover tests (default: test*.py)")
    parser.add_argument("--source", default="backend_server",
                        help="Directory to measure coverage for (default: backend_server)")
    parser.add_argument("--omit", nargs="*", default=["*/tests/*", "*/site-packages/*"],
                        help="Glob patterns to omit from coverage")
    parser.add_argument("--verbosity", type=int, default=2,
                        help="unittest verbosity (default: 2)")
    args = parser.parse_args()

    # Start coverage (optional dependency)
    try:
        import coverage
    except ImportError:
        print("coverage.py not installed. Install with: pip install coverage", file=sys.stderr)
        return 2

    cov = coverage.Coverage(source=[args.source], omit=args.omit, branch=True)
    cov.start()

    # Discover & run tests
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=args.tests_dir, pattern=args.pattern)
    runner = unittest.TextTestRunner(verbosity=args.verbosity)
    result: unittest.TestResult = runner.run(suite)

    # Stop coverage and compute percentage
    cov.stop()
    cov.save()
    report_buffer = io.StringIO()
    try:
        total_percent = cov.report(file=report_buffer)
    except coverage.CoverageException as e:
        # If no files matched (e.g., wrong --source), handle gracefully
        print(f"Coverage error: {e}", file=sys.stderr)
        total_percent = 0.0

    # Compute pass stats
    total_run = result.testsRun
    n_fail = len(result.failures)
    n_err = len(result.errors)
    n_unexp = len(getattr(result, "unexpectedSuccesses", []))
    n_skip = len(getattr(result, "skipped", []))
    n_xfail = len(getattr(result, "expectedFailures", []))

    passed = total_run - n_fail - n_err - n_unexp  # skips & xfails do not count as passes

    # Summary line
    print("\n" + "-" * 60)
    print(f"{passed}/{total_run} test cases passed. {total_percent:.2f}% line coverage achieved.")
    if n_skip or n_xfail:
        print(f"(skipped: {n_skip}, expected failures: {n_xfail})")
    if n_fail or n_err or n_unexp:
        print(f"(failures: {n_fail}, errors: {n_err}, unexpected successes: {n_unexp})")

    # Exit code: 0 only if clean
    return 0 if (n_fail == 0 and n_err == 0 and n_unexp == 0) else 1


if __name__ == "__main__":
    sys.exit(run_testsuite())
