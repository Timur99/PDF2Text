"""Batch runner for ocr_engines_benchmark.ipynb over every file in inputs/."""

from __future__ import annotations

import importlib.util
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
INPUTS_DIR = ROOT / "inputs"
OUTPUT_ROOT = ROOT / "benchmark_outputs"
LANG = "ru"
MAX_PAGES: int | None = None
MINERU_BACKEND = "pipeline"
UNLIMITED_MODEL = "baidu/Unlimited-OCR"
UNLIMITED_MAX_PAGES = 40

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
RESULTS: dict[str, dict[str, Any]] = {}


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def safe_stem(path: Path) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in path.stem)
    return cleaned[:80] or "document"


def record(file_name: str, engine: str, started: float, status: str, **details: Any) -> None:
    RESULTS.setdefault(file_name, {})[engine] = {
        "status": status,
        "seconds": round(time.perf_counter() - started, 3),
        **details,
    }


def make_jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): make_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [make_jsonable(v) for v in value]
    for attr in ("json", "to_json", "to_dict"):
        candidate = getattr(value, attr, None)
        if candidate is not None:
            candidate = candidate() if callable(candidate) else candidate
            if isinstance(candidate, str):
                try:
                    candidate = json.loads(candidate)
                except json.JSONDecodeError:
                    return candidate
            return make_jsonable(candidate)
    return str(value)


def collect_text(value: Any, texts: list[str]) -> None:
    if isinstance(value, dict):
        if isinstance(value.get("rec_texts"), list):
            texts.extend(str(x) for x in value["rec_texts"])
        else:
            for child in value.values():
                collect_text(child, texts)
    elif isinstance(value, list):
        if (
            len(value) == 2
            and isinstance(value[1], (list, tuple))
            and value[1]
            and isinstance(value[1][0], str)
        ):
            texts.append(value[1][0])
        else:
            for child in value:
                collect_text(child, texts)


def prepare_page_images(path: Path, out_dir: Path, dpi: int = 150) -> list[Path]:
    if path.suffix.lower() != ".pdf":
        return [path]
    if not has_module("pymupdf"):
        raise RuntimeError("Для PDF установите pymupdf: pip install pymupdf")

    import pymupdf as fitz

    out_dir.mkdir(parents=True, exist_ok=True)
    pages: list[Path] = []
    with fitz.open(path) as document:
        page_count = document.page_count if MAX_PAGES is None else min(document.page_count, MAX_PAGES)
        for index in range(page_count):
            page = document[index]
            # На 18 GB RAM server/high-DPI рендер уходит в своп. Держим длинную сторону <= 1400.
            scale = min(dpi / 72, 1400 / max(page.rect.width, page.rect.height, 1))
            output = out_dir / f"page_{index + 1:04d}.png"
            page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).save(output)
            pages.append(output)
    return pages


