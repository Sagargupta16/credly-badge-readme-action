#!/usr/bin/env python3
"""
Credly Badge README Updater
Auto-sync your Credly certifications and badges to your GitHub profile README.

Fetches badges from the Credly public API, categorizes them into
Industry Certifications, Professional/Partner Badges, and Knowledge/Learning Badges,
then updates the README between <!-- CREDLY-BADGES:START --> and <!-- CREDLY-BADGES:END --> markers.
With OUTPUT=svg (or both) it draws every badge into one self-contained,
animated SVG card at SVG_PATH instead (or as well).

Usage as GitHub Action:
  See action.yml for inputs/outputs.

Usage standalone:
  CREDLY_USERNAME=your-username python update-credly-badges.py
  CREDLY_USERNAME=your-username OUTPUT=svg python update-credly-badges.py
"""

from __future__ import annotations

import base64
import html
import io
import json
import os
import re
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from typing import NoReturn

# Configuration from environment
CREDLY_USERNAME = os.environ.get("CREDLY_USERNAME", "")
README_PATH = os.environ.get("README_PATH", "README.md")
BADGE_SIZE = int(os.environ.get("BADGE_SIZE", "100"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
# What to write: readme (the marker section), svg (the card) or both
OUTPUT = os.environ.get("OUTPUT", "readme").strip().lower()
SVG_PATH = os.environ.get("SVG_PATH", "assets/credly-badges.svg")
SVG_GROUPS = os.environ.get("SVG_GROUPS", "two").strip().lower()
SVG_PER_ROW = os.environ.get("SVG_PER_ROW", "6,8")
# the narrow phone card is drawn only when this is set
SVG_MOBILE_PATH = os.environ.get("SVG_MOBILE_PATH", "").strip()
ACCENT = os.environ.get("ACCENT", "#60a5fa")
# Which badges to show, in what order: the defaults keep every badge in profile order
HIDE_EXPIRED = os.environ.get("HIDE_EXPIRED", "false").strip().lower()
SORT = os.environ.get("SORT", "credly").strip().lower()
MAX_BADGES = os.environ.get("MAX_BADGES", "0").strip()
# Commit and push the written files from inside the action
COMMIT = os.environ.get("COMMIT", "false").strip().lower()
COMMIT_MESSAGE = os.environ.get("COMMIT_MESSAGE", "chore: update Credly badges")

# Keywords for badge categorization (comma-separated from env)
CERT_KEYWORDS = [
    k.strip()
    for k in os.environ.get("CERT_KEYWORDS", "Certified").split(",")
    if k.strip()
]
PROFESSIONAL_KEYWORDS = [
    k.strip()
    for k in os.environ.get(
        "PROFESSIONAL_KEYWORDS",
        "Partner: Technical,Generative AI Technical Intermediate,AI Foundational,Well-Architected Proficient",
    ).split(",")
    if k.strip()
]

# GitHub Actions output file
GITHUB_OUTPUT = os.environ.get("GITHUB_OUTPUT", "")

# Every badges.json page, the first and each next_page_url, lives under this prefix
CREDLY_USERS = "https://www.credly.com/users/"


def set_output(name, value):
    """Write a key=value pair to $GITHUB_OUTPUT if running in Actions."""
    if GITHUB_OUTPUT:
        with open(GITHUB_OUTPUT, "a") as f:
            f.write(f"{name}={value}\n")


def fail(message: str) -> NoReturn:
    """Print an error and stop with exit status 1."""
    print(f"ERROR: {message}")
    sys.exit(1)


def fetch_url(url: str, accept: str) -> bytes:
    """GET a URL with retry logic and return the response body."""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "GitHub-Actions-Credly-Badge-Updater/1.0",
        },
    )
    # Always attempt at least once; a non-positive MAX_RETRIES would otherwise
    # skip the loop and return None, crashing later with a cryptic AttributeError.
    attempts = max(1, MAX_RETRIES)
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as e:
            # a 4xx other than 429 (a wrong username is a 404) fails the same way every time
            if (
                isinstance(e, urllib.error.HTTPError)
                and 400 <= e.code < 500
                and e.code != 429
            ):
                raise
            if attempt < attempts - 1:
                wait = 5 * (attempt + 1)
                print(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"ERROR: All {attempts} attempts failed for {url}")
                raise


