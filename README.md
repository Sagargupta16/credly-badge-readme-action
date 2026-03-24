# Credly Badge README Updater

**Auto-sync your Credly certifications and badges to your GitHub profile README.**

No more manually updating badge images when you earn a new certification. This Action fetches your badges from Credly's public API and updates your README automatically.

---

## Features

- Fetches all badges from your Credly profile automatically
- Categorizes badges into **Industry Certifications**, **Professional/Partner**, and **Knowledge/Learning**
- Updates your README between markers (non-destructive -- only touches the badge section)
- Dark/light theme support via Credly CDN
- Configurable badge size, retry logic, and categorization keywords
- Outputs badge counts for use in downstream workflow steps

## Quick Start

### 1. Add markers to your README

Add these two HTML comments where you want your badges to appear:

```markdown
## Certifications

<!-- CREDLY-BADGES:START -->
<!-- CREDLY-BADGES:END -->
```

### 2. Create the workflow

Create `.github/workflows/update-credly-badges.yml`:

```yaml
name: Update Credly Badges

on:
  schedule:
    - cron: "0 9 * * 1" # Every Monday at 9 AM UTC
  workflow_dispatch:

permissions:
  contents: write

jobs:
  update-badges:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Update Credly badges
        uses: Sagargupta16/credly-badge-readme-action@v1
        with:
          credly-username: "your-credly-username"

      - name: Commit changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add README.md
          if ! git diff --cached --quiet; then
            git commit -m "chore: update Credly badges"
            git push
          fi
```

### 3. Find your Credly username

Go to your [Credly profile](https://www.credly.com/users/me) and copy the username from the URL:
```
https://www.credly.com/users/YOUR-USERNAME-HERE
```

That's it. Your badges will auto-update every Monday.

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `credly-username` | Yes | - | Your Credly username from your profile URL |
| `readme-path` | No | `README.md` | Path to your README file |
| `badge-size` | No | `100` | Badge image size in pixels |
| `max-retries` | No | `3` | Max retry attempts for Credly API calls |
| `cert-keywords` | No | `Certified` | Comma-separated keywords to identify industry certifications |
| `professional-keywords` | No | `Partner: Technical,...` | Comma-separated keywords for professional/partner badges |

## Outputs

| Output | Description |
|--------|-------------|
| `total-badges` | Total number of badges found |
| `certifications-count` | Number of industry certifications |
| `professional-count` | Number of professional/partner badges |
| `knowledge-count` | Number of knowledge/learning badges |
| `changed` | Whether the README was updated (`true`/`false`) |

## Example Output

The action generates categorized badge sections like this:

**Industry Certifications**

<div align="center">
<img src="https://images.credly.com/size/80x80/images/0e284c3f-5164-4b21-8660-0d84737941bc/image.png" width="80" height="80" alt="AWS Solutions Architect">
<img src="https://images.credly.com/size/80x80/images/b9feab85-1a43-4f6c-99a5-631b88d5461b/image.png" width="80" height="80" alt="AWS Developer">
<img src="https://images.credly.com/size/80x80/images/0dc62494-dc94-469a-83af-e35309f27356/blob" width="80" height="80" alt="Terraform Associate">
</div>

**Professional & Partner Badges**

<div align="center">
<img src="https://images.credly.com/size/80x80/images/b870667f-00a3-48d7-b988-9c02b441b883/image.png" width="80" height="80" alt="Well-Architected">
<img src="https://images.credly.com/size/80x80/images/a5e0f58e-77c2-452d-b81d-79981315f238/blob" width="80" height="80" alt="GenAI Technical">
</div>

**Knowledge & Learning Badges**

<div align="center">
<img src="https://images.credly.com/size/80x80/images/7cf036b0-c609-4378-a7be-9969e1dea7ab/blob" width="80" height="80" alt="Cloud Essentials">
<img src="https://images.credly.com/size/80x80/images/519a6dba-f145-4c1a-85a2-1d173d6898d9/image.png" width="80" height="80" alt="Architecting">
</div>

## Advanced Usage

### Custom categorization

Override how badges are categorized using keywords matched against the badge name:

```yaml
- uses: Sagargupta16/credly-badge-readme-action@v1
  with:
    credly-username: "your-username"
    cert-keywords: "Certified,Professional"
    professional-keywords: "Partner,Proficient,Associate"
```

### Conditional commit (only when changed)

```yaml
- name: Update Credly badges
  id: credly
  uses: Sagargupta16/credly-badge-readme-action@v1
  with:
    credly-username: "your-username"

- name: Commit if changed
  if: steps.credly.outputs.changed == 'true'
  run: |
    git config user.name "github-actions[bot]"
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
    git add README.md
    git commit -m "chore: update ${{ steps.credly.outputs.total-badges }} Credly badges"
    git push
```

### Use badge counts in other steps

```yaml
- name: Update Credly badges
  id: credly
  uses: Sagargupta16/credly-badge-readme-action@v1
  with:
    credly-username: "your-username"

- name: Summary
  run: |
    echo "Found ${{ steps.credly.outputs.total-badges }} badges:"
    echo "  Certifications: ${{ steps.credly.outputs.certifications-count }}"
    echo "  Professional:   ${{ steps.credly.outputs.professional-count }}"
    echo "  Knowledge:      ${{ steps.credly.outputs.knowledge-count }}"
```

## Live Example

See this action in use on [@Sagargupta16's profile README](https://github.com/Sagargupta16/Sagargupta16#certifications--badges) -- 6x AWS Certified badges auto-synced weekly.

## How It Works

1. Fetches badges from `https://www.credly.com/users/{username}/badges.json`
2. Categorizes each badge based on its name (using configurable keywords)
3. Generates HTML with linked badge images from Credly's CDN
4. Replaces content between `<!-- CREDLY-BADGES:START -->` and `<!-- CREDLY-BADGES:END -->` markers in your README
5. Reports badge counts via action outputs

## License

MIT