def run_paddle(file_name: str, page_images: list[Path], out_dir: Path, paddle: Any) -> None:
    started = time.perf_counter()
    try:
        if paddle is None:
            raise RuntimeError("PaddleOCR не установлен; выполните pip install paddlepaddle paddleocr")

        raw_pages = []
        for index, page in enumerate(page_images, start=1):
            page_started = time.perf_counter()
            try:
                raw_pages.append(list(paddle.predict(str(page))))
            except TypeError:
                raw_pages.append(paddle.ocr(str(page), cls=True))
            print(
                f"  page {index}/{len(page_images)} in {time.perf_counter() - page_started:.1f}s",
                flush=True,
            )

        paddle_data = make_jsonable(raw_pages)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(
            json.dumps(paddle_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        texts: list[str] = []
        collect_text(paddle_data, texts)
        paddle_text = "\n".join(texts)
        (out_dir / "result.txt").write_text(paddle_text, encoding="utf-8")
        record(
            file_name,
            "PaddleOCR",
            started,
            "ok",
            pages=len(page_images),
            chars=len(paddle_text),
            output=str(out_dir),
            preview=paddle_text[:1500],
        )
        print(f"[PaddleOCR] {file_name}: {len(page_images)} pages, {len(paddle_text)} chars")
    except Exception as exc:
        record(file_name, "PaddleOCR", started, "error", error=f"{type(exc).__name__}: {exc}")
        print(f"[PaddleOCR] {file_name}: ERROR {exc}")


def run_vision(file_name: str, page_images: list[Path], out_dir: Path) -> None:
    """Apple Vision — встроенный в macOS OCR. Ноль мегабайт в бандле.

    Требует pyobjc-framework-Vision и -Quartz. Изображение грузим через
    CGImageSource: initWithURL_options_ на этой связке молча отдаёт
    zero-dimensioned image.
    """
    started = time.perf_counter()
    try:
        if not has_module("Vision") or not has_module("Quartz"):
            raise RuntimeError(
                "Нужны pyobjc: pip install pyobjc-framework-Vision pyobjc-framework-Quartz"
            )

        import Quartz
        import Vision
        from Foundation import NSURL

        out_dir.mkdir(parents=True, exist_ok=True)
        texts: list[str] = []
        scores: list[float] = []
        for page in page_images:
            url = NSURL.fileURLWithPath_(str(page.resolve()))
            source = Quartz.CGImageSourceCreateWithURL(url, None)
            if source is None:
                raise RuntimeError(f"Не удалось прочитать изображение: {page}")
            image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)

            request = Vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
            request.setRecognitionLanguages_(["ru-RU" if LANG == "ru" else LANG, "en-US"])
            request.setUsesLanguageCorrection_(True)
            handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, None)
            ok, error = handler.performRequests_error_([request], None)
            if not ok:
                raise RuntimeError(str(error))
            for observation in request.results() or []:
                candidates = observation.topCandidates_(1)
                if candidates:
                    texts.append(str(candidates[0].string()))
                    scores.append(float(candidates[0].confidence()))

        vision_text = "\n".join(texts)
        (out_dir / "result.txt").write_text(vision_text, encoding="utf-8")
        record(
            file_name,
            "Apple Vision",
            started,
            "ok",
            pages=len(page_images),
            chars=len(vision_text),
            mean_confidence=round(sum(scores) / len(scores), 4) if scores else None,
            output=str(out_dir),
            preview=vision_text[:1500],
        )
        print(f"[Apple Vision] {file_name}: {len(page_images)} pages, {len(vision_text)} chars")
    except Exception as exc:
        record(file_name, "Apple Vision", started, "error", error=f"{type(exc).__name__}: {exc}")
        print(f"[Apple Vision] {file_name}: ERROR {exc}")


def run_mineru(file_name: str, input_path: Path, out_dir: Path) -> None:
    started = time.perf_counter()
    try:
        mineru_executable = shutil.which("mineru")
        if not mineru_executable:
            raise RuntimeError("CLI mineru не найден. Установите MinerU в активное окружение.")

        out_dir.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [
                mineru_executable,
                "-p",
                str(input_path.resolve()),
                "-o",
                str(out_dir.resolve()),
                "-b",
                MINERU_BACKEND,
            ],
            text=True,
            capture_output=True,
            timeout=3600,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr[-4000:] or completed.stdout[-4000:])

        markdown_files = sorted(out_dir.rglob("*.md"))
        markdown = "\n\n".join(path.read_text(encoding="utf-8") for path in markdown_files)
        record(
            file_name,
            "MinerU",
            started,
            "ok",
            backend=MINERU_BACKEND,
            chars=len(markdown),
            markdown_files=len(markdown_files),
            output=str(out_dir),
            preview=markdown[:1500],
        )
        print(f"[MinerU] {file_name}: {len(markdown)} chars")
    except subprocess.TimeoutExpired:
        record(file_name, "MinerU", started, "error", error="TimeoutExpired: превышен лимит 3600 сек")
        print(f"[MinerU] {file_name}: timeout")
    except Exception as exc:
        record(file_name, "MinerU", started, "error", error=f"{type(exc).__name__}: {exc}")
        print(f"[MinerU] {file_name}: ERROR {exc}")


