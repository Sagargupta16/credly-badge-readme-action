#!/usr/bin/env python3
"""
Credly Badge README Updater
Auto-sync your Credly certifications and badges to your GitHub profile README.

Fetches badges from the Credly public API, categorizes them into
Industry Certifications, Professional/Partner Badges, and Knowledge/Learning Badges,
then updates the README between <!-- CREDLY-BADGES:START --> and <!-- CREDLY-BADGES:END --> markers.
With OUTPUT=svg (or both) it draws every badge into one self-contained,
animated SVG card at SVG_PATH instead (or as well). STYLE=flat draws the
card, and the phone card, in the newer flat look.

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
import math
import os
import re
import subprocess
import sys
import textwrap
import time
import unicodedata
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
# How the cards look: classic (the card every earlier version drew) or flat
STYLE = os.environ.get("STYLE", "classic").strip().lower()
# Which badges to show, in what order: the defaults keep every badge in profile order
HIDE_EXPIRED = os.environ.get("HIDE_EXPIRED", "false").strip().lower()
SORT = os.environ.get("SORT", "credly").strip().lower()
MAX_BADGES = os.environ.get("MAX_BADGES", "0").strip()
# Also show the profile's Other tab: badges added from outside Credly, unverified
INCLUDE_OTHER = os.environ.get("INCLUDE_OTHER", "false").strip().lower()
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
# and every page of the Other tab's badges under this one
CREDLY_API_USERS = "https://www.credly.com/api/v1/users/"


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
    return {"data": fetch_pages(f"{CREDLY_USERS}{username}/badges.json", username)}


def fetch_other_badges(username: str) -> list[dict]:
    """Fetch the profile's Other tab (badges added from outside Credly), shaped like badges.json."""
    url = f"{CREDLY_API_USERS}{username}/external_badges/open_badges/public?page=1&page_size=48"
    badges = []
    for record in fetch_pages(url, username):
        ext = record.get("external_badge") or {}
        image_url = ext.get("image_url") or ""
        # the URLs come from the API: only Credly-hosted images, only https links
        if not image_url.startswith(CREDLY_CDN):
            print(
                f"Skipping Other badge without a Credly image: {ext.get('badge_name')}"
            )
            continue
        link = ext.get("badge_url") or ""
        if not link.startswith("https://"):
            link = f"{CREDLY_USERS}{username}/badges/other"
        badges.append(
            {
                "id": record.get("id", ""),
                "issued_at_date": ext.get("issued_at_date"),
                "expires_at_date": ext.get("expires_at_date"),
                "link": link,
                "badge_template": {
                    "name": ext.get("badge_name") or "Badge",
                    "image_url": image_url,
                },
            }
        )
    return badges


def fetch_pages(url: str, username: str) -> list[dict]:
    """Return the data of every page, following metadata.next_page_url under Credly's own paths."""
    prefix = CREDLY_API_USERS if url.startswith(CREDLY_API_USERS) else CREDLY_USERS
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
        if url and not url.startswith(prefix):
            fail(f"refusing to follow a page URL outside {prefix}: {url}")
    return badges


SORTS = ("credly", "newest", "oldest")


