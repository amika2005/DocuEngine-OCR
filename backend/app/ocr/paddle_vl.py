"""PaddleOCR-VL 0.9B — primary engine. Document-parsing VLM: layout analysis +
recognition (JA/EN mixed, handwriting, tables → HTML/markdown) in one pipeline.

Weights are loaded from MODELS_DIR only — never downloaded — to keep client
installs air-gapped. Requires the `ocr` dependency extra (paddleocr, paddlepaddle-gpu).
"""

import html
import re
from pathlib import Path

from app.config import get_settings
from app.ocr.assemble import html_table_to_markdown
from app.ocr.engine import OcrEngine, PageResult, Region


class PaddleOcrVlEngine(OcrEngine):
    name = "paddleocr-vl"

    def __init__(self) -> None:
        self._pipeline = None

    def load(self) -> None:
        from paddleocr import PaddleOCRVL  # heavy import — worker only

        settings = get_settings()
        vl_dir = settings.models_dir / "paddleocr-vl"
        layout_dir = settings.models_dir / "pp-doclayoutv2"
        self._pipeline = PaddleOCRVL(
            vl_rec_model_dir=str(vl_dir) if vl_dir.exists() else None,
            layout_detection_model_dir=str(layout_dir) if layout_dir.exists() else None,
        )

    def parse_page(self, image_path: Path) -> PageResult:
        assert self._pipeline is not None, "engine not loaded"
        regions: list[Region] = []
        for output in self._pipeline.predict(str(image_path)):
            res = output if isinstance(output, dict) else getattr(output, "json", {}).get("res", {})
            for block in res.get("parsing_res_list", []):
                regions.append(self._block_to_region(block))
        return PageResult(regions=regions)

    @staticmethod
    def _block_to_region(block: dict) -> Region:
        label = str(block.get("block_label", "text")).lower()
        content = str(block.get("block_content", "") or "")
        bbox = block.get("block_bbox") or [0, 0, 0, 0]
        confidence = float(block.get("block_score") or block.get("score") or 1.0)

        if label == "table":
            kind = "table"
            markdown = (
                html_table_to_markdown(content) if "<table" in content.lower() else content
            )
        elif label in ("doc_title", "paragraph_title", "title"):
            kind = "title"
            markdown = f"## {html.unescape(content).strip()}"
        elif label in ("image", "figure", "chart", "seal"):
            kind = "figure"
            markdown = ""
        else:
            kind = "handwriting" if "hand" in label else "text"
            markdown = html.unescape(content).strip()

        vertical = bool(re.search(r"vertical|vert", label))
        return Region(
            bbox=tuple(float(v) for v in bbox[:4]),
            kind=kind,
            markdown=markdown,
            confidence=confidence,
            vertical=vertical,
        )
