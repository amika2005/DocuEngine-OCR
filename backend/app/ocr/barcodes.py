"""Barcode & QR-code detection for document pages — location only, offline.

Invoices and delivery notes often carry a QR code or barcode (payment QR,
qualified-invoice QR, product barcodes). We locate them on the page so the UI
can show the code as a cropped image in the result — we deliberately do NOT
decode them to a value. Detection is pure image geometry via OpenCV and adds
only a few tens of milliseconds per page.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class DetectedCode:
    kind: str  # "qr" | "barcode"
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 in page pixels
    data_uri: str = ""  # PNG crop as a data: URI, for inline embedding


def _crop_data_uri(img, bbox, pad: int = 6) -> str:
    """Crop the code region (with a small quiet-zone margin) and return it as a
    base64 PNG data URI suitable for embedding directly in markdown."""
    import base64

    import cv2

    h, w = img.shape[:2]
    x0, y0, x1, y1 = (int(v) for v in bbox)
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(w, x1 + pad), min(h, y1 + pad)
    crop = img[y0:y1, x0:x1]
    if crop.size == 0:
        return ""
    ok, buf = cv2.imencode(".png", crop)
    if not ok:
        return ""
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def _bbox_of(points) -> tuple[float, float, float, float]:
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _valid(bbox, img_w, img_h) -> bool:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    # Reject degenerate / whole-page detections.
    return w > 12 and h > 12 and w < img_w * 0.95 and h < img_h * 0.95


def detect_codes(image_path: Path) -> list[DetectedCode]:
    """Locate every QR and 1-D barcode on the page image (no decoding)."""
    import cv2

    img = cv2.imread(str(image_path))
    if img is None:
        return []
    h, w = img.shape[:2]
    codes: list[DetectedCode] = []

    # The ArUco-based detector locates far more QR codes than the classic one
    # (finds all codes on a dense invoice; the classic one misses most).
    qr = cv2.QRCodeDetectorAruco() if hasattr(cv2, "QRCodeDetectorAruco") else cv2.QRCodeDetector()
    try:
        ok, points = qr.detectMulti(img)
        if ok and points is not None:
            for quad in points:
                bbox = _bbox_of(quad)
                if _valid(bbox, w, h):
                    codes.append(DetectedCode(kind="qr", bbox=bbox, data_uri=_crop_data_uri(img, bbox)))
    except cv2.error:
        pass

    if hasattr(cv2, "barcode"):
        try:
            ok, points = cv2.barcode.BarcodeDetector().detect(img)
            if ok and points is not None:
                for quad in points:
                    bbox = _bbox_of(quad)
                    if _valid(bbox, w, h):
                        codes.append(
                            DetectedCode(kind="barcode", bbox=bbox, data_uri=_crop_data_uri(img, bbox))
                        )
        except cv2.error:
            pass

    return codes
