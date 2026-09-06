"""Самостоятельный воркер PaddleOCR.

Запускается отдельным процессом из внешнего Python, где установлен paddleocr.
Собранное приложение весит 49 МБ именно потому, что стек paddle (480 МБ) в него
не вшит; инвариант №6 архитектуры того же требует — тяжёлый движок живёт своим
процессом, а не импортом в общий venv.

Ничего из `backend` не импортирует: должен запускаться в любом окружении с paddleocr.

    python paddle_worker.py '{"images": [[1, "/path/page.png"]], "language": "ru"}'

Печатает в stdout JSON: {"pages": [{"page": 1, "text": "...", "confidence": 0.93}]}
"""

from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

EAST_SLAVIC = {"ru", "uk", "be"}


def recognition_model(language: str) -> str | None:
    """PaddleOCR игнорирует `lang`, когда задано имя модели, а детектор мы задаём
    ради памяти. Значит распознавалку надо выбирать самим, иначе для русского
    берётся латинская и кириллица теряется целиком."""
    code = language.split("-")[0].lower()
    return "eslav_PP-OCRv5_mobile_rec" if code in EAST_SLAVIC else None


def collect(value, texts: list[str], scores: list[float]) -> None:
    if isinstance(value, dict):
        if isinstance(value.get("rec_texts"), list):
            texts.extend(str(item) for item in value["rec_texts"] if item)
            for score in value.get("rec_scores") or []:
                if isinstance(score, (int, float)):
                    scores.append(float(score))
            return
        for child in value.values():
            collect(child, texts, scores)
    elif isinstance(value, list):
        for child in value:
            collect(child, texts, scores)


def main() -> int:
    request = json.loads(sys.argv[1])
    language = request.get("language", "ru")

    from paddleocr import PaddleOCR

    kwargs = {
        "lang": language,
        # server_det на 18 GB съедал ~30 GB и уходил в своп
        "text_detection_model_name": "PP-OCRv5_mobile_det",
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
    }
    recognition = recognition_model(language)
    if recognition is not None:
        kwargs["text_recognition_model_name"] = recognition
    client = PaddleOCR(**kwargs)

    pages = []
    for page_no, image in request["images"]:
        texts: list[str] = []
        scores: list[float] = []
        for item in client.predict(str(image)):
            payload = item.json if not callable(getattr(item, "json", None)) else item.json()
            collect(payload, texts, scores)
        pages.append(
            {
                "page": page_no,
                "text": "\n".join(texts).strip(),
                "confidence": round(sum(scores) / len(scores), 4) if scores else None,
            }
        )
    # Всё, что paddle пишет в stdout, ушло бы в наш JSON — печатаем маркером.
    sys.stdout.write("---PDF2TEXT-RESULT---" + json.dumps({"pages": pages}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