def selection_settings() -> tuple[bool, str, int]:
    """Validate the badge selection inputs and return (hide expired, sort, limit)."""
    if HIDE_EXPIRED not in ("true", "false"):
        fail(f"hide-expired must be true or false, got '{HIDE_EXPIRED}'.")
    if SORT not in SORTS:
        fail(f"sort must be credly, newest or oldest, got '{SORT}'.")
    if not re.fullmatch(r"\d+", MAX_BADGES, re.ASCII):
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
    # an Other badge links to its issuer's page; a Credly badge to its Credly page
    badge_url = badge.get("link") or f"https://www.credly.com/badges/{badge_id}"

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
# the first group is drawn large, every group after it small. Labels are 10.5 px, which
# reads at 10.4 px in an 831 px README column; one more line than the 8.5 and 7.5 px labels
# had keeps more names whole (on sagar-gupta.f8eb96cc's 22 badges 3 lose a word, against 4 before)
LARGE = (84, 4, 10.5, 18)
SMALL = (58, 3, 10.5, 16)
# (card width px, group heading font px, first group spec, later groups spec).
# GitHub draws a README 309px wide on a 375px phone (measured 2026-10-18), which
# shrinks the 840px card to 37%. The 340px phone card is drawn at 91% there. It
# draws badges at the desktop card's default sizes, so both share every image.
DESKTOP = (SVG_WIDTH, 10.5, LARGE, SMALL)
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
    # a 10.5 px heading leaves y fractional; the card itself stays whole pixels
    head, tail = svg_frame(round(y - 10), "Credly badges: " + ", ".join(titles), width)
    return "".join([head, *parts, tail])


# ---------------------------------------------------------------- flat style
# style: flat draws both cards in the newer look of Sagargupta16/Sagargupta16
# (scripts/kit.py, and certs_mobile in scripts/cards/stats.py for the phone card):
# one flat surface with a hairline border, every badge in its finished place on a
# tile, mono micro-labels that carry the counts, and one loop, a lit border that
# walks the first group's tiles on a 12 s clock. Each entrance holds its start
# value until its turn and the elements' own attributes are the finished frame,
# so a still render (a link preview, a viewer without SMIL) shows the whole card.
STYLES = ("classic", "flat")
CARD = "#0f171c"  # a tile that holds a badge and its name
INK = "#f3f4f6"  # certification names
BODY = "rgba(255,255,255,0.78)"  # the other badges' names
META = "rgba(255,255,255,0.62)"  # group headings and the +N more line
HAIR = "rgba(255,255,255,0.09)"  # the card's border
HAIR_STRONG = "rgba(255,255,255,0.14)"  # a tile's border
HAIR_FILL = "rgba(255,255,255,0.03)"  # a phone tile, which holds only an image
SANS = "'Segoe UI',Inter,-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif"
TRACK = 1.2  # letter-spacing of a mono micro-label
# The smallest text: 10.5 px on the 840 px card, 11.5 px on the 320 px phone card.
# A name that does not fit its tile wraps; nothing shrinks below these.
MICRO, MICRO_PHONE = 10.5, 11.5
EASE = "0.16 1 0.3 1"  # entrances ease out
# The inlined images are most of a card's weight, so together they stay inside
# IMAGE_BUDGET characters of data URI, which keeps a card well under 100 KB however
# many badges a profile has. The first group takes the budget first, in whole rows,
# and a group's badges that do not fit are counted in a "+N MORE ON CREDLY" line.
IMAGE_BUDGET = 64_000
# drawn size of a certification and of every other badge; fetched at twice that
FLAT_CERT, FLAT_BADGE = 64, 48
PAD = 24
PHONE, PHONE_PAD = 320, 18
# the phone card: certifications three a row on tiles, other badges five a row,
# one row a group while there are certifications above them
PHONE_ROWS = [3, 5]
SLIDE = 0.35  # how long the lit border takes to reach the next tile in a row
LIT_MAX = 16  # the lit border walks at most this many tiles, 1.5 s each in 24 s


def advance(character: str) -> float:
    """Return the rough width of one sans character, in em."""
    if unicodedata.combining(character):
        return 0
    if unicodedata.east_asian_width(character) in {"W", "F"}:
        return 1.05
    if character in "W@%M":
        return 1
    if character in "ilI.,:;'!|`":
        return 0.34
    if character in " fjrt()[]":
        return 0.44
    return 0.7 if character.isupper() else 0.58


def text_width(text: str, size: float, mono: bool = False) -> float:
    """Measure text conservatively: sans advances, or monospace plus its tracking."""
    if mono:
        return len(text) * (size * 0.6 + TRACK)
    return sum(advance(character) for character in text) * size


