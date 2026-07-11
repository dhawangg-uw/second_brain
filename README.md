# second-brain

`second-brain` is a small Python application scaffold with an installable
src-layout package, structured logging, tests, linting, coverage, and MkDocs
documentation.

## Project Setup

The project uses these conventions:

- **Python:** 3.13 or newer
- **Package manager and build tool:** [uv](https://docs.astral.sh/uv/)
- **Build backend:** `uv_build`
- **Package layout:** source code lives in `src/second_brain/`
- **Runtime logging:** Loguru writes to stderr and a rotating log file
- **Quality tools:** Ruff for linting and formatting; pytest and coverage for tests
- **Documentation:** Material for MkDocs with API reference generated from source

The application version is defined once in `pyproject.toml`. Keep the generated
`uv.lock` file committed so every environment resolves the same dependencies.

## Initial Installation

Clone the repository and install the application plus its development tools:

```bash
uv sync
```

This creates a local `.venv`, installs dependencies, and updates `uv.lock` when
necessary. There is no need to activate the virtual environment when using
`uv run`.

## Project Layout

```text
src/second_brain/  Application package and CLI entry point
tests/             Pytest suite
docs/              MkDocs pages
scripts/           Development helper scripts
pyproject.toml     Package metadata and tool configuration
.env.example       Committed development-environment template
.env.test          Test-only environment values (not committed)
```

## Usage Pattern

The normal workflow is to make changes under `src/second_brain/`, run the
application with `uv run`, then run the test and lint checks before committing.

### Run with production defaults

```bash
uv run second_brain
```

This is the installed CLI entry point. It writes an informational greeting to
stderr and to `app.log` by default.

### Run with development settings

Create your local environment file once:

```bash
cp .env.example .env
```

Then load it explicitly when running the application:

```bash
uv run --env-file .env second_brain
```

`.env` files are intentionally not loaded automatically. Keeping the
`--env-file` flag in the command makes the active configuration clear.

### Run as a module

```bash
uv run python -m second_brain
```

This invokes the same `main()` function as the CLI entry point.

## Configuration

Copy `.env.example` to `.env` for local development. Do not commit `.env` or
`.env.test`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Minimum level displayed on stderr. The development template uses `DEBUG`. |
| `LOG_FILE` | `app.log` | File path for DEBUG-and-higher logs. The file rotates at 50 KB and retains one backup. |

Tests load `.env.test` through pytest-env. The autouse test fixture redirects
`LOG_FILE` to pytest's temporary directory, so a test run never writes `app.log`
to the repository root.

## Development Commands

Run tests:

```bash
uv run pytest
```

Run tests with coverage (the project requires at least 80% coverage):

```bash
uv run pytest --cov
```

Check style and automatically format files:

```bash
uv run ruff check .
uv run ruff format .
```

## Documentation

Preview the Material for MkDocs site locally:

```bash
uv run python scripts/serve_docs.py
```

The helper streams server output to both the terminal and `mkdocs.log`.

Build static documentation without starting a server:

```bash
uv run mkdocs build
```

The generated site is written to `site/`, which is ignored by Git.
