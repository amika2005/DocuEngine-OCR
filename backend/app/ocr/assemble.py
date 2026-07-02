"""Turns engine regions into final Markdown.

Reading order rules:
- Horizontal (yokogaki) regions read top-to-bottom, then left-to-right within a band.
- Vertical (tategaki) regions — common in Japanese business letters — read
  right-to-left, then top-to-bottom within a column.
- Mixed pages are ordered band-by-band; vertical regions inside a band sort
  right-to-left while horizontal ones sort left-to-right.
"""

import re
from html.parser import HTMLParser

from app.ocr.engine import PageResult, Region

# Regions whose vertical centers are within this fraction of page height are
# treated as one horizontal band (side-by-side content).
_BAND_TOLERANCE = 0.04

PAGE_SEPARATOR = "\n\n---\n\n"


def page_markdown(result: PageResult) -> str:
    regions = [r for r in result.regions if r.markdown.strip()]
    if not regions:
        return ""
    ordered = order_regions(regions)
    return "\n\n".join(r.markdown.strip() for r in ordered)


def order_regions(regions: list[Region]) -> list[Region]:
    page_height = max((r.bbox[3] for r in regions), default=1.0) or 1.0
    tolerance = page_height * _BAND_TOLERANCE

    def center_y(r: Region) -> float:
        return (r.bbox[1] + r.bbox[3]) / 2

    # Group into horizontal bands of visually-aligned regions.
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
