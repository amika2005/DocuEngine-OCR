"""Rebuild GFM tables from OCR line boxes when the engine has no table output.

Office RapidOCR returns text + positions only. This module:

- prefers img2table bounding boxes from the page image (ruled + borderless)
- falls back to geometry: 3+ column grids, wrapped 品目, 合計金額 pairs
"""

from __future__ import annotations

from pathlib import Path
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

_KV_LABELS = (
    "合計金額",
    "消費税額合計",
    "消費税額",
    "消費税",
    "税率別内訳",
    "税抜金額",
    "税込金額",
    "対象額",
    "小計",
    "合計",
    "備考",
    "件名",
    "税額",
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
    """Group lines that share a horizontal band (boxes overlap in y)."""
    if not lines:
        return []
    ordered = sorted(lines, key=lambda item: (item.cy, item.bbox[0]))
    rows: list[list[Line]] = []
    for line in ordered:
        best_i: int | None = None
        best_overlap = 0.0
        for index, row in enumerate(rows):
            y0 = min(item.bbox[1] for item in row)
            y1 = max(item.bbox[3] for item in row)
            overlap = min(line.bbox[3], y1) - max(line.bbox[1], y0)
            if overlap <= 0:
                continue
            threshold = min(line.height, max(y1 - y0, 1.0)) * 0.25
            if overlap >= threshold and overlap > best_overlap:
                best_overlap = overlap
                best_i = index
        if best_i is None:
            rows.append([line])
        else:
            rows[best_i].append(line)
    rows.sort(key=lambda row: min(item.cy for item in row))
    for row in rows:
        row.sort(key=lambda item: item.bbox[0])
    return rows


def column_anchors(rows: list[list[Line]], table_width: float) -> list[float]:
    """Column centers. Prefer the richest row (usually the header) so wrapped
    品目 text does not invent extra columns."""
    if not rows:
        return []
    rich = max(rows, key=_row_cell_count)
    if _row_cell_count(rich) >= 2:
        return [line.cx for line in sorted(rich, key=lambda item: item.cx)]
    centers = sorted(line.cx for row in rows for line in row)
    min_gap = max(table_width * 0.05, 30.0)
    clusters: list[list[float]] = [[centers[0]]]
    for center in centers[1:]:
        if center - clusters[-1][-1] <= min_gap:
            clusters[-1].append(center)
        else:
            clusters.append([center])
    return [sum(cluster) / len(cluster) for cluster in clusters]


def table_to_markdown(lines: list[Line], bbox: BBox) -> str:
    rows = _merge_wrap_rows(cluster_rows(lines))
    if not rows:
        return ""
    anchors = column_anchors(rows, table_width=max(bbox[2] - bbox[0], 1.0))
    if not anchors:
        return ""
    grid: list[list[str]] = []
    for row in rows:
        cells = [""] * len(anchors)
        for line in row:
            col = min(range(len(anchors)), key=lambda i: abs(anchors[i] - line.cx))
            if cells[col]:
                sep = "\n" if abs(line.cy - row[0].cy) > row[0].height * 0.6 else " "
                cells[col] = f"{cells[col]}{sep}{line.text}".strip()
            else:
                cells[col] = line.text
        grid.append(cells)
    used = [i for i in range(len(anchors)) if any(row[i] for row in grid)]
    grid = [[row[i] for i in used] for row in grid]
    return cells_to_markdown(grid)


def detect_table_bboxes_from_lines(lines: list[Line]) -> list[BBox]:
    """Item grids plus label/amount pairs. Wrapped description rows stay inside
    the grid span instead of splitting it."""
    rows = _logical_rows(lines)
    if not rows:
        return []
    kinds = [_row_kind(row) for row in rows]
    used = [False] * len(rows)
    bboxes: list[BBox] = []

    index = 0
    while index < len(rows):
        if kinds[index] != "grid":
            index += 1
            continue
        start = index
        end = index + 1
        while end < len(rows):
            if kinds[end] in ("grid", "kv"):
                end += 1
                continue
            if _is_continuation(rows[end], rows[start:end]):
                end += 1
                continue
            break
        n_grid = sum(1 for j in range(start, end) if kinds[j] == "grid")
        if n_grid >= 2 or (n_grid >= 1 and end - start >= 2):
            for j in range(start, end):
                used[j] = True
            table_lines = [line for row in rows[start:end] for line in row]
            bboxes.append(_union_bbox(table_lines))
        index = max(end, start + 1)

    index = 0
    while index < len(rows):
        if used[index] or kinds[index] != "kv":
            index += 1
            continue
        start = index
        end = index + 1
        while end < len(rows) and not used[end] and kinds[end] == "kv":
            end += 1
        for j in range(start, end):
            used[j] = True
        table_lines = [line for row in rows[start:end] for line in row]
        bboxes.append(_union_bbox(table_lines))
        index = end

    bboxes.sort(key=lambda box: (box[1], box[0]))
    return bboxes


def detect_tables_on_image(image_path: Path) -> list[BBox]:
    """img2table structure only — cell text comes from the OCR line pass.

    Missing opencv/img2table (API image without the tables extra) is a
    no-op so geometry fallback still runs.
    """
    try:
        from img2table.document import Image as Img2TableImage

        document = Img2TableImage(str(image_path))
        tables = document.extract_tables(implicit_rows=True, borderless_tables=True)
    except Exception:
        return []
    boxes: list[BBox] = []
    for table in tables:
        box = (
            float(table.bbox.x1),
            float(table.bbox.y1),
            float(table.bbox.x2),
            float(table.bbox.y2),
        )
        boxes.append(_expand_bbox(box, pad=8.0))
    return boxes


def merge_table_bboxes(image_boxes: list[BBox], geometry_boxes: list[BBox]) -> list[BBox]:
    """Prefer img2table grids; keep geometry boxes (合計金額, …) that do not overlap."""
    merged = list(image_boxes)
    for geo in geometry_boxes:
        if any(_bbox_iou(geo, existing) > 0.25 for existing in merged):
            continue
        merged.append(geo)
    merged.sort(key=lambda box: (box[1], box[0]))
    return merged


def _expand_bbox(box: BBox, pad: float) -> BBox:
    return (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)


def _bbox_iou(a: BBox, b: BBox) -> float:
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if inter <= 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    denom = area_a + area_b - inter
    return inter / denom if denom else 0.0


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


def _logical_rows(lines: list[Line]) -> list[list[Line]]:
    """Visual bands, split at a wide horizontal gap (title | 合計金額 box)."""
    logical: list[list[Line]] = []
    for band in cluster_rows(lines):
        logical.extend(_split_wide_gaps(band))
    return logical


def _split_wide_gaps(row: list[Line]) -> list[list[Line]]:
    """Split a visual band when one gap is an outlier (title | 合計金額).

    Item-table columns have similar gaps; do not split those.
    """
    if len(row) < 2:
        return [row]
    ordered = sorted(row, key=lambda line: line.bbox[0])
    gaps = [current.bbox[0] - prev.bbox[2] for prev, current in zip(ordered, ordered[1:])]
    split_after: set[int] = set()
    for index, gap in enumerate(gaps):
        others = [other for j, other in enumerate(gaps) if j != index]
        sibling = max(others) if others else 0.0
        if gap >= 120 and (not others or gap >= max(sibling * 2.0, 120.0)):
            split_after.add(index)
    if not split_after:
        return [row]
    groups: list[list[Line]] = [[ordered[0]]]
    for index, current in enumerate(ordered[1:]):
        if index in split_after:
            groups.append([current])
        else:
            groups[-1].append(current)
    return groups


def _row_kind(row: list[Line]) -> str:
    n_cols = _row_cell_count(row)
    joined = "".join(line.text for line in row)
    if n_cols >= 3:
        return "grid"
    if n_cols >= 2 and _header_hint_count(joined) >= 2:
        return "grid"
    if (n_cols == 2 or len(row) == 2) and _is_kv_pair(row):
        return "kv"
    return "other"


def _header_hint_count(text: str) -> int:
    return sum(1 for header in _TABLE_HEADERS if header in text)


def _is_kv_pair(row: list[Line]) -> bool:
    ordered = sorted(row, key=lambda line: line.bbox[0])
    left, right = ordered[0], ordered[-1]
    if left is right:
        return False
    left_text, right_text = left.text.strip(), right.text.strip()
    if any(label in left_text for label in _KV_LABELS):
        return True
    if any(label in right_text for label in _KV_LABELS) and _looks_amount(left_text):
        return True
    return False


def _looks_amount(text: str) -> bool:
    compact = (
        text.replace(",", "")
        .replace(" ", "")
        .replace("円", "")
        .replace("¥", "")
        .replace("￥", "")
    )
    digits = sum(ch.isdigit() for ch in compact)
    if digits < 1:
        return False
    other = sum(ch.isalpha() for ch in compact)
    return digits >= other


def _is_continuation(row: list[Line], table_rows: list[list[Line]]) -> bool:
    if _row_cell_count(row) != 1 or not table_rows:
        return False
    line = row[0]
    prev_lines = [item for group in table_rows for item in group]
    table_x0 = min(item.bbox[0] for item in prev_lines)
    table_x1 = max(item.bbox[2] for item in prev_lines)
    width = max(table_x1 - table_x0, 1.0)
    if line.cx > table_x0 + width * 0.45:
        return False
    last_y1 = max(item.bbox[3] for item in table_rows[-1])
    gap = line.bbox[1] - last_y1
    typical = median(item.height for item in prev_lines)
    return gap <= typical * 4


def _merge_wrap_rows(rows: list[list[Line]]) -> list[list[Line]]:
    if not rows:
        return []
    merged: list[list[Line]] = [list(rows[0])]
    for row in rows[1:]:
        if _row_cell_count(row) == 1 and merged[-1]:
            line = row[0]
            prev = merged[-1]
            second_x = (
                sorted(prev, key=lambda item: item.bbox[0])[1].bbox[0]
                if len(prev) >= 2
                else prev[0].bbox[2] + 80
            )
            if line.cx < second_x:
                left = min(prev, key=lambda item: item.bbox[0])
                merged[-1] = [
                    Line(left.bbox, f"{left.text}\n{line.text}", left.confidence)
                    if item is left
                    else item
                    for item in prev
                ]
                continue
        merged.append(list(row))
    return merged


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
