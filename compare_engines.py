"""Сравнение OCR-движков с настоящим эталоном.

Идея: у текстового PDF внутри уже лежит правильный текст. Рендерим страницу
в картинку, распознаём её движками и сравниваем с этим текстом. Эталон получается
бесплатно и точно — вычитывать вручную ничего не надо.

Плюс искусственные искажения (наклон, шум, размытие, контраст, JPEG) — грубая
замена сканам и фото, которых в корпусе пока нет. Эталон при этом тот же самый.

    .venv/bin/python compare_engines.py

Важно про интерпретацию: CER считается против текстового слоя, а его порядок
чтения не всегда совпадает с порядком, в котором движок обходит страницу.
Поэтому абсолютный CER здесь завышен у обоих и годится только для сравнения
движков между собой. Порядко-независимую картину даёт F1 по словам.
"""

from __future__ import annotations

import io
import statistics
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter

INPUTS = Path("inputs")
OUT = Path("benchmark_outputs/engine_comparison")
DPI = 150
MAX_PAGES = 5
MIN_CHARS = 400
# Признак сломанной кодировки шрифтов: такой текстовый слой эталоном быть не может.
BROKEN_MARKERS = ("ĸ", "�")


def norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = norm(reference), norm(hypothesis)
    if not ref:
        return float("nan")
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        current = [i]
        for j, h in enumerate(hyp, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h)))
        previous = current
    return previous[-1] / len(ref)


def word_f1(reference: str, hypothesis: str) -> float:
    """F1 по мультимножеству слов — не зависит от порядка обхода страницы."""
    ref = Counter(norm(reference).lower().split())
    hyp = Counter(norm(hypothesis).lower().split())
    if not ref or not hyp:
        return 0.0
    common = sum((ref & hyp).values())
    if not common:
        return 0.0
    precision = common / sum(hyp.values())
    recall = common / sum(ref.values())
    return 2 * precision * recall / (precision + recall)


def render(pdf: Path, page_no: int) -> Image.Image:
    with pymupdf.open(pdf) as document:
        page = document[page_no - 1]
        scale = min(DPI / 72, 1400 / max(page.rect.width, page.rect.height, 1))
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def degrade(image: Image.Image, kind: str) -> Image.Image:
    """Грубая имитация скана и фото. Не заменяет настоящий корпус."""
    if kind == "чистая":
        return image
    if kind == "наклон 1.5°":
        return image.rotate(1.5, resample=Image.BICUBIC, fillcolor=(255, 255, 255), expand=True)
    if kind == "размытие+шум":
        blurred = image.filter(ImageFilter.GaussianBlur(0.8))
        buffer = io.BytesIO()
        blurred.save(buffer, format="JPEG", quality=35)
        buffer.seek(0)
        return Image.open(buffer).convert("RGB")
    raise ValueError(kind)


# Русский текст с заведомо точным эталоном. В inputs/ чистой русской страницы
# нет вообще: у одного файла сломана кодировка шрифтов, у другого слайды-картинки
# без текстового слоя. А русский — основной язык продукта, и мерить его надо.
RUSSIAN_SAMPLES = [
    """Цена — это количество денег, уплачиваемое за единицу товара, то есть
продукции, работ или услуг. С другой стороны, цену можно описать как
маркетинговый инструмент, с помощью которого компания быстро воздействует
на свои доходы и прибыль. Ниже приведена упрощённая формула расчёта.""",
    """Перекрёстная эластичность спроса показывает, насколько изменится спрос
на один товар при изменении цены другого. Если коэффициент положительный,
товары взаимозаменяемы; если отрицательный — взаимодополняемы. Значение
около нуля означает, что товары независимы друг от друга.""",
    """Настоящим подтверждается бронирование номера в гостинице «Изумруд».
Номер подтверждения: 4585-762-950. Заезд одиннадцатого февраля в четырнадцать
часов, отъезд двадцатого февраля в десять часов. Стоимость проживания
составляет 26 663 рубля, включая налог на добавленную стоимость.""",
]

FONT = "/System/Library/Fonts/Supplemental/Times New Roman.ttf"


