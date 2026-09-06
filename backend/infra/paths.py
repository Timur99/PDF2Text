"""Пути, которые обязаны работать и в разработке, и внутри собранного приложения.

В бандле нельзя опираться ни на `__file__` (он указывает во временный каталог
распаковки), ни на текущий каталог (у приложения, запущенного из Finder, он
непредсказуем — обычно `/`).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "PDF2Text"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def resource_dir() -> Path:
    """Каталог со статикой, положенной в сборку (frontend/)."""
    if is_frozen():
        # PyInstaller распаковывает данные сюда; для onedir это каталог рядом с бинарём.
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def frontend_dir() -> Path:
    return resource_dir() / "frontend"


def data_dir() -> Path:
    """Куда писать задачи пользователя.

    Приоритет: явная переменная окружения → пользовательский каталог приложения
    (в собранном виде) → `./data/jobs` рядом с репозиторием (в разработке).
    """
    override = os.environ.get("PDF2TEXT_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if is_frozen():
        if sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / APP_NAME
        elif sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
        else:
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME
        return base / "jobs"
    return Path.cwd() / "data" / "jobs"
