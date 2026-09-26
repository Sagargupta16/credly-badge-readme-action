# Changelog

## [1.1.1] - 2026-09-26

### Fixed

- SVG card labels drop the word "Badge". It said nothing under a badge and could push the real name past the label's last line: "Claude Partner Badge - Claude Code" showed as "CLAUDE PARTNER / BADGE CLAUDE" and now shows "CLAUDE PARTNER / CLAUDE CODE". README mode is unchanged.

## [1.1.0] - 2026-09-25

The first release since `1.0.0`, so besides SVG card mode it ships every fix made after
that tag.

### Added

- SVG card mode. The new `output` input (`readme`, `svg` or `both`; default `readme`) draws every badge into one self-contained, animated SVG card at `svg-path` (default `assets/credly-badges.svg`), grouped by the existing `cert-keywords` and `professional-keywords` categorization. `svg-groups` picks `two` groups (industry certifications, then every other badge as learning and partner badges; the default) or the README's `three`, `svg-per-row` sets the badges per row for each group (default `6,8`), and `accent` colors the group labels. The design is the Credly card on @Sagargupta16's profile README.
- Badge images for the card are downloaded from `images.credly.com` only and inlined as data URIs, so the SVG loads nothing external. When Pillow is importable, each image is shrunk to twice its drawn size; `action.yml` installs a pinned `pillow==12.3.0` wheel for that, and only when `output` is not `readme`.
- En and em dashes in badge titles become plain hyphens in the card. README mode keeps titles exactly as Credly sends them.
- `examples/credly-badges.svg`, rendered from a live Credly profile.
- CI runs the action a second time with `output: svg` and fails unless the card parses as XML.
- Tests for the card (grouping, per-row wrapping, dash normalization, escaping, XML validity) and a frozen-output test that pins README mode byte for byte.
- Unit test suite for the pure functions, no network required (2026-07-03).
- CI workflow running ruff and pytest (2026-07-04), now with a Python 3.12/3.13/3.14 test matrix and pinned tool versions.
- CI job that runs `action.yml` from the checkout against a scratch README and fails if any declared output resolves to an empty string. Nothing else in CI loads `action.yml`.
- README sections covering troubleshooting, categorization behavior, version pinning, and local development.

### Changed

- `action.yml` sets up Python with `actions/setup-python@v6` (was `v5`), matching CI.
- The `changed` output is also `true` when the SVG card was rewritten.
- Upgrade the Python that the action installs from 3.11 to 3.13 (2026-03-16).

### Fixed

- Composite action outputs (`total-badges`, `certifications-count`, `professional-count`, `knowledge-count`, `changed`) were declared without the required `value:` mapping, so every one of them resolved to an empty string. Consumers gating a commit step on `steps.<id>.outputs.changed == 'true'` never ran it.
- HTML-escape all Credly-supplied badge names and URLs before interpolating them into the README (2026-07-03).
- Treat badge content as literal text in the `re.subn` replacement, so backslash sequences in a badge name are no longer read as regex backreferences (2026-07-01).
- Skip the "Industry Certifications" heading when no badge matches the certification keywords, instead of emitting the heading above an empty `<div>`.
- Sort imports so `ruff check .` passes under ruff 0.16.0 and later, whose default ruleset grew from 59 rules to 413 and now flags the unsorted stdlib imports as `I001`.
- Record `update-credly-badges.py` as mode 100755 in git, so the shebang it carries is actually usable on checkout (`EXE001`).

## [1.0.0] - 2026-03-04

Initial release, published as tag `v1.0.0` (and `v1`).

- GitHub Action for Credly badge auto-sync
- Fetches badges from Credly API, categorizes, generates HTML
- Supports custom badge sizing, categories, and README markers
- Installs Python 3.11

An earlier revision of this file listed these same changes as `0.1.0` and described
`1.0.0` as the Python 3.13 upgrade dated 2026-03-16. No `0.1.0` tag was ever
published, and the 3.13 upgrade landed after `v1.0.0` was tagged, so the entries
above and under 1.1.0 reflect what each tag actually contains.
