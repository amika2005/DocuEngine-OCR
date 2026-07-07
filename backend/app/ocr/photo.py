"""Camera-photo enhancement for OCR.

Phone photos of documents have three problems a flatbed scan never has: the
page sits at an angle inside a larger frame (desk/table around it), keystone
perspective distortion, and uneven lighting (shadows, glare). This module
detects the document quadrilateral, warps it to a flat rectangle (which also
crops the background), and evens out the lighting. Clean scans are left alone
because the quad detector only fires when a document clearly sits inside a
larger frame.
"""

from __future__ import annotations

import cv2
import numpy as np

# The detected page must cover at least this fraction of the frame (rejects
# small clutter) and leave at least this margin (else it's already full-bleed
# and warping would only add interpolation blur).
_MIN_QUAD_AREA_FRAC = 0.20
_MAX_QUAD_AREA_FRAC = 0.985


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """Return the 4 points ordered top-left, top-right, bottom-right,
    bottom-left using the sum/diff-of-coordinates trick."""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # smallest x+y → top-left
    rect[2] = pts[np.argmax(s)]  # largest  x+y → bottom-right
    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]  # smallest y-x → top-right
    rect[3] = pts[np.argmax(d)]  # largest  y-x → bottom-left
    return rect


def _quad_from_contour(contour: np.ndarray) -> np.ndarray | None:
    """Reduce a contour to four corners: convex hull, then an epsilon sweep of
    approxPolyDP, falling back to the min-area rotated rectangle."""
    hull = cv2.convexHull(contour)
    peri = cv2.arcLength(hull, True)
    for eps in (0.02, 0.03, 0.05, 0.07, 0.1):
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return approx.reshape(4, 2).astype(np.float32)
    # Rotated bounding box — recovers angle even when a corner is occluded.
    return cv2.boxPoints(cv2.minAreaRect(contour)).astype(np.float32)


def find_document_quad(img: np.ndarray) -> np.ndarray | None:
    """Locate the document's four corners in `img` (BGR). Returns corners in
    original-image coordinates, or None when the page already fills the frame
    (a clean scan) or nothing document-like is found.

    Paper is brighter than a desk, so an Otsu threshold segments the page far
    more reliably than edge detection on a folded/soft-edged photo.
    """
    h, w = img.shape[:2]
    scale = 1000.0 / max(h, w)
    small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    frame_area = small.shape[0] * small.shape[1]

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(contour)
    if not (_MIN_QUAD_AREA_FRAC * frame_area <= area):
        return None

    quad = _quad_from_contour(contour)
    if quad is None:
        return None

    # Only warp when it's worth it: the page is meaningfully inset from the
    # frame, or clearly rotated. A near-full-frame upright page is a clean
    # scan — leave it alone.
    (_, _), (rw, rh), angle_deg = cv2.minAreaRect(contour)
    rect_frac = (rw * rh) / frame_area
    angle = min(abs(angle_deg % 90), 90 - abs(angle_deg % 90))
    if rect_frac > _MAX_QUAD_AREA_FRAC and angle < 2.0:
        return None
    return quad / scale


def correct_perspective(img: np.ndarray) -> tuple[np.ndarray, bool]:
    """Warp the detected document to a flat rectangle. Returns (image, warped)
    — the original image unchanged when no quad is found."""
    quad = find_document_quad(img)
    if quad is None:
        return img, False
    rect = _order_corners(quad)
    (tl, tr, br, bl) = rect
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if width < 200 or height < 200:
        return img, False
    dst = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(img, matrix, (width, height), flags=cv2.INTER_CUBIC)
    return warped, True


def normalize_illumination(img: np.ndarray) -> np.ndarray:
    """Even out shadows and glare, returning a clean grayscale-on-white image.

    Background is estimated with a large median blur of a dilated copy, then
    the page is divided by it (flat-field correction) so paper reads as white
    everywhere regardless of the original lighting gradient.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    # Dilating first removes dark text before we estimate the paper background.
    dilated = cv2.dilate(gray, np.ones((7, 7), np.uint8))
    bg = cv2.medianBlur(dilated, 21)
    bg = np.where(bg == 0, 1, bg)
    normalized = np.clip(gray.astype(np.float32) / bg.astype(np.float32) * 255.0, 0, 255)
    normalized = normalized.astype(np.uint8)
    # Gentle contrast lift so faint text stays legible after flattening.
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    normalized = clahe.apply(normalized)
    return cv2.cvtColor(normalized, cv2.COLOR_GRAY2BGR)


def enhance_photo(img: np.ndarray) -> np.ndarray:
    """Full photo pipeline for camera/scanner image inputs: crop+flatten the
    page when it sits inside a larger frame, then even out the lighting.
    Illumination normalization is always applied (neutral-to-positive even on
    already-flat photos); perspective correction only when a quad is found."""
    warped, _ = correct_perspective(img)
    return normalize_illumination(warped)
