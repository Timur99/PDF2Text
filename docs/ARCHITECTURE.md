# Архитектура local_OCR

## Цель

Локальное веб-приложение: пользователь загружает документ или изображение,
выбирает режим распознавания и получает текст, Markdown/JSON и артефакты.
Файл по умолчанию не покидает устройство. OCR запускается только там, где
native extraction невозможна или явно запрошена тяжёлая обработка.

## Принципы

- PDF не должен по умолчанию идти целиком через OCR.
- **pdf-inspector** — первый шаг для PDF: классификация + native Markdown.
- **PaddleOCR** — дефолтный OCR для фото и страниц, требующих OCR.
- **MinerU** — расширенный разбор документов в Markdown/JSON.
- **Unlimited OCR** — опциональный GPU-backend для длинных документов.
- UI и API не зависят от SDK конкретного движка.
- Все задачи асинхронны, отменяемы и сохраняют прогресс.
- Исходники и результаты удаляются пользователем или по TTL.

## Компоненты

```text
Browser
  │ upload / progress / result
  ▼
FastAPI
  ├── File validation & quarantine
  ├── Document triage
  │     ├── Images ───────────────► OCR path
  │     └── PDF → pdf-inspector
  │           ├── TextBased pages → native Markdown
  │           ├── Mixed pages     → native + OCR only pages_needing_ocr
  │           └── Scanned/Image  → OCR path
  ├── Job service ───── SQLite
  ├── Engine registry
  │     ├── PaddleOCR adapter (default OCR, in-process)
  │     ├── MinerU adapter (CLI/HTTP worker)
  │     └── Unlimited OCR adapter (OpenAI-compatible GPU server)
  ├── Worker queue ─── local process pool
  └── Artifact store ─ local filesystem
```

Для MVP очередь реализуется через `asyncio` + отдельный process worker.
При необходимости масштабирования контракт не меняется, реализация заменяется
на Redis + Dramatiq/Celery.

## Слои

```text
frontend/          загрузка, выбор режима, прогресс, просмотр и экспорт
backend/api/       HTTP/WebSocket endpoints и DTO
backend/domain/    Job, DocumentTriage, OCRRequest, OCRResult, Artifact
backend/app/       orchestration, routing, lifecycle и retention
backend/triage/    pdf-inspector wrapper (classify + native extract)
backend/engines/   adapters OCR-движков
backend/infra/     SQLite, filesystem, process runner, metrics
```

Зависимости направлены внутрь: adapters и API зависят от domain-контрактов,
но domain не импортирует PaddleOCR, MinerU, Unlimited OCR или pdf-inspector.

## Pre-OCR triage (pdf-inspector)

