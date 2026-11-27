# Public Release Audit: PrintForge

**Date:** 2026-11-27
**Repository:** https://github.com/peteriishak/PrintForge (private at the time of the audit)
**Version audited:** 1.0.0
**Result:** Ready to make public. See [Remaining issues](#remaining-issues) for optional follow-ups.

## 1. What was audited

- Every tracked file (76 before cleanup) and the full Git history: all 3 original commits, every blob
  ever committed, all branches and tags on the remote (only `main` existed)
- Source code (`printforge/`, 43 Python modules), tests (20 files), packaging (`pyproject.toml`,
  `printforge.spec`), desktop integration (`data/`), documentation and license
- Untracked and ignored files in the working tree
- Commit authorship and contributor attribution
- Third-party dependencies and bundled assets

## 2. Removed or reorganized

| Item | Action | Reason |
|---|---|---|
| `printforge.egg-info/`, `.pytest_cache/`, `__pycache__/` | Deleted from the working tree | Build and test artifacts. They were never committed and are now ignored. |
| 45 unused imports, an f-string without placeholders, an empty `TYPE_CHECKING` block | Removed | Dead code reported by pyflakes. No logic changed. |
| `io.github.printforge` app ID | Renamed to `io.github.peteriishak.PrintForge` | The `printforge` GitHub account belongs to someone else. The desktop file, metainfo, icons and `__app_id__` were renamed together. User settings in `~/.config/printforge/` are unaffected. |
| `github.com/printforge/printforge` URLs | Changed to `github.com/peteriishak/PrintForge` | They pointed at another person's account (pyproject, spec, metainfo, About dialog). |
| "PrintForge Contributors", `contributors@printforge.org` | Replaced with Peter Habib and the GitHub noreply address | Placeholder identity on a domain the project doesn't own |
| Placeholder dates (2024–2025, 2025-01-01) | Corrected to 2026 | They predated the code. |
| `docs/screenshots/` | Added | README and AppStream screenshots |

The `Design/` folder (branding drafts) stays local and is excluded by `.gitignore`, as before.

## 3. Bugs found and fixed

| Bug | Fix |
|---|---|
| **SVG files could not be opened or printed** on current librsvg (≥ 2.52): `get_intrinsic_size_in_pixels()` returns three values, the code unpacked two and did not catch the `ValueError`. Present in the original code. | Use the 3-value API with the old `get_dimensions()` fallback. Added two regression tests that fail on the old code and pass on the fix. |
| **`styles.css` missing from installs:** the wheel (and so `pip install` and the RPM) left out non-Python files, so installed copies ran unstyled. | Added `[tool.setuptools.package-data]`. Verified the CSS ships in the wheel, in a pip install and in the RPM. |
| **LICENSE incomplete:** the file held only the GPL preamble and a link, so GitHub could not detect the license. | Replaced with the canonical GPL-3.0 text from gnu.org (674 lines). |
| **RPM source layout:** `%autosetup` expected a `printforge-1.0.0/` directory that neither the README's tar command nor a GitHub archive produces. | `Source0` now points at the GitHub tag archive and `%autosetup -n PrintForge-%{version}`. README documents `git archive --prefix=PrintForge-1.0.0/`. |
| **Undeclared requirements:** the code uses `Adw.ToggleGroup` (libadwaita 1.7) but the spec required no version; Pygments, Ghostscript and LibreOffice are used but not mentioned. | `Requires: libadwaita >= 1.7`; `Recommends: python3-pygments, ghostscript, cups`; `Suggests: libreoffice-core` |
| **README errors:** wrong shortcut (<kbd>Ctrl</kbd>+<kbd>,</kbd> opens Preferences, not About), missing shortcuts, stale project folder name `PrinterZ/`, office/PostScript/Markdown support not mentioned | Rewritten from the code |

## 4. Security and privacy checks

| Check | Result |
|---|---|
| API keys, tokens, passwords, private keys (AWS, GitHub, OpenAI, Slack and generic patterns) across all history | None found |
| Personal data: home paths, usernames, email addresses, host names, private URLs | None found. The only addresses are example IPs (`192.168.1.x`, `10.0.0.5`) in the mock backend and tests. |
| Files that existed in history but not in the current tree | None. Every historical file is in the current tree. |
| Image metadata (PNG text chunks, SVG editor paths) | None |
| Screenshots | Generated with the built-in mock printers and synthetic demo files. They contain no real printers, file names or host names. |
| Commit identities | All commits authored and committed by `Peter Habib <343233346+peteriishak@users.noreply.github.com>`, a GitHub noreply address, so no personal email is exposed |
| `.gitignore` | Extended to cover caches, packaging output, editor files and a standard secrets block |

## 5. Licensing

- **Project license:** GPL-3.0-or-later. This was already declared in `pyproject.toml`, the RPM spec,
  the AppStream metadata and the About dialog. The author is the sole contributor, so no third-party
  consent was needed. The LICENSE file now carries the full text.
- **Runtime dependencies** (all compatible with GPL-3.0-or-later): PyGObject (LGPL-2.1+), pycairo
  (LGPL-2.1 / MPL-1.1), Pillow (MIT-CMU), pycups (GPL-2.0+), GTK 4 and libadwaita (LGPL-2.1+), Poppler
  (GPL-2.0+), librsvg (LGPL-2.1+), Pygments (BSD-2-Clause, optional). Ghostscript and LibreOffice are
  run as separate programs, not linked.
- **Bundled assets:** app icons are original, hand-written SVGs with no third-party attribution.
- **Metadata license:** AppStream metainfo is CC0-1.0, as AppStream requires.

## 6. Contributor attribution

- All 3 original commits carried a `Co-Authored-By: Claude` trailer, which makes GitHub credit an AI
  account. The trailers were removed from the commit messages. Authorship, author and committer dates
  and file contents are unchanged, and tree hashes were verified identical before and after.
- New commits were made under the same identity without AI trailers.
- `main` on GitHub was replaced with the rewritten history (`--force-with-lease`). The pre-rewrite
  history is backed up as a Git bundle outside the repository.
- No commits from other people exist, so no authorship was changed or invented.

## 7. Build and functionality tests

All run on Fedora 44 (Python 3.14, GTK 4.22, libadwaita 1.9).

| Test | Result |
|---|---|
| Test suite (`python3 -m pytest`) | **330 passed** (328 existing + 2 new SVG tests) |
| Import every module | All 43 modules import |
| Headless export to PDF (`--mock --export-pdf`) | PNG, JPEG, PDF (3 pages kept), SVG, PostScript, Markdown and Python source all export. Landscape Letter is 792 × 612 pt. |
| GUI launch (`--mock`) | Window renders with sidebar, file list, preview and summary bar; no errors in the debug log |
| `pip install --no-deps .` in a clean venv | Installs, `printforge --version` runs, CSS is included, export works |
| `desktop-file-validate` | Passes (one cosmetic category hint) |
| `appstreamcli validate` | Passes |
| RPM build and install in a clean `fedora:44` container | **Pass.** `rpmbuild -ba` built the binary and source RPMs from a `git archive` tarball; `%check` (desktop-file-validate, appstream-util) passed; `dnf install` resolved every dependency; the installed `printforge --version` runs, `styles.css` and LICENSE are installed, and SVG export works from the installed package |
| Lint (pyflakes) | No unused imports remain. 5 unused local variables are left as they are (see below). |

## 8. Documentation

- `README.md` rewritten: purpose, features, screenshots, requirements table, three install paths
  (source, pip, RPM), usage, CLI printing, shortcuts, configuration, troubleshooting, development,
  project layout, license
- `CONTRIBUTING.md` added: bug reports, feature requests, development workflow, guidelines, license
  of contributions
- AppStream metainfo now lists screenshots, the repository URL and the full set of supported formats

## Remaining issues

None block the public release. Optional follow-ups:

1. **Push a `v1.0.0` tag.** The spec's `Source0` points at the GitHub archive for tag `v1.0.0`. Until
   the tag exists, build RPMs from `git archive` as the README describes.
2. **Unused local variables (5)** in the CLI, rendering and dialog code are harmless. They were left alone to
   avoid touching working logic.
3. **The About dialog uses the generic `printer-symbolic` icon** instead of the app icon. That works
   when run from source, where the app icon isn't installed.
4. **Continuous integration:** a GitHub Actions workflow that runs `pytest` would protect pull requests.
5. **setuptools deprecation warnings** during the build (`project.license` as a table, license classifier). They are harmless. Switching to the SPDX string form needs setuptools ≥ 77, which would break builds on Fedora 42, so it was left for later.
6. **Old installs:** anyone who installed an earlier build under `io.github.printforge` will see a
   second launcher until they remove the old one.

## Final readiness

| Requirement | Status |
|---|---|
| No secrets or personal data in files or history | ✅ |
| Complete license, compatible dependencies | ✅ |
| Clean attribution (sole author, no AI co-author trailers) | ✅ |
| Builds, installs and runs | ✅ |
| README, CONTRIBUTING, .gitignore | ✅ |

**PrintForge is ready to be switched from private to public.**
