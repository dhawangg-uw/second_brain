# Usage

## Installation

Clone the repository and install dependencies:

```bash
uv sync
```

## Running

Via the CLI entrypoint:

```bash
uv run second_brain                          # production defaults
uv run --env-file .env second_brain          # dev settings
```

Or as a Python module:

```bash
uv run python -m second_brain
```

## Log Output

Console and file logs use the same compact layout:

```text
YYYY-MM-DD HH:mm:ss | LEVEL | module:function:line | message
```

The configured stderr and file sinks disable ANSI colors by default, producing
the same deterministic plain-text layout on terminals, CI runners, containers,
and redirected output. Set `LOG_COLORIZE=true` to opt into colors on stderr;
the file remains plain text. Custom sinks and log aggregators should pass
`colorize=False` to `logger.add()` when they require plain text.

The timestamp is written to whole-second precision. Level labels have no fixed
padding and use the following display names:

| Loguru level | Display label |
|--------------|---------------|
| `DEBUG`      | `DEBUG`       |
| `INFO`       | `INFO`        |
| `WARNING`    | `WARN`        |
| `ERROR`      | `ERR`         |

Levels not listed in the table retain their original Loguru names. These are
display-only labels; filtering continues to use Loguru's original severity
levels. Downstream parsers should therefore accept unmapped display labels and
base severity-sensitive alerting on structured native level data when available.

The rotating file sink queues writes to avoid blocking application threads.
The CLI drains this queue during normal shutdown so all submitted records reach
the file before the process returns. Its `finally` block also performs the drain
when logging setup or application work raises, before `logger.catch(reraise=True)`
propagates the failure. An abrupt process termination can still prevent queued
records from being written.

The queued file handler uses a module-level formatter so it remains importable
and picklable for spawn-based multiprocessing workers. Each spawned process
must configure and complete its own process-local Loguru handlers.
Call `configure_logging()` during single-threaded process startup. It replaces
all existing handlers and is not a live-reconfiguration API for active workers.

## Environment Variables

| Variable    | Default    | Description                          |
|-------------|------------|--------------------------------------|
| `LOG_LEVEL` | `INFO`     | Console log level (DEBUG, INFO, …)   |
| `LOG_FILE`  | `app.log`  | Path to the log file                 |
| `LOG_COLORIZE` | `false` | Enable ANSI colors on stderr with `true`, `t`, `1`, `yes`, `y`, or `on` (case-insensitive) |

Copy `.env.example` to `.env` for development defaults, then run with `uv run --env-file .env`.

### Windows log path

In PowerShell, set an absolute Windows path before starting the application:

```powershell
$env:LOG_FILE = "C:\Users\you\AppData\Local\second-brain\app.log"
uv run second_brain
```

Loguru creates the parent directories when needed. PowerShell treats
backslashes as literal path separators, and the application passes the
configured value to Loguru without rewriting it.
