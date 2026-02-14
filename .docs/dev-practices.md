# Developer guide

This document provides an overview of the development process, best practices, and tooling for this project.

## Package manager (uv)

This project uses [uv](https://docs.astral.sh/uv/) as build tool and package manager.

```sh
# Install dependencies
uv sync --dev

# Add a dependency
uv add <package>

# Add a dev dependency
uv add --dev <package>

# Run a command
uv run <command>
```

Refer to [uv documentation](https://docs.astral.sh/uv/) for more details.

## Project structure

```
dl_obs/
├── src/                        # Main source code
│   ├── data/                   # Data access layer
│   │   ├── az.py               # Azure Blob Storage client
│   │   ├── grafana.py          # Grafana API client (DAO)
│   │   └── grafana_dto.py      # Grafana data structures (DTO)
│   ├── features/               # Feature engineering
│   ├── models/                 # ML models
│   └── processing/             # Data processing pipelines
├── configs/                    # Python project configuration
│   ├── constants.py            # Project constants
│   └── queries.yaml            # Query definitions
├── scripts/                    # Utility scripts
│   └── push_to_blob.py         # Azure blob upload script
├── experiments/                # ML experiments
├── tests/                      # Unit tests
│   ├── conftest.py             # Shared fixtures
│   └── test_*.py               # Test files
├── utils/                      # Shared utilities
│   ├── exceptions.py           # Custom exceptions
│   └── logging.py              # Logging configuration
├── .docker/                    # Docker container configs
│   ├── conf.alloy              # Alloy configuration
│   ├── loki.yaml               # Loki configuration
│   └── prometheus.yml          # Prometheus configuration
├── .docs/                      # Internal documentation
├── .tf/                        # Terraform configuration
├── .github/workflows/          # CI/CD GitHub Actions
├── .pre-commit-config.yaml     # Pre-commit hooks
├── docker-compose.yml          # Local stack definition
├── pyproject.toml              # Project configuration
├── Makefile                    # Development commands
└── py.typed                    # PEP 561 marker (typed package)
```

## Development tools

### Ruff (linter + formatter)

Ruff replaces flake8, isort, and black in a single tool.

```sh
# Check code
uv run ruff check .

# Auto-fix issues
uv run ruff check --fix .

# Format code
uv run ruff format .
```

Configuration in `pyproject.toml`:
- Enabled rules: E, W, F, I, B, C4, UP, SIM
- Line length: 100 characters
- Target: Python 3.12

### Mypy (type checking)

Mypy statically checks type annotations.

```sh
uv run mypy dao dto azure
```

Configuration:
- `disallow_untyped_defs`: All functions must have type annotations
- `warn_return_any`: Warns if a function returns `Any`
- `ignore_missing_imports`: Ignores imports without stubs

### Pytest (tests)

Pytest is the testing framework, with code coverage support.

```sh
# Run tests
uv run pytest

# With coverage
uv run pytest --cov --cov-report=term-missing

# HTML report
uv run pytest --cov --cov-report=html
```

Configuration:
- Test directory: `tests/`
- File pattern: `test_*.py`
- Function pattern: `test_*`
- Coverage threshold: 50% (increase progressively)

## Code conventions

### Naming

Follow these naming conventions:

- **Classes:** PascalCase (`GrafanaDao`, `GrafanaQueryResponse`).
- **Functions/methods:** snake_case (`get_frames`, `upload_blob`).
- **Constants:** UPPER_SNAKE_CASE (`DEFAULT_TIME_WINDOW`).
- **Files:** snake_case (`grafana.py`, `test_dto_grafana.py`).

### Architecture

The codebase follows these patterns:

- **DAO:** Handles API calls and returns DTOs.
- **DTO:** Immutable data structures with `@dataclass`.
- **Tests:** One file per module (`test_<module>.py`).

### Type hints

All public functions must have type annotations:

```python
def query(
    self,
    kind: DatasourceKind,
    datasource_uid: str,
    expr: str,
    from_time: float | None = None,
) -> GrafanaQueryResponse:
```

### Docstrings
Recommended format (Google style):

```python
def upload(self, blob_name: str, data: bytes) -> BlobClient:
    """Uploads data to Azure Blob Storage.

    Args:
        blob_name: Name/path of the blob in the container.
        data: Content to upload.

    Returns:
        BlobClient for the uploaded blob.

    Raises:
        ValueError: If connection string is missing.
    """
```

## Pre-commit hooks

Pre-commit hooks run automatically before each commit.

### Installation (once)
```sh
make setup
```

### Configured hooks

The following hooks run on every commit:

- **ruff:** Linting + auto-fix
- **ruff-format:** Automatic formatting.
- **mypy:** Type checking.
- **trailing-whitespace:** Removes trailing whitespace.
- **end-of-file-fixer:** Adds newline at end of file.
- **check-yaml:** Validates YAML syntax.
- **check-added-large-files:** Blocks files > 1MB.
- **detect-private-key:** Blocks private keys.

### Bypass (if needed)

To skip hooks for a specific commit:

```sh
git commit --no-verify -m "message"
```

## Custom exceptions

Use exceptions from the `utils.exceptions` module:

```python
from utils.exceptions import ConfigurationError, GrafanaQueryError

# Raise an exception
if not api_key:
    raise ConfigurationError("GRAFANA_API_KEY is required")

# Catch an exception
try:
    response = dao.query(...)
except GrafanaQueryError as e:
    logger.error(f"Query failed: {e}")
```

### Hierarchy
```
DlObsError (base)
├── ConfigurationError
├── GrafanaError
│   ├── GrafanaConnectionError
│   └── GrafanaQueryError
└── AzureError
    ├── AzureConnectionError
    └── AzureUploadError
```

## Logging

Use `utils.logging` module instead of `print()`:

```python
from utils.logging import get_logger, setup_logging

# At application startup
setup_logging(level="INFO")

# In each module
logger = get_logger(__name__)

# Usage
logger.info("Starting process")
logger.warning("Rate limit approaching")
logger.error("Failed to connect", exc_info=True)
```

## Development workflow

### Before each commit
```sh
make validate
```

This command runs:
1. `ruff check` - Checks linting
2. `ruff format --check` - Checks formatting
3. `mypy` - Checks types
4. `pytest --cov` - Runs tests with coverage

### Adding a new feature

Follow these steps to add a new feature:
1. Create DTOs if needed in `dto/`
2. Implement DAO in `dao/`
3. Write tests in `tests/test_<module>.py`
4. Run `make validate`
5. Commit and push

## Environment variables

Create a `.env` file (never committed):

```sh
# Grafana
GRAFANA_URL=https://your-grafana-instance.com
GRAFANA_SA_TOKEN=your-service-account-token

# Azure
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...
AZURE_STORAGE_CONTAINER_NAME=your-container
```

## CI/CD (GitHub Actions)

Workflow example `.github/workflows/ci.yml`:

```yaml
name: CI

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --dev
      - run: make validate
```

## Related documentation

- [Local development stack](./local-stack.md) - Docker Compose setup for testing
- [Architecture](./architecture.md) - System architecture overview
- [Quality assurance](./qa.md) - QA processes and standards
- [Runbook](./runbook.md) - Operational procedures