def wrap_text(text: str, room: float, size: float, mono: bool = False) -> list[str]:
    """Wrap words to a pixel width, splitting a token too long for a line, dropping nothing."""
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if text_width(candidate, size, mono) <= room:
            current = candidate
            continue
        if current:
            # a token wider than the line splits anyway, so it starts on this line; so
            # does a long one with a "/", "-", "_" or "." to break at after a short line
            token = text_width(word, size, mono)
            short_line = text_width(current, size, mono) < room / 2
            breakable = token > room * 0.75 and re.search("[/_.-].", word)
            if token > room or (short_line and breakable):
                current += " "
            else:
                lines.append(current)
                current = ""
        # a token too long for a line breaks after "/", "-", "_" or "." first,
        # and only splits between letters where no separator fits
        for piece in re.findall(r"[^/\-_.]+[/\-_.]*|[/\-_.]+", word):
            if current.strip() and text_width(current + piece, size, mono) > room:
                lines.append(current.rstrip())
                current = ""
            for character in piece:
                if (
                    current.strip()
                    and text_width(current + character, size, mono) > room
                ):
                    lines.append(current.rstrip())
                    current = ""
                current += character
    if current:
        lines.append(current)
    return lines


def clip(text: str, room: float, size: float) -> str:
    """Shorten sans text to a width: whole words first, then letters, ending in three dots."""
    if text_width(text, size) <= room:
        return text
    while " " in text and text_width(text + "...", size) > room:
        text = text.rsplit(" ", 1)[0]
    while len(text) > 1 and text_width(text + "...", size) > room:
        text = text[:-1]
    return text.rstrip(" ,;:.-") + "..."


def name_lines(name: str, room: float, size: float, cap: int) -> list[str]:
    """Wrap a badge name to its tile and keep at most cap lines, the last clipped with three dots."""
    lines = wrap_text(name, room, size)
    if len(lines) <= cap:
        return lines
    return [*lines[: cap - 1], clip(" ".join(lines[cap - 1 :]), room, size)]


