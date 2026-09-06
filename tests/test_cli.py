from pathlib import Path

import pytest

from backend.cli import EXIT_USAGE, build_parser, main, render
from backend.domain.models import OCRResult, PageResult, ProcessingPath


def test_defaults_are_auto_and_markdown() -> None:
    args = build_parser().parse_args(["scan.pdf"])
    assert args.engine == "auto"
    assert args.format == "md"
    assert args.lang == "ru"
    assert args.output is None


def test_render_formats() -> None:
    result = OCRResult(
        text="плоский текст",
        markdown="## заголовок",
        pages=[PageResult(page=1, source=ProcessingPath.native, text="плоский текст")],
    )
    assert render(result, "md") == "## заголовок"
    assert render(result, "txt") == "плоский текст"
    assert '"markdown"' in render(result, "json")


def test_render_md_falls_back_to_text() -> None:
    """Изображение не даёт Markdown — в md-режиме отдаём текст, а не пустоту."""
    result = OCRResult(text="распознанный текст", markdown="")
    assert render(result, "md") == "распознанный текст"


def test_missing_file_is_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["/нет/такого/файла.pdf"]) == EXIT_USAGE
    assert "не найден" in capsys.readouterr().err


def test_workdir_is_removed_after_run(tmp_path: Path) -> None:
    """CLI не оставляет документ пользователя и промежуточные PNG на диске:
    работа идёт во временном каталоге, который удаляется в finally."""
    import pymupdf

    import backend.cli as cli

    source = tmp_path / "note.pdf"
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "hello")
    document.save(source)
    document.close()

    created: list[Path] = []
    original = cli.tempfile.mkdtemp

    def spy(*args, **kwargs):
        path = Path(original(*args, **kwargs))
        created.append(path)
        return str(path)

    cli.tempfile.mkdtemp = spy
    try:
        assert main([str(source), "-e", "native", "-q", "-o", str(tmp_path / "out.md")]) == 0
    finally:
        cli.tempfile.mkdtemp = original

    assert created, "временный каталог не создавался — тест ничего не проверил"
    assert all(not path.exists() for path in created)


def test_external_paddle_python_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Стек paddle (480 МБ) в бандл не вшит — движок зовётся отдельным процессом.
    Путь к внешнему Python берётся из переменной окружения или из файла настройки."""
    import backend.engines.paddle as paddle

    fake = tmp_path / "python"
    fake.write_text("#!/bin/sh\n")

    monkeypatch.setenv(paddle.PYTHON_ENV_VAR, str(fake))
    assert paddle.external_python() == fake

    # Несуществующий путь не выдаём за рабочий.
    monkeypatch.setenv(paddle.PYTHON_ENV_VAR, str(tmp_path / "нет-такого"))
    assert paddle.external_python() is None

    # Без переменной — файл настройки рядом с данными приложения.
    monkeypatch.delenv(paddle.PYTHON_ENV_VAR, raising=False)
    config_root = tmp_path / "app"
    (config_root / "jobs").mkdir(parents=True)
    (config_root / paddle.PYTHON_CONFIG).write_text(str(fake), encoding="utf-8")
    monkeypatch.setattr(paddle, "data_dir", lambda: config_root / "jobs")
    assert paddle.external_python() == fake


def test_worker_script_is_shipped() -> None:
    """Воркер должен лежать рядом с движком: без него мост в бандле не соберётся."""
    from backend.engines.paddle import worker_script

    assert worker_script().exists()
