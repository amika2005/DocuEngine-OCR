"""OCR engine seam. Every engine (PaddleOCR-VL on GPU, PP-OCRv5 on CPU, mock in
tests) implements parse_page() and is selected by the OCR_ENGINE setting, so the
pipeline, storage, and correction flow never depend on a specific model."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Region:
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 in page pixels
    kind: str  # text | table | figure | title | handwriting
    markdown: str
    confidence: float = 1.0
    vertical: bool = False  # tategaki — affects reading order


@dataclass
class PageResult:
    regions: list[Region] = field(default_factory=list)

    @property
    def avg_confidence(self) -> float | None:
        if not self.regions:
            return None
        return sum(r.confidence for r in self.regions) / len(self.regions)


class OcrEngine(ABC):
    name: str = "abstract"

    def load(self) -> None:
        """Load model weights into memory (called once per worker process)."""

    @abstractmethod
    def parse_page(self, image_path: Path) -> PageResult:
        """Parse one page image into layout regions with per-region markdown."""


_engine: OcrEngine | None = None


def get_engine() -> OcrEngine:
    """Process-wide engine singleton; the GPU worker keeps the model resident."""
    global _engine
    if _engine is None:
        from app.config import get_settings

        name = get_settings().ocr_engine
        if name == "paddleocr-vl":
            from app.ocr.paddle_vl import PaddleOcrVlEngine

            _engine = PaddleOcrVlEngine()
        elif name == "ppocrv5-cpu":
            from app.ocr.ppocrv5 import PpOcrV5CpuEngine

            _engine = PpOcrV5CpuEngine()
        elif name == "mock":
            from app.ocr.mock import MockEngine

            _engine = MockEngine()
        else:
            raise ValueError(f"Unknown OCR_ENGINE: {name}")
        _engine.load()
    return _engine


def reset_engine() -> None:
    global _engine
    _engine = None
