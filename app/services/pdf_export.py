from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


def _hex_to_reportlab_color(value: str):
    return colors.HexColor(value)


def _register_cyrillic_fonts() -> tuple[str, str, str]:
    """
    Register a Unicode-capable font for Cyrillic output.
    Returns (regular, bold, italic) font names.
    """
    candidates = [
        (
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("C:/Windows/Fonts/ariali.ttf"),
        ),
        (
            Path("C:/Windows/Fonts/calibri.ttf"),
            Path("C:/Windows/Fonts/calibrib.ttf"),
            Path("C:/Windows/Fonts/calibrii.ttf"),
        ),
    ]
    for regular, bold, italic in candidates:
        if regular.exists() and bold.exists() and italic.exists():
            if "UI-Regular" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("UI-Regular", str(regular)))
            if "UI-Bold" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("UI-Bold", str(bold)))
            if "UI-Italic" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("UI-Italic", str(italic)))
            return "UI-Regular", "UI-Bold", "UI-Italic"
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


def _wrap_text(text: str, font_name: str, font_size: float, max_width: float) -> list[str]:
    words = (text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_wrapped(
    c: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    max_width: float,
    font_name: str,
    font_size: float,
    line_height: float,
    max_lines: int | None = None,
) -> float:
    lines = _wrap_text(text, font_name, font_size, max_width)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines:
            last = lines[-1]
            while pdfmetrics.stringWidth(f"{last}...", font_name, font_size) > max_width and last:
                last = last[:-1]
            lines[-1] = f"{last}..."
    c.setFont(font_name, font_size)
    cy = y
    for line in lines:
        c.drawString(x, cy, line)
        cy -= line_height
    return cy


def build_palette_pdf(record: dict) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    font_regular, font_bold, font_italic = _register_cyrillic_fonts()

    input_data = record["input"]
    palette = record["palette"]
    checks = record["checks"]

    c.setFont(font_bold, 14)
    c.drawString(20 * mm, height - 20 * mm, "Генератор палитры коллекции")

    meta = (
        f"season={input_data['season']}  audience={input_data['audience']}  "
        f"style={input_data['style']}  geography={input_data['geography']}"
    )
    _draw_wrapped(
        c=c,
        text=meta,
        x=20 * mm,
        y=height - 26 * mm,
        max_width=width - 40 * mm,
        font_name=font_regular,
        font_size=9,
        line_height=3.8 * mm,
        max_lines=2,
    )

    top = height - 38 * mm
    card_w = (width - 46 * mm) / 3
    card_h = 42 * mm

    for idx, color_item in enumerate(palette):
        row = idx // 3
        col = idx % 3
        x = 15 * mm + col * (card_w + 8 * mm)
        y = top - row * (card_h + 8 * mm)

        c.setFillColor(_hex_to_reportlab_color(color_item["hex"]))
        c.rect(x, y - card_h, card_w, card_h, fill=1, stroke=0)

        c.setFillColor(colors.black)
        c.rect(x, y - card_h, card_w, card_h, fill=0, stroke=1)

        text_x = x + 2 * mm
        text_y = y - 5 * mm
        text_w = card_w - 4 * mm
        text_y = _draw_wrapped(
            c=c,
            text=f"{color_item['role']} ({color_item['percent']}%)",
            x=text_x,
            y=text_y,
            max_width=text_w,
            font_name=font_bold,
            font_size=8.6,
            line_height=3.5 * mm,
            max_lines=1,
        )

        l, a, b = color_item["lab"]
        text_y = _draw_wrapped(
            c=c,
            text=f"HEX {color_item['hex']}",
            x=text_x,
            y=text_y,
            max_width=text_w,
            font_name=font_regular,
            font_size=7.8,
            line_height=3.3 * mm,
            max_lines=1,
        )
        text_y = _draw_wrapped(
            c=c,
            text=f"LAB {l:.2f}, {a:.2f}, {b:.2f}",
            x=text_x,
            y=text_y,
            max_width=text_w,
            font_name=font_regular,
            font_size=7.8,
            line_height=3.3 * mm,
            max_lines=1,
        )

        top1 = color_item["pantone_matches"][0] if color_item["pantone_matches"] else None
        if top1:
            _draw_wrapped(
                c=c,
                text=f"TCX: {top1['code']} {top1['name']} (dE00={top1['delta_e00']:.2f})",
                x=text_x,
                y=text_y,
                max_width=text_w,
                font_name=font_regular,
                font_size=7.4,
                line_height=3.1 * mm,
                max_lines=3,
            )

    c.setFont(font_bold, 10)
    c.drawString(20 * mm, 54 * mm, "Рекомендованное распределение, %")

    bar_x = 20 * mm
    bar_y = 44 * mm
    bar_w = width - 40 * mm
    bar_h = 8 * mm

    cursor = bar_x
    for item in palette:
        segment_w = bar_w * (item["percent"] / 100)
        c.setFillColor(_hex_to_reportlab_color(item["hex"]))
        c.rect(cursor, bar_y, segment_w, bar_h, fill=1, stroke=0)
        cursor += segment_w

    c.setFillColor(colors.black)
    c.rect(bar_x, bar_y, bar_w, bar_h, fill=0, stroke=1)

    c.setFont(font_regular, 8)
    c.drawString(20 * mm, 34 * mm, f"min ΔE00: {checks['min_delta_e00']}")
    if checks["warnings"]:
        _draw_wrapped(
            c=c,
            text="Предупреждения: " + "; ".join(checks["warnings"]),
            x=20 * mm,
            y=30 * mm,
            max_width=width - 40 * mm,
            font_name=font_regular,
            font_size=8,
            line_height=3.3 * mm,
            max_lines=2,
        )

    c.setFont(font_italic, 8)
    c.drawString(
        20 * mm,
        20 * mm,
        "Цветовые значения расчетные, зависят от среды/материала.",
    )

    c.showPage()
    c.save()
    return buffer.getvalue()
