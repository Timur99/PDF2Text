from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anyio
import pymupdf
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.mcpserver.exceptions import ToolError

import backend.mcp_server as mcp_server


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def document(tmp_path):
    source = tmp_path / "Текст с пробелами.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Hello from the shared PDF pipeline.")
        pdf.save(source)
    return source


def test_path_boundaries(tmp_path, document):
    roots = (tmp_path.resolve(),)
    assert mcp_server.validate_source(str(document), roots) == document.resolve()
    with pytest.raises(ToolError, match="абсолютный"):
        mcp_server.validate_source(document.name, roots)
    with pytest.raises(ToolError, match="не найден"):
        mcp_server.validate_source(str(tmp_path / "absent.pdf"), roots)
    with pytest.raises(ToolError, match="обычный файл"):
        mcp_server.validate_source(str(tmp_path), roots)
    with pytest.raises(ToolError, match="вне разрешённых"):
        mcp_server.validate_source(str(document), (tmp_path / "narrow",))
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (allowed / "escape.pdf").symlink_to(document)
    with pytest.raises(ToolError, match="вне разрешённых"):
        mcp_server.validate_source(str(allowed / "escape.pdf"), (allowed,))
    wrong_type = tmp_path / "secret.txt"
    wrong_type.write_text("secret")
    with pytest.raises(ToolError, match="Office"):
        mcp_server.validate_source(str(wrong_type), roots)


def test_size_limit(tmp_path):
    source = tmp_path / "large.pdf"
    with source.open("wb") as stream:
        stream.truncate(mcp_server.MAX_FILE_BYTES + 1)
    with pytest.raises(ToolError, match="80 MB"):
        mcp_server.validate_source(str(source), (tmp_path.resolve(),))


@pytest.mark.anyio
async def test_stdio_roundtrip(document, tmp_path):
    original = document.read_bytes()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "backend.mcp_server", "--allow-dir", str(tmp_path)],
        cwd=str(tmp_path),  # Installed entry point must not rely on repository cwd.
        env={"TMPDIR": str(scratch), "TEMP": str(scratch), "TMP": str(scratch)},
    )
    with anyio.fail_after(30):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                listing = await client.list_tools()
                assert {tool.name for tool in listing.tools} == {"extract_text", "list_engines"}
                assert all(tool.annotations.read_only_hint for tool in listing.tools)
                engines = await client.call_tool("list_engines")
                assert not engines.is_error
                assert engines.structured_content["engines"][0] == {"name": "native", "available": True}
                result = await client.call_tool("extract_text", {"path": str(document), "engine": "native"})
                assert not result.is_error, result
                data = result.structured_content
                assert "Hello from the shared PDF pipeline." in data["content"]
                assert data["path"] == "native"
                assert data["page_count"] == 1
                assert data["complete"] is True
                assert data["skipped_pages"] == []
                assert data["filename"] == document.name
                # Backwards-compatible text content also contains warnings and completeness.
                assert json.loads(result.content[0].text)["complete"] is True
                missing = await client.call_tool("extract_text", {"path": str(tmp_path / "missing.pdf")})
                assert missing.is_error
                invalid = await client.call_tool("extract_text", {"path": str(document), "engine": "unknown"})
                assert invalid.is_error
                # A bad call does not kill the server.
                text = await client.call_tool("extract_text", {"path": str(document), "format": "text"})
                assert text.structured_content["format"] == "text"
    assert document.read_bytes() == original
    assert list(scratch.iterdir()) == []


@pytest.mark.anyio
async def test_incomplete_result_is_explicit(document, monkeypatch):
    async def fake_worker(request):
        return {
            "text": "first page", "markdown": "# first page", "engine": "vision", "path": "ocr",
            "warnings": ["OCR page limit reached"],
            "pages": [
                {"page": 1, "source": "ocr", "text": "first page", "confidence": 0.9},
                {"page": 2, "source": "ocr", "skipped_reason": "limit", "ocr_reason": "scanned"},
            ],
        }

    monkeypatch.setattr(mcp_server, "run_worker", fake_worker)
    server = mcp_server.create_server([document.parent])
    result = await server.call_tool("extract_text", {"path": str(document)})
    data = result.structured_content
    assert data["complete"] is False
    assert data["skipped_pages"] == [2]
    assert data["warnings"] == ["OCR page limit reached"]
    assert data["pages"][1]["skipped_reason"] == "limit"
    assert data["content"] == "# first page"


@pytest.mark.anyio
async def test_bad_pdf_is_tool_error_and_cleans_up(tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(mcp_server.tempfile, "tempdir", str(scratch))
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"not a PDF")
    server = mcp_server.create_server([tmp_path])
    with pytest.raises(ToolError, match="Не удалось обработать") as error:
        await server.call_tool("extract_text", {"path": str(source), "engine": "native"})
    assert str(tmp_path) not in str(error.value)
    assert list(scratch.iterdir()) == []


@pytest.mark.anyio
@pytest.mark.parametrize("cancel", [False, True], ids=["timeout", "cancellation"])
async def test_worker_stops_and_cleans_up(tmp_path, monkeypatch, cancel):
    monkeypatch.setattr(mcp_server.tempfile, "tempdir", str(tmp_path))
    original_open = anyio.open_process
    started = anyio.Event()
    children = []

    async def slow_worker(command, **kwargs):
        process = await original_open([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
        children.append(process)
        started.set()
        return process

    monkeypatch.setattr(mcp_server.anyio, "open_process", slow_worker)
    if cancel:
        async with anyio.create_task_group() as group:
            group.start_soon(mcp_server.run_worker, {"operation": "engines"})
            await started.wait()
            group.cancel_scope.cancel()
    else:
        with pytest.raises(ToolError, match="время обработки"):
            await mcp_server.run_worker({"operation": "engines"}, timeout=0.05)
    assert children and children[0].returncode is not None
    assert list(tmp_path.iterdir()) == []
    if os.name == "posix":
        with pytest.raises(ProcessLookupError):
            os.kill(children[0].pid, 0)
