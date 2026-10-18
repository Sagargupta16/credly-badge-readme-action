# Contributing to credly-badge-readme-action

This repo is a composite GitHub Action that syncs Credly badges into a README section or a self-contained SVG card. Bug reports, fixes, doc corrections and new inputs that come with tests are welcome.

## Setup

README mode is Python standard library only, so the action itself needs no install. Lint and tests run with `uv` locally; CI uses pip with pinned versions. SVG mode optionally uses `pillow==13.0.0`.

## Before you open a PR

CI (`.github/workflows/ci.yml`) runs three jobs on every push to `main` and every pull request:

- `lint`: `pip install --only-binary :all: ruff==0.17.1`, then `ruff check .` on Python 3.13
- `test`: `pip install --only-binary :all: pytest==9.1.1`, then `pytest -v` on Python 3.12, 3.13 and 3.14
- `action`: runs `action.yml` from the checkout against a live Credly profile, fails if any of the five outputs is empty or a step gated on `changed` is skipped, then runs again with `output: svg` and fails unless the card parses as XML with every badge image inlined as WebP

Run the first two locally. The `test` job installs no Pillow, so its five Pillow tests (the WebP image path) skip there; the second pytest line runs them:

```bash
uvx ruff@0.17.1 check .
uv run --no-project --with pytest==9.1.1 pytest -v
uv run --no-project --with pytest==9.1.1 --with pillow==13.0.0 pytest -v
```

The `action` job only runs on GitHub. To exercise the script by hand without touching a real README:

```bash
printf '<!-- CREDLY-BADGES:START -->\n<!-- CREDLY-BADGES:END -->\n' > scratch.md
CREDLY_USERNAME=<your-credly-username> README_PATH=scratch.md python update-credly-badges.py
CREDLY_USERNAME=<your-credly-username> OUTPUT=svg SVG_PATH=card.svg uv run --no-project --with pillow==13.0.0 python update-credly-badges.py
```

Do not commit `scratch.md` or `card.svg`.

## Conventions

- Tests live in `test_update_credly_badges.py` at the repo root and stub every network fetch. The `commit: true` tests need `git` on `PATH`; they push to a bare remote in a temporary folder. Add tests there for any new behavior.
- `FROZEN_SECTION` in the tests pins README mode's output byte for byte. If that test fails, README mode changed for every consumer.
- A new input touches three places in sync: `inputs` in `action.yml`, the `env` block of the `run-updater` step, and the `os.environ` read in `update-credly-badges.py`. Add it to the README Inputs table too.
- Keep README mode standard library only. Pillow is the one third-party import, inside `downscale()` behind `except ImportError`, and `action.yml` installs it only when `output` is not `readme`.
- Credly data is untrusted: keep `html.escape()` on badge names and URLs, and keep the check that badge images are fetched only from `https://images.credly.com/`.
- SVG output must stay deterministic for a given Pillow version, because consumers use `git diff` as the change check.
- There is no `ruff.toml` on purpose: the tree passes ruff's full default ruleset.
- Tool pins (`ruff` and `pytest` in `ci.yml`, `pillow` in `action.yml`) are bumped by hand. Renovate does not read versions inside `run:` blocks.
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`).
- Add a `CHANGELOG.md` entry under a concrete next version, for example `## [1.1.2] - YYYY-MM-DD`, grouped under `Added`, `Changed` or `Fixed`.

## Security issues

Do not report vulnerabilities in public issues. Follow [SECURITY.md](SECURITY.md).

## License

This project is released under the MIT License (see [LICENSE](LICENSE)). By contributing, you agree that your contributions are licensed under it.
