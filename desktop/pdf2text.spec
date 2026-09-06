# PyInstaller spec для бэкенда PDF2Text.
# Собирать из корня репозитория:
#   .venv/bin/pyinstaller desktop/pdf2text.spec --noconfirm
#
# Главное здесь — EXCLUDES. Дефолтный движок теперь Apple Vision (встроен в macOS,
# ноль мегабайт), поэтому paddle со всем ML-стеком в бандл не едет. Он остаётся
# опциональной докачкой для тех, кому Vision не хватит.

EXCLUDES = [
    "paddle", "paddleocr", "paddlex", "torch", "torchvision",
    "tensorflow", "scipy", "matplotlib", "pandas", "IPython",
    "notebook", "tkinter", "PyQt5", "PySide6", "sklearn", "transformers",
]

HIDDEN = [
    # uvicorn подтягивает реализации циклов и протоколов динамически
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
    # Apple Vision через pyobjc
    "Vision", "Quartz", "Foundation", "objc",
]

# Пути считаем от самого spec-файла, а не от текущего каталога: иначе сборка
# из корня репозитория и из desktop/ дают разный результат, причём вторая молча
# собирает битый бинарь без модуля `backend`.
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))

a = Analysis(
    [os.path.join(SPECPATH, "pdf2text_server.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "frontend"), "frontend"),
        # Воркер PaddleOCR: сам paddle в бандл не едет, но скрипт, которым его
        # зовут из внешнего Python, лежать в бандле должен.
        (os.path.join(ROOT, "backend", "engines", "paddle_worker.py"), "backend/engines"),
    ],
    hiddenimports=HIDDEN,
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="pdf2text-server",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
