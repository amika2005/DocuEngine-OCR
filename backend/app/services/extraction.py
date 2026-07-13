"""Template field extraction — offline, layout-based.

For each template field we look for its label among the OCR regions (text
lines and table cells), then capture the value from the same line (after ：),
the region to the right on the same row, or the region directly below —
the three layouts Japanese business documents actually use. Values are
type-checked and normalized (date → ISO, amount → digits), and every hit
carries a confidence plus the source bbox so the UI can highlight it.
"""

import re
import unicodedata
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, OcrResult, Page, Template

_SEPARATORS = "：:︓"
_DATE_RE = re.compile(
    r"(?P<y>\d{2,4})[年/\-.](?P<m>\d{1,2})[月/\-.](?P<d>\d{1,2})日?"
)
_AMOUNT_RE = re.compile(r"[¥￥]?\s*(?P<n>\d{1,3}(?:,\d{3})+|\d+)\s*(?:円|yen)?", re.IGNORECASE)
_NUMBER_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*")


def _norm(text: str) -> str:
    """Comparison form: full/half width unified, spaces dropped, lowered."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).lower()


class _Item:
    """One searchable snippet: a text region or a single table cell."""

    __slots__ = ("text", "bbox", "page_number", "confidence")

    def __init__(self, text: str, bbox: list, page_number: int, confidence: float):
        self.text = text.strip()
        self.bbox = bbox
        self.page_number = page_number
        self.confidence = confidence


def _collect_items(db: Session, document: Document) -> list[_Item]:
    items: list[_Item] = []
    pages = db.scalars(
        select(Page).where(Page.document_id == document.id).order_by(Page.page_number)
    ).all()
    for page in pages:
        result = db.scalar(
            select(OcrResult).where(OcrResult.page_id == page.id, OcrResult.is_current)
        )
        if result is None:
            continue
        for region in (result.layout_json or {}).get("regions", []):
            text = region.get("markdown", "")
            bbox = region.get("bbox", [0, 0, 0, 0])
            conf = float(region.get("confidence", 1.0))
            if region.get("kind") == "table":
                # Each cell becomes its own searchable item (table bbox as location).
                for line in text.splitlines():
                    if not (line.startswith("|") and line.endswith("|")):
                        continue
                    if re.fullmatch(r"\|[\s\-:|]+\|", line):
                        continue
                    for cell in line[1:-1].split("|"):
                        cell = cell.strip().replace("\\|", "|").replace("<br>", " ")
                        if cell:
                            items.append(_Item(cell, bbox, page.page_number, conf))
            else:
                items.append(_Item(text, bbox, page.page_number, conf))
    return items


def _labels_for(field: dict) -> list[str]:
    labels = [field.get("label", ""), field.get("key", "").replace("_", " ")]
    # Short comma/slash-separated hints in the description act as synonyms.
    for part in re.split(r"[,、/・;|]", field.get("description", "")):
        part = part.strip()
        if 0 < len(part) <= 20:
            labels.append(part)
    return [l for l in {_norm(l): l for l in labels if l.strip()}.values()]


def _typed_value(raw: str, field_type: str) -> tuple[str | None, bool]:
    """Normalize `raw` according to the field type.
    Returns (value, type_matched)."""
    raw = raw.strip()
    if not raw:
        return None, False
    if field_type == "date":
        m = _DATE_RE.search(unicodedata.normalize("NFKC", raw))
        if not m:
            return None, False
        y = int(m.group("y"))
        if y < 100:
            y += 2000
        return f"{y:04d}-{int(m.group('m')):02d}-{int(m.group('d')):02d}", True
    if field_type == "amount":
        m = _AMOUNT_RE.search(unicodedata.normalize("NFKC", raw))
        if not m:
            return None, False
        return m.group("n").replace(",", ""), True
    if field_type == "number":
        m = _NUMBER_RE.search(unicodedata.normalize("NFKC", raw))
        if not m:
            return None, False
        return m.group(0).replace(",", ""), True
    return raw, True  # text


def _rows_overlap(a: list, b: list) -> bool:
    """Vertical overlap ≥ half the smaller height → same visual row."""
    top = max(a[1], b[1])
    bottom = min(a[3], b[3])
    smaller = max(min(a[3] - a[1], b[3] - b[1]), 1)
    return (bottom - top) / smaller >= 0.5


def _value_candidates(item: _Item, label_norm: str, items: list[_Item]):
    """Yield (raw_value, source_item, proximity_score) for one label hit."""
    # 1. label：value on the same line
    stripped = re.sub(r"\s+", "", unicodedata.normalize("NFKC", item.text))
    pos = stripped.lower().find(label_norm)
    if pos >= 0:
        after = stripped[pos + len(label_norm):]
        after = after.lstrip("".join(_SEPARATORS) + " 　")
        if after:
            yield after, item, 1.0
    # 2. region to the right on the same row
    right = [
        other
        for other in items
        if other is not item
        and other.page_number == item.page_number
        and _rows_overlap(other.bbox, item.bbox)
        and other.bbox[0] >= item.bbox[2] - 5
    ]
    right.sort(key=lambda o: o.bbox[0])
    if right:
        yield right[0].text, right[0], 0.9
    # 3. region directly below (horizontal overlap)
    below = [
        other
        for other in items
        if other is not item
        and other.page_number == item.page_number
        and other.bbox[1] >= item.bbox[3] - 5
        and min(other.bbox[2], item.bbox[2]) - max(other.bbox[0], item.bbox[0]) > 0
    ]
    below.sort(key=lambda o: o.bbox[1])
    if below:
        yield below[0].text, below[0], 0.7


def _extract_field(field: dict, items: list[_Item]) -> dict:
    field_type = field.get("type", "text")
    best: dict | None = None
    for label in _labels_for(field):
        label_norm = _norm(label)
        if not label_norm:
            continue
        for item in items:
            if label_norm not in _norm(item.text):
                continue
            for raw, source, proximity in _value_candidates(item, label_norm, items):
                # Don't accept the label itself (or another field's label) as value.
                if _norm(raw) == label_norm or not raw.strip():
                    continue
                value, type_ok = _typed_value(raw, field_type)
                if value is None:
                    continue
                confidence = round(proximity * source.confidence * (1.0 if type_ok else 0.6), 3)
                candidate = {
                    "value": value,
                    "confidence": confidence,
                    "page_number": source.page_number,
                    "bbox": list(source.bbox),
                }
                if best is None or candidate["confidence"] > best["confidence"]:
                    best = candidate
            if best and best["confidence"] >= 0.85:
                break
        if best and best["confidence"] >= 0.85:
            break
    out = {
        "key": field["key"],
        "label": field.get("label", field["key"]),
        "type": field_type,
        "required": bool(field.get("required")),
        "value": best["value"] if best else None,
        "confidence": best["confidence"] if best else 0.0,
        "page_number": best["page_number"] if best else None,
        "bbox": best["bbox"] if best else None,
        "missing": best is None,
    }
    return out


# Common fields pulled from every document when no template is assigned, so
# the bulk export and Fields tab still carry the useful data.
_DEFAULT_FIELDS = [
    {"key": "recipient", "label": "宛先", "type": "text"},
    {"key": "issuer", "label": "発行会社", "type": "text"},
    {"key": "doc_no", "label": "書類番号", "type": "text",
     "description": "請求書番号,納品書番号,見積書番号,領収書番号,伝票番号,注文番号,発注番号"},
    {"key": "subject", "label": "件名", "description": "品名,内容", "type": "text"},
    {"key": "total", "label": "合計金額", "type": "amount",
     "description": "ご請求金額,合計金額,総額,税込,お支払金額"},
    {"key": "date", "label": "発行日", "type": "date",
     "description": "日付,請求日,納品日,取引日,発行年月日"},
    {"key": "reg_no", "label": "登録番号", "description": "インボイス番号,適格請求書", "type": "text"},
]

_COMPANY_MARKERS = ("株式会社", "有限会社", "合同会社", "合資会社")


def _company_result(item: _Item) -> dict:
    return {
        "value": item.text.strip(),
        "confidence": round(item.confidence, 3),
        "page_number": item.page_number,
        "bbox": list(item.bbox),
        "missing": False,
    }


def _empty_field() -> dict:
    return {"value": None, "confidence": 0.0, "page_number": None, "bbox": None, "missing": True}


def _extract_recipient(items: list[_Item]) -> dict:
    """The recipient is the company written just before 御中 (X御中)."""
    for item in items:
        idx = item.text.find("御中")
        if idx > 0:
            name = item.text[:idx].strip(" 　:：")
            if len(name) >= 2:
                out = _company_result(item)
                out["value"] = name
                return out
    return _empty_field()


def _extract_issuer(items: list[_Item], recipient: str | None) -> dict:
    """The issuing company: the first 株式会社/有限会社 line that isn't the
    recipient (no 御中) — usually the seller's own name near its 登録番号."""
    for item in items:
        text = item.text.strip()
        if "御中" in text or len(text) > 30:
            continue
        if recipient and recipient in text:
            continue
        if any(marker in text for marker in _COMPANY_MARKERS):
            return _company_result(item)
    return _empty_field()