def num(value: float) -> str:
    """Return a coordinate to two places at most, with no trailing zeros and never -0."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def flat_text(
    x: float,
    y: float,
    content: str,
    size: float,
    fill: str,
    cls: str = "m",
    anchor: str = "",
) -> str:
    """Return one text element: class m is a mono micro-label, s a sans name."""
    align = f' text-anchor="{anchor}"' if anchor else ""
    return (
        f'<text class="{cls}" x="{num(x)}" y="{num(y)}" font-size="{size:g}" fill="{fill}"{align}>'
        f"{html.escape(content)}</text>"
    )


def flat_rect(
    x: float,
    y: float,
    w: float,
    h: float,
    fill: str,
    stroke: str = HAIR_STRONG,
    extra: str = "",
    inner: str = "",
) -> str:
    """Return a tile: a rounded rectangle with one border, holding inner if given."""
    head = (
        f'<rect x="{num(x)}" y="{num(y)}" width="{num(w)}" height="{num(h)}" rx="10" '
        f'fill="{fill}" stroke="{stroke}"{extra}'
    )
    return f"{head}>{inner}</rect>" if inner else f"{head}/>"


def entrance(at: float, body: str) -> str:
    """Wrap a block so it fades in and rises 8 px at `at`, poster-safe.

    The animation runs from 0 s and holds its start value until `at`; the block's own
    attributes are the finished frame, so a still render shows it in place.
    """
    total = at + 0.4
    timing = (
        f'keyTimes="0;{at / total:.3f};1" dur="{total:.2f}s" fill="freeze" '
        f'calcMode="spline" keySplines="0 0 1 1;{EASE}"'
    )
    return (
        f'<g><animate attributeName="opacity" values="0;0;1" {timing}/>'
        f'<animateTransform attributeName="transform" type="translate" values="0 8;0 8;0 0" {timing}/>'
        f"{body}</g>"
    )


def turn(index: int) -> float:
    """Return when block number index enters, in reading order: 0.08 s apart, all by 1.2 s."""
    return min(0.15 + index * 0.08, 1.2)


def clock_loop(
    attribute: str, points: list[tuple[float, str]], dur: float, extra: str = ""
) -> str:
    """Return a repeating animation through (seconds, value) points from 0 to dur."""
    values = ";".join(value for _, value in points)
    times = ";".join(f"{round(second / dur, 4):g}" for second, _ in points)
    tag = "animateTransform" if attribute == "transform" else "animate"
    kind = ' type="translate"' if attribute == "transform" else ""
    return (
        f'<{tag} attributeName="{attribute}"{kind} values="{values}" keyTimes="{times}"{extra} '
        f'dur="{dur:g}s" repeatCount="indefinite"/>'
    )


def stepper(offsets: list[tuple[float, float]]) -> str:
    """Walk the element this sits in through (dx, dy) offsets, one slot each.

    The loop is 12 s when each tile gets 1.5 s or more, else 24 s. Along a row the
    border slides; to a new row, and back to the first tile, it fades out, jumps and
    fades in. A lone tile has nowhere to go, so its border breathes on a 3 s beat.
    """
    count = len(offsets)
    if count < 2:
        return clock_loop("opacity", [(0.0, "1"), (1.5, "0.4"), (3.0, "1")], 3)
    loop = 12 if count * 1.5 <= 12 else 24
    slot = loop / count
    moves, fades, splines = [(0.0, offsets[0])], [(0.0, "1")], []
    for index in range(1, count + 1):
        end = loop if index == count else index * slot
        before, after = offsets[index - 1], offsets[index % count]
        along = index < count and (before[0] == after[0] or before[1] == after[1])
        if along:
            moves += [(end - SLIDE, before), (end, after)]
            splines += ["0 0 1 1", "0.4 0 0.2 1"]
        else:
            moves += [(end - 0.2, before), (end - 0.19, after)]
            splines += ["0 0 1 1", "0 0 1 1"]
            fades += [
                (end - 0.35, "1"),
                (end - 0.2, "0"),
                (end - 0.15, "0"),
                (end, "1"),
            ]
    if moves[-1][0] < loop:
        moves.append((loop, moves[-1][1]))
        splines.append("0 0 1 1")
    if fades[-1][0] < loop:
        fades.append((loop, "1"))
    spline = f' calcMode="spline" keySplines="{";".join(splines)}"'
    out = clock_loop(
        "transform",
        [(t, f"{num(dx)} {num(dy)}") for t, (dx, dy) in moves],
        loop,
        spline,
    )
    if len(fades) > 2:
        out += clock_loop("opacity", fades, loop)
    return out


def lit_border(
    places: list[tuple[float, float]], w: float, h: float, accent: str
) -> str:
    """Return the lit border: an accent tint and edge that walks the tiles at places."""
    x0, y0 = places[0]
    offsets = [(x - x0, y - y0) for x, y in places[:LIT_MAX]]
    extra = ' fill-opacity="0.14" stroke-width="1.5"'
    return flat_rect(x0, y0, w, h, accent, accent, extra, stepper(offsets))


def card_image(images: dict, badge: dict, size: int) -> str:
    """Return the badge's image drawn at size as a data URI, fetched once per (URL, size)."""
    url = badge.get("badge_template", {}).get("image_url", "")
    if (url, size) not in images:
        images[url, size] = badge_data_uri(url, size * 2)
    return images[url, size]


def within_budget(badges: list[dict], budget: int, row: int, image) -> list[dict]:
    """Return the badges, in order, whose images fit the budget, cut back to whole rows.

    image(badge) returns its data URI, so images are fetched only until the budget
    runs out. When not even one whole row fits, the badges that fit stay.
    """
    shown, used = [], 0
    for badge in badges:
        used += len(image(badge))
        if used > budget:
            break
        shown.append(badge)
    if len(shown) < len(badges):
        shown = shown[: len(shown) - len(shown) % row] or shown
    return shown


