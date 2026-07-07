"""Input normalization: PDFs and scanner images (PNG/JPEG/TIFF, incl. multi-page
TIFF) are rasterized to per-page PNGs via PyMuPDF. Resolution is capped so a
single oversized scan can never blow GPU memory.

Image inputs (camera photos, scanned JPEG/PNG) get photo enhancement —
perspective correction, background crop, illumination normalization — before
deskew. Native PDFs are digital scans that already OCR near-perfectly, so they
take the deskew-only path to guarantee no regression on that flagship flow."""

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

from app.config import get_settings

_PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp", ".heic"}

# Deskew only within this window: below the minimum the page is effectively
# straight; above the maximum the "skew" is probably page content (e.g. a
# rotated photo of several documents) and rotating would make things worse.
_DESKEW_MIN_DEG = 0.4
_DESKEW_MAX_DEG = 15.0


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
    is_photo = settings.ocr_photo_enhance and input_path.suffix.lower() in _PHOTO_SUFFIXES

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
            if is_photo:
                enhance_photo_in_place(out)
            width, height = deskew_in_place(out)
            pages.append(
                RasterizedPage(
                    page_number=number,
                    path=out,
                    width_px=width,
                    height_px=height,
                    dpi=int(72 * zoom),
                )
            )
    return pages


def enhance_photo_in_place(image_path: Path) -> None:
    """Apply camera-photo enhancement, overwriting the file. Best-effort: any
    failure leaves the rasterized image untouched."""
    import cv2

    from app.ocr.photo import enhance_photo

    try:
        img = cv2.imread(str(image_path))
        if img is None:
            return
        cv2.imwrite(str(image_path), enhance_photo(img))
    except Exception:
        pass


def deskew_in_place(image_path: Path) -> tuple[int, int]:
    """Straighten a slightly tilted page image, overwriting the file.

    The skew angle is the median slope of long near-horizontal edges (table
    rules, text baselines). Returns the final (width, height); on any failure
    the original file is kept untouched.
    """
    import cv2
    import numpy as np

    img = cv2.imread(str(image_path))
    if img is None:
        from PIL import Image

        with Image.open(image_path) as pil:
            return pil.size

    height, width = img.shape[:2]
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 360,
            threshold=120,
            minLineLength=width // 4,
            maxLineGap=15,
        )
        if lines is None:
            return width, height
        angles = []
        for (x0, y0, x1, y1) in lines[:, 0]:
            angle = np.degrees(np.arctan2(y1 - y0, x1 - x0))
            if abs(angle) <= _DESKEW_MAX_DEG:
                angles.append(angle)
        if len(angles) < 5:
            return width, height
        skew = float(np.median(angles))
        if not (_DESKEW_MIN_DEG <= abs(skew) <= _DESKEW_MAX_DEG):
            return width, height
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), skew, 1.0)
        rotated = cv2.warpAffine(
            img,
            matrix,
            (width, height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
        cv2.imwrite(str(image_path), rotated)
    except Exception:
        return width, height
    return width, height
