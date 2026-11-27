"""Typeset a cover image for the EPUB bookshelf and opening page."""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FONT_PAIRS = (
    (("NotoSerifCJK-Bold.ttc", 2), ("NotoSansCJK-Regular.ttc", 2)),
    (("Songti.ttc", 0), ("PingFang.ttc", 0)),
    (("simsun.ttc", 0), ("msyh.ttc", 0)),
)
TITLE_WORDS = re.compile(r"[A-Za-z0-9_+#./=-]+|[^\s][，、。；：？！）》】」』]*| +")


def cover_fonts() -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont] | None:
    for (serif, serif_index), (sans, sans_index) in FONT_PAIRS:
        try:
            return (
                ImageFont.truetype(serif, size=68, index=serif_index),
                ImageFont.truetype(sans, size=30, index=sans_index),
            )
        except OSError:
            continue
    return None


def wrap_title(title: str, font: ImageFont.FreeTypeFont, width: int) -> str:
    lines = []
    line = ""
    for word in TITLE_WORDS.findall(title):
        # Split identifiers that are wider than the cover.
        parts = word if font.getlength(word) > width else (word,)
        for part in parts:
            if line and font.getlength(line + part.rstrip()) > width:
                lines.append(line.rstrip())
                line = part.lstrip()
            else:
                line += part if line else part.lstrip()
    lines.append(line.rstrip())
    return "\n".join(lines)


def write_cover(
    path: Path,
    title: str,
    author: str,
    date: str,
    fonts: tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont],
) -> None:
    serif, sans = fonts
    image = Image.new("RGB", (720, 1080), "#f3efe5")
    draw = ImageDraw.Draw(image)
    ink, accent = "#163235", "#3c6863"
    left, right = 80, 640

    draw.rectangle((0, 0, 23, 1080), fill=ink)
    draw.text((left, 86), "技术学习笔记", font=sans, fill=accent)
    draw.line((left, 151, right, 151), fill=accent, width=2)

    main_title, separator, subtitle = title.partition("：")
    if not separator or not main_title.strip() or not subtitle.strip():
        main_title, subtitle = title, ""
    for size in range(68, 20, -4):
        title_font = serif.font_variant(size=size)
        subtitle_font = serif.font_variant(size=max(25, round(.57 * size)))
        caption = wrap_title(main_title.strip(), title_font, right - left)
        subtitle_lines = wrap_title(subtitle.strip(), subtitle_font, right - left)
        spacing = round(size * 0.32)
        bounds = draw.multiline_textbbox(
            (0, 0), caption, font=title_font, spacing=spacing,
        )
        height = bounds[3] - bounds[1]
        subtitle_bounds = draw.multiline_textbbox(
            (0, 0), subtitle_lines, font=subtitle_font, spacing=12,
        )
        subtitle_height = subtitle_bounds[3] - subtitle_bounds[1]
        combined_height = height + (36 + subtitle_height if subtitle_lines else 0)
        if combined_height <= 530:
            break
    title_top = 235 + max(0, (470 - combined_height) // 3)
    draw.multiline_text(
        (left, title_top - bounds[1]), caption, font=title_font, spacing=spacing, fill=ink,
    )
    if subtitle_lines:
        draw.multiline_text(
            (left, title_top + height + 36 - subtitle_bounds[1]), subtitle_lines,
            font=subtitle_font, spacing=12, fill=accent,
        )

    draw.line((left, 923, right, 923), fill=accent, width=2)
    draw.text((left, 961), author, font=sans, fill=ink)
    draw.text((right, 961), date, font=sans, fill=ink, anchor="ra")
    image.save(path, optimize=True)
