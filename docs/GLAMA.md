# Размещение PDF2Text на Glama

Подготовлено 10.10.2026. Карточка, удалённая проверка Glama и обновление PR
пока не подтверждены. Эти файлы сами по себе не публикуют сервер.

1. Отправьте `glama.json` и остальные изменения проекта в GitHub.
2. На https://glama.ai/mcp/servers выберите **Add MCP Server** и укажите
   `https://github.com/Timur99/PDF2Text`, название
   **PDF2Text — Local PDF & Image OCR MCP** и описание:

   > Extract text and Markdown from local PDFs and images. Uses native PDF text first and Apple Vision OCR on macOS. No OCR API key required.

3. Войдите на Glama через GitHub-аккаунт `Timur99` и откройте **Admin → Dockerfile**
   карточки. Dockerfile нужно настроить **непосредственно на Glama**;
   наличие файла в репозитории не заменяет этот шаг.
   Если редактор принимает полный Dockerfile, используйте [Dockerfile.glama](../Dockerfile.glama)
   с контекстом сборки в корне репозитория.
   Если он предлагает поля сборки, задайте Python `3.12`, шаги сборки из корня
   репозитория `python -m pip install .` и `mkdir -p /tmp/pdf2text-documents`,
   аргументы CMD: `["pdf2text-mcp", "--allow-dir", "/tmp/pdf2text-documents"]`.
   Переменные окружения, ключи API и HTTP-порт серверу не нужны.
4. Запустите проверку Glama. Сервер должен отвечать на `initialize` и `tools/list`,
   возвращая `extract_text` и `list_engines`. Проверьте реальные результаты сборки,
   лицензии, безопасности и запуска в карточке перед обновлением PR.
5. Скопируйте фактический путь карточки Glama и добавьте бейдж **после описания**
   сервера в существующем PR awesome-mcp-servers.

Пример строки, если Glama выдала путь `Timur99/PDF2Text`:

```markdown
- [Timur99/PDF2Text](https://github.com/Timur99/PDF2Text) 🐍 🏠 🍎 - Extract text and Markdown from local PDFs and images, using native PDF text first and Apple Vision OCR on macOS. No OCR API key required. [![Timur99/PDF2Text MCP server](https://glama.ai/mcp/servers/Timur99/PDF2Text/badges/score.svg)](https://glama.ai/mcp/servers/Timur99/PDF2Text)
```

## Возможности контейнера

Контейнер запускает настоящий stdio MCP-сервер. На Linux доступно извлечение
готового текста из PDF; Apple Vision отсутствует, PaddleOCR в этот образ не входит.
Это не облачная OCR-версия macOS-приложения. Для распознавания сканов и изображений
через Apple Vision пользователь устанавливает MCP локально на Mac.

Для локальной проверки при запущенном Docker:

```bash
docker build -f Dockerfile.glama -t pdf2text-glama .
docker run --rm -i pdf2text-glama
```

Вторая команда ждёт MCP-сообщения на stdin. Для работы с PDF подключите папку:
`docker run --rm -i -v /absolute/documents:/documents:ro pdf2text-glama`.
Пути инструменту передаются внутри контейнера, например `/documents/report.pdf`.

Локальная сборка контейнера пока не проверена: Docker daemon на машине разработки
не запущен. Упакованный сервер ранее прошёл MCP handshake и tool discovery через uvx.

## Лицензия

В репозитории пока нет файла `LICENSE`; Glama проверяет наличие лицензии.
Лицензию выбирает владелец проекта, затем её нужно добавить в репозиторий
и повторить проверку. Без результатов Glama нельзя заявлять, что все проверки прошли.

Источники: [добавление сервера и настройка Dockerfile в Admin](https://glama.ai/blog/2025-09-10-glama-mcp-server-hosting),
[проверки каталога](https://glama.ai/mcp/faq),
[схема glama.json](https://glama.ai/mcp/schemas/server.json).