[pdf-inspector](https://github.com/firecrawl/pdf-inspector) — локальная Rust-библиотека
(есть Python/Node bindings). Без LLM, без сети, без ML-моделей.

Задачи:

1. Классифицировать PDF: `TextBased` / `Scanned` / `ImageBased` / `Mixed`.
2. Извлечь Markdown со страниц с нормальным текстом.
3. Вернуть `pages_needing_ocr` — только проблемные страницы.
4. Пометить broken encoding / нечитаемые шрифты как кандидатов на OCR.

Контракт triage:

```python
class DocumentTriage(Protocol):
    async def inspect(self, path: Path) -> TriageResult: ...

class TriageResult(BaseModel):
    pdf_type: Literal["text_based", "scanned", "image_based", "mixed", "not_pdf"]
    confidence: float
    page_count: int
    pages_needing_ocr: list[int]
    native_markdown_by_page: dict[int, str]
    warnings: list[str]
```

Правила маршрутизации после triage:

| Вход | Действие |
|---|---|
| JPG/PNG/фото | сразу PaddleOCR (или выбранный OCR) |
| PDF TextBased | native Markdown; OCR не запускать |
| PDF Mixed | native + OCR только `pages_needing_ocr` |
| PDF Scanned/ImageBased | OCR выбранным движком |
| Явный режим `structured` | MinerU (inspector всё равно полезен для метрик) |
| Явный `long_document` + GPU | Unlimited OCR |
| `engine=auto` (позже) | triage + эвристики длины/layout/железа |

## Общий контракт движка

```python
class OCREngine(Protocol):
    name: str

    async def health(self) -> EngineHealth: ...
    async def capabilities(self) -> EngineCapabilities: ...
    async def recognize(
        self,
        document: NormalizedDocument,
        options: OCROptions,
        progress: ProgressCallback,
    ) -> OCRResult: ...
    async def cancel(self, job_id: str) -> None: ...
```

`OCRResult` содержит:

- `text` — плоский текст;
- `markdown` — если backend или native path сохраняет структуру;
- `pages` — текст, размеры, confidence и blocks по страницам;
- `artifacts` — JSON, изображения, HTML-таблицы и прочие файлы;
- `metadata` — engine/model/version/options/duration/device/warnings + triage info.

## Профили движков

Что для чего лучше — по замерам от 02–03.09.2026, а не по интуиции. Инструмент:
`compare_engines.py`. Полные числа и оговорки — в `DECISIONS.md`.

| Условие | Лучше | Насколько |
|---|---|---|
| PDF с текстовым слоем | **native** | мгновенно и без ошибок: текст берётся как есть |
| Чистый русский текст | ничья | F1 0.990 против 1.000; Vision в 12 раз быстрее |
| Настоящий скан | **Vision** | у Paddle рвутся строки и появляются битые символы |
| Светлый текст на тёмном | **Vision** | CER 0.002 против 0.025, вшестеро быстрее |
| Многоколоночная страница | **Vision** | держит колонки; Paddle читает поперёк и склеивает |
| Наклон, размытие, шум | ничья | ни один не разваливается |
| Не macOS | **PaddleOCR** | Vision там не существует |
| Фото документа под углом | **не измерено** | единственный оставшийся пробел |

Практический вывод: дефолт «Авто» (Vision под капотом) закрывает всё измеренное.
PaddleOCR держим как запасной для конкретных промахов и для систем кроме macOS.

### pdf-inspector — triage / fast path

- Не OCR-движок, а router + native extractor.
- Вход: PDF. Выход: тип PDF, confidence, Markdown, `pages_needing_ocr`.
- CPU-only, миллисекунды–сотни мс на типичный документ.
- **Слабое место:** сломанную кодировку шрифтов не всегда замечает. На `booking.pdf`
  отдаёт `text_based` с `has_encoding_issues=False`, а в тексте `ĸ` вместо `к`.
  Пользователь получает уверенно неправильный результат — хуже пустого.

### Apple Vision — дефолтный OCR

- `VNRecognizeTextRequest`, revision 3, уровень Accurate, языки `ru-RU` + `en-US`.
- Встроен в macOS: **0 МБ в бандле**, ничего не скачивается.
- Скорость 0.2–1.2 с на страницу — в 6–15 раз быстрее PaddleOCR.
- Изображение грузить только через `CGImageSourceCreateWithURL`.
- **Размен:** версию модели зафиксировать нельзя, Apple меняет её с обновлением ОС.
  Это нарушение инварианта №7, принято сознательно.
- Только macOS 13+.

### PaddleOCR — запасной OCR

Две модели на проход, обе выбираются явно:

| Роль | Модель | Вес |
|---|---|---|
| Поиск строк | `PP-OCRv5_mobile_det` | 4.8 МБ |
| Распознавание RU/UK/BE | `eslav_PP-OCRv5_mobile_rec` | 7.7 МБ |
| Распознавание латиницы | `PP-OCRv6_medium_rec` | 73 МБ |

- **`lang` игнорируется, если задано имя любой модели.** Детектор мы задаём ради памяти,
  значит распознавалку обязаны выбирать сами — иначе для русского берётся латинская
  и кириллица теряется целиком. См. `recognition_model()`.
- `PP-OCRv5_server_det` точнее mobile, но на M3 Pro 18 GB съел ~30 GB и ушёл в своп.
- Предобработка (ориентация, выпрямление) отключена ради памяти — для фото под углом
  её стоит попробовать включить, это неисследованный резерв.
- Стек весит 480 МБ и **в бандл не входит**: приложение зовёт его отдельным процессом
  через внешний Python (`paddle_worker.py`), путь берётся из `PDF2TEXT_PADDLE_PYTHON`
  или из `paddle_python.txt` рядом с данными приложения.

### MinerU — `structured` (заморожен)

Отдельный локальный сервис/CLI. Вход: PDF, изображения, DOCX, PPTX, XLSX.
Выход: Markdown, JSON, HTML-таблицы, LaTeX. Заморожен: не приближает ни DMG, ни MCP.

**Это единственный кандидат на поддержку Office-форматов.** Сейчас `.docx`, `.doc`,
`.xlsx`, `.txt`, `.svg` отвергаются на загрузке — приложение принимает только PDF
и изображения.

### Unlimited OCR — `long_document` (отложен)

Требует NVIDIA и 12+ GB VRAM. На macOS не запускается, в DMG не попадает.

## Выбор и маршрутизация

Пользователь всегда может выбрать движок явно. `engine=auto`:

1. PDF → pdf-inspector.
2. TextBased → native path.
3. Нужен OCR + обычный скан/фото → PaddleOCR.
4. Структурный режим / Office / сложные таблицы → MinerU.
5. Длинный документ + GPU → Unlimited OCR.

Автоматический fallback не должен молча менять результат. UI показывает,
какой путь был использован (native / OCR / hybrid) и почему.

## Поток задачи

```text
upload → validate → quarantine → triage
       → native extract and/or enqueue OCR pages
       → merge pages → postprocess → persist → completed/failed/cancelled
```

Статусы: `queued`, `preparing`, `triaging`, `running`, `postprocessing`,
`completed`, `failed`, `cancelled`.

## HTTP API

```text
POST   /api/v1/jobs                 multipart file + engine + options
GET    /api/v1/jobs/{id}            статус, прогресс, metadata, triage
GET    /api/v1/jobs/{id}/result     нормализованный OCRResult
GET    /api/v1/jobs/{id}/artifacts/{name}
DELETE /api/v1/jobs/{id}            удалить файлы и запись
POST   /api/v1/jobs/{id}/cancel
GET    /api/v1/engines              capabilities + health + requirements
WS     /api/v1/jobs/{id}/events     прогресс и логи для пользователя
```

## Хранение

```text
data/
  jobs/<uuid>/
    source/
    normalized/
    triage/triage.json
    result/result.json
    artifacts/
```

SQLite хранит только состояние, безопасные имена, timestamps и metadata.
Путь никогда не принимается напрямую от клиента. Имена файлов нормализуются.

## Безопасность и приватность

- API слушает `127.0.0.1` по умолчанию.
- Ограничения MIME, размера, числа страниц и времени обработки.
- Проверка реального типа файла, защита от zip bombs и path traversal.
- Office/PDF parsing изолируется в subprocess с лимитами ресурсов.
- HTML/Markdown очищаются перед отображением.
- Телеметрия отключена по умолчанию; содержимое документов не логируется.
- Модели скачиваются явно при установке или первом запуске с подтверждением.

## Наблюдаемость

Для каждого запуска: triage type, доля страниц на OCR, движок и версия модели,
устройство, длительность этапов, страницы/сек, peak memory, warnings и код ошибки.
Содержимое документа и OCR-текст не попадают в технические логи.

## Развертывание

1. MVP: Python backend + pdf-inspector + PaddleOCR + встроенный web frontend.
2. Docker Compose: app + опциональные MinerU/Unlimited OCR profiles.
3. Desktop: Tauri как оболочка над тем же локальным API.

Пример профилей:

```text
docker compose up app                       # pdf-inspector + PaddleOCR
docker compose --profile mineru up          # + MinerU
docker compose --profile gpu-long up        # + Unlimited OCR
```

## Ключевые решения

- OCR — не первый шаг пайплайна для PDF.
- Основной backend не должен иметь общий Python environment с тремя ML-стеками.
- Версии моделей фиксируются отдельно от версии приложения.
- Benchmark notebook используется для выбора параметров, но не является
  production-кодом.
- До реализации полного auto-routing сначала собираются измерения на реальном корпусе.