def flat_pick(
    groups: list[tuple[str, list[dict]]], rows: list[int], image, one_row: bool = False
) -> list[list[dict]]:
    """Return the badges each group shows, every image inside one IMAGE_BUDGET, first group first.

    rows holds the badges a row for each group, the last value repeating. image(badge, i)
    returns the data URI group i draws. With one_row, a group after the first shows one
    row at most when the first group has badges (the phone card).
    """
    left, picks = IMAGE_BUDGET, []
    for i, (_, badges) in enumerate(groups):
        row = rows[min(i, len(rows) - 1)]
        pool = badges[:row] if one_row and i and groups[0][1] else badges
        shown = within_budget(pool, left, row, lambda badge, i=i: image(badge, i))
        left -= sum(len(image(badge, i)) for badge in shown)
        picks.append(shown)
    return picks


def badge_name(badge: dict) -> str:
    return plain_dashes(badge.get("badge_template", {}).get("name", "Badge"))


def flat_open(w: int, h: int, groups: list[tuple[str, list[dict]]]) -> str:
    """Return the opening markup of a flat card: root, text classes and the surface."""
    names = [badge_name(badge) for _, badges in groups for badge in badges]
    return (
        svg_open(w, h, f"{len(names)} Credly badges: " + ", ".join(names))
        + f"<style>.m{{font-family:{MONO};font-weight:700;letter-spacing:{TRACK}px}}"
        f".s{{font-family:{SANS};font-weight:600}}</style>"
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="14" fill="{SVG_BG}" '
        f'stroke="{HAIR}"/>'
    )


def more_line(
    shown: int, count: int, x: float, y: float, room: float, size: float, at: float
) -> tuple[str, float]:
    """Return what a group has no room for, counted and found on Credly, and the y under it."""
    note = f"+{count - shown} MORE ON CREDLY" if shown else f"{count} ON CREDLY"
    body = []
    y += 12
    for line in wrap_text(note, room, size, True):
        y += 16
        body.append(flat_text(x, y, line, size, META))
    return entrance(at, "".join(body)), y


def headings(
    text: str, x: float, y: float, room: float, size: float
) -> tuple[str, float]:
    """Return a group heading, wrapped to the room and never shrunk, and its last baseline."""
    out = []
    for index, line in enumerate(wrap_text(text, room, size, True)):
        out.append(flat_text(x, y + index * 16, line, size, META))
    return "".join(out), y + (len(out) - 1) * 16


