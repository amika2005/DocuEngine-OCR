"""Input normalization: PDFs and scanner images (PNG/JPEG/TIFF, incl. multi-page
TIFF) are rasterized to per-page PNGs via PyMuPDF. Resolution is capped so a
single oversized scan can never blow GPU memory."""

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

from app.config import get_settings


@dataclass
class RasterizedPage:
    page_number: int  # 1-based
    path: Path
    width_px: int
    height_px: int
    dpi: int


def rasterize(
    input_path: Path,
    output_dir: Path,
    dpi: int | None = None,
    max_long_edge: int | None = None,
) -> list[RasterizedPage]:
    settings = get_settings()
    dpi = dpi or settings.ocr_dpi
    max_long_edge = max_long_edge or settings.ocr_max_long_edge
    output_dir.mkdir(parents=True, exist_ok=True)

    pages: list[RasterizedPage] = []
    with fitz.open(input_path) as doc:
        for index, page in enumerate(doc):
            number = index + 1
            zoom = dpi / 72
            rect = page.rect
            long_edge = max(rect.width, rect.height) * zoom
            if long_edge > max_long_edge:
                zoom *= max_long_edge / long_edge
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            out = output_dir / f"p{number}.png"
            pixmap.save(out)
            pages.append(
                RasterizedPage(
                    page_number=number,
                    path=out,
                    width_px=pixmap.width,
                    height_px=pixmap.height,
                    dpi=int(72 * zoom),
                )
            )
    return pages
