"""Private subprocess entry point; OCR output never shares MCP's stdout."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.app.pipeline import DocumentPipeline, PipelineError
from backend.domain.models import EngineChoice, JobRecord
from backend.engines import default_engines
from backend.infra.storage import JobStore


def main(workdir: Path) -> None:
    request = json.loads((workdir / "request.json").read_text(encoding="utf-8"))
    try:
        engines = default_engines()
        if request["operation"] == "engines":
            data = {
                "default": "auto",
                "engines": [{"name": "native", "available": True}]
                + [{"name": engine.name, "available": engine.available()} for engine in engines],
            }
        else:
            source = Path(request["path"])
            job = JobRecord(
                id="mcp",
                filename=source.name,
                engine=EngineChoice(request["engine"]),
                language=request["language"],
            )
            pipeline = DocumentPipeline(JobStore(workdir / "jobs"), engines)
            data = pipeline.run(job, source).model_dump(mode="json")
        response = {"data": data}
    except PipelineError as exc:
        # These are intentional, user-facing errors from the shared pipeline.
        response = {"error": str(exc)}
    except Exception:
        # Library tracebacks can contain document contents and private paths.
        response = {"error": "Не удалось обработать документ. Проверьте файл и доступность движка через list_engines."}
    (workdir / "response.json").write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
