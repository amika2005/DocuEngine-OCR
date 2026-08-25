"""RapidOCR engine — PP-OCRv6 multilingual models via ONNX Runtime.

Runs PaddleOCR's PP-OCRv6 detection + recognition models through ONNX Runtime,
which avoids the Windows oneDNN/PIR crashes of the paddle runtime while keeping
the same model quality.  The v6 multilingual recognizer covers Japanese
(kanji + kana) and English in one model; OCR_MODEL_SIZE picks the
speed/accuracy trade-off (tiny | small | medium).

Model files are downloaded once into MODELS_DIR/ppocr and reused offline.
Tables are detected with img2table and assembled from the single OCR pass by
clustering lines into rows (y) and columns (x), so no second OCR pass is needed.
"""

from pathlib import Path
from statistics import median

from app.config import get_settings
from app.ocr.assemble import cells_to_markdown
from app.ocr.engine import OcrEngine, PageResult, Region

# The multilingual recognizer sometimes emits the simplified/traditional Chinese
# variant of a kanji in Japanese text (爱知県 instead of 愛知県).  Map the
# common confusions back to the Japanese (shinjitai) form.
_ZH_TO_JA = str.maketrans(
    {
        "爱": "愛",
        "纳": "納",
        "单": "単",
        "稅": "税",
        "额": "額",
        "别": "別",
        "况": "況",
        "錄": "録",
        "录": "録",
        "览": "覧",
        "覽": "覧",
        "历": "歴",
        "歷": "歴",
        "详": "詳",
        "确": "確",
        "变": "変",
        "變": "変",
        "拔": "抜",
        "拨": "抜",
        "处": "処",
        "處": "処",
        "间": "間",
        "问": "問",
        "开": "開",
        "关": "関",
        "报": "報",
        "设": "設",
        "计": "計",
        "记": "記",
        "货": "貨",
        "价": "価",
        "顾": "顧",
        "顯": "顕",
        "机": "機",
        "级": "級",
        "组": "組",
        "线": "線",
        "编": "編",
        "认": "認",
        "证": "証",
        "验": "験",
        "险": "険",
        "务": "務",
        "员": "員",
        "购": "購",
        "销": "銷",
        "费": "費",
        "资": "資",
        "质": "質",
        "选": "選",
        "达": "達",
        "运": "運",
        "邮": "郵",
        "银": "銀",
        "钱": "銭",
        "铁": "鉄",
        "总": "総",
        "统": "統",
        "继": "継",
        "续": "続",
        "绝": "絶",
        "终": "終",
        "结": "結",
        "给": "給",
        "绿": "緑",
        "网": "網",
    }
)


def _normalize_ja(text: str) -> str:
    return text.translate(_ZH_TO_JA)


