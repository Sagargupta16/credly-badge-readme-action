"""Tests for update-credly-badges.py (no network: every fetch is stubbed)."""

import base64
import importlib.util
import xml.etree.ElementTree as ET
from itertools import pairwise
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "update_credly_badges", Path(__file__).parent / "update-credly-badges.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def make_badge(
    name, badge_id="abc-123", image_url="https://images.credly.com/images/x/y.png"
):
    return {"id": badge_id, "badge_template": {"name": name, "image_url": image_url}}


def test_categorize_badges():
    cert = make_badge("AWS Certified Solutions Architect")
    prof = make_badge("Partner: Technical Accredited")
    know = make_badge("Cloud Practitioner Essentials")

    certs, professional, knowledge = mod.categorize_badges([cert, prof, know])

    assert certs == [cert]
    assert professional == [prof]
    assert knowledge == [know]


def test_categorize_cert_wins_over_professional():
    badge = make_badge("Certified Partner: Technical")
    certs, professional, knowledge = mod.categorize_badges([badge])
    assert certs == [badge]
    assert not professional
    assert not knowledge


def test_badge_to_html_sizes_and_escapes():
    badge = make_badge('AI "Expert" <Pro>', badge_id="id-1")
    tag = mod.badge_to_html(badge, size=100)

    assert "images.credly.com/size/100x100/images/" in tag
    assert 'href="https://www.credly.com/badges/id-1"' in tag
    assert "AI &quot;Expert&quot; &lt;Pro&gt;" in tag
    assert "<Pro>" not in tag


def test_generate_section_skips_empty_categories():
    knowledge = make_badge("Cloud Practitioner Essentials", badge_id="k-1")

    section = mod.generate_section([], [], [knowledge])

    assert "Industry Certifications" not in section
    assert "Professional & Partner Badges" not in section
    assert "Knowledge & Learning Badges" in section
    # No stray blank line before the first rendered heading
    assert not section.startswith("\n")


def test_generate_section_renders_all_categories():
    cert = make_badge("AWS Certified Solutions Architect", badge_id="c-1")
    prof = make_badge("Partner: Technical", badge_id="p-1")
    know = make_badge("Cloud Practitioner Essentials", badge_id="k-1")

    section = mod.generate_section([cert], [prof], [know])

    assert "Industry Certifications" in section
    assert "Professional & Partner Badges" in section
    assert "Knowledge & Learning Badges" in section


def test_update_readme_replaces_between_markers(tmp_path, monkeypatch, capsys):
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Hi\n<!-- CREDLY-BADGES:START -->\nold stuff\n<!-- CREDLY-BADGES:END -->\nfooter\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "README_PATH", str(readme))

    changed = mod.update_readme(r"new badges \g<0>")

    assert changed is True
    content = readme.read_text(encoding="utf-8")
    assert "old stuff" not in content
    # Backslash sequences must be kept literal, not treated as backreferences
    assert r"new badges \g<0>" in content
    assert content.startswith("# Hi\n")
    assert content.endswith("footer\n")


def test_update_readme_no_change(tmp_path, monkeypatch):
    readme = tmp_path / "README.md"
    readme.write_text(
        "<!-- CREDLY-BADGES:START -->\nsame\n<!-- CREDLY-BADGES:END -->",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "README_PATH", str(readme))

    assert mod.update_readme("same") is False


def test_update_readme_missing_markers_exits(tmp_path, monkeypatch):
    readme = tmp_path / "README.md"
    readme.write_text("no markers here", encoding="utf-8")
    monkeypatch.setattr(mod, "README_PATH", str(readme))

    with pytest.raises(SystemExit):
        mod.update_readme("anything")


# ---------------------------------------------------------------- README mode is frozen

