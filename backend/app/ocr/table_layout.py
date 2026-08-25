"""Rebuild GFM tables from OCR line boxes when the engine has no table output.

Office RapidOCR (and img2table-less installs) return text + positions only.
Rows are clustered by y, columns by x gaps, then rendered with cells_to_markdown.
Two-column letterheads are ignored; item grids (品目 / 単価 / 数量 / 価格) are not.
"""

from __future__ import annotations

from statistics import median

from app.ocr.assemble import cells_to_markdown
from app.ocr.engine import Region

BBox = tuple[float, float, float, float]

_TABLE_HEADERS = (
    "品目",
    "品名",
    "摘要",
    "内容",
    "明細",
    "単価",
    "数量",
    "単位",
    "金額",
    "価格",
    "税額",
    "小計",
)


class Line:
    """One recognized text line with an axis-aligned box."""

    __slots__ = ("bbox", "text", "confidence")

    def __init__(self, bbox: BBox, text: str, confidence: float):
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


def center_inside(line: Line, bbox: BBox, pad: float = 4.0) -> bool:
    x0, y0, x1, y1 = bbox
    return x0 - pad <= line.cx <= x1 + pad and y0 - pad <= line.cy <= y1 + pad


def cluster_rows(lines: list[Line]) -> list[list[Line]]:
    if not lines:
        return []
    tolerance = median(line.height for line in lines) * 0.6
    rows: list[list[Line]] = []
    for line in sorted(lines, key=lambda item: item.cy):
        if rows and abs(line.cy - rows[-1][0].cy) <= tolerance:
            rows[-1].append(line)
        else:
            rows.append([line])
    for row in rows:
        row.sort(key=lambda item: item.bbox[0])
    return rows


def column_anchors(rows: list[list[Line]], table_width: float) -> list[float]:
    centers = sorted(line.cx for row in rows for line in row)
    if not centers:
        return []
    min_gap = max(table_width * 0.05, 30.0)
    clusters: list[list[float]] = [[centers[0]]]
    for center in centers[1:]:
        if center - clusters[-1][-1] <= min_gap:
            clusters[-1].append(center)
        else:
            clusters.append([center])
    return [sum(cluster) / len(cluster) for cluster in clusters]


def table_to_markdown(lines: list[Line], bbox: BBox) -> str:
    rows = cluster_rows(lines)
    if not rows:
        return ""
    anchors = column_anchors(rows, table_width=bbox[2] - bbox[0])
    if not anchors:
        return ""
    grid: list[list[str]] = []
    for row in rows:
        cells = [""] * len(anchors)
        for line in row:
            col = min(range(len(anchors)), key=lambda i: abs(anchors[i] - line.cx))
            cells[col] = f"{cells[col]} {line.text}".strip() if cells[col] else line.text
        grid.append(cells)
    used = [i for i in range(len(anchors)) if any(row[i] for row in grid)]
    grid = [[row[i] for i in used] for row in grid]
    return cells_to_markdown(grid)


def detect_table_bboxes_from_lines(lines: list[Line]) -> list[BBox]:
    """Find item-grid spans from geometry. Does not require img2table."""
    rows = cluster_rows(lines)
    if len(rows) < 2:
        return []
    flags = [_is_table_row(row) for row in rows]
    bboxes: list[BBox] = []
    index = 0
    while index < len(rows):
        if not flags[index]:
            index += 1
            continue
        start = index
        index += 1
        while index < len(rows) and flags[index]:
            index += 1
        if index - start < 2:
            continue
        table_lines = [line for row in rows[start:index] for line in row]
        bboxes.append(_union_bbox(table_lines))
    return bboxes


def regions_from_ocr_lines(lines: list[Line], table_bboxes: list[BBox]) -> list[Region]:
    regions: list[Region] = []
    remaining = list(lines)
    for bbox in table_bboxes:
        inside = [line for line in remaining if center_inside(line, bbox)]
        remaining = [line for line in remaining if line not in inside]
        if not inside:
            continue
        markdown = table_to_markdown(inside, bbox)
        if not markdown.strip():
            remaining.extend(inside)
            continue
        confidence = sum(line.confidence for line in inside) / len(inside)
        regions.append(Region(bbox=bbox, kind="table", markdown=markdown, confidence=confidence))
    for line in remaining:
        regions.append(
            Region(bbox=line.bbox, kind="text", markdown=line.text, confidence=line.confidence)
        )
    return regions


def _is_table_row(row: list[Line]) -> bool:
    n_cols = _row_cell_count(row)
    if n_cols >= 3:
        return True
    joined = "".join(line.text for line in row)
    hints = sum(1 for header in _TABLE_HEADERS if header in joined)
    return n_cols >= 2 and hints >= 2


def _row_cell_count(row: list[Line]) -> int:
    if not row:
        return 0
    ordered = sorted(row, key=lambda line: line.bbox[0])
    if len(ordered) == 1:
        return 1
    min_gap = max(median(line.height for line in ordered) * 0.8, 20.0)
    count = 1
    for prev, current in zip(ordered, ordered[1:]):
        gap = current.bbox[0] - prev.bbox[2]
        if gap > min_gap:
            count += 1
    return count


def _union_bbox(lines: list[Line]) -> BBox:
    return (
        min(line.bbox[0] for line in lines),
        min(line.bbox[1] for line in lines),
        max(line.bbox[2] for line in lines),
        max(line.bbox[3] for line in lines),
    )
