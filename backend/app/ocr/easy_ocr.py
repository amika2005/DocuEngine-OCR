"""EasyOCR engine with img2table integration for table extraction.

Text is recognised by EasyOCR (Japanese + English).  Tables are detected
structurally by img2table (OpenCV-based, no GPU needed) and converted to
Markdown.  Text regions that overlap a detected table are excluded to avoid
duplication.
"""

from pathlib import Path

from app.ocr.assemble import cells_to_markdown
from app.ocr.engine import OcrEngine, PageResult, Region


def _boxes_overlap(a: tuple, b: tuple, threshold: float = 0.5) -> bool:
    """Return True if >threshold of box *a* is inside box *b*."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return False
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = max((ax1 - ax0) * (ay1 - ay0), 1)
    return inter / area_a >= threshold


class EasyOcrEngine(OcrEngine):
    name = "easyocr"

    def __init__(self) -> None:
        self._reader = None

    def load(self) -> None:
        import easyocr

        # Load the reader with Japanese and English
        self._reader = easyocr.Reader(["ja", "en"], gpu=False, verbose=False)

    def parse_page(self, image_path: Path) -> PageResult:
        assert self._reader is not None, "engine not loaded"

        regions: list[Region] = []

        # ── 1. Detect tables with img2table ──────────────────────────────
        table_bboxes: list[tuple[float, float, float, float]] = []
        try:
            from img2table.document import Image as Img2TableImage

            img_doc = Img2TableImage(str(image_path))
            extracted_tables = img_doc.extract_tables()

            for table in extracted_tables:
                # table.bbox is (x1, y1, x2, y2)
                bbox = (
                    float(table.bbox.x1),
                    float(table.bbox.y1),
                    float(table.bbox.x2),
                    float(table.bbox.y2),
                )
                table_bboxes.append(bbox)

                # Build a markdown table from the cell content
                # table.content is a dict {row_idx: {col_idx: CellContent}}
                if table.content:
                    rows: list[list[str]] = []
                    row_indices = sorted(table.content.keys())
                    for ri in row_indices:
                        col_dict = table.content[ri]
                        col_indices = sorted(col_dict.keys())
                        row_cells: list[str] = []
                        for ci in col_indices:
                            cell = col_dict[ci]
                            # cell.value is the text content
                            row_cells.append(str(cell.value) if cell.value else "")
                        rows.append(row_cells)
                    md = cells_to_markdown(rows) if rows else ""
                else:
                    md = ""

                # If table had no OCR content, use EasyOCR to read inside it
                if not md or all(c.strip() == "" for row in (rows if table.content else []) for c in row):
                    md = self._ocr_table_region(image_path, bbox)

                if md.strip():
                    regions.append(
                        Region(
                            bbox=bbox,
                            kind="table",
                            markdown=md,
                            confidence=0.8,
                            vertical=False,
                        )
                    )
        except Exception:
            # If table detection fails, continue with text-only OCR
            pass

        # ── 2. OCR all text with EasyOCR ─────────────────────────────────
        raw_results = self._reader.readtext(str(image_path))

        for bbox_pts, text, confidence in raw_results:
            xs = [point[0] for point in bbox_pts]
            ys = [point[1] for point in bbox_pts]
            text_bbox = (float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)))

            # Skip text regions that are inside a detected table
            if any(_boxes_overlap(text_bbox, tb) for tb in table_bboxes):
                continue

            regions.append(
                Region(
                    bbox=text_bbox,
                    kind="text",
                    markdown=text.strip(),
                    confidence=float(confidence),
                    vertical=False,
                )
            )

        return PageResult(regions=regions)

    def _ocr_table_region(self, image_path: Path, bbox: tuple) -> str:
        """Use EasyOCR to read text inside a table bounding box and format as markdown table."""
        from PIL import Image as PILImage

        img = PILImage.open(image_path)
        x0, y0, x1, y1 = [int(v) for v in bbox]
        cropped = img.crop((x0, y0, x1, y1))

        # Save temp crop
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            cropped.save(f.name)
            tmp_path = f.name

        try:
            results = self._reader.readtext(tmp_path)
            if not results:
                return ""

            # Group text by rows based on Y coordinate
            items = []
            for bbox_pts, text, conf in results:
                ys = [p[1] for p in bbox_pts]
                xs = [p[0] for p in bbox_pts]
                items.append({
                    "y_center": sum(ys) / len(ys),
                    "x_center": sum(xs) / len(xs),
                    "text": text.strip(),
                })

            if not items:
                return ""

            # Sort by Y, group into rows (items within 15px of each other)
            items.sort(key=lambda i: i["y_center"])
            rows: list[list[dict]] = [[items[0]]]
            for item in items[1:]:
                if abs(item["y_center"] - rows[-1][0]["y_center"]) < 15:
                    rows[-1].append(item)
                else:
                    rows.append([item])

            # Sort each row by X, extract text
            table_rows = []
            for row in rows:
                row.sort(key=lambda i: i["x_center"])
                table_rows.append([i["text"] for i in row])

            return cells_to_markdown(table_rows)
        finally:
            os.unlink(tmp_path)
