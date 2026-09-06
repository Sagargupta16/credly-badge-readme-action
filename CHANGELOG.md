# Changelog

## [Unreleased]

Everything below is on `main` but not yet released. The `v1` and `v1.0.0` tags both
still point at the initial commit, so consumers on `@v1` are running the 2026-03-04
code and none of the fixes listed below have reached them.

### Fixed

- Composite action outputs (`total-badges`, `certifications-count`, `professional-count`, `knowledge-count`, `changed`) were declared without the required `value:` mapping, so every one of them resolved to an empty string. Consumers gating a commit step on `steps.<id>.outputs.changed == 'true'` never ran it.
- HTML-escape all Credly-supplied badge names and URLs before interpolating them into the README (2026-07-03).
- Treat badge content as literal text in the `re.subn` replacement, so backslash sequences in a badge name are no longer read as regex backreferences (2026-07-01).
- Skip the "Industry Certifications" heading when no badge matches the certification keywords, instead of emitting the heading above an empty `<div>`.
- Sort imports so `ruff check .` passes under ruff 0.16.6, whose default ruleset added isort.

### Changed

- Upgrade the Python that the action installs from 3.11 to 3.13 (2026-03-16).

### Added

- Unit test suite for the pure functions, no network required (2026-07-03).
- CI workflow running ruff and pytest (2026-07-04), now with a pinned ruff version, an explicit `ruff.toml` ruleset, and a Python 3.12/3.13/3.14 test matrix.
- README sections covering troubleshooting, non-AWS categorization keywords, version pinning, and local development.

## [1.0.0] - 2026-03-04

Initial release, published as tag `v1.0.0` (and `v1`).

- GitHub Action for Credly badge auto-sync
- Fetches badges from Credly API, categorizes, generates HTML
- Supports custom badge sizing, categories, and README markers
- Installs Python 3.11

An earlier revision of this file listed these same changes as `0.1.0` and described
`1.0.0` as the Python 3.13 upgrade dated 2026-03-16. No `0.1.0` tag was ever
published, and the 3.13 upgrade landed after `v1.0.0` was tagged, so the entries
above and under Unreleased reflect what each tag actually contains.