def _extract_fields(items: list[_Item], field_defs: list[dict]) -> list[dict]:
    fields = []
    recipient_value: str | None = None
    for field in field_defs:
        key = field["key"]
        if key == "recipient":
            best = _extract_recipient(items)
            recipient_value = best["value"]
        elif key == "issuer":
            best = _extract_issuer(items, recipient_value)
        else:
            fields.append(_extract_field(field, items))
            continue
        fields.append({"key": key, "label": field["label"], "type": "text",
                       "required": False, **best})
    return fields


def extract_document(db: Session, document: Document) -> dict | None:
    """Extract structured fields for a completed document. Uses the assigned
    template's fields, or a built-in set of common business-document fields
    when there is no template — so every document carries usable data."""
    items = _collect_items(db, document)
    if document.template_id is not None:
        template = db.get(Template, document.template_id)
        if template is not None:
            document.extracted_json = {
                "template_id": str(template.id),
                "template_name": template.name,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "fields": _extract_fields(items, template.fields),
            }
            return document.extracted_json

    document.extracted_json = {
        "template_id": None,
        "template_name": "自動抽出",
        "auto": True,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "fields": _extract_fields(items, _DEFAULT_FIELDS),
    }
    return document.extracted_json


def apply_template(db: Session, document: Document, template_id: uuid.UUID | None) -> None:
    """Assign (or clear) a template and re-run extraction from the stored OCR
    regions — no re-OCR needed."""
    document.template_id = template_id
    extract_document(db, document)
