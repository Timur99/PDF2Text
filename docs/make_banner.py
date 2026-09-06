"""Баннер для GitHub: социальное превью 1280x640.

Строится из визуального языка самого продукта — карты страниц, где синим
отмечены те, что потребовали OCR. Палитра совпадает с тёмной темой
интерфейса (`frontend/styles.css`).

    python docs/make_banner.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "images" / "social-preview.png"

W, H = 1280, 640
SCALE = 2  # рисуем вдвое крупнее и уменьшаем — сглаживание текста и скруглений
PAD = 84

BG = "#1e1e1e"
LABEL = "#f5f5f7"
LABEL_2 = "#98989d"
LABEL_3 = "#6e6e73"
CELL = "#2c2c2e"
ACCENT = "#0a84ff"
ACCENT_TEXT = "#cde3fa"

PAGES = 22
OCR_PAGE = 11

FONTS = [
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
]


def font(size: int, medium: bool = False) -> ImageFont.FreeTypeFont:
    """Начертания только 400 и 500 — как записано в DESIGN.md.

    В HelveticaNeue.ttc индекс 10 — Medium, 0 — Regular. Индекс 2 это Italic,
    а не Bold: подобранный «на глаз» индекс даст курсив.
    """
    for path in FONTS:
        if not Path(path).exists():
            continue
        for index in ((10, 1, 0) if medium else (0,)):
            try:
                return ImageFont.truetype(path, size * SCALE, index=index)
            except (OSError, ValueError):
                continue
    return ImageFont.load_default()


def main() -> None:
    image = Image.new("RGB", (W * SCALE, H * SCALE), BG)
    draw = ImageDraw.Draw(image)
    pad = PAD * SCALE

    draw.text((pad, 118 * SCALE), "PDF2Text", font=font(88, medium=True), fill=LABEL)
    draw.text((pad, 244 * SCALE), "Текст из PDF и фото. Локально", font=font(34), fill=LABEL_2)
    draw.text(
        (pad, 300 * SCALE),
        "OCR запускается только там, где текст не читается",
        font=font(26),
        fill=LABEL_3,
    )

    # карта страниц — та же, что на экране результата
    strip_top = 430 * SCALE
    cell_h = 54 * SCALE
    gap = 9 * SCALE
    width = W * SCALE - pad * 2
    cell_w = (width - gap * (PAGES - 1)) / PAGES

    for page in range(1, PAGES + 1):
        x = pad + (page - 1) * (cell_w + gap)
        is_ocr = page == OCR_PAGE
        draw.rounded_rectangle(
            [x, strip_top, x + cell_w, strip_top + cell_h],
            radius=9 * SCALE,
            fill=ACCENT if is_ocr else CELL,
        )
        number = str(page)
        glyph = font(19)
        box = draw.textbbox((0, 0), number, font=glyph)
        draw.text(
            (x + (cell_w - (box[2] - box[0])) / 2, strip_top + (cell_h - (box[3] - box[1])) / 2 - box[1]),
            number,
            font=glyph,
            fill=ACCENT_TEXT if is_ocr else LABEL_3,
        )

    draw.text(
        (pad, 512 * SCALE),
        f"{PAGES} страницы · 1 через OCR · остальное взято напрямую",
        font=font(22),
        fill=LABEL_3,
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.resize((W, H), Image.LANCZOS).save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
