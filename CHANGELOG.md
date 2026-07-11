# Changelog

Notable user-facing changes to `second-brain` are documented here.

## Unreleased

### Changed

- Console and file logs now use whole-second timestamps without milliseconds.
- Log level padding was removed, and the displayed `WARNING` and `ERROR` labels
  changed to `WARN` and `ERR`.
- The source location and message are separated with ` | ` instead of ` - `.
- Rotated log files are retained for one week.

Users who parse log output should update their patterns for the new timestamp,
level-label, and separator formats before upgrading.