def render_flat(
    groups: list[tuple[str, list[dict]]],
    per_row: list[int],
    accent: str,
    images: dict | None = None,
) -> str:
    """Return the 840 px card in the flat style (see the comment above STYLES).

    images caches the data URIs by (URL, drawn size), as render_svg does.
    """
    images = {} if images is None else images
    room = SVG_WIDTH - 2 * PAD
    # (badges a row, gap, tile width, drawn size) of each group
    shapes = []
    for i in range(len(groups)):
        count = per_row[min(i, len(per_row) - 1)]
        gap = 12 if i == 0 else 10
        w = (room - gap * (count - 1)) / count
        size = min(FLAT_CERT, int(w) - 24) if i == 0 else min(FLAT_BADGE, int(w) - 20)
        shapes.append((count, gap, w, size))
    picks = flat_pick(
        groups, per_row, lambda badge, i: card_image(images, badge, shapes[i][3])
    )
    total = sum(len(badges) for _, badges in groups)
    parts = [flat_text(PAD, 30, f"{total} CREDLY BADGES", MICRO, accent)]
    y, block, walked = 30, 0, False
    for i, ((label, badges), shown) in enumerate(zip(groups, picks)):
        if not badges:
            continue
        count, gap, w, size = shapes[i]
        heading, y = headings(
            f"{len(badges)} {label.upper()}", PAD, y + 28, room, MICRO
        )
        parts.append(heading)
        y += 12
        # certification names in ink, up to four lines; the other badges' in body, three
        font, step, fill, cap = (12, 15, INK, 4) if i == 0 else (11, 14, BODY, 3)
        names = [
            name_lines(short_badge(badge_name(b)), w - 12, font, cap) for b in shown
        ]
        tall = max((len(lines) for lines in names), default=0)
        h = 12 + size + 12 + (font + (tall - 1) * step + 14 if tall else 0)
        tiles, places, rows = [], [], []
        for start in range(0, len(shown), count):
            row = shown[start : start + count]
            x0 = PAD + (room - w * len(row) - gap * (len(row) - 1)) / 2
            body = []
            for j, badge in enumerate(row):
                x = x0 + j * (w + gap)
                places.append((x, y))
                tiles.append(flat_rect(x, y, w, h, CARD))
                body.append(
                    f"<g><title>{html.escape(badge_name(badge))}</title>"
                    f'<image href="{card_image(images, badge, size)}" x="{num(x + (w - size) / 2)}" '
                    f'y="{num(y + 12)}" width="{size}" height="{size}"/></g>'
                )
                body += [
                    flat_text(
                        x + w / 2,
                        y + 24 + size + font + k * step,
                        line,
                        font,
                        fill,
                        "s",
                        "middle",
                    )
                    for k, line in enumerate(names[start + j])
                ]
            rows.append("".join(body))
            y += h + gap
        if shown:
            y -= gap
            if not walked:
                tiles.append(lit_border(places, w, h, accent))
                walked = True
            parts.append(entrance(turn(block), "".join(tiles)))
            parts += [entrance(turn(block + r), row) for r, row in enumerate(rows)]
            block += len(rows)
        if len(shown) < len(badges):
            note, y = more_line(
                len(shown), len(badges), PAD, y, room, MICRO, turn(block)
            )
            parts.append(note)
        block += 1
    return (
        flat_open(SVG_WIDTH, math.ceil(y + PAD), groups) + "".join(parts) + "</svg>\n"
    )


def render_flat_phone(
    groups: list[tuple[str, list[dict]]], accent: str, images: dict | None = None
) -> str:
    """Return the 320 px phone card in the flat style, the profile's certs_mobile layout.

    Its counts are the 840 px card's; certifications sit three a row on tiles, every
    later group shows one row of five while certifications are drawn above it.
    """
    images = {} if images is None else images
    column = PHONE - 2 * PHONE_PAD
    # (badges a row, gap, drawn size, image size, on tiles) of the first group, then the rest
    shapes = [(3, 10, 64, FLAT_CERT, True), (5, 2, 46, FLAT_BADGE, False)]
    picks = flat_pick(
        groups,
        PHONE_ROWS,
        lambda badge, i: card_image(images, badge, shapes[min(i, 1)][3]),
        one_row=True,
    )
    total = sum(len(badges) for _, badges in groups)
    blocks = [flat_text(PHONE_PAD, 30, f"{total} CREDLY BADGES", MICRO_PHONE, accent)]
    y, block, walked, drawn = 30, 0, False, False
    for i, ((label, badges), shown) in enumerate(zip(groups, picks)):
        if not badges:
            continue
        count, gap, size, fetched, tiled = shapes[min(i, 1)]
        heading, y = headings(
            f"{len(badges)} {label.upper()}",
            PHONE_PAD,
            y + (30 if drawn else 26),
            column,
            MICRO_PHONE,
        )
        blocks.append(heading)
        drawn = True
        y += 12 if tiled else 10
        cell = (column - gap * (count - 1)) / count
        tiles, places, rows = [], [], []
        for start in range(0, len(shown), count):
            chunk = shown[start : start + count]
            # a short last row of tiles is centred, a short row of bare badges starts left
            shift = (count - len(chunk)) * (cell + gap) / 2 if tiled else 0
            body = []
            for j, badge in enumerate(chunk):
                x = PHONE_PAD + shift + j * (cell + gap)
                places.append((x, y))
                if tiled:
                    tiles.append(flat_rect(x, y, cell, cell, HAIR_FILL))
                inset = (cell - size) / 2
                body.append(
                    f"<g><title>{html.escape(badge_name(badge))}</title>"
                    f'<image href="{card_image(images, badge, fetched)}" x="{x + inset:.1f}" '
                    f'y="{y + inset:.1f}" width="{size}" height="{size}"/></g>'
                )
            rows.append("".join(body))
            y += cell + gap
        if shown:
            y -= gap
            if not walked:
                tiles.append(lit_border(places, cell, cell, accent))
                walked = True
            if tiles:
                blocks.append(entrance(turn(block), "".join(tiles)))
            blocks += [entrance(turn(block + r), row) for r, row in enumerate(rows)]
            block += len(rows)
        if len(shown) < len(badges):
            note, y = more_line(
                len(shown),
                len(badges),
                PHONE_PAD,
                y,
                column,
                MICRO_PHONE,
                turn(block),
            )
            blocks.append(note)
        block += 1
    return (
        flat_open(PHONE, math.ceil(y + PHONE_PAD), groups)
        + "".join(blocks)
        + "</svg>\n"
    )


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


