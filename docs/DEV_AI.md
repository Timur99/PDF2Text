# AI-инструменты для разработки local_OCR

Документ про то, чем помогать себе при разработке продукта, а не про
ML-стеки внутри runtime.

## Уже есть

| Инструмент | Зачем |
|---|---|
| `.cursor/rules/tech-lead-product.mdc` | Постоянная роль техлида/продакта |
| `.local-dev/docs/` | Архитектура и план вне git |
| `ocr_engines_benchmark.ipynb` | Сравнение OCR-движков |
| Cursor skills: `review`, `review-security`, `babysit`, `split-to-prs`, `create-skill`, `create-hook` | Готовые workflow агента |

## Что взять для этого проекта

### 1. Project rules (обязательно)

Держать короткие always-on / glob rules:

- `tech-lead-product` — уже есть: план → критерии → код.
- `backend-fastapi` — API contracts, Pydantic models, no secrets in logs.
- `engines-adapters` — OCR SDK только внутри `backend/engines/*`.
- `privacy-local` — никаких внешних upload без явного opt-in.

### 2. Project skills (рекомендуется)

Сделать 2–3 локальных skill в `.cursor/skills/` (папка тоже в `.gitignore`
или только внутри `.local-dev/skills/`):

| Skill | Когда вызывать |
|---|---|
| `add-ocr-engine` | Новый backend: Protocol → adapter → health → docs → benchmark cell |
| `triage-pdf-path` | Работа с pdf-inspector и merge native+OCR pages |
| `ocr-regression` | Прогон корпуса, CER/WER, сравнение native vs OCR |

Не тащить generic «агентный фреймворк ради фреймворка». Skills должны
кодировать наши решения из ARCHITECTURE.md.

### 3. Hooks (полезно после появления кода)

- pre-commit / Cursor hook: не коммитить `data/`, модели, `.env`, sample docs с ПДн.
- after-edit: прогон `ruff` / `pytest` на затронутых тестах.
- PR babysit skill — когда появится CI.

### 4. Runtime frameworks — что НЕ брать рано

| Идея | Вердикт |
|---|---|
| LangChain / LlamaIndex как ядро приложения | Нет для MVP. Лишний слой; у нас не RAG-чат, а document job pipeline |
| CrewAI / multi-agent orchestration | Нет. Один оркестратор jobs достаточно |
| Unstructured / LlamaParse как cloud default | Только опционально позже; конфликт с privacy-first |
| LiteLLM / OpenAI-compatible client | Да, точечно для Unlimited OCR GPU server |
| Pydantic AI / instructor | Можно позже для structured post-processing, не сейчас |

### 5. Что взять в runtime стеке продукта

- FastAPI + Pydantic — API и контракты.
- pdf-inspector — triage.
- PaddleOCR / MinerU / Unlimited OCR — adapters.
- SQLite — jobs.
- React+Vite — UI.
- Tauri — desktop оболочка на этапе 6.

## Практичный минимум на ближайшие 2 недели

1. Оставить роль tech-lead.
2. Добавить 1–2 project skills: `add-ocr-engine`, `triage-pdf-path`.
3. Не подключать agent frameworks в runtime.
4. Использовать `review` / `review-security` перед merge чувствительных частей
   (upload, path handling, subprocess).
5. После MVP — `babysit` + CI.

## Решение

Для разработки: **Cursor rules + project skills + security/review skills**.  
Для продукта: **простой job pipeline**, без LangChain/multi-agent.