class _Line:
    """One recognized text line from the full-page OCR pass."""

    __slots__ = ("bbox", "text", "confidence")

    def __init__(self, bbox: tuple[float, float, float, float], text: str, confidence: float):
        self.bbox = bbox
        self.text = text
        self.confidence = confidence

    @property
    def cx(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2

    @property
    def cy(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]


def _center_inside(line: _Line, bbox: tuple, pad: float = 4.0) -> bool:
    x0, y0, x1, y1 = bbox
    return x0 - pad <= line.cx <= x1 + pad and y0 - pad <= line.cy <= y1 + pad


def _cluster_rows(lines: list[_Line]) -> list[list[_Line]]:
    """Group lines whose vertical centers are within ~60% of a line height."""
    if not lines:
        return []
    tolerance = median(line.height for line in lines) * 0.6
    rows: list[list[_Line]] = []
    for line in sorted(lines, key=lambda l: l.cy):
        if rows and abs(line.cy - rows[-1][0].cy) <= tolerance:
            rows[-1].append(line)
        else:
            rows.append([line])
    for row in rows:
        row.sort(key=lambda l: l.bbox[0])
    return rows


def _column_anchors(rows: list[list[_Line]], table_width: float) -> list[float]:
    """Derive column center positions by 1-D clustering of line centers.

    Centers across all rows are sorted and split wherever the gap exceeds a
    fraction of the table width; each cluster's mean becomes a column anchor.
    """
    centers = sorted(line.cx for row in rows for line in row)
    if not centers:
        return []
    min_gap = max(table_width * 0.05, 30.0)
    clusters: list[list[float]] = [[centers[0]]]
    for c in centers[1:]:
        if c - clusters[-1][-1] <= min_gap:
            clusters[-1].append(c)
        else:
            clusters.append([c])
    return [sum(c) / len(c) for c in clusters]


def _table_to_markdown(lines: list[_Line], bbox: tuple) -> str:
    """Assemble OCR lines inside a table bbox into a GFM markdown table."""
    rows = _cluster_rows(lines)
    if not rows:
        return ""
    anchors = _column_anchors(rows, table_width=bbox[2] - bbox[0])
    if not anchors:
        return ""

    grid: list[list[str]] = []
    for row in rows:
        cells = [""] * len(anchors)
        for line in row:
            col = min(range(len(anchors)), key=lambda i: abs(anchors[i] - line.cx))
            cells[col] = f"{cells[col]} {line.text}".strip() if cells[col] else line.text
        grid.append(cells)

    # Drop columns that ended up entirely empty.
    used = [i for i in range(len(anchors)) if any(row[i] for row in grid)]
    grid = [[row[i] for i in used] for row in grid]
    return cells_to_markdown(grid)


class RapidOcrEngine(OcrEngine):
    name = "rapidocr"

    def __init__(self) -> None:
        self._engine = None

    def load(self) -> None:
        from rapidocr import ModelType, OCRVersion, RapidOCR

        settings = get_settings()
        size = settings.ocr_model_size
        model_dir = settings.models_dir / "ppocr"
        model_dir.mkdir(parents=True, exist_ok=True)
        self._engine = RapidOCR(
            params={
                "Global.model_root_dir": str(model_dir),
                # Don't downscale below the rasterizer's own cap.
                "Global.max_side_len": settings.ocr_max_long_edge,
                # Only flip a text line 180° when the classifier is very sure;
                # at the default 0.9 it flips handwriting on skewed photos and
                # the line comes out reversed (e.g. NOTL07-… for …-LOTION).
                "Cls.cls_thresh": 0.98,
                # DirectML GPU acceleration; rapidocr falls back to CPU with a
                # warning when the provider is missing, so this is safe to set.
                "EngineConfig.onnxruntime.use_dml": settings.ocr_use_gpu,
                "Det.ocr_version": OCRVersion.PPOCRV6,
                "Det.model_type": ModelType(size),
                "Rec.ocr_version": OCRVersion.PPOCRV6,
                "Rec.model_type": ModelType(size),
            }
        )

    def parse_page(self, image_path: Path) -> PageResult:
        assert self._engine is not None, "engine not loaded"

        lines = self._recognize(image_path)
        table_bboxes = self._detect_tables(image_path)

        regions: list[Region] = []
        remaining = lines
        for bbox in table_bboxes:
            inside = [l for l in remaining if _center_inside(l, bbox)]
            remaining = [l for l in remaining if l not in inside]
            md = _table_to_markdown(inside, bbox)
            if md.strip():
                confidence = sum(l.confidence for l in inside) / len(inside)
                regions.append(
                    Region(bbox=bbox, kind="table", markdown=md, confidence=confidence)
                )

        for line in remaining:
            regions.append(
                Region(
                    bbox=line.bbox,
                    kind="text",
                    markdown=line.text,
                    confidence=line.confidence,
                )
            )
        return PageResult(regions=regions)

    def _recognize(self, image_path: Path) -> list[_Line]:
        """Full-page OCR pass — one detection + recognition over the image."""
        result = self._engine(str(image_path))
        lines: list[_Line] = []
        boxes = result.boxes if result.boxes is not None else []
        txts = result.txts or []
        scores = result.scores or [1.0] * len(txts)
        for box, text, score in zip(boxes, txts, scores):
            text = _normalize_ja(str(text)).strip()
            if not text:
                continue
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
            lines.append(
                _Line(
                    bbox=(min(xs), min(ys), max(xs), max(ys)),
                    text=text,
                    confidence=float(score),
                )
            )
        return lines

    def _detect_tables(self, image_path: Path) -> list[tuple[float, float, float, float]]:
        from app.ocr.table_layout import detect_tables_on_image

        return detect_tables_on_image(image_path)
