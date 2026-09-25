# CLAUDE.md

> This file stacks on top of the workspace root at `C:\Code\GitHub\`:
> - Root [`CLAUDE.md`](../../CLAUDE.md) -- voice, rules, routing map, references, skills, slash commands, conventions.
> - Root [`MEMORY.md`](../../MEMORY.md) -- live facts across repos.
> - Root [`STATUS.md`](../../STATUS.md) -- live PR/CI/security dashboard.
> - [`.claude/resources/`](../../.claude/resources/README.md) -- deep reference for collaboration, workflow, git, OSS, debugging, voice.
>
> Read those first. The guidance below only adds **repo-specific context** -- it does not override anything in the root.

## Project

Composite GitHub Action that auto-syncs Credly certifications/badges into a profile README between `<!-- CREDLY-BADGES:START/END -->` markers. The `output` input picks the mode: `readme` (the default, the original behavior), `svg` (one self-contained animated SVG card of every badge, written to `svg-path`), or `both`.

Published as `Sagargupta16/credly-badge-readme-action@v1`; runs live on Sagar's profile README via weekly cron.

## Stack

- **Language**: Python 3.13, stdlib only; Pillow is optional and only SVG mode uses it
- **Framework**: GitHub Actions composite action (`action.yml`)
- **Database**: none
- **Package manager**: none; `action.yml` pip-installs a pinned `pillow==12.3.0` wheel only when `output` is not `readme`
- **Deploy target**: consumed via `uses:` in other repos' workflows; releases are git tags

## Run

```
CREDLY_USERNAME=<credly-username> python update-credly-badges.py
```

Needs a `README.md` with the CREDLY-BADGES markers in cwd (or set `README_PATH`). SVG mode needs no README; with Pillow it renders exactly like the action:

```
CREDLY_USERNAME=<credly-username> OUTPUT=svg SVG_PATH=/tmp/card.svg uv run --no-project --with pillow==12.3.0 python update-credly-badges.py
```

`examples/credly-badges.svg` (linked from the README) was rendered that way from `sagar-gupta.f8eb96cc`; rerun it to refresh the preview.

## Test

```
uv run --with pytest python -m pytest -v
uv run --with ruff ruff check .
```

`test_update_credly_badges.py` covers the pure functions (categorization, HTML escaping, marker splicing, empty-category skipping), the SVG card (grouping, per-row wrapping, dash normalization, escaping, XML validity) and `main()` in each mode, with every fetch stubbed. `FROZEN_SECTION` there is README mode's output captured before SVG mode existed (main at 92ca53e): if that test fails, README mode changed for every consumer. `.github/workflows/ci.yml` has three jobs, on every push to `main` and every PR: `lint` (ruff, Python 3.13 only), `test` (pytest, matrixed over 3.12/3.13/3.14 -- 3.13 is the version `action.yml` installs for consumers), and `action`, which is the only job that loads `action.yml`: it runs the composite action from the checkout against a scratch README and fails if any of the five outputs comes back empty or if a step gated on `changed` gets skipped, then runs it again with `output: svg` and fails unless the card parses as XML. That second run is the only place the Pillow install step and the live badge-image fetch execute.

`ruff==0.16.6` and `pytest==9.1.1` are pinned inline in `ci.yml`, and `pillow==12.3.0` in `action.yml`, so a tool release cannot turn an unchanged tree red: ruff 0.16.0 grew its default ruleset from 59 rules to 413, which flagged `I001` on an unchanged import block here. Bump them by hand; Renovate's github-actions manager reads `uses:`/`with:`/`container:`/`services:`/`runs-on:`, not `run:` text. A `requirements-dev.txt` does not work here either: SonarCloud rule `githubactions:S8544` fails the quality gate when the installed versions are not visible at the `pip install` site (measured on PR #8).

There is deliberately no `ruff.toml`: an earlier one cut enforcement from ruff's 413 default rules to 100, and the tree passes the full default set anyway. That narrowing hid a real finding, `EXE001` on the script's shebang, which is why `update-credly-badges.py` is mode 100755 in git.

For an end-to-end check by hand, run the script standalone against a scratch README containing the markers, then eyeball the generated HTML.

## Entry points

- `action.yml` -- action contract: inputs/outputs, sets up Python 3.13, installs Pillow unless `output` is `readme`, maps inputs to env vars, runs the script
- `update-credly-badges.py` -- entire logic: fetch badges JSON, categorize, generate HTML, splice into README, render the SVG card, write `$GITHUB_OUTPUT`

## Key files

- `update-credly-badges.py` -- the whole action lives in this one script
- `action.yml` -- env var names here must match the `os.environ` reads in the script

## Gotchas

- Adding an input means touching three places in sync: `action.yml` inputs, `action.yml` env block, and the env read in the script.
- `v1` is a moving major tag. After cutting a new `v1.x.y`, retag: `git tag -f v1 && git push -f origin v1`, and update `CHANGELOG.md`.
- This retag has never actually been run. As of 2026-09-06 both `v1` and `v1.0.0` still dereference to the initial commit `53428cd` (2026-03-04), so consumers on `@v1` get Python 3.11, no `html.escape()`, and empty action outputs. Every fix since then is unreleased -- see `CHANGELOG.md` under Unreleased.
- Moving the `v1` tag does not reach the one known consumer. `Sagargupta16/Sagargupta16/.github/workflows/update-credly-badges.yml` pins `@53428cd4bf0496ade08bbc52632b6f540b029af0 # v1`, so a release means three steps: tag `v1.x.y`, move `v1`, then re-pin that workflow to the new SHA. Confirmed broken there on 2026-09-06: run 33414078659 (2026-08-31) logged "README updated with latest Credly badges." and "Changes detected:", while its commit step, gated on `steps.credly.outputs.changed == 'true'`, was skipped.
- Composite action outputs need an explicit `value:` mapping plus an `id:` on the step that writes `$GITHUB_OUTPUT`. Declaring only a `description` makes every output silently resolve to an empty string.
- Badge names/URLs from the Credly API are `html.escape()`d before interpolation -- untrusted data, keep it.
- `update_readme` uses `re.subn` with a lambda replacement so backslashes in badge content are literal, not backreferences. Don't "simplify" it away.
- `MAX_RETRIES <= 0` is intentionally clamped to 1 attempt in `fetch_badges`.
- Data source is the undocumented public endpoint `https://www.credly.com/users/{username}/badges.json` (`{"data": [...]}` shape). If it breaks, that endpoint changed.
- The SVG card design is copied from `brand/Sagargupta16/scripts/render-svgs.py` (`render_certs`). With default inputs the markup is byte-identical to that script's `assets/svg/certs.svg` apart from the image payloads and a trailing newline (checked 2026-09-25); change both together or note the divergence.
- The card fetches each badge's original `image_url`, not a `size/NxN` URL: the Credly CDN serves a resized image only for some sizes, differently per badge, and 302s every other size to the original (measured 2026-09-25: sizes 110, 160, 220 and 340 across all 22 badges of the profile above). Pillow then shrinks each image to twice its drawn size (84 and 58 px drawn): about 390 KB for 22 badges, against 1.26 MB without Pillow.
- Badge images are fetched only from `https://images.credly.com/` (`badge_data_uri` refuses anything else), since the URLs come from the API. Keep the check: urllib would also open a `file://` URL.
- The Pillow install in `action.yml` must stay a YAML block scalar (`run: |`): a bare `:all:` in a plain scalar parses as a mapping. Renovate does not read the pin there; bump it by hand.
- SVG output is deterministic for a given Pillow version, which is what makes `git diff` a valid change check for consumers. Anything time- or order-dependent in `render_svg` would break that.