def make_russian_page(text: str, index: int) -> tuple[Path, str]:
    """Рисует русский текст в PDF. Эталон — ровно то, что нарисовали."""
    document = pymupdf.open()
    page = document.new_page()
    box = pymupdf.Rect(60, 60, page.rect.width - 60, page.rect.height - 60)
    page.insert_textbox(box, text, fontfile=FONT, fontname="tnr", fontsize=13, lineheight=1.5)
    path = OUT / f"russian_{index}.pdf"
    document.save(path)
    document.close()
    return path, text


def pick_pages() -> list[tuple[str, int, str, Path]]:
    """Страницы-эталоны: сначала настоящие из inputs/, затем сгенерированные русские."""
    picked: list[tuple[str, int, str, Path]] = []
    for pdf in sorted(INPUTS.glob("*.pdf")):
        taken = 0
        with pymupdf.open(pdf) as document:
            for index in range(document.page_count):
                if taken >= 3:
                    break
                text = document[index].get_text()
                if len(norm(text)) < MIN_CHARS:
                    continue
                if any(marker in text for marker in BROKEN_MARKERS):
                    continue  # сломанная кодировка — эталоном служить не может
                # Слипшиеся слова выдают текстовый слой, который сам получен плохим
                # OCR (так у конспекта DLS): эталоном он быть не может.
                words = norm(text).split()
                long_words = sum(1 for w in words if len(w) > 14)
                if words and long_words / len(words) > 0.04:
                    continue
                picked.append((pdf.name, index + 1, text, pdf))
                taken += 1
    OUT.mkdir(parents=True, exist_ok=True)
    for number, sample in enumerate(RUSSIAN_SAMPLES, start=1):
        path, truth = make_russian_page(sample, number)
        picked.append((f"[сгенерировано] русский {number}", 1, truth, path))
    return picked


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pages = pick_pages()
    if not pages:
        print("В inputs/ нет текстовых страниц, годных в эталон.")
        return 1

    from backend.engines import AppleVisionEngine, PaddleOCREngine

    engines = [AppleVisionEngine(), PaddleOCREngine()]
    engines = [engine for engine in engines if engine.available()]
    print(f"движки: {', '.join(e.name for e in engines)}")
    print(f"страниц-эталонов: {len(pages)}\n")

    results: dict[tuple[str, str], list[tuple[float, float, float]]] = {}
    for label, page_no, truth, pdf in pages:
        base = render(pdf, page_no)
        for kind in ("чистая", "наклон 1.5°", "размытие+шум"):
            image_path = OUT / f"{abs(hash(label)) % 1000}_{page_no}_{kind.split()[0]}.png"
            degrade(base, kind).save(image_path)
            for engine in engines:
                started = time.perf_counter()
                text = engine.recognize_images([(page_no, image_path)], "ru")[0].text
                elapsed = time.perf_counter() - started
                group = "русский" if label.startswith("[сгенерировано]") else "из inputs/"
                results.setdefault((engine.name, kind, group), []).append(
                    (cer(truth, text), word_f1(truth, text), elapsed)
                )
            print(f"  {label[:34]:<34} стр.{page_no:<3} {kind}", flush=True)

    print(f"\n{'выборка':<12} {'условие':<16} {'движок':<11} {'CER':>7} {'F1 слов':>9} {'сек/стр':>9}")
    print("-" * 70)
    for group in ("русский", "из inputs/"):
        for kind in ("чистая", "наклон 1.5°", "размытие+шум"):
            for engine in engines:
                rows = results.get((engine.name, kind, group))
                if not rows:
                    continue
                print(
                    f"{group:<12} {kind:<16} {engine.name:<11} "
                    f"{statistics.mean(r[0] for r in rows):>7.3f} "
                    f"{statistics.mean(r[1] for r in rows):>9.3f} "
                    f"{statistics.mean(r[2] for r in rows):>9.2f}"
                )
    print("\nCER завышен у обоих: порядок текстового слоя не всегда совпадает")
    print("с порядком обхода страницы. Сравнивать движки между собой, не с нулём.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
