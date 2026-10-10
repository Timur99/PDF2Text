# Размещение PDF2Text в MCP-каталогах

Проверено по документации площадок 03.10.2026. Это план публикации и готовые тексты
для карточек. Добавление этого файла не означает, что заявки уже отправлены.

## Название и описание

Рекомендуемое название карточки: **PDF2Text — Local PDF & Image OCR MCP**.
Оно сохраняет имя продукта и добавляет понятные поисковые слова: PDF, image, OCR, MCP.
Репозиторий остаётся `Timur99/PDF2Text`, ключ подключения — `pdf2text`, команда —
`pdf2text-mcp`, инструменты — `extract_text` и `list_engines`.

Короткое описание для каталога и GitHub About:

> Local MCP server for extracting text and Markdown from PDFs, scans and images. Uses native PDF text first and Apple Vision OCR on macOS. Reports skipped pages and warnings. No OCR API key required.

Дополнение для полной карточки:

> Runs locally over stdio with access limited to configured document folders. Returns extracted content and page metadata to AI agents. Optional PaddleOCR support. Extracted text is shared with the MCP client; its model provider may process that text. Auto mode processes up to 12 OCR pages; explicit OCR modes support PDFs up to 200 pages.

Для русскоязычных каталогов:

**Название:** PDF2Text — локальный OCR для PDF и изображений.

**Описание:** MCP-сервер для извлечения текста и Markdown из PDF, сканов и фотографий.
Использует готовый текст PDF, а при необходимости — Apple Vision на macOS.
Сообщает о пропущенных страницах. Устанавливается через промпт AI-агенту, API-ключ
для OCR не нужен. Распознавание локальное; извлечённый текст получает MCP-клиент.

**Репозиторий:** https://github.com/Timur99/PDF2Text.
**Инструкция установки:** README, раздел «Установка через агента».

Предлагаемые теги: `mcp`, `mcp-server`, `pdf`, `ocr`, `text-extraction`, `markdown`,
`apple-vision`, `macos`, `local-first`.

Предлагаемый идентификатор официального Registry: `io.github.Timur99/pdf2text`.
Это кандидат, не зарезервированное имя. При публикации namespace должен соответствовать
авторизованному GitHub-аккаунту. Для PyPI кандидат — `pdf2text-mcp`; доступность имени
нужно проверить перед переименованием и публикацией. Сейчас имя Python-дистрибутива
в `pyproject.toml` — `local-ocr`; команды установки из GitHub уже работают с ним.

## Куда подавать

