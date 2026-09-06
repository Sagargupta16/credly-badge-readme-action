"""Tests for update-credly-badges.py (pure functions, no network)."""

import importlib.util
from pathlib import Path

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
    assert not professional and not knowledge


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
    assert content.startswith("# Hi\n") and content.endswith("footer\n")


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

    import pytest

    with pytest.raises(SystemExit):
        mod.update_readme("anything")
