"""Measure how the two SVG cards read on a phone and save a side-by-side preview.

Opens this repo on github.com at a 375px phone viewport to measure how wide GitHub
draws README images there, then draws examples/credly-badges.svg (the 840px card)
and examples/credly-badges-mobile.svg (the svg-mobile-path card) at that width,
prints the scale and the label font size each one ends up at, and writes
docs/phone-preview.webp. Needs a network connection and Chromium:

  uv run --no-project --with playwright --with pillow==13.0.0 playwright install chromium
  uv run --no-project --with playwright --with pillow==13.0.0 python scripts/phone-preview.py
"""

import base64
import io
import re
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/Sagargupta16/credly-badge-readme-action"
PHONE = {"viewport": {"width": 375, "height": 812}, "device_scale_factor": 2}
CARDS = [
    ("840px card", ROOT / "examples" / "credly-badges.svg"),
    ("svg-mobile-path card", ROOT / "examples" / "credly-badges-mobile.svg"),
]
OUT = ROOT / "docs" / "phone-preview.webp"


def readme_width(browser) -> float:
    """Return the width GitHub gives a README image on a 375px phone."""
    page = browser.new_page(**PHONE)
    page.goto(REPO, wait_until="networkidle")
    width = page.eval_on_selector("article.markdown-body", "e => e.clientWidth")
    page.close()
    return width


def card_sizes(svg: str) -> tuple[float, float]:
    """Return a card's own width and the font size of its first badge label."""
    width = float(re.search(r'<svg[^>]* width="([\d.]+)"', svg).group(1))
    label = re.search(r'text-anchor="middle" [^>]*font-size="([\d.]+)"', svg)
    return width, float(label.group(1))


def preview_html(width: float) -> str:
    """Return a page with each card in its own phone-width column."""
    columns = "".join(
        f"<figure><figcaption>{name} at {width:g}px</figcaption>"
        # inlined: a page set from a string cannot load file:// images
        f'<img src="data:image/svg+xml;base64,{base64.b64encode(path.read_bytes()).decode()}" '
        f'width="{width:g}"></figure>'
        for name, path in CARDS
    )
    return (
        "<!doctype html><style>body{margin:0;display:flex;gap:24px;padding:24px;"
        "background:#0d1117;align-items:flex-start;font:600 15px system-ui,sans-serif}"
        "figure{margin:0}figcaption{color:#e6edf3;margin:0 0 12px}"
        f"</style>{columns}"
    )


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        width = readme_width(browser)
        print(f"GitHub README width on a 375px phone: {width:g}px")
        for name, path in CARDS:
            own, font = card_sizes(path.read_text(encoding="utf-8"))
            scale = min(1.0, width / own)
            print(
                f"{name}: {own:g}px drawn at {scale:.0%}, "
                f"first label {font:g}px -> {font * scale:.1f}px"
            )
        # two columns, 24px apart and from the edges
        page_width = round(2 * width + 3 * 24)
        page = browser.new_page(
            viewport={"width": page_width, "height": 600}, device_scale_factor=2
        )
        page.set_content(preview_html(width))
        # let every badge finish fading in before the shot
        page.wait_for_timeout(3500)
        shot = page.screenshot(full_page=True)
        browser.close()
    OUT.parent.mkdir(exist_ok=True)
    with Image.open(io.BytesIO(shot)) as img:
        img.save(OUT, format="WEBP", quality=82, method=6)
    print(f"Wrote {OUT.relative_to(ROOT).as_posix()}, {OUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
