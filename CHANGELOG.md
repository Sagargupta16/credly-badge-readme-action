# Changelog

## [1.3.0] - 2026-10-18

### Added

- `svg-mobile-path`: with `output: svg` or `both`, also write a 340px phone card for a `<picture>` source. GitHub draws a README 309px wide on a 375px phone, which shrinks the 840px card to 37% and its badge labels to 3.1px; the phone card is drawn at 91% there, with 10px labels (measured 2026-10-18 by `scripts/phone-preview.py`). It lays certifications out three a row and other badges four a row, with labels of up to three and four lines, and draws badges at the 840px card's default sizes, so both cards share every downloaded image. Empty by default, so nothing changes unless it is set.
- `hide-expired`, `sort` and `max-badges` choose the badges, in README mode and both cards alike: drop badges past their `expires_at_date`, order by `issued_at_date` (`newest` or `oldest`; the default `credly` keeps the profile order) and keep the first N. With the defaults the README section and the card are byte-identical to 1.2.1.
- `commit` and `commit-message`: `commit: true` commits only the files the action wrote, as `github-actions[bot]`, when one of them changed, and pushes. Off by default.
- `examples/credly-badges-mobile.svg`, the phone card of the same 22-badge profile (126,085 bytes), and `docs/phone-preview.webp`, both cards at a phone's README width.
- `scripts/phone-preview.py` measures GitHub's README width on a 375px phone and redraws the preview.
- CI's SVG-mode run also writes the phone card and fails unless it is 340px wide with every image WebP.
- Tests for badge selection, the phone layout, image sharing between the two cards, input validation and `commit: true` against a local bare remote.
- README: the card at the top (the phone card on phones), a CI badge, a comparison with pemtajo/badge-readme and credly-readme-stats, and sections for the phone card, choosing badges and letting the action commit.

### Changed

- `total-badges` counts the badges written, after `hide-expired` and `max-badges`. Without those inputs it is the same number as before.

## [1.2.1] - 2026-10-18

### Fixed

- Profiles with more than 48 badges are no longer cut off. Credly serves `badges.json` 48 badges a page, and the script read only the first one; it now follows `metadata.next_page_url` to the last page, in README and SVG mode alike, so `total-badges` counts every badge. Only page links under `https://www.credly.com/users/` are followed.
- A wrong username stops at once with `Credly user '<name>' not found (404). Use the slug from your profile URL.` instead of retrying for 15 seconds and ending in a raw `HTTPError` traceback. Other 4xx responses are not retried either; timeouts, `429` and `5xx` still are.

### Changed

- The action installs `pillow==13.0.0` (was `12.3.0`) for SVG mode. The card renders different bytes with it, so SVG-mode consumers get one card commit on their first run after upgrading; after that the same badges give the same bytes again. The 22-badge example card goes from 124,291 to 124,099 bytes, identical on the Windows and Linux wheels. README mode is unchanged and still installs nothing.
- `examples/credly-badges.svg` re-rendered with `pillow==13.0.0`.
- CI pins `ruff==0.17.1` (was `0.16.6`); the tree passes unchanged.
- CI's `GITHUB_TOKEN` is limited to `contents: read`. No job writes; the three open CodeQL `actions/missing-workflow-permissions` alerts flagged the missing block.

### Added

- Tests for following a second page and for stopping on a 404 without a retry.
- README: a flow diagram in How It Works, a Design Decisions section, a Used by list, and an up-to-date Live Example. The Outputs note now says the empty outputs were a `v1.0.0`-only bug.

## [1.2.0] - 2026-10-11

### Changed

- The SVG card inlines its badge images as WebP (quality 85, method 6, alpha channel lossless) instead of optimized PNG. Images are still shrunk to twice their drawn size, so they stay sharp on high-density screens and transparent corners stay transparent. The 22-badge example card drops from 390,601 bytes to 124,291, under a third of its size. No new dependency: the pinned `pillow==12.3.0` wheel the action already installs writes WebP. README mode is unchanged.
- The same badges still give the same bytes on every run, so `git diff` stays an exact change check. Expect one card commit on the first run after upgrading, since every image is re-encoded.
- Fallbacks are kept: a Pillow built without WebP support inlines the optimized PNG as before, and without Pillow the original image is inlined unchanged.
- `examples/credly-badges.svg` re-rendered with WebP images, which also brings in the 1.1.1 label fix.
- CI's SVG-mode run of the action fails unless every badge image in the card is WebP.

### Added

- Tests for the WebP image path (format, size, transparency, same bytes twice) and both PNG fallbacks. The ones that need Pillow skip where it is not installed.

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
