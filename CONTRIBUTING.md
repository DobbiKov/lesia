# Contributing

Before contributing, make sure to read [the profound
explanation](./docs/tool-profound-explanation.md) in order to understand how
the tool work and its idea.

If you want to contribute but don't know what to start with, read the issues
page, all the tickets and changes are stored there.

All pull requests, ideas and suggestions are welcome!

## Logging and CLI output

This project standardizes diagnostics on Loguru and keeps user-facing CLI output as prints:

- **Default CLI behavior**: show user-facing `print` output plus Loguru warnings/errors on stderr.
- **Verbose mode (`--verbose` / `-v`)**: show both `print` output and all Loguru logs (including debug/trace).

Conventions:

- Use `print` only for user-facing CLI messages (results, progress, prompts).
- Use `loguru.logger` for diagnostics (debug/info/warn/error, stack traces, internal state).
- Library code should not configure Loguru; the CLI entrypoint wires log sinks and verbosity.