def commit_settings() -> None:
    """Validate the commit inputs."""
    if COMMIT not in ("true", "false"):
        fail(f"commit must be true or false, got '{COMMIT}'.")
    if COMMIT == "true" and not COMMIT_MESSAGE.strip():
        fail("commit-message must not be empty.")


def build_cards(
    certs: list, prof: list, know: list, svg: tuple[list[int], str] | None
) -> list[tuple[str, str]]:
    """Return (path, SVG) for the card and, when svg-mobile-path is set, the phone card.

    Both cards share one image cache, so the phone card downloads nothing extra.
    """
    if svg is None:
        return []
    per_row, accent = svg
    groups = svg_groups(certs, prof, know, SVG_GROUPS)
    images = {}
    if STYLE == "flat":
        cards = [(SVG_PATH, render_flat(groups, per_row, accent, images))]
        if SVG_MOBILE_PATH:
            phone = render_flat_phone(groups, accent, images)
            cards.append((SVG_MOBILE_PATH, phone))
        return cards
    cards = [(SVG_PATH, render_svg(groups, per_row, accent, DESKTOP, images))]
    if SVG_MOBILE_PATH:
        mobile = render_svg(groups, MOBILE_PER_ROW, accent, MOBILE, images)
        cards.append((SVG_MOBILE_PATH, mobile))
    return cards


def main():
    if not CREDLY_USERNAME:
        print("ERROR: CREDLY_USERNAME is required.")
        print("Set it via environment variable or the credly-username action input.")
        sys.exit(1)
    if OUTPUT not in ("readme", "svg", "both"):
        fail(f"output must be readme, svg or both, got '{OUTPUT}'.")
    # every input is checked before any network call, so a typo fails fast
    hide_expired, sort, limit = selection_settings()
    if INCLUDE_OTHER not in ("true", "false"):
        fail(f"include-other must be true or false, got '{INCLUDE_OTHER}'.")
    commit_settings()
    svg = svg_settings() if OUTPUT != "readme" else None
    if svg and STYLE not in STYLES:
        fail(f"style must be classic or flat, got '{STYLE}'.")

    print(f"Fetching badges for Credly user: {CREDLY_USERNAME}")
    data = fetch_badges(CREDLY_USERNAME)

    # The API returns {"data": [...]}
    badges = data.get("data", data)
    if not isinstance(badges, list):
        print(f"ERROR: Unexpected API response format: {type(badges)}")
        sys.exit(1)

    print(f"Found {len(badges)} total badges on Credly.")
    if INCLUDE_OTHER == "true":
        other = fetch_other_badges(CREDLY_USERNAME)
        print(f"Found {len(other)} Other badges (added from outside Credly).")
        badges = badges + other
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
    cards = build_cards(certs, prof, know, svg)

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
