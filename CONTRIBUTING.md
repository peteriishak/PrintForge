# Contributing to PrintForge

Thanks for your interest in improving PrintForge. Bug reports, feature ideas, documentation fixes and
code are all welcome.

## Reporting a bug

Open an issue at <https://github.com/peteriishak/PrintForge/issues> and include:

- What you did, what you expected, and what happened instead
- Your distribution and version, and the libadwaita version (`rpm -q libadwaita` or `dpkg -l libadwaita-1-0`)
- The printer model and how it is connected (USB, network, driverless/IPP Everywhere) if the problem is printer-related
- The output of `printforge --debug` (or `python3 -m printforge --debug`) while reproducing the problem

Please remove anything private from logs before posting, such as printer IP addresses, host names or file names.

## Suggesting a feature

Open an issue describing the problem you want solved, not only the solution. Screenshots or mock-ups help.

## Working on the code

1. Fork the repository and create a branch from `main`.
2. Install the system packages listed in the [README](README.md#requirements), plus `python3-pytest`.
3. Run the app from the source tree with `python3 -m printforge --mock` to use demo printers.
4. Make your change, and add or update tests in `tests/` where it makes sense.
5. Run the test suite: `python3 -m pytest`. All tests must pass.
6. Open a pull request that explains what changed and why.

### Guidelines

- Keep changes focused: one fix or feature per pull request.
- Follow the existing style: PEP 8, type hints, and short docstrings on public functions.
- User-facing text should be short, plain and free of jargon. Follow the
  [GNOME Human Interface Guidelines](https://developer.gnome.org/hig/) for UI work.
- Prefer the GNOME platform (GTK, libadwaita, GLib) and existing system libraries over new dependencies.
- Never commit secrets, credentials or personal data.

## License

By contributing, you agree that your contributions are licensed under the
[GNU General Public License v3.0 or later](LICENSE), the same license as the project.
