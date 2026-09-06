from __future__ import annotations

from backend.app.pipeline import DocumentPipeline
from backend.engines import default_engines
from backend.infra.paths import data_dir
from backend.infra.storage import JobStore

DATA_DIR = data_dir()
MAX_UPLOAD_BYTES = 80 * 1024 * 1024

store = JobStore(DATA_DIR)
pipeline = DocumentPipeline(store, default_engines())
