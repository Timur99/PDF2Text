"""Иконки приложения PDF2Text.

Каждый размер рисуется отдельно со сверхсэмплингом x4 — при уменьшении
из одного мастера 1024px тонкие детали схлопываются в пятно. На размерах
меньше 128 px рисуется упрощённая версия: мелкие строки не разделяются.

Геометрия задаётся в координатах SVG-макета (холст 100, тело 4..96) и
переводится в сетку macOS: тело иконки 824/1024 от холста.

    python desktop/make_icon.py            # все варианты
    python desktop/make_icon.py stack      # только один

Сборка .icns (iconutil не работает под песочницей Claude Code):

    iconutil -c icns desktop/icons/AppIcon-stack.iconset \\
             -o desktop/icons/AppIcon-stack.icns
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ICONS = Path(__file__).resolve().parent / "icons"
SUPERSAMPLE = 4
SMALL = 128  # ниже этого порога рисуем упрощённую версию

SAND = "#ddc9a0"
INK = "#35302a"
VERMILION = "#c0492b"
CREAM = "#fffdf7"
SLATE = "#39424f"
BLUE = "#0060df"
GRAY = "#b3bcc9"

SIZES = {
    16: ["icon_16x16.png"],
    32: ["icon_16x16@2x.png", "icon_32x32.png"],
    64: ["icon_32x32@2x.png"],
    128: ["icon_128x128.png"],
    256: ["icon_128x128@2x.png", "icon_256x256.png"],
    512: ["icon_256x256@2x.png", "icon_512x512.png"],
    1024: ["icon_512x512@2x.png"],
}


class Canvas:
    """Холст в координатах макета: 4..96 — тело иконки, как в SVG."""

    def __init__(self, size: int) -> None:
        self.side = size * SUPERSAMPLE
        self.image = Image.new("RGBA", (self.side, self.side), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)
        self._scale = self.side / 1024

    def at(self, value: float) -> float:
        """Координата макета → пиксель холста."""
        return (100 + (value - 4) * 824 / 92) * self._scale

    def size_of(self, value: float) -> float:
        """Длина в координатах макета → длина в пикселях."""
        return value * 824 / 92 * self._scale

    def box(self, x, y, w, h, radius, fill, outline=None, width=0):
        self.draw.rounded_rectangle(
            [self.at(x), self.at(y), self.at(x + w), self.at(y + h)],
            radius=self.size_of(radius),
            fill=fill,
            outline=outline,
            width=int(self.size_of(width)) if width else 0,
        )

    def bar(self, x, y, w, h, fill):
        """Строка текста со скруглёнными торцами."""
        self.box(x, y, w, h, h / 2, fill)

    def circle(self, cx, cy, r, fill, outline=None, width=0):
        self.draw.ellipse(
            [self.at(cx - r), self.at(cy - r), self.at(cx + r), self.at(cy + r)],
            fill=fill,
            outline=outline,
            width=int(self.size_of(width)) if width else 0,
        )

    def thick_line(self, x0, y0, x1, y1, width, fill):
        """Линия с круглыми торцами: у PIL нет line-cap."""
        self.draw.line(
            [self.at(x0), self.at(y0), self.at(x1), self.at(y1)],
            fill=fill,
            width=int(self.size_of(width)),
        )
        for x, y in ((x0, y0), (x1, y1)):
            self.circle(x, y, width / 2, fill=fill)

    def body(self, fill):
        self.box(4, 4, 92, 92, 21, fill)

    def finish(self, size: int) -> Image.Image:
        return self.image.resize((size, size), Image.LANCZOS)


def draw_stack(c: Canvas, size: int) -> None:
    """Концепт 8: стопка страниц, красная — та, что ушла в OCR."""
    c.body(SAND)
    if size >= SMALL:
        c.box(42, 22, 30, 44, 4, VERMILION)
        c.box(28, 32, 30, 44, 4, CREAM)
        c.bar(34, 42, 18, 4, INK)
        c.bar(34, 51, 18, 4, INK)
        c.bar(34, 60, 11, 4, INK)
    else:
        # мельче — страницы уже и разнесены сильнее, иначе сливаются в пятно.
        # Кремовая близка по светлоте к песочному, поэтому с обводкой.
        c.box(48, 18, 26, 42, 4, VERMILION)
        c.box(24, 36, 26, 42, 4, CREAM, outline=INK, width=3)


def draw_loupe(c: Canvas, size: int) -> None:
    """Концепт 10: лупа над строкой текста."""
    c.body(SAND)
    if size >= SMALL:
        c.thick_line(58, 58, 74, 74, 9, INK)
        c.circle(44, 44, 21, fill=CREAM, outline=INK, width=6)
        c.bar(34, 38, 20, 5, VERMILION)
        c.bar(34, 47, 13, 5, VERMILION)
    else:
        c.thick_line(58, 58, 76, 76, 11, INK)
        c.circle(43, 43, 22, fill=CREAM, outline=INK, width=7)
        c.bar(32, 39, 22, 7, VERMILION)


def draw_page(c: Canvas, size: int) -> None:
    """Первая версия: страница, одна строка распознана. Оставлена для сравнения."""
    c.body(SLATE)
    c.box(25, 18, 50, 64, 5, CREAM)
    if size >= SMALL:
        for index, y in enumerate((30, 41, 52, 63)):
            c.bar(33, y, 34, 5, BLUE if index == 2 else GRAY)
    else:
        for index, y in enumerate((32, 46, 60)):
            c.bar(33, y, 34, 6, BLUE if index == 1 else GRAY)


VARIANTS = {
    "stack": ("AppIcon-stack", draw_stack),
    "loupe": ("AppIcon-loupe", draw_loupe),
    "page": ("AppIcon-page", draw_page),
}


def build(variant: str) -> Path:
    name, painter = VARIANTS[variant]
    out = ICONS / f"{name}.iconset"
    out.mkdir(parents=True, exist_ok=True)
    for size, filenames in SIZES.items():
        canvas = Canvas(size)
        painter(canvas, size)
        icon = canvas.finish(size)
        for filename in filenames:
            icon.save(out / filename)
    return out


def main() -> None:
    requested = sys.argv[1:] or list(VARIANTS)
    unknown = [name for name in requested if name not in VARIANTS]
    if unknown:
        raise SystemExit(f"Неизвестный вариант: {', '.join(unknown)}. Есть: {', '.join(VARIANTS)}")
    for variant in requested:
        print(build(variant))


if __name__ == "__main__":
    main()
