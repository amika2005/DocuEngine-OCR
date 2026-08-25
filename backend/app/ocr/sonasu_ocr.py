"""Office RapidOCR via the Sonasu gateway (https://edge.sonasu.jp/ocr).

No local model weights. Each rasterized page is POSTed as JSON; the worker
maps line boxes back into DocuEngine regions. The API key stays in server
config and is sent only as Authorization: Bearer — never X-Api-Key.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from app.ocr.engine import OcrEngine, PageResult, Region

PostJson = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


def http_error_message(status: int, body: str, api_key: str = "") -> str:
    text = (body or "")[:500]
    if api_key:
        text = text.replace(api_key, "***")
    return f"Office OCR HTTP {status}: {text}"


def page_result_from_office_payload(payload: dict[str, Any]) -> PageResult:
    raw_lines = payload.get("lines") or []
    regions: list[Region] = []
    for line in raw_lines:
        text = str(line.get("text") or "").strip()
        if not text:
            continue
        regions.append(
            Region(
                bbox=_box_to_bbox(line.get("box") or []),
                kind="text",
                markdown=text,
                confidence=float(line.get("score") or 0.0),
            )
        )
    if regions:
        return PageResult(regions=regions)
    full = str(payload.get("text") or "").strip()
    if full and not raw_lines:
        return PageResult(
            regions=[
                Region(bbox=(0.0, 0.0, 0.0, 0.0), kind="text", markdown=full, confidence=1.0)
            ]
        )
    return PageResult(regions=[])


def _box_to_bbox(box: list) -> tuple[float, float, float, float]:
    if not box:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [float(p[0]) for p in box]
    ys = [float(p[1]) for p in box]
    return (min(xs), min(ys), max(xs), max(ys))


def default_office_ocr_post(
    url: str, headers: dict[str, str], body: dict[str, Any], timeout: float
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    api_key = headers.get("Authorization", "").removeprefix("Bearer ").strip()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(http_error_message(exc.code, err_body, api_key)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Office OCR unreachable: {exc.reason}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Office OCR returned non-JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Office OCR returned an unexpected JSON shape")
    return payload


class SonasuOcrEngine(OcrEngine):
    name = "sonasu-ocr"

    def __init__(self, post_json: PostJson | None = None) -> None:
        self._post_json = post_json or default_office_ocr_post
        self._base_url = ""
        self._api_key = ""
        self._timeout = 120.0

    def load(self) -> None:
        from app.config import get_settings

        settings = get_settings()
        key = (settings.sonasu_ocr_api_key or "").strip().replace("\r", "")
        if not key:
            raise RuntimeError(
                "SONASU_OCR_API_KEY is required when OCR_ENGINE=sonasu-ocr. "
                "Issue a DocuEngine-only Bearer key for https://edge.sonasu.jp."
            )
        self._api_key = key
        self._base_url = (settings.sonasu_ocr_base_url or "https://edge.sonasu.jp").rstrip("/")
        self._timeout = float(settings.sonasu_ocr_timeout_seconds)

    def parse_page(self, image_path: Path) -> PageResult:
        image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        payload = self._post_json(
            f"{self._base_url}/ocr/ocr",
            {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            {"image_b64": image_b64},
            self._timeout,
        )
        return page_result_from_office_payload(payload)