EN_DASH, EM_DASH = chr(0x2013), chr(0x2014)
MEDAL, MILITARY_MEDAL, BOOKS, VS16 = (
    chr(0x1F3C5),
    chr(0x1F396),
    chr(0x1F4DA),
    chr(0xFE0F),
)
MARKERS = "<!-- CREDLY-BADGES:START -->\n<!-- CREDLY-BADGES:END -->\n"
FROZEN_BADGES = [
    make_badge(f"AWS Certified Developer {EN_DASH} Associate", badge_id="c-1"),
    make_badge(
        'Terraform "Certified" <Pro> & Co\'s',
        badge_id="c-2",
        image_url="https://images.credly.com/images/t/blob",
    ),
    make_badge("Well-Architected Proficient", badge_id="p-1"),
    make_badge(
        f"AWS Knowledge: Cloud Essentials {EM_DASH} Training Badge", badge_id="k-1"
    ),
]
# Captured from the script before SVG mode existed (main at 92ca53e). README mode
# must not move a byte, and it keeps Credly's en and em dashes as they come.
FROZEN_SECTION = "\n".join(
    [
        f"{MEDAL} **Industry Certifications**",
        "",
        '<div align="center">',
        "",
        (
            '<a href="https://www.credly.com/badges/c-1" '
            f'title="AWS Certified Developer {EN_DASH} Associate">'
            '<img src="https://images.credly.com/size/100x100/images/x/y.png" '
            f'alt="AWS Certified Developer {EN_DASH} Associate" width="100" height="100"></a>'
        ),
        (
            '<a href="https://www.credly.com/badges/c-2" '
            'title="Terraform &quot;Certified&quot; &lt;Pro&gt; &amp; Co&#x27;s">'
            '<img src="https://images.credly.com/size/100x100/images/t/blob" '
            'alt="Terraform &quot;Certified&quot; &lt;Pro&gt; &amp; Co&#x27;s" '
            'width="100" height="100"></a>'
        ),
        "",
        "</div>",
        "",
        f"{MILITARY_MEDAL}{VS16} **Professional & Partner Badges**",
        "",
        '<div align="center">',
        "",
        (
            '<a href="https://www.credly.com/badges/p-1" title="Well-Architected Proficient">'
            '<img src="https://images.credly.com/size/100x100/images/x/y.png" '
            'alt="Well-Architected Proficient" width="100" height="100"></a>'
        ),
        "",
        "</div>",
        "",
        f"{BOOKS} **Knowledge & Learning Badges**",
        "",
        '<div align="center">',
        "",
        (
            '<a href="https://www.credly.com/badges/k-1" '
            f'title="AWS Knowledge: Cloud Essentials {EM_DASH} Training Badge">'
            '<img src="https://images.credly.com/size/100x100/images/x/y.png" '
            f'alt="AWS Knowledge: Cloud Essentials {EM_DASH} Training Badge" '
            'width="100" height="100"></a>'
        ),
        "",
        "</div>",
    ]
)


def test_generate_section_output_is_frozen():
    section = mod.generate_section(*mod.categorize_badges(FROZEN_BADGES))

    assert section == FROZEN_SECTION


# ---------------------------------------------------------------- SVG card

SVG = "{http://www.w3.org/2000/svg}"
# A real 1x1 PNG, so the Pillow path can decode it too when Pillow is installed.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


@pytest.fixture
def fetched(monkeypatch):
    """Serve every image fetch from memory and record the URLs asked for."""
    urls = []

    def fake_fetch_url(url, accept):
        urls.append(url)
        return TINY_PNG

    monkeypatch.setattr(mod, "fetch_url", fake_fetch_url)
    return urls


def badges(prefix, count):
    """Return count badges with distinct ids and image URLs."""
    return [
        make_badge(
            f"{prefix} {n}",
            badge_id=f"{prefix}-{n}",
            image_url=f"https://images.credly.com/images/{prefix}-{n}/image.png",
        )
        for n in range(count)
    ]


def card(groups, per_row=(6, 8)):
    """Render groups into a card and parse it, which fails on invalid XML."""
    return ET.fromstring(mod.render_svg(groups, list(per_row), "#60a5fa"))


def group_labels(root):
    return [t.text for t in root.iter(f"{SVG}text") if t.get("x") == "24"]


def badge_labels(root):
    return [t for t in root.iter(f"{SVG}text") if t.get("x") != "24"]


def rows(root):
    """Return the badge images of the card, grouped by row, top to bottom."""
    by_top = {}
    for img in root.iter(f"{SVG}image"):
        by_top.setdefault(img.get("y"), []).append(img)
    return list(by_top.values())


