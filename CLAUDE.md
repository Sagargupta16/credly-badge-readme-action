# CLAUDE.md

> This file stacks on top of the workspace root at `C:\Code\GitHub\`:
> - Root [`CLAUDE.md`](../../CLAUDE.md) -- voice, rules, routing map, references, skills, slash commands, conventions.
> - Root [`MEMORY.md`](../../MEMORY.md) -- live facts across repos.
> - Root [`STATUS.md`](../../STATUS.md) -- live PR/CI/security dashboard.
> - [`.claude/resources/`](../../.claude/resources/README.md) -- deep reference for collaboration, workflow, git, OSS, debugging, voice.
>
> Read those first. The guidance below only adds **repo-specific context** -- it does not override anything in the root.

## Project

Composite GitHub Action that auto-syncs Credly certifications/badges into a profile README between `<!-- CREDLY-BADGES:START/END -->` markers.

Published as `Sagargupta16/credly-badge-readme-action@v1`; runs live on Sagar's profile README via weekly cron.

## Stack

- **Language**: Python 3.13, stdlib only (no third-party deps)
- **Framework**: GitHub Actions composite action (`action.yml`)
- **Database**: none
- **Package manager**: none (nothing to install)
- **Deploy target**: consumed via `uses:` in other repos' workflows; releases are git tags

## Run

```
CREDLY_USERNAME=<credly-username> python update-credly-badges.py
```

Needs a `README.md` with the CREDLY-BADGES markers in cwd (or set `README_PATH`).

## Test

No test suite. Verify by running the script standalone against a scratch README containing the markers, then eyeball the generated HTML.

## Entry points

- `action.yml` -- action contract: inputs/outputs, sets up Python 3.13, maps inputs to env vars, runs the script
- `update-credly-badges.py` -- entire logic: fetch badges JSON, categorize, generate HTML, splice into README, write `$GITHUB_OUTPUT`

## Key files

- `update-credly-badges.py` -- the whole action lives in this one script
- `action.yml` -- env var names here must match the `os.environ` reads in the script

## Gotchas

- Adding an input means touching three places in sync: `action.yml` inputs, `action.yml` env block, and the env read in the script.
- `v1` is a moving major tag. After cutting a new `v1.x.y`, retag: `git tag -f v1 && git push -f origin v1`, and update `CHANGELOG.md`.
- Badge names/URLs from the Credly API are `html.escape()`d before interpolation -- untrusted data, keep it.
- `update_readme` uses `re.subn` with a lambda replacement so backslashes in badge content are literal, not backreferences. Don't "simplify" it away.
- `MAX_RETRIES <= 0` is intentionally clamped to 1 attempt in `fetch_badges`.
- Data source is the undocumented public endpoint `https://www.credly.com/users/{username}/badges.json` (`{"data": [...]}` shape). If it breaks, that endpoint changed.

## Repo-specific rules

- Keep the script stdlib-only. `action.yml` has no dependency-install step, so any third-party import silently breaks every consumer.

## Usage

- In a workflow: `uses: Sagargupta16/credly-badge-readme-action@v1` with `credly-username` input; consumer workflow commits the README change itself (see README examples).
- Standalone: `CREDLY_USERNAME=<u> python update-credly-badges.py`.

## Config

- No config file. Everything flows action input -> env var -> script: `CREDLY_USERNAME` (required), `README_PATH`, `BADGE_SIZE`, `MAX_RETRIES`, `CERT_KEYWORDS`, `PROFESSIONAL_KEYWORDS`.
- Categorization is keyword-substring match against `badge_template.name`; cert keywords win over professional, remainder is knowledge.
