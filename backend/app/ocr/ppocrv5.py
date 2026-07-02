"""PP-OCRv5 CPU fallback — for GPU-less installs and degraded mode. Text
detection + recognition only (no VLM layout understanding); tables come out as
plain text lines, so accuracy expectations are documented as lower."""

from pathlib import Path

from app.config import get_settings
from app.ocr.engine import OcrEngine, PageResult, Region


class PpOcrV5CpuEngine(OcrEngine):
    name = "ppocrv5"

    def __init__(self) -> None:
        self._ocr = None

    def load(self) -> None:
        from paddleocr import PaddleOCR  # heavy import — worker only

        settings = get_settings()
        model_dir = settings.models_dir / "pp-ocrv5"
        kwargs = {"lang": "japan", "device": "cpu"}
        if model_dir.exists():
            kwargs["text_detection_model_dir"] = str(model_dir / "det")
            kwargs["text_recognition_model_dir"] = str(model_dir / "rec")
        self._ocr = PaddleOCR(**kwargs)

    def parse_page(self, image_path: Path) -> PageResult:
        assert self._ocr is not None, "engine not loaded"
        regions: list[Region] = []
        for output in self._ocr.predict(str(image_path)):
            res = output if isinstance(output, dict) else getattr(output, "json", {}).get("res", {})
            texts = res.get("rec_texts", [])
            scores = res.get("rec_scores", [1.0] * len(texts))
            boxes = res.get("rec_boxes", [[0, 0, 0, 0]] * len(texts))
            for text, score, box in zip(texts, scores, boxes):
                regions.append(
                    Region(
                        bbox=tuple(float(v) for v in list(box)[:4]),
                        kind="text",
                        markdown=str(text),
                        confidence=float(score),
                    )
                )
        return PageResult(regions=regions)