| Площадка | Действие | Что нужно для нашего сервера |
|---|---|---|
| [mcpservers.org](https://mcpservers.org/ru/submit) | Бесплатная форма: название, категория, описание, ссылка, контактный email | Начать с обычной подачи; Premium необязателен. Форма принимает ссылку на репозиторий или документацию. |
| [mcp-catalog.ru](https://mcp-catalog.ru/about) | Основной источник — awesome-mcp-servers; для ускорения авторы предлагают контакт или issue | Подать upstream PR либо запросить добавление у редакции. На главной указаны mcp@atomno.com и @atomno_support_bot; на странице «О сайте» — @mcp_digest. Контакты на страницах расходятся, предпочтителен текущий контакт с главной. |
| [NeuralDeep](https://neuraldeep.ru/submit) | Форма «Добавить навык или MCP сервер» после входа | Доступен вход через Яндекс ID или RMR (Bitrix24). Поля формы за авторизацией ещё не проверены. |
| [Glama](https://glama.ai/mcp/servers) | Add MCP Server: GitHub URL, название и описание | Подавать как сервер из исходников. Указать локальный stdio и macOS для Vision. У Glama есть проверки лицензии, безопасности и работоспособности. |
| [PulseMCP](https://www.pulsemcp.com/submit) | Подать репозиторий через форму Submit | Использовать те же название, описание и ссылку на установку. Каталог также получает данные из официального Registry. |
| [Official MCP Registry](https://registry.modelcontextprotocol.io/) | Опубликовать артефакт, затем metadata через `mcp-publisher` | Для Python удобен PyPI; альтернативно MCPB в GitHub Releases. Одной ссылки на GitHub-исходники для такой поставки недостаточно. |
| [Smithery](https://smithery.ai/) | Опубликовать локальный `.mcpb` через CLI/API | Сначала собрать MCPB и проверить установку. Поддержка публикации URL относится к удалённому серверу; у нас локальный stdio. |
| [Awesome MCP Servers](https://github.com/punkpeye/awesome-mcp-servers) | PR со ссылкой и кратким описанием | Следовать актуальному CONTRIBUTING и формату выбранной категории; принятие зависит от сопровождающих списка. |

Основания: [Glama FAQ](https://glama.ai/mcp/faq),
[источники данных PulseMCP](https://www.pulsemcp.com/api),
[типы пакетов Registry](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/package-types.mdx),
[Smithery Publish API](https://smithery.mintlify.app/api-reference/servers/publish-a-server),
[Awesome CONTRIBUTING](https://github.com/punkpeye/awesome-mcp-servers/blob/main/CONTRIBUTING.md).

Для трёх добавленных каталогов проверены [форма mcpservers.org](https://mcpservers.org/ru/submit),
[описание источников mcp-catalog.ru](https://mcp-catalog.ru/about),
[контакты на главной](https://mcp-catalog.ru/) и
[страница подачи NeuralDeep](https://neuraldeep.ru/submit).

Карточка в каталоге помогает найти сервер. Она сама по себе не устанавливает Python,
не даёт доступ к локальным документам и не превращает сервер в облачный endpoint.
Apple Vision требует macOS, поэтому обычный Linux-хостинг не воспроизводит основной
вариант OCR. Для текущей версии рекомендуем локальную установку на машине пользователя.

## Порядок публикации

1. Выложить текущую версию README и `docs/INSTALL_MCP.md` на GitHub. Проверить, что
   публичные ссылки в установочном промпте открываются и ведут на нужную ветку.
2. Определить лицензию проекта: сейчас файла LICENSE в репозитории нет. Добавить
   выбранную владельцем лицензию до представления проекта как open source в каталогах.
3. Начать с бесплатной формы mcpservers.org и подачи в NeuralDeep после входа;
   для mcp-catalog.ru — обратиться к редакции или попасть в upstream-список.
   Затем Glama и PulseMCP. Использовать готовые тексты выше и README с промптом установки.
4. Подготовить пакет для PyPI: выбрать доступное имя, определить версию, добавить
   метаданные и проверить запуск `pdf2text-mcp` с нужными extras в чистом окружении.
   Только после этого публиковать пакет из аккаунта владельца.
5. Подготовить `server.json` и опубликоваться в официальном Registry. Затем при желании
   подать PR в Awesome MCP Servers.
6. Для установки через диалог приложения собрать `.mcpb` и проверить его на чистом
   Mac; после этого публиковать bundle в GitHub Releases и Smithery.

Для шага 5 официальный порядок: `mcp-publisher init`, заполнение `server.json`,
`mcp-publisher login github`, `mcp-publisher validate`, `mcp-publisher publish`.
Metadata должны ссылаться на уже опубликованный артефакт, его точную версию,
stdio transport и обязательный параметр `--allow-dir`. При варианте PyPI требуется
маркер `mcp-name: io.github.Timur99/pdf2text` в описании пакета; его значение должно
совпадать с `name` в `server.json`. Маркер добавляется до сборки и публикации пакета.
Extras для MCP/Vision и команда запуска должны проверяться именно в той форме,
которую сгенерирует выбранный каталог, а не только в рабочем venv разработчика.
[Официальный порядок публикации](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/quickstart.mdx),
[проверка владения PyPI-пакетом](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/package-types.mdx#pypi-packages).

## Установка без ручного ввода команд

Уже подготовлены промпт в начале README и [инструкция для агента](INSTALL_MCP.md).
Пользователь вставляет промпт, а агент устанавливает зависимости, настраивает клиент
и проверяет инструменты. Требуется агент, умеющий выполнять команды на компьютере
пользователя. Первый запуск может занять минуты; не обещаем установку за секунду.

Следующий уровень удобства — MCPB. Это формат bundle с manifest для установки через
диалог в поддерживающих его клиентах. Его нужно отдельно собрать с зависимостями и
проверить; один файл manifest без рабочей поставки сервера этого не обеспечивает.
[Спецификация и инструменты MCPB](https://github.com/anthropics/mcpb).
