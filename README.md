# ECE-461 Project 1 CLI

## Phase 1 Team Members
- Eric Song  
- Lucas Nguyen  
- Shriya Gupta  
- Mythrai Kapidi

## Phase 2 Team Members
- Daniel Brown
- Michael Ray
- Matthew Weiss
- Brian Diaz 

## Project Structure

```
ECE-461-Project1-CLI/
├── src/                           # Source package
│   ├── run.py                     # CLI entry point (invoked by ./run)
│   ├── classes/                   # Metric implementations
│   │   ├── AvailableDatasetAndCode.py  # Dataset/code availability scoring
│   │   ├── BusFactor.py               # Number of evenly distributed active contributors score
│   │   ├── CodeQuality.py             # Repository lint/readability score
│   │   ├── DatasetQuality.py          # Data documentation and fidelity
│   │   ├── License.py                 # License compatibility check
│   │   ├── PerformanceClaims.py       # Claim verification workflow
│   │   ├── RampUpTime.py              # Documentation ramp-up estimation
│   │   ├── Metric.py                  # Shared scoring interface and weights
│   │   ├── ScoreCard.py               # Aggregates metric results
│   │   └── Size.py                    # Model artifact sizing by device
│   └── utils/                    # Shared utilities
│       ├── check_url.py          # Validates Hugging Face / GitHub URLs
│       ├── get_metadata.py       # Scrapes Hugging Face + GitHub metadata
│       ├── hf_api.py             # Hugging Face Hub API helpers
│       ├── llm_api.py            # Fallback LLM prompts for heuristics
│       └── run_tests.py          # Coverage-enabled unittest runner
├── tests/                        # Main automated test suite
│   ├── test_RampUpTime.py
│   ├── test_Size.py
│   ├── test_availabledatasetandcode.py
│   ├── test_codequality.py
│   ├── test_datasetquality.py
│   ├── test_get_metadata.py
│   ├── test_hf_api.py
│   ├── test_license.py
│   ├── test_llm.py
│   ├── test_metrics.py
│   ├── test_performanceclaims.py
│   ├── test_scoring.py
│   └── test_url.py
├── test/                         # Legacy unittest scaffolding (kept for rubric)
├── run                           # Convenience script for install/test/CLI
├── requirements.txt              # Python dependencies
├── urls.txt                      # Example list of Hugging Face resources
├── message.txt                   # Maintainer notes / rubric reminders
└── README.md                     # This document
```

## Getting Started

### Prerequisites
- Python 3.10 or higher
- `pip` (ships with most Python distributions)
- Git (optional, but recommended for managing changes)

### Installation
```bash
# (Optional) create an isolated environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# From the repository root
chmod +x run  # only needed once on Unix-like systems

# Install dependencies into the active environment
./run install
```

## Running Tests

### Quick Test Run
```bash
# Discover tests, execute with coverage summary
./run test
```

### Custom Test Execution
```bash
# Specify pattern or directory
python -m src.utils.run_tests --pattern "test_*.py" --tests-dir tests

# Run a single module with unittest
python -m unittest tests.test_scoring
```

### Coverage Report
`run_tests.py` wraps `coverage.py` and prints pass counts plus line coverage. For an HTML report:
```bash
coverage html
open htmlcov/index.html   # Windows: start htmlcov\index.html
```

## Code Quality
- Unit tests must remain green (`./run test`). Attach new tests for every feature or bug fix.
- Keep modules and public functions documented with top-of-file/context comments to satisfy the course rubric.
- Optional static checks:
  - `python -m compileall src` to catch syntax errors
  - `pip install ruff` then `ruff check src tests` for linting suggestions

## Usage

### Running the CLI
```bash
# Score every resource listed in urls.txt (comma or newline separated)
./run urls.txt
```

Each scored Hugging Face model prints a single NDJSON record:
- `net_score` — weighted total across all metrics
- `*_latency` — milliseconds spent computing the metric
- Individual metric scores (`bus_factor`, `ramp_up_time`, etc.)

### Input Expectations
- Hugging Face model URLs (e.g., `https://huggingface.co/owner/model`)
- Optional accompanying dataset or GitHub repository URLs can appear on preceding lines; the CLI associates them with the next model encountered.

## Evaluated Metrics
- **Bus Factor** (`src/classes/BusFactor.py`): combines GitHub contributor distribution with a language-model fallback when collaboration data is unavailable.
- **Code Quality** (`src/classes/CodeQuality.py`): inspects repository files and README heuristics to estimate maintainability.
- **Dataset Quality** (`src/classes/DatasetQuality.py`): reviews dataset documentation, licensing, and provenance for clarity.
- **Available Dataset and Code** (`src/classes/AvailableDatasetAndCode.py`): checks linked datasets and code repositories for access parity.
- **License Compliance** (`src/classes/License.py`): verifies the permissiveness and compatibility of the published license.
- **Performance Claims** (`src/classes/PerformanceClaims.py`): searches for documented benchmarks and ensures they are supported by references.
- **Ramp-Up Time** (`src/classes/RampUpTime.py`): measures how quickly a newcomer can understand usage from the README.
- **Size Scoring** (`src/classes/Size.py`): categorizes model artifacts by hardware footprint.

The aggregated `ScoreCard` class fuses these metrics into a weighted `net_score` and tracks total latency for each evaluation.

## Configuration
- `.env` (optional) controls runtime logging.
  - `LOG_FILE` (default `run.log`) designates the log destination.
  - `LOG_LEVEL` (`0` = silent, `1` = info, `2` = debug) toggles structured JSON logs.
- Set environment variables before invoking `./run` to enable persistent audit trails.

## Contributing
1. Open an issue describing the proposed change and expected rubric impact.
2. Implement features with clear module-level and function-level docstrings; mirror existing style for scoring classes.
3. Update or add tests (`tests/`) that exercise new behavior and keep coverage healthy.
4. Run `./run test` before pushing. Include README updates when workflows or dependencies change.

## License

Coursework submission for Purdue ECE-461. Redistribution outside class context may require instructor approval.

## Workload Planning
- The course expects roughly 40 hours per teammate across the 5-week project timeline (~8 hours/week). Front-load research and integration tasks so the postmortem week can focus on polishing documentation and tests.
