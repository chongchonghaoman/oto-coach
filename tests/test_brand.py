from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_brand_files_exist():
    brand = ROOT / "assets" / "brand"
    for name in ("logo-light.svg", "logo-dark.svg", "logo-light.png", "logo-dark.png", "banner.svg", "banner.png"):
        assert (brand / name).stat().st_size > 500
    banner = (brand / "banner.svg").read_text(encoding="utf-8")
    assert 'width="1280"' in banner and 'height="640"' in banner
    assert "音" in banner or "path" in banner
