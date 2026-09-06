"""Точка входа бэкенда в собранном приложении.

Запускается Tauri как sidecar-процесс. `app` передаём объектом, а не строкой
импорта: в замороженном виде строковый путь uvicorn разрешает ненадёжно.
"""

from __future__ import annotations

import os
import sys

import uvicorn

from backend.main import app


def main() -> None:
    port = int(os.environ.get("PDF2TEXT_PORT", "8765"))
    # По умолчанию тихо: в собранном приложении логи уходят в системный журнал,
    # а содержимое документов туда попадать не должно. `info` — для отладки сборки.
    level = os.environ.get("PDF2TEXT_LOG_LEVEL", "warning")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level=level)


if __name__ == "__main__":
    sys.exit(main())
