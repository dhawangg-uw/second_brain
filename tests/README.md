# Logging Test Reference

This page explains how the logging tests validate the compact Loguru output
defined in `src/second_brain/app.py`.

## Rendered log format

The formatter template is:

```text
<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{extra[level_label]}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>\n{exception}
```

Loguru strips the color markup when the sink does not render colors. A normal
record therefore has this shape:

```text
YYYY-MM-DD HH:mm:ss | LEVEL | module:function:line | message
```

## Main format regex

`_assert_compact_standard_lines()` validates each standard log line with:

```python
rf"\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}}"
rf" \| {label} \| [^|\n]+:[^:|\n]+:\d+"
rf" \| {message}"
```

| Component | Regex | Example output |
| --- | --- | --- |
| Timestamp | `\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}` | `2026-07-11 14:30:45` |
| Separator | ` \| ` | ` \| ` |
| Level | `{label}` | `DEBUG`, `INFO`, `WARN`, or `ERR` |
| Source | `[^|\n]+:[^:|\n]+:\d+` | `tests.test_app:test_compact_log_format:32` |
| Message | `{message}` | `debug message` |

The test uses `re.fullmatch()` so the complete line must conform to the format,
with no unexpected leading or trailing content. It applies the same assertions
to both the console and file sinks. The source assertion requires module,
function, and numeric line fields without coupling the test to their names.

## Exception format regex

`test_compact_log_format_preserves_exceptions()` validates the first line of an
exception record with:

```python
r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
r" \| ERR \| [^|\n]+:[^:|\n]+:\d+"
r" \| operation failed\n"
```

| Component | Regex | Example output |
| --- | --- | --- |
| Timestamp | `\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}` | `2026-07-11 14:30:45` |
| Level | `ERR` | `ERR` |
| Source | `[^|\n]+:[^:|\n]+:\d+` | `tests.test_app:test_compact_log_format_preserves_exceptions:87` |
| Message and newline | `operation failed\n` | `operation failed` followed by a newline |

This test uses `re.search()` because Loguru appends the traceback after the
first line. A separate assertion checks that the traceback contains
`ValueError: example failure`.

## Coverage summary

| Test | What it validates | Matching strategy |
| --- | --- | --- |
| `test_compact_log_format` | Four mapped labels, exact output, console sink, and file sink | `re.fullmatch()` |
| `test_configured_thresholds_are_preserved` | Console and file level filtering | Substring checks |
| `test_custom_loguru_levels_retained` | Fallback labels for unmapped Loguru levels | Substring check |
| `test_compact_log_format_preserves_exceptions` | Compact exception line and preserved traceback | `re.search()` plus substring check |

Together, these tests cover whole-second timestamps without milliseconds, pipe
separators, mapped and fallback level labels, source locations, messages,
exceptions, sink consistency, and configured filtering thresholds.

## Fixture isolation

The `log_file` fixture returns the exact `Path` assigned to `LOG_FILE`, allowing
tests to read the same file that `configure_logging()` configures. The autouse
`_isolate_logger` fixture depends on `log_file`, so the environment variable is
always set before a test runs, even when that test does not request the path
directly. Its teardown removes all Loguru handlers after every test to prevent
the global logger singleton from leaking configuration into later tests. Tests
must configure and assert a complete logger scenario within one test function;
cross-test handler state is intentionally unsupported so test order cannot hide
handler leaks or configuration mistakes.

The console sink writes synchronously. The file sink is queued, so test helpers
call `logger.complete()` before reading files and teardown drains the queue
before removing handlers.
