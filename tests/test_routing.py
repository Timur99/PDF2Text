from pathlib import Path

from backend.app.pipeline import merge_pages
from backend.domain.models import EngineChoice, ProcessingPath, TriageResult
from backend.domain.routing import ocr_reason, pages_for_ocr, processing_path


def test_text_based_pdf_skips_ocr() -> None:
    triage = TriageResult(pdf_type="text_based", confidence=0.9, page_count=3)
    assert pages_for_ocr(is_pdf=True, page_count=3, engine=EngineChoice.auto, triage=triage) == []


def test_mixed_pdf_ocr_only_listed_pages() -> None:
    triage = TriageResult(
        pdf_type="mixed",
        confidence=0.8,
        page_count=5,
        pages_needing_ocr=[2, 5],
    )
    assert pages_for_ocr(is_pdf=True, page_count=5, engine=EngineChoice.auto, triage=triage) == [2, 5]


def test_image_always_goes_to_ocr() -> None:
    assert pages_for_ocr(is_pdf=False, page_count=1, engine=EngineChoice.auto, triage=None) == [1]


def test_force_paddle_uses_all_pages() -> None:
    triage = TriageResult(pdf_type="text_based", confidence=1, page_count=2)
    assert pages_for_ocr(is_pdf=True, page_count=2, engine=EngineChoice.paddleocr, triage=triage) == [1, 2]


def test_auto_caps_ocr_pages_in_pipeline_constant() -> None:
    from backend.app.pipeline import MAX_AUTO_OCR_PAGES

    assert MAX_AUTO_OCR_PAGES <= 12


def test_merge_hybrid_pages() -> None:
    pages = merge_pages(
        page_count=2,
        native_by_page={1: "native page"},
        ocr_by_page={2: ("ocr page", 0.91)},
        ocr_pages=[2],
    )
    assert pages[0].source == ProcessingPath.native
    assert pages[1].source == ProcessingPath.ocr
    assert processing_path(True, True) == ProcessingPath.hybrid


def test_skipped_page_is_not_disguised_as_native() -> None:
    """Главный тест S1: страница, которой был нужен OCR, но он не состоялся,
    не должна выглядеть как взятая напрямую."""
    pages = merge_pages(
        page_count=3,
        native_by_page={1: "native page"},
        ocr_by_page={2: ("ocr page", 0.9)},
        ocr_pages=[2],
        reason="scanned",
        skipped={3: "limit"},
    )
    skipped = pages[2]
    assert skipped.source == ProcessingPath.ocr
    assert skipped.needs_ocr is True
    assert skipped.text == ""
    assert skipped.skipped_reason == "limit"
    assert skipped.ocr_reason == "scanned"
    # Успешная OCR-страница остаётся без отметки о пропуске.
    assert pages[1].skipped_reason is None
    assert pages[1].ocr_reason == "scanned"
    # Native-страница не получает причин вообще.
    assert pages[0].ocr_reason is None
    assert pages[0].skipped_reason is None


def test_ocr_reason_matches_routing_branch() -> None:
    scanned = TriageResult(pdf_type="scanned", confidence=0.9, page_count=2)
    assert ocr_reason(is_pdf=True, engine=EngineChoice.auto, triage=scanned) == "scanned"

    mixed = TriageResult(pdf_type="mixed", confidence=0.8, page_count=2, pages_needing_ocr=[2])
    assert ocr_reason(is_pdf=True, engine=EngineChoice.auto, triage=mixed) == "no_text_layer"

    broken = TriageResult(
        pdf_type="text_based", confidence=0.5, page_count=2, has_encoding_issues=True
    )
    assert ocr_reason(is_pdf=True, engine=EngineChoice.auto, triage=broken) == "encoding_issues"

    assert ocr_reason(is_pdf=False, engine=EngineChoice.auto, triage=None) == "image"
    assert ocr_reason(is_pdf=True, engine=EngineChoice.paddleocr, triage=scanned) == "forced"


def test_russian_gets_east_slavic_recognition_model() -> None:
    """PaddleOCR игнорирует lang, если задано имя модели, а детектор мы пиним
    ради памяти. Значит модель распознавания обязаны выбирать сами, иначе для
    русского берётся латинская и кириллица теряется целиком."""
    from backend.engines.paddle import recognition_model

    assert recognition_model("ru") == "eslav_PP-OCRv5_mobile_rec"
    assert recognition_model("ru-RU") == "eslav_PP-OCRv5_mobile_rec"
    assert recognition_model("uk") == "eslav_PP-OCRv5_mobile_rec"
    # Для латиницы дефолт PaddleOCR подходит — не навязываем модель.
    assert recognition_model("en") is None


def test_auto_prefers_first_available_engine() -> None:
    """«Авто» берёт первый доступный движок из списка — так задаётся дефолт."""
    from backend.app.pipeline import DocumentPipeline
    from backend.infra.storage import JobStore

    class Stub:
        def __init__(self, name: str, ok: bool) -> None:
            self.name, self._ok = name, ok

        def available(self) -> bool:
            return self._ok

        def recognize_images(self, images, language, on_page=None):  # pragma: no cover
            return []

    import tempfile

    store = JobStore(Path(tempfile.mkdtemp()))
    vision, paddle = Stub("vision", True), Stub("paddleocr", True)

    pipeline = DocumentPipeline(store, [vision, paddle])
    assert pipeline.select_engine(EngineChoice.auto) is vision
    assert pipeline.select_engine(EngineChoice.paddleocr) is paddle
    assert pipeline.select_engine(EngineChoice.vision) is vision
    assert pipeline.select_engine(EngineChoice.native) is None

    # Vision недоступен (не macOS) — «Авто» откатывается на PaddleOCR, а не падает.
    fallback = DocumentPipeline(store, [Stub("vision", False), paddle])
    assert fallback.select_engine(EngineChoice.auto) is paddle

    # Ни одного доступного — None, пайплайн выдаст понятную ошибку.
    empty = DocumentPipeline(store, [Stub("vision", False), Stub("paddleocr", False)])
    assert empty.select_engine(EngineChoice.auto) is None


def test_forced_engines_ocr_every_page() -> None:
    triage = TriageResult(pdf_type="text_based", confidence=1.0, page_count=3)
    for engine in (EngineChoice.vision, EngineChoice.paddleocr):
        assert pages_for_ocr(is_pdf=True, page_count=3, engine=engine, triage=triage) == [1, 2, 3]
        assert ocr_reason(is_pdf=True, engine=engine, triage=triage) == "forced"