def run_unlimited(file_name: str, page_images: list[Path], out_dir: Path) -> None:
    started = time.perf_counter()
    try:
        if not has_module("torch") or not has_module("transformers"):
            record(file_name, "Unlimited OCR", started, "skipped", reason="torch/transformers не установлены")
            print(f"[Unlimited OCR] {file_name}: skipped (no torch/transformers)")
            return

        import torch
        from transformers import AutoModel, AutoTokenizer

        if not torch.cuda.is_available():
            record(file_name, "Unlimited OCR", started, "skipped", reason="NVIDIA CUDA недоступна")
            print(f"[Unlimited OCR] {file_name}: skipped (no CUDA)")
            return

        out_dir.mkdir(parents=True, exist_ok=True)
        selected_pages = [str(path) for path in page_images[:UNLIMITED_MAX_PAGES]]
        tokenizer = AutoTokenizer.from_pretrained(UNLIMITED_MODEL, trust_remote_code=True)
        model = (
            AutoModel.from_pretrained(
                UNLIMITED_MODEL,
                trust_remote_code=True,
                use_safetensors=True,
                torch_dtype=torch.bfloat16,
            )
            .eval()
            .cuda()
        )
        torch.cuda.reset_peak_memory_stats()
        if len(selected_pages) == 1:
            model.infer(
                tokenizer,
                prompt="<image>document parsing.",
                image_file=selected_pages[0],
                output_path=str(out_dir),
                base_size=1024,
                image_size=640,
                crop_mode=True,
                max_length=32768,
                no_repeat_ngram_size=35,
                ngram_window=128,
                save_results=True,
            )
        else:
            model.infer_multi(
                tokenizer,
                prompt="<image>Multi page parsing.",
                image_files=selected_pages,
                output_path=str(out_dir),
                image_size=1024,
                max_length=32768,
                no_repeat_ngram_size=35,
                ngram_window=1024,
                save_results=True,
            )
        text_files = sorted(out_dir.rglob("*.txt")) + sorted(out_dir.rglob("*.md"))
        unlimited_text = "\n\n".join(
            path.read_text(encoding="utf-8", errors="replace") for path in text_files
        )
        record(
            file_name,
            "Unlimited OCR",
            started,
            "ok",
            pages=len(selected_pages),
            chars=len(unlimited_text),
            peak_vram_gb=round(torch.cuda.max_memory_allocated() / 1024**3, 2),
            output=str(out_dir),
            preview=unlimited_text[:1500],
        )
        print(f"[Unlimited OCR] {file_name}: {len(unlimited_text)} chars")
        del model
        torch.cuda.empty_cache()
    except Exception as exc:
        record(file_name, "Unlimited OCR", started, "error", error=f"{type(exc).__name__}: {exc}")
        print(f"[Unlimited OCR] {file_name}: ERROR {exc}")


def load_paddle() -> Any:
    if not has_module("paddleocr"):
        return None
    from paddleocr import PaddleOCR

    from backend.engines.paddle import recognition_model

    try:
        # mobile + без unwarping: server_det на M3 Pro 18GB съел 30GB и ушёл в своп
        kwargs = {
            "lang": LANG,
            "text_detection_model_name": "PP-OCRv5_mobile_det",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        }
        # PaddleOCR игнорирует lang, когда задано имя модели: без этой строки
        # для русского берётся латинская PP-OCRv6_medium_rec и кириллица теряется.
        recognition = recognition_model(LANG)
        if recognition is not None:
            kwargs["text_recognition_model_name"] = recognition
        return PaddleOCR(**kwargs)
    except TypeError:
        return PaddleOCR(lang=LANG, use_angle_cls=True)


def main() -> None:
    inputs = sorted(
        p
        for p in INPUTS_DIR.iterdir()
        if p.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
    )
    print(
        {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "inputs": [p.name for p in inputs],
            "paddleocr_installed": has_module("paddleocr"),
            "mineru_cli": shutil.which("mineru"),
            "torch_installed": has_module("torch"),
            "apple_vision": has_module("Vision"),
        }
    )
    if not inputs:
        raise SystemExit(f"В {INPUTS_DIR} нет PDF/изображений")

    print("Loading PaddleOCR once...")
    paddle = load_paddle()
    print("PaddleOCR ready" if paddle is not None else "PaddleOCR missing")

    # Сначала короткие файлы, чтобы быстрее получить сравнимые результаты.
    inputs.sort(key=lambda p: p.stat().st_size)
    for input_path in inputs:
        file_name = input_path.name
        file_root = OUTPUT_ROOT / safe_stem(input_path)
        print(f"\n===== {file_name} =====")
        pages = prepare_page_images(input_path, file_root / "rendered_pages")
        print(f"pages rendered: {len(pages)}")
        run_paddle(file_name, pages, file_root / "paddleocr", paddle)
        run_vision(file_name, pages, file_root / "apple_vision")
        run_mineru(file_name, input_path, file_root / "mineru")
        run_unlimited(file_name, pages, file_root / "unlimited_ocr")

    report_path = OUTPUT_ROOT / "benchmark_report.json"
    report_path.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nОтчёт сохранён: {report_path}")
    print(json.dumps(RESULTS, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