def test_svg_groups_two_folds_everything_after_certifications():
    cert, prof, know = make_badge("A"), make_badge("B"), make_badge("C")

    groups = mod.svg_groups([cert], [prof], [know], "two")

    assert groups == [
        ("Industry certifications", [cert]),
        ("Learning and partner badges", [prof, know]),
    ]


def test_svg_groups_three_keeps_the_readme_categories():
    cert, prof, know = make_badge("A"), make_badge("B"), make_badge("C")

    groups = mod.svg_groups([cert], [prof], [know], "three")

    assert groups == [
        ("Industry certifications", [cert]),
        ("Professional and partner badges", [prof]),
        ("Knowledge and learning badges", [know]),
    ]


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("two", ["1 INDUSTRY CERTIFICATIONS", "2 LEARNING AND PARTNER BADGES"]),
        (
            "three",
            [
                "1 INDUSTRY CERTIFICATIONS",
                "1 PROFESSIONAL AND PARTNER BADGES",
                "1 KNOWLEDGE AND LEARNING BADGES",
            ],
        ),
    ],
)
def test_render_svg_labels_each_group_with_its_count(fetched, mode, expected):
    groups = mod.svg_groups(badges("c", 1), badges("p", 1), badges("k", 1), mode)

    root = card(groups)

    assert group_labels(root) == expected


def test_render_svg_skips_empty_groups(fetched):
    groups = mod.svg_groups([], [], badges("k", 2), "three")

    root = card(groups)

    assert group_labels(root) == ["2 KNOWLEDGE AND LEARNING BADGES"]


def test_render_svg_wraps_rows_at_per_row(fetched):
    root = card([("Industry certifications", badges("c", 7))], per_row=(6,))

    assert [len(row) for row in rows(root)] == [6, 1]
    # the lone badge on the second row sits in the middle of the 840px card
    (lone,) = rows(root)[1]
    assert float(lone.get("x")) + float(lone.get("width")) / 2 == 420


def test_render_svg_repeats_the_last_per_row_value(fetched):
    groups = mod.svg_groups(badges("c", 1), badges("p", 1), badges("k", 3), "three")

    root = card(groups, per_row=(6, 2))

    # knowledge is the third group, so it wraps at the repeated last value, 2
    assert [len(row) for row in rows(root)] == [1, 1, 2, 1]


def test_render_svg_shrinks_badges_that_would_overlap(fetched):
    root = card([("Industry certifications", badges("c", 12))], per_row=(12,))

    (row,) = rows(root)
    xs = [float(img.get("x")) for img in row]
    width = float(row[0].get("width"))
    assert min(b - a for a, b in pairwise(xs)) > width


def test_render_svg_shrinks_a_long_word_to_its_column(fetched):
    long_word = [make_badge("Practitionerpractitioner")]

    root = card([("Industry certifications", long_word)], per_row=(12,))

    (label,) = badge_labels(root)
    assert float(label.get("font-size")) < 8.5


def test_render_svg_draws_plain_dashes(fetched):
    title = f"AWS Certified Developer {EN_DASH} Associate {EM_DASH} 2026"

    svg = mod.render_svg(
        [("Industry certifications", [make_badge(title)])], [6], "#fff"
    )

    assert EN_DASH not in svg
    assert EM_DASH not in svg
    assert (
        'aria-label="Credly badges: AWS Certified Developer - Associate - 2026"' in svg
    )


def test_render_svg_escapes_titles_into_valid_xml(fetched):
    title = 'AI "Expert" <Pro> & Co\'s'

    svg = mod.render_svg(
        [("Industry certifications", [make_badge(title)])], [6], "#fff"
    )

    root = ET.fromstring(svg)  # raises on anything that is not well-formed XML
    assert root.get("aria-label") == f"Credly badges: {title}"
    assert [t.text for t in badge_labels(root)] == ['AI "EXPERT" <PRO>', "& CO'S"]
    assert "<PRO>" not in svg


def test_render_svg_inlines_each_image_once(fetched):
    twins = [make_badge("A"), make_badge("B")]  # both use the default image URL

    root = card([("Industry certifications", twins)])

    hrefs = [img.get("href") for img in root.iter(f"{SVG}image")]
    assert all(href.startswith("data:image/png;base64,") for href in hrefs)
    assert fetched == ["https://images.credly.com/images/x/y.png"]


