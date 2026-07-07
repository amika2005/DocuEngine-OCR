"""Turns engine regions into final Markdown.

Reading order: recursive XY-cut. The page is split into horizontal strips at
significant vertical whitespace; a strip that contains side-by-side blocks
(e.g. client address on the left, issuer address on the right) is split into
columns at a wide horizontal gap and each column is read completely,
top-to-bottom, before moving to the next. Strips that don't split cleanly
fall back to band ordering (left-to-right within a visual row; right-to-left
for vertical/tategaki text).
"""

import re
from html.parser import HTMLParser
from statistics import median

from app.ocr.engine import PageResult, Region

# Regions whose vertical centers are within this fraction of page height are
# treated as one horizontal band (side-by-side content).
_BAND_TOLERANCE = 0.04
_MAX_CUT_DEPTH = 6

PAGE_SEPARATOR = "\n\n---\n\n"


def page_markdown(result: PageResult) -> str:
    regions = [r for r in result.regions if r.markdown.strip()]
    if not regions:
        return ""
    ordered = order_regions(regions)
    return "\n\n".join(r.markdown.strip() for r in ordered)


def order_regions(regions: list[Region]) -> list[Region]:
    if not regions:
        return []
    return _xy_cut(list(regions), depth=0)


def _split_on_gaps(regions: list[Region], axis: int, min_gap: float) -> list[list[Region]]:
    """Group regions whose projections onto `axis` (0=x, 1=y) are separated by
    whitespace wider than min_gap."""
    items = sorted(regions, key=lambda r: r.bbox[axis])
    groups: list[list[Region]] = [[items[0]]]
    group_end = items[0].bbox[axis + 2]
    for region in items[1:]:
        if region.bbox[axis] - group_end > min_gap:
            groups.append([region])
        else:
            groups[-1].append(region)
        group_end = max(group_end, region.bbox[axis + 2])
    return groups


def _xy_cut(regions: list[Region], depth: int) -> list[Region]:
    if len(regions) <= 1 or depth >= _MAX_CUT_DEPTH:
        return _band_sort(regions)

    line_height = median(r.bbox[3] - r.bbox[1] for r in regions)

    # 1. Horizontal strips at clear vertical whitespace (paragraph breaks).
    strips = _split_on_gaps(regions, axis=1, min_gap=line_height * 0.8)
    if len(strips) > 1:
        ordered: list[Region] = []
        for strip in strips:
            ordered.extend(_xy_cut(strip, depth + 1))
        return ordered

    # 2. Columns at a wide horizontal gap — read each column fully before the
    #    next, so left/right address blocks don't interleave line by line.
    width = max(r.bbox[2] for r in regions) - min(r.bbox[0] for r in regions)
    columns = _split_on_gaps(regions, axis=0, min_gap=max(width * 0.06, line_height * 1.5))
    if len(columns) > 1:
        ordered = []
        for column in columns:
            ordered.extend(_xy_cut(column, depth + 1))
        return ordered

    # 3. Nothing splits — plain visual-row ordering.
    return _band_sort(regions)


def _band_sort(regions: list[Region]) -> list[Region]:
    """Original band ordering: top-to-bottom rows, left-to-right within a row
    (right-to-left when the row is mostly vertical/tategaki text)."""
    if not regions:
        return []
    page_height = max((r.bbox[3] for r in regions), default=1.0) or 1.0
    tolerance = page_height * _BAND_TOLERANCE

    def center_y(r: Region) -> float:
        return (r.bbox[1] + r.bbox[3]) / 2

    bands: list[list[Region]] = []
    for region in sorted(regions, key=center_y):
        if bands and abs(center_y(region) - center_y(bands[-1][0])) <= tolerance:
            bands[-1].append(region)
        else:
            bands.append([region])

    ordered: list[Region] = []
    for band in bands:
        vertical_count = sum(1 for r in band if r.vertical)
        right_to_left = vertical_count > len(band) / 2
        band.sort(key=lambda r: -r.bbox[0] if right_to_left else r.bbox[0])
        ordered.extend(band)
    return ordered


def document_markdown(page_markdowns: list[str]) -> str:
    return PAGE_SEPARATOR.join(page_markdowns)


# --- Tables ---


def cells_to_markdown(rows: list[list[str]]) -> str:
    """Render a rectangular cell grid as a GFM table (first row = header)."""
    if not rows:
        return ""
    width = max(len(row) for row in rows)

    def render_row(row: list[str]) -> str:
        padded = list(row) + [""] * (width - len(row))
        return "| " + " | ".join(_escape_cell(c) for c in padded) + " |"

    lines = [render_row(rows[0]), "| " + " | ".join(["---"] * width) + " |"]
    lines += [render_row(row) for row in rows[1:]]
    return "\n".join(lines)


def _escape_cell(cell: str) -> str:
    return cell.strip().replace("|", "\\|").replace("\n", "<br>")


class _TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._cell: list[str] | None = None
        self._colspan = 1

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th"):
            self._cell = []
            self._colspan = int(dict(attrs).get("colspan", 1) or 1)
        elif tag == "br" and self._cell is not None:
            self._cell.append("\n")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self.rows:
            text = "".join(self._cell)
            self.rows[-1].append(text)
            # Preserve column alignment when a cell spans multiple columns.
            self.rows[-1].extend([""] * (self._colspan - 1))
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def html_table_to_markdown(html_str: str) -> str:
    """PaddleOCR-VL emits tables as HTML; convert to a GFM markdown table."""
    parser = _TableHTMLParser()
    parser.feed(html_str)
    rows = [row for row in parser.rows if any(c.strip() for c in row)]
    if not rows:
        # Fall back to stripping tags so content is never silently dropped.
        return re.sub(r"<[^>]+>", " ", html_str).strip()
    return cells_to_markdown(rows)
