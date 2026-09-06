from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_engines_default_is_auto() -> None:
    response = client.get("/api/v1/engines")
    assert response.status_code == 200
    body = response.json()
    assert body["default"] == "auto"
    ids = [item["id"] for item in body["engines"]]
    # Vision перед PaddleOCR: он дефолтный движок, а порядок задаёт вид сегментов в UI.
    assert ids == ["auto", "native", "vision", "paddleocr"]
    assert len(ids) <= 4, "DESIGN.md: больше четырёх пунктов в сегменты не влезает"


def test_create_job_returns_immediately() -> None:
    response = client.post(
        "/api/v1/jobs",
        files={"file": ("note.pdf", b"%PDF-1.1\n", "application/pdf")},
        data={"engine": "auto", "language": "ru"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"queued", "preparing", "triaging", "running", "failed", "completed"}
    assert "id" in body


def test_rejects_unsupported_file() -> None:
    response = client.post(
        "/api/v1/jobs",
        files={"file": ("note.txt", b"hello", "text/plain")},
        data={"engine": "auto", "language": "ru"},
    )
    assert response.status_code == 415


def test_safe_filename_keeps_extension_for_cyrillic_names() -> None:
    """Русское имя целиком схлопывалось в `_`, а strip съедал точку: файл ложился
    на диск без расширения, и пайплайн отвергал его как неподдерживаемый формат."""
    from backend.infra.storage import safe_filename

    assert safe_filename("Кузмицкий Евгений.pdf").endswith(".pdf")
    assert safe_filename("скан.jpg").endswith(".jpg")
    assert safe_filename("Booking.com: Подтверждение.pdf").endswith(".pdf")
    # Обход каталогов по-прежнему невозможен.
    assert safe_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert "/" not in safe_filename("a/b/c.pdf")


def test_upload_with_cyrillic_filename_is_processed() -> None:
    """Сквозная проверка того же бага: имя из одной кириллицы должно доходить
    до обработки, а не падать на «Поддерживаются PDF и изображения»."""
    import pymupdf

    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "hello")
    payload = document.tobytes()
    document.close()

    response = client.post(
        "/api/v1/jobs",
        files={"file": ("Кузмицкий Евгений.pdf", payload, "application/pdf")},
        data={"engine": "native", "language": "ru"},
    )
    assert response.status_code == 200
    job_id = response.json()["id"]

    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert "Поддерживаются PDF" not in (job.get("error") or "")
    assert job["status"] == "completed", job.get("error")

    client.delete(f"/api/v1/jobs/{job_id}")