## Repo-specific rules

- Keep README mode stdlib-only. The one third-party import is Pillow, inside `downscale()` behind `except ImportError`, and `action.yml` installs it only when `output` is not `readme`; any other third-party import silently breaks every consumer.

## Usage

- In a workflow: `uses: Sagargupta16/credly-badge-readme-action@v1` with `credly-username` input; consumer workflow commits the README change itself (see README examples). Add `output: svg` (or `both`) for the card; the README's SVG example commits it on `git diff`.
- Standalone: `CREDLY_USERNAME=<u> python update-credly-badges.py` (add `OUTPUT=svg` for the card).

## Config

- No config file. Everything flows action input -> env var -> script: `CREDLY_USERNAME` (required), `README_PATH`, `BADGE_SIZE`, `MAX_RETRIES`, `CERT_KEYWORDS`, `PROFESSIONAL_KEYWORDS`, `OUTPUT`, `SVG_PATH`, `SVG_GROUPS`, `SVG_PER_ROW`, `ACCENT`.
- Categorization is keyword-substring match against `badge_template.name`; cert keywords win over professional, remainder is knowledge. The SVG card reuses it: `svg-groups: two` merges professional and knowledge into one "Learning and partner badges" group, `three` keeps all three.
- SVG inputs are validated only when `output` is not `readme`, before any network call: `svg-groups` two or three, `svg-per-row` whole numbers 1 to 12 (`MAX_PER_ROW`), `accent` a 3- or 6-digit hex color with or without `#`.