def test_badge_data_uri_refuses_hosts_outside_the_credly_cdn(fetched):
    with pytest.raises(ValueError, match="refusing"):
        mod.badge_data_uri("file:///etc/passwd", 168)

    assert fetched == []


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("SVG_GROUPS", "four"),
        ("SVG_PER_ROW", "6,x"),
        ("SVG_PER_ROW", "0"),
        ("SVG_PER_ROW", "13"),
        ("ACCENT", "blue"),
        ("ACCENT", '#fff" onload="x'),
        ("SVG_PATH", " "),
    ],
)
def test_svg_settings_rejects_bad_values(monkeypatch, setting, value):
    monkeypatch.setattr(mod, setting, value)

    with pytest.raises(SystemExit):
        mod.svg_settings()


def test_svg_settings_accepts_a_bare_hex_accent(monkeypatch):
    monkeypatch.setattr(mod, "SVG_GROUPS", "two")
    monkeypatch.setattr(mod, "SVG_PER_ROW", "6, 8")
    monkeypatch.setattr(mod, "ACCENT", "60A5FA")

    assert mod.svg_settings() == ([6, 8], "#60a5fa")


# ---------------------------------------------------------------- main()


def stub_profile(tmp_path, monkeypatch, output):
    """Point main() at scratch files and a stubbed Credly profile."""
    readme = tmp_path / "README.md"
    readme.write_text(MARKERS, encoding="utf-8")
    svg = tmp_path / "assets" / "credly-badges.svg"
    outputs = tmp_path / "github-output"
    monkeypatch.setattr(mod, "fetch_badges", lambda username: {"data": FROZEN_BADGES})
    settings = {
        "CREDLY_USERNAME": "someone",
        "OUTPUT": output,
        "README_PATH": str(readme),
        "SVG_PATH": str(svg),
        "SVG_GROUPS": "two",
        "SVG_PER_ROW": "6,8",
        "ACCENT": "#60a5fa",
        "GITHUB_OUTPUT": str(outputs),
    }
    for name, value in settings.items():
        monkeypatch.setattr(mod, name, value)
    return readme, svg, outputs


def test_main_readme_mode_writes_only_the_readme(tmp_path, monkeypatch, fetched):
    readme, svg, outputs = stub_profile(tmp_path, monkeypatch, "readme")

    mod.main()

    assert readme.read_text(encoding="utf-8") == (
        f"<!-- CREDLY-BADGES:START -->\n{FROZEN_SECTION}\n<!-- CREDLY-BADGES:END -->\n"
    )
    assert not svg.exists()
    assert fetched == []  # README mode never downloads an image
    assert outputs.read_text(encoding="utf-8") == (
        "total-badges=4\ncertifications-count=2\nprofessional-count=1\n"
        "knowledge-count=1\nchanged=true\n"
    )


def test_main_svg_mode_writes_the_card_and_leaves_the_readme(
    tmp_path, monkeypatch, fetched
):
    readme, svg, outputs = stub_profile(tmp_path, monkeypatch, "svg")

    mod.main()

    assert readme.read_text(encoding="utf-8") == MARKERS
    assert ET.parse(svg).getroot().tag == f"{SVG}svg"
    assert outputs.read_text(encoding="utf-8").endswith("changed=true\n")


def test_main_svg_mode_reports_no_change_on_a_rerun(tmp_path, monkeypatch, fetched):
    _, svg, outputs = stub_profile(tmp_path, monkeypatch, "svg")
    mod.main()
    first = svg.read_bytes()

    mod.main()

    assert svg.read_bytes() == first
    assert outputs.read_text(encoding="utf-8").endswith("changed=false\n")


def test_main_rejects_an_unknown_output_before_fetching(tmp_path, monkeypatch):
    stub_profile(tmp_path, monkeypatch, "pdf")
    monkeypatch.setattr(mod, "fetch_badges", lambda username: pytest.fail("fetched"))

    with pytest.raises(SystemExit):
        mod.main()
