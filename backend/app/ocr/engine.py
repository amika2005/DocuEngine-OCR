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
        elif name == "easyocr":
            from app.ocr.easy_ocr import EasyOcrEngine

            _engine = EasyOcrEngine()
        elif name == "rapidocr":
            from app.ocr.rapid_ocr import RapidOcrEngine

            _engine = RapidOcrEngine()
        elif name == "sonasu-ocr":
            from app.ocr.sonasu_ocr import SonasuOcrEngine

            _engine = SonasuOcrEngine()
        elif name == "mock":
            from app.ocr.mock import MockEngine

            _engine = MockEngine()
        else:
            raise ValueError(f"Unknown OCR_ENGINE: {name}")
        try:
            _engine.load()
        except ImportError as exc:
            _engine = None  # retry cleanly once the environment is fixed
            raise RuntimeError(
                f"OCR engine '{name}' could not load: {exc}. "
                "The paddle stack is not installed in this environment — install it "
                "with `uv sync --extra ocr` (CPU) or use the worker Docker image, "
                "or set OCR_ENGINE=mock for development without models."
            ) from exc
        except Exception as exc:
            _engine = None
            hint = (
                "Set SONASU_OCR_API_KEY (Bearer key for https://edge.sonasu.jp) "
                "or set OCR_ENGINE=mock."
                if name == "sonasu-ocr"
                else (
                    "Check MODELS_DIR points at the downloaded model weights "
                    "(scripts/fetch_models.py) or set OCR_ENGINE=mock."
                )
            )
            raise RuntimeError(f"OCR engine '{name}' failed to load: {exc}. {hint}") from exc
    return _engine


def reset_engine() -> None:
    global _engine
    _engine = None
