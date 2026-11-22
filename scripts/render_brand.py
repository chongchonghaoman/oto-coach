"""Render the Oto mark, logos, and social banner.

Glyph outlines come from SIL OFL fonts and are embedded so the SVG does not
need those fonts at display time:

- Zen Old Mincho, Yoshimichi Ohira
- Noto Sans SC, Google
- Inter, Rasmus Andersson

The pitch contour is original geometry.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "brand"
FONT = Path("/tmp/oto-fonts")
INTER = Path("/usr/share/fonts/truetype/macos")

PAPER = "#F3EEE6"
INK = "#1A1814"
MUTED = "#8A8175"
VERMILION = "#C24532"
DARK = "#141311"
DARK_INK = "#F4F0E6"
DARK_MUTED = "#A79E93"
DARK_VERMILION = "#E25B45"


def load(path: Path) -> TTFont:
    return TTFont(str(path))


MINCHO = load(FONT / "ZenOldMincho-Regular.ttf")
SANS = load(FONT / "NotoSansSC-500.ttf")
SANS_TEXT = load(FONT / "NotoSansSC-400.ttf")
LATIN = load(INTER / "Inter-Medium.ttf")


def bounds(font: TTFont, char: str) -> tuple[float, float, float, float]:
    gs = font.getGlyphSet()
    name = font.getBestCmap()[ord(char)]
    pen = BoundsPen(gs)
    gs[name].draw(pen)
    return pen.bounds


def commands(font: TTFont, char: str) -> tuple[str, float]:
    gs = font.getGlyphSet()
    name = font.getBestCmap()[ord(char)]
    pen = SVGPathPen(gs)
    gs[name].draw(pen)
    return pen.getCommands(), gs[name].width


class Svg:
    def __init__(self, width: float, height: float, background: str | None):
        self.width = width
        self.height = height
        self.parts: list[str] = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Oto 音">',
            "<!-- Outlines: Zen Old Mincho (OFL, Yoshimichi Ohira); Noto Sans SC (OFL, Google); Inter (OFL, Rasmus Andersson). Pitch contour is original. -->",
        ]
        if background:
            self.parts.append(f'<rect width="100%" height="100%" fill="{background}"/>')

    def text(self, font: TTFont, text: str, x: float, baseline: float, size: float, fill: str, tracking: float = 0) -> float:
        upem = font["head"].unitsPerEm
        scale = size / upem
        cursor = 0.0
        glyphs: list[str] = []
        for char in text:
            if char == " ":
                cursor += upem * 0.33
                continue
            path, width = commands(font, char)
            if path:
                glyphs.append(f'<path d="{path}" transform="translate({cursor:.2f} 0)"/>')
            cursor += width + tracking * upem
        self.parts.append(
            f'<g fill="{fill}" transform="translate({x:.2f} {baseline:.2f}) scale({scale:.6f} {-scale:.6f})">'
            + "".join(glyphs)
            + "</g>"
        )
        return cursor * scale

    def width_of(self, font: TTFont, text: str, size: float, tracking: float = 0) -> float:
        upem = font["head"].unitsPerEm
        scale = size / upem
        cursor = 0.0
        for char in text:
            if char == " ":
                cursor += upem * 0.33
                continue
            _path, width = commands(font, char)
            cursor += width + tracking * upem
        return cursor * scale

    def glyph(self, font: TTFont, char: str, cx: float, cy: float, size: float, fill: str) -> None:
        upem = font["head"].unitsPerEm
        scale = size / upem
        x0, y0, x1, y1 = bounds(font, char)
        path, _width = commands(font, char)
        visual_cx = (x0 + x1) / 2
        visual_cy = (y0 + y1) / 2
        # Place the ink's visual center on (cx, cy). Font y is up; SVG y is down.
        origin_x = cx - visual_cx * scale
        origin_y = cy + visual_cy * scale
        self.parts.append(
            f'<g fill="{fill}" transform="translate({origin_x:.2f} {origin_y:.2f}) scale({scale:.6f} {-scale:.6f})">'
            f'<path d="{path}"/></g>'
        )

    def pitch(self, x: float, y: float, w: float, h: float, ink: str, accent: str, stroke: float) -> None:
        """Three morae. The fall after the second mora is the only color."""
        x1, x2, x3 = x + w * 0.08, x + w * 0.46, x + w * 0.90
        y_low, y_high = y + h * 0.72, y + h * 0.22
        r = max(2.4, stroke * 1.55)
        rise = (
            f"M {x1:.2f} {y_low:.2f} "
            f"C {x1 + w * 0.12:.2f} {y_low:.2f}, {x2 - w * 0.16:.2f} {y_high:.2f}, {x2:.2f} {y_high:.2f}"
        )
        fall = (
            f"M {x2:.2f} {y_high:.2f} "
            f"C {x2 + w * 0.10:.2f} {y_high:.2f}, {x3 - w * 0.08:.2f} {y_low:.2f}, {x3:.2f} {y_low:.2f}"
        )
        common = f'fill="none" stroke-linecap="round" stroke-width="{stroke:.2f}"'
        self.parts.append(f'<path d="{rise}" stroke="{ink}" {common}/>')
        self.parts.append(f'<path d="{fall}" stroke="{accent}" {common}/>')
        self.parts.append(f'<circle cx="{x1:.2f}" cy="{y_low:.2f}" r="{r:.2f}" fill="{ink}"/>')
        self.parts.append(f'<circle cx="{x2:.2f}" cy="{y_high:.2f}" r="{r:.2f}" fill="{ink}"/>')
        self.parts.append(f'<circle cx="{x3:.2f}" cy="{y_low:.2f}" r="{r:.2f}" fill="{accent}"/>')

    def save(self, path: Path) -> None:
        self.parts.append("</svg>")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.parts), encoding="utf-8")


def logo(path: Path, *, dark: bool) -> None:
    bg = DARK if dark else PAPER
    ink = DARK_INK if dark else INK
    muted = DARK_MUTED if dark else MUTED
    accent = DARK_VERMILION if dark else VERMILION
    svg = Svg(1024, 1024, bg)
    svg.glyph(MINCHO, "音", 512, 430, 560, ink)
    svg.pitch(332, 690, 360, 92, ink, accent, 5.5)
    word = "OTO"
    tracking = 0.34
    size = 42
    width = svg.width_of(LATIN, word, size, tracking)
    svg.text(LATIN, word, (1024 - width) / 2, 880, size, muted, tracking)
    svg.save(path)


def banner(path: Path) -> None:
    svg = Svg(1280, 640, PAPER)
    svg.glyph(MINCHO, "音", 318, 268, 420, INK)
    svg.pitch(138, 478, 360, 72, INK, VERMILION, 4.25)

    svg.text(LATIN, "OTO", 700, 196, 22, VERMILION, 0.48)
    svg.parts.append(f'<rect x="700" y="222" width="48" height="2.5" fill="{VERMILION}"/>')
    svg.text(SANS, "日语系统课", 700, 318, 64, INK, 0.02)
    svg.text(SANS_TEXT, "为中文母语者而写", 700, 382, 28, INK, 0.04)
    svg.text(SANS_TEXT, "从五十音到 N3", 700, 452, 24, MUTED, 0.06)
    meta_x = 700
    for index, part in enumerate(["同形异义词", "语法", "音高"]):
        meta_x += svg.text(SANS_TEXT, part, meta_x, 524, 20, MUTED, 0.03)
        if index < 2:
            meta_x += 14
            svg.parts.append(f'<circle cx="{meta_x:.2f}" cy="517" r="2" fill="{MUTED}"/>')
            meta_x += 14
    svg.save(path)


def png(svg: Path, dest: Path, width: int, height: int) -> None:
    subprocess.run(
        ["rsvg-convert", "-w", str(width), "-h", str(height), "-o", str(dest), str(svg)],
        check=True,
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    light = OUT / "logo-light.svg"
    dark = OUT / "logo-dark.svg"
    social = OUT / "banner.svg"
    logo(light, dark=False)
    logo(dark, dark=True)
    banner(social)
    png(light, OUT / "logo-light.png", 1024, 1024)
    png(dark, OUT / "logo-dark.png", 1024, 1024)
    png(social, OUT / "banner.png", 1280, 640)
    print(OUT)


if __name__ == "__main__":
    main()
