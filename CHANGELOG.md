# Changelog

Notable user-facing changes to `second-brain` are documented here.

## Unreleased

### Changed

- Console and file logs now use whole-second timestamps without milliseconds.
- Log level padding was removed, and the displayed `WARNING` and `ERROR` labels
  changed to `WARN` and `ERR`. These are display-only changes; Loguru filtering
  continues to use the native `WARNING` and `ERROR` severities.
- The source location and message are separated with ` | ` instead of ` - `.

### Migration

Before upgrading, operators should update log-parser patterns to accept
whole-second timestamps, the `WARN` and `ERR` display labels, and pipe
separators. Alerting rules should continue matching native severity values when
they consume structured Loguru records.
