from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

from backend.engines.base import OCRPageOutput
from backend.infra.paths import data_dir, resource_dir

# Стек paddle весит 480 МБ и в бандл не вшивается — приложение осталось бы
# полугигабайтным. Вместо этого зовём внешний Python, где paddleocr установлен.
# Инвариант №6 архитектуры того же требует: тяжёлый движок — отдельный процесс.
PYTHON_ENV_VAR = "PDF2TEXT_PADDLE_PYTHON"
PYTHON_CONFIG = "paddle_python.txt"
RESULT_MARKER = "---PDF2TEXT-RESULT---"
WORKER_TIMEOUT = 900


def external_python() -> Path | None:
    """Внешний Python с paddleocr: переменная окружения или файл настройки."""
    override = os.environ.get(PYTHON_ENV_VAR)
    if override:
        candidate = Path(override).expanduser()
        return candidate if candidate.exists() else None
    config = data_dir().parent / PYTHON_CONFIG
    if config.exists():
        candidate = Path(config.read_text(encoding="utf-8").strip()).expanduser()
        return candidate if candidate.exists() else None
    return None


def worker_script() -> Path:
    bundled = resource_dir() / "backend" / "engines" / "paddle_worker.py"
    return bundled if bundled.exists() else Path(__file__).with_name("paddle_worker.py")


def _collect_text(value: Any, texts: list[str], scores: list[float]) -> None:
    if isinstance(value, dict):
        rec_texts = value.get("rec_texts")
        rec_scores = value.get("rec_scores")
        if isinstance(rec_texts, list):
            texts.extend(str(item) for item in rec_texts if item)
            if isinstance(rec_scores, list):
                scores.extend(float(item) for item in rec_scores if item is not None)
            return
        for child in value.values():
            _collect_text(child, texts, scores)
        return
    if isinstance(value, list):
        if (
            len(value) == 2
            and isinstance(value[1], (list, tuple))
            and value[1]
            and isinstance(value[1][0], str)
        ):
            texts.append(value[1][0])
            if len(value[1]) > 1 and isinstance(value[1][1], (int, float)):
                scores.append(float(value[1][1]))
            return
        for child in value:
            _collect_text(child, texts, scores)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    for attr in ("json", "to_json", "to_dict"):
        candidate = getattr(value, attr, None)
        if candidate is None:
            continue
        candidate = candidate() if callable(candidate) else candidate
        if isinstance(candidate, str):
            try:
                candidate = json.loads(candidate)
            except json.JSONDecodeError:
                return candidate
        return _to_jsonable(candidate)
    return str(value)


EAST_SLAVIC = {"ru", "uk", "be"}


def recognition_model(language: str) -> str | None:
    """Имя модели распознавания под язык, или None — оставить выбор PaddleOCR.

    PaddleOCR **игнорирует `lang`, если задано имя любой модели** — он пишет об
    этом предупреждением при инициализации. Мы обязаны пиновать детектор ради
    памяти (см. `_client`), а значит модель распознавания надо выбирать самим.
    Иначе для русского молча берётся латинская `PP-OCRv6_medium_rec`, и вся
    кириллица теряется: строки находятся, текст выходит пустым.
    """
    code = language.split("-")[0].lower()
    if code in EAST_SLAVIC:
        return "eslav_PP-OCRv5_mobile_rec"
    return None


class PaddleOCREngine:
    name = "paddleocr"

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}
        # None — ещё не проверяли, False — внешнего Python нет, Path — найден.
        self._external: Path | bool | None = None

    def available(self) -> bool:
        if importlib.util.find_spec("paddleocr") is not None:
            return True
        return self._external_ready()

    def _external_ready(self) -> bool:
        """Есть ли внешний Python и стоит ли в нём paddleocr. Результат кэшируем:
        проверка — запуск процесса, а `available()` дёргается на каждый /engines."""
        if self._external is not None:
            return self._external is not False
        python = external_python()
        if python is None:
            self._external = False
            return False
        try:
            probe = subprocess.run(
                [str(python), "-c", "import importlib.util,sys;"
                 "sys.exit(0 if importlib.util.find_spec('paddleocr') else 1)"],
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            self._external = False
            return False
        self._external = python if probe.returncode == 0 else False
        return self._external is not False

    def _run_worker(
        self,
        images: list[tuple[int, Path]],
        language: str,
        on_page: Callable[[int, int, int], None] | None,
    ) -> list[OCRPageOutput]:
        python = self._external
        assert isinstance(python, Path)
        if on_page is not None:
            # Воркер обрабатывает пачку целиком, поэтому прогресс на страницу
            # отдать нечем — сообщаем хотя бы о старте.
            on_page(1, len(images), images[0][0])
        request = json.dumps(
            {"images": [[page, str(path)] for page, path in images], "language": language},
            ensure_ascii=False,
        )
        completed = subprocess.run(
            [str(python), str(worker_script()), request],
            capture_output=True,
            text=True,
            timeout=WORKER_TIMEOUT,
        )
        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout or "").strip()[-500:]
            raise RuntimeError(f"PaddleOCR не отработал: {tail}")
        marker = completed.stdout.rfind(RESULT_MARKER)
        if marker < 0:
            raise RuntimeError("PaddleOCR не вернул результат")
        payload = json.loads(completed.stdout[marker + len(RESULT_MARKER):])
        return [
            OCRPageOutput(page=item["page"], text=item["text"], confidence=item["confidence"])
            for item in payload["pages"]
        ]

    def recognize_images(
        self,
        images: list[tuple[int, Path]],
        language: str,
        on_page: Callable[[int, int, int], None] | None = None,
    ) -> list[OCRPageOutput]:
        if importlib.util.find_spec("paddleocr") is None:
            if not self._external_ready():
                raise RuntimeError(
                    "PaddleOCR недоступен. Установите его в отдельное окружение и укажите "
                    f"путь к его python в {PYTHON_ENV_VAR} или в файле "
                    f"{data_dir().parent / PYTHON_CONFIG}"
                )
            return self._run_worker(images, language, on_page)
        client = self._client(language)
        outputs: list[OCRPageOutput] = []
        total = len(images)
        for index, (page, image) in enumerate(images, start=1):
            if on_page is not None:
                on_page(index, total, page)
            raw = self._run(client, image)
            texts: list[str] = []
            scores: list[float] = []
            _collect_text(_to_jsonable(raw), texts, scores)
            outputs.append(
                OCRPageOutput(
                    page=page,
                    text="\n".join(texts).strip(),
                    confidence=round(sum(scores) / len(scores), 4) if scores else None,
                )
            )
        return outputs

    def _client(self, language: str) -> Any:
        lang = "ru" if language.startswith("ru") else language
        if lang not in self._clients:
            from paddleocr import PaddleOCR

            kwargs: dict[str, Any] = {
                "lang": lang,
                # server_det на M3 Pro 18 GB съедал ~30 GB и уходил в своп
                "text_detection_model_name": "PP-OCRv5_mobile_det",
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
            }
            recognition = recognition_model(lang)
            if recognition is not None:
                kwargs["text_recognition_model_name"] = recognition
            try:
                self._clients[lang] = PaddleOCR(**kwargs)
            except TypeError:
                self._clients[lang] = PaddleOCR(lang=lang, use_angle_cls=False)
        return self._clients[lang]

    def _run(self, client: Any, image: Path) -> Any:
        try:
            return list(client.predict(str(image)))
        except TypeError:
            return client.ocr(str(image), cls=True)