def fetch_badges(username):
    """Fetch every badge from the Credly public JSON API, one page at a time."""
    url = f"{CREDLY_USERS}{username}/badges.json"
    badges, seen = [], set()
    # Credly serves 48 badges a page and links the next one in metadata.next_page_url
    while url and url not in seen:
        seen.add(url)
        try:
            page = json.loads(fetch_url(url, "application/json").decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                fail(
                    f"Credly user '{username}' not found (404). "
                    "Use the slug from your profile URL."
                )
            raise
        data = page.get("data")
        if not isinstance(data, list):
            fail(f"Unexpected API response format: {type(data)}")
        badges += data
        url = (page.get("metadata") or {}).get("next_page_url")
        # the URL comes from the API response, so only Credly's own pages are followed
        if url and not url.startswith(CREDLY_USERS):
            fail(f"refusing to follow a page URL outside {CREDLY_USERS}: {url}")
    return {"data": badges}


SORTS = ("credly", "newest", "oldest")


def selection_settings() -> tuple[bool, str, int]:
    """Validate the badge selection inputs and return (hide expired, sort, limit)."""
    if HIDE_EXPIRED not in ("true", "false"):
        fail(f"hide-expired must be true or false, got '{HIDE_EXPIRED}'.")
    if SORT not in SORTS:
        fail(f"sort must be credly, newest or oldest, got '{SORT}'.")
    if not re.fullmatch(r"[0-9]+", MAX_BADGES):
        fail(
            f"max-badges must be a whole number, 0 for every badge, got '{MAX_BADGES}'."
        )
    return HIDE_EXPIRED == "true", SORT, int(MAX_BADGES)


def badge_date(badge: dict, key: str) -> date | None:
    """Return one of the badge's ISO date fields, or None when missing or malformed."""
    try:
        return date.fromisoformat(str(badge.get(key) or ""))
    except ValueError:
        return None


def select_badges(
    badges: list[dict], hide_expired: bool, sort: str, limit: int, today: date
) -> list[dict]:
    """Drop expired badges, sort by issue date, then keep the first limit (0 keeps all)."""
    if hide_expired:
        # still valid on its expiry day; a badge without an expiry date never expires
        badges = [
            badge
            for badge in badges
            if (expires := badge_date(badge, "expires_at_date")) is None
            or expires >= today
        ]
    if sort != "credly":
        dated = [b for b in badges if badge_date(b, "issued_at_date")]
        # a stable sort, so badges issued the same day keep their profile order
        dated.sort(
            key=lambda b: badge_date(b, "issued_at_date"), reverse=sort == "newest"
        )
        badges = dated + [b for b in badges if not badge_date(b, "issued_at_date")]
    return badges[:limit] if limit else badges


def categorize_badges(badges):
    """Split badges into certifications, professional, and knowledge categories."""
    certifications = []
    professional = []
    knowledge = []

    for badge in badges:
        template = badge.get("badge_template", {})
        name = template.get("name", "")

        if any(kw in name for kw in CERT_KEYWORDS):
            certifications.append(badge)
        elif any(kw in name for kw in PROFESSIONAL_KEYWORDS):
            professional.append(badge)
        else:
            knowledge.append(badge)

    return certifications, professional, knowledge


def badge_to_html(badge, size=BADGE_SIZE):
    """Generate an HTML anchor+img tag for a single badge."""
    template = badge.get("badge_template", {})
    name = template.get("name", "Badge")
    image_url = template.get("image_url", "")
    badge_id = badge.get("id", "")
    badge_url = f"https://www.credly.com/badges/{badge_id}"

    # Insert size prefix into Credly CDN URL
    sized_url = image_url.replace(
        "images.credly.com/images/",
        f"images.credly.com/size/{size}x{size}/images/",
    )

    # Escape API-supplied values before interpolating into HTML attributes.
    # name/image_url come from the Credly API response (untrusted); an
    # unescaped quote or angle bracket would break out of the tag or corrupt
    # the generated README markup.
    name = html.escape(name)
    badge_url = html.escape(badge_url)
    sized_url = html.escape(sized_url)

    return (
        f'<a href="{badge_url}" title="{name}">'
        f'<img src="{sized_url}" alt="{name}" width="{size}" height="{size}">'
        f"</a>"
    )


def generate_section(certifications, professional, knowledge):
    """Generate the full markdown/HTML for the badges section."""
    lines = []

    # Industry Certifications
    if certifications:
        lines.append("\U0001f3c5 **Industry Certifications**")
        lines.append("")
        lines.append('<div align="center">')
        lines.append("")
        for badge in certifications:
            lines.append(badge_to_html(badge))
        lines.append("")
        lines.append("</div>")

    # Professional & Partner Badges
    if professional:
        if lines:
            lines.append("")
        lines.append("\U0001f396\ufe0f **Professional & Partner Badges**")
        lines.append("")
        lines.append('<div align="center">')
        lines.append("")
        for badge in professional:
            lines.append(badge_to_html(badge))
        lines.append("")
        lines.append("</div>")

    # Knowledge & Learning Badges
    if knowledge:
        if lines:
            lines.append("")
        lines.append("\U0001f4da **Knowledge & Learning Badges**")
        lines.append("")
        lines.append('<div align="center">')
        lines.append("")
        for badge in knowledge:
            lines.append(badge_to_html(badge))
        lines.append("")
        lines.append("</div>")

    return "\n".join(lines)


def update_readme(section_content):
    """Replace content between CREDLY-BADGES markers in README."""
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r"<!-- CREDLY-BADGES:START -->.*?<!-- CREDLY-BADGES:END -->"
    replacement = (
        f"<!-- CREDLY-BADGES:START -->\n{section_content}\n<!-- CREDLY-BADGES:END -->"
    )

    # Use a lambda so backslash sequences in badge content (e.g. \g, \1)
    # are treated as literal text, not regex replacement backreferences.
    new_content, count = re.subn(
        pattern, lambda _: replacement, content, flags=re.DOTALL
    )

    if count == 0:
        print("ERROR: Could not find CREDLY-BADGES markers in README.")
        print("Add these markers to your README where you want badges to appear:")
        print("  <!-- CREDLY-BADGES:START -->")
        print("  <!-- CREDLY-BADGES:END -->")
        sys.exit(1)

    if new_content == content:
        print("No changes detected in badges section.")
        return False

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print("README updated with latest Credly badges.")
    return True


# ---------------------------------------------------------------- SVG card
# The card design comes from Sagargupta16/Sagargupta16 (scripts/render-svgs.py).
# GitHub serves README images through an <img>, which loads nothing external,
# so the card is self-contained: every badge image is inlined as a data URI and
# the animation is CSS and SMIL only.

SVG_WIDTH = 840
SVG_BG = "#0b1012"
MONO = "'JetBrains Mono','SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"
CREDLY_CDN = "https://images.credly.com/"
PNG_MAGIC = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
JPEG_MAGIC = bytes([0xFF, 0xD8, 0xFF])
# en dash (U+2013) and em dash (U+2014), both drawn as a plain hyphen
PLAIN_DASHES = str.maketrans({0x2013: "-", 0x2014: "-"})
MAX_PER_ROW = 12
# (drawn size px, label lines, label font px, label characters per line):
# the first group is drawn large, every group after it small
LARGE = (84, 3, 8.5, 18)
SMALL = (58, 2, 7.5, 16)
# (card width px, group heading font px, first group spec, later groups spec).
# GitHub draws a README 309px wide on a 375px phone (measured 2026-10-18), which
# shrinks the 840px card to 37%. The 340px phone card is drawn at 91% there. It
# draws badges at the desktop card's default sizes, so both share every image.
DESKTOP = (SVG_WIDTH, 10, LARGE, SMALL)
MOBILE = (340, 13, (84, 3, 11, 18), (58, 4, 10, 16))
MOBILE_PER_ROW = [3, 4]
ISSUER_PREFIXES = (
    "AWS Certified ",
    "HashiCorp Certified: ",
    "AWS Knowledge: ",
    "AWS Partner: ",
    "AWS Educate ",
)


def svg_settings() -> tuple[list[int], str]:
    """Validate the SVG inputs and return (badges per row, accent color)."""
    if SVG_GROUPS not in ("two", "three"):
        fail(f"svg-groups must be two or three, got '{SVG_GROUPS}'.")
    if not SVG_PATH.strip():
        fail("svg-path must not be empty.")
    if SVG_MOBILE_PATH and Path(SVG_MOBILE_PATH) == Path(SVG_PATH):
        fail("svg-mobile-path must differ from svg-path.")
    try:
        per_row = [int(n) for n in SVG_PER_ROW.split(",")]
    except ValueError:
        per_row = []
    if not per_row or not all(1 <= n <= MAX_PER_ROW for n in per_row):
        fail(
            "svg-per-row must be comma-separated whole numbers from 1 to "
            f"{MAX_PER_ROW}, got '{SVG_PER_ROW}'."
        )
    accent = ACCENT.strip().removeprefix("#")
    if not re.fullmatch(r"(?:[0-9a-fA-F]{3}){1,2}", accent):
        fail(f"accent must be a hex color such as #60a5fa, got '{ACCENT}'.")
    return per_row, f"#{accent.lower()}"


def svg_groups(
    certifications: list[dict],
    professional: list[dict],
    knowledge: list[dict],
    mode: str,
) -> list[tuple[str, list[dict]]]:
    """Return the card's (label, badges) groups: two, or the README's three."""
    if mode == "three":
        return [
            ("Industry certifications", certifications),
            ("Professional and partner badges", professional),
            ("Knowledge and learning badges", knowledge),
        ]
    return [
        ("Industry certifications", certifications),
        ("Learning and partner badges", professional + knowledge),
    ]


def plain_dashes(text: str) -> str:
    """Return text with en and em dashes replaced by a plain hyphen."""
    return text.translate(PLAIN_DASHES)


def short_badge(title: str) -> str:
    """Drop the issuer prefixes and suffixes that crowd a badge's label."""
    for prefix in ISSUER_PREFIXES:
        title = title.replace(prefix, "")
    title = title.replace(" - Training Badge", "").replace(" - ", " ")
    # the word "Badge" says nothing under a badge and can push the real name past
    # the label's last line ("Claude Partner Badge - Claude Code" lost "Code")
    return " ".join(word for word in title.split() if word != "Badge")


def glyph(font: float) -> float:
    """Return the rough width of one label character at this font size."""
    # a monospace glyph is about 0.6em wide, plus the card's 1px letter-spacing
    return 0.6 * font + 1


def line_step(font: float) -> int:
    """Return the baseline distance between two label lines at this font size."""
    return max(12, round(font * 1.35))


def fit(spec: tuple, per_row: int, width: int = SVG_WIDTH) -> tuple:
    """Shrink a group's badge size and label width to fit per_row columns."""
    size, lines, font, chars = spec
    col = (width - 32) / per_row
    return (
        min(size, int(col) - 16),
        lines,
        font,
        min(chars, int((col - 6) / glyph(font))),
    )


def label_font(line: str, font: float, col: float) -> float:
    """Return the font size for one label line, shrunk if a long word overflows."""
    fitted = ((col - 6) / len(line) - 1) / 0.6
    return font if fitted >= font else round(fitted, 1)


def downscale(raw: bytes, px: int) -> bytes:
    """Return the image shrunk to px square as WebP or PNG, or unchanged without Pillow."""
    try:
        # optional: action.yml installs it unless output is readme
        from PIL import Image, features
    except ImportError:
        return raw
    with Image.open(io.BytesIO(raw)) as source:
        # palette images would resize nearest-neighbour, and CMYK cannot be saved as WebP or PNG
        img = source if source.mode in ("RGB", "RGBA") else source.convert("RGBA")
        img.thumbnail((px, px), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        if features.check("webp"):
            # lossy color, lossless alpha: under a third of the optimized PNG's bytes
            img.save(out, format="WEBP", quality=85, method=6)
        else:
            # a Pillow built without libwebp; the action's pinned wheel always has it
            img.save(out, format="PNG", optimize=True)
    return out.getvalue() if out.tell() < len(raw) else raw


def badge_data_uri(url: str, px: int) -> str:
    """Fetch one badge image from the Credly CDN and return it as a data URI."""
    # the URL comes from the API response, so nothing outside the Credly CDN is fetched
    if not url.startswith(CREDLY_CDN):
        raise ValueError(f"refusing to fetch a badge image outside {CREDLY_CDN}: {url}")
    raw = downscale(fetch_url(url, "image/png,image/jpeg"), px)
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        mime = "image/webp"
    elif raw.startswith(PNG_MAGIC):
        mime = "image/png"
    elif raw.startswith(JPEG_MAGIC):
        mime = "image/jpeg"
    else:
        raise ValueError(f"badge image is neither WebP, PNG nor JPEG: {url}")
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def svg_open(w: int, h: int, label: str) -> str:
    """Return the opening <svg> tag, labelled for screen readers."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{html.escape(label)}">'
    )


def badge_row(
    cells: list[tuple[str, str]],
    top: int,
    delay: float,
    spec: tuple,
    per_row: int,
    width: int = SVG_WIDTH,
) -> list[str]:
    """Return one centered row of floating badges with their wrapped labels."""
    size, lines, font, chars = spec
    col = (width - 32) / per_row
    x0 = 16 + (width - 32 - col * len(cells)) / 2
    step = line_step(font)
    out = []
    for i, (title, image) in enumerate(cells):
        cx = x0 + col * i + col / 2
        label = textwrap.wrap(
            short_badge(title), chars, break_long_words=False, break_on_hyphens=False
        )
        text = "".join(
            f'<text class="m" x="{cx:.1f}" y="{top + size + 16 + j * step}" text-anchor="middle" '
            f'fill="rgba(255,255,255,0.7)" font-size="{label_font(line, font, col)}">'
            f"{html.escape(line.upper())}</text>"
            for j, line in enumerate(label[:lines])
        )
        out.append(
            f'<g opacity="0"><animate attributeName="opacity" to="1" begin="{delay + i * 0.06:.2f}s" '
            'dur="0.5s" fill="freeze"/>'
            f'<g class="float" style="animation-delay:{i * 0.35:.2f}s">'
            f'<image href="{image}" x="{cx - size / 2:.1f}" y="{top}" width="{size}" height="{size}"/>'
            f"</g>{text}</g>"
        )
    return out


def svg_frame(h: int, label: str, w: int = SVG_WIDTH) -> tuple[str, str]:
    """Return the card's opening markup and its closing shine sweep."""
    head = (
        svg_open(w, h, label)
        + f"<style>.m{{font-family:{MONO};font-weight:700;letter-spacing:1px}}"
        ".float{animation:float 4s ease-in-out infinite}"
        "@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}</style>"
        '<defs><linearGradient id="shine" x1="0" x2="1">'
        '<stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset="0.5" stop-color="#fff" stop-opacity="0.14"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        f'<clipPath id="card"><rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="14"/>'
        "</clipPath></defs>"
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="14" fill="{SVG_BG}" '
        'stroke="rgba(255,255,255,0.08)"/>'
    )
    tail = (
        f'<g clip-path="url(#card)"><rect x="-160" y="0" width="120" height="{h}" '
        'fill="url(#shine)" transform="skewX(-20)"><animateTransform attributeName="transform" '
        # the sweep starts left of the card and ends past its right edge
        f'type="translate" values="0 0;{w + 260} 0" dur="6s" repeatCount="indefinite" additive="sum"/>'
        "</rect></g></svg>\n"
    )
    return head, tail


def render_svg(
    groups: list[tuple[str, list[dict]]],
    per_row: list[int],
    accent: str,
    layout: tuple = DESKTOP,
    images: dict | None = None,
) -> str:
    """Return every badge as one self-contained, animated SVG card.

    images caches the data URIs by (URL, drawn size); pass the same dict to a
    second card and an image drawn at the same size is fetched only once.
    """
    width, heading, first, later = layout
    parts, titles = [], []
    images = {} if images is None else images
    y, delay = 34, 0.2
    for i, (label, badges) in enumerate(groups):
        if not badges:
            continue
        # one per_row value per group; the last one repeats for later groups
        count = per_row[min(i, len(per_row) - 1)]
        spec = fit(first if i == 0 else later, count, width)
        size, lines, font = spec[0], spec[1], spec[2]
        cells = []
        for badge in badges:
            template = badge.get("badge_template", {})
            title = plain_dashes(template.get("name", "Badge"))
            url = template.get("image_url", "")
            # fetched once, shrunk to twice the drawn size: sharp on high-density screens
            if (url, size) not in images:
                images[url, size] = badge_data_uri(url, size * 2)
            cells.append((title, images[url, size]))
            titles.append(title)
        parts.append(
            f'<text class="m" x="24" y="{y}" fill="{accent}" font-size="{heading}">'
            f"{len(badges)} {html.escape(label.upper())}</text>"
        )
        top = y + heading + 4
        # at most count badges per row, so labels never collide
        for start in range(0, len(cells), count):
            row = cells[start : start + count]
            parts += badge_row(row, top, delay, spec, count, width)
            delay += 0.06 * len(row)
            top += size + 16 + lines * line_step(font) + 14
        y = top + 12
    head, tail = svg_frame(y - 10, "Credly badges: " + ", ".join(titles), width)
    return "".join([head, *parts, tail])


def write_svg(content: str, svg_path: str) -> bool:
    """Write an SVG card to svg_path; return True when the file changed."""
    path = Path(svg_path)
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        print(f"No changes detected in {svg_path}.")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"SVG card written to {svg_path}.")
    return True


BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


def git(*args: str) -> subprocess.CompletedProcess:
    """Run one git command in the working directory as github-actions[bot]."""
    return subprocess.run(
        ["git", "-c", f"user.name={BOT_NAME}", "-c", f"user.email={BOT_EMAIL}", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def commit_and_push(paths: list[str], message: str) -> bool:
    """Commit only these files and push them; return False when none differs."""
    result = git("add", "--", *paths)
    if result.returncode:
        fail(f"git add failed: {result.stderr.strip()}")
    # exit status 1 means the staged files differ from HEAD
    if not git("diff", "--cached", "--quiet", "--", *paths).returncode:
        print("Nothing to commit.")
        return False
    result = git("commit", "--quiet", "-m", message, "--", *paths)
    if result.returncode:
        fail(f"git commit failed: {result.stderr.strip()}")
    result = git("push", "--quiet")
    if result.returncode:
        fail(
            f"git push failed: {result.stderr.strip()} "
            "(the job needs permissions: contents: write)"
        )
    print(f"Committed and pushed {', '.join(paths)}.")
    return True


def main():
    if not CREDLY_USERNAME:
        print("ERROR: CREDLY_USERNAME is required.")
        print("Set it via environment variable or the credly-username action input.")
        sys.exit(1)
    if OUTPUT not in ("readme", "svg", "both"):
        fail(f"output must be readme, svg or both, got '{OUTPUT}'.")
    # every input is checked before any network call, so a typo fails fast
    hide_expired, sort, limit = selection_settings()
    if COMMIT not in ("true", "false"):
        fail(f"commit must be true or false, got '{COMMIT}'.")
    if COMMIT == "true" and not COMMIT_MESSAGE.strip():
        fail("commit-message must not be empty.")
    if OUTPUT != "readme":
        per_row, accent = svg_settings()

    print(f"Fetching badges for Credly user: {CREDLY_USERNAME}")
    data = fetch_badges(CREDLY_USERNAME)

    # The API returns {"data": [...]}
    badges = data.get("data", data)
    if not isinstance(badges, list):
        print(f"ERROR: Unexpected API response format: {type(badges)}")
        sys.exit(1)

    print(f"Found {len(badges)} total badges on Credly.")
    today = datetime.now(UTC).date()
    shown = select_badges(badges, hide_expired, sort, limit, today)
    if len(shown) != len(badges):
        print(f"Showing {len(shown)} after hide-expired and max-badges.")
    total = len(shown)

    certs, prof, know = categorize_badges(shown)
    print(
        f"  Industry Certifications: {len(certs)}\n"
        f"  Professional & Partner:  {len(prof)}\n"
        f"  Knowledge & Learning:    {len(know)}"
    )

    # The cards are built before anything is written, so a failed image fetch
    # leaves the README and the SVGs exactly as they were.
    cards = []
    if OUTPUT != "readme":
        groups = svg_groups(certs, prof, know, SVG_GROUPS)
        images = {}
        cards.append((SVG_PATH, render_svg(groups, per_row, accent, DESKTOP, images)))
        if SVG_MOBILE_PATH:
            mobile = render_svg(groups, MOBILE_PER_ROW, accent, MOBILE, images)
            cards.append((SVG_MOBILE_PATH, mobile))

    changed = False
    written = []
    if OUTPUT != "svg":
        section = generate_section(certs, prof, know)
        changed = update_readme(section)
        written.append(README_PATH)
    for path, content in cards:
        changed = write_svg(content, path) or changed
        written.append(path)

    if COMMIT == "true" and changed:
        commit_and_push(written, COMMIT_MESSAGE)

    # Write GitHub Actions outputs
    set_output("total-badges", str(total))
    set_output("certifications-count", str(len(certs)))
    set_output("professional-count", str(len(prof)))
    set_output("knowledge-count", str(len(know)))
    set_output("changed", str(changed).lower())

    if changed:
        print("Badges section has been updated.")
    else:
        print("Badges section is already up to date.")


if __name__ == "__main__":
    main()
