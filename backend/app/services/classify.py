"""Document category detection from OCR text — offline, keyword based.

Japanese business documents carry their type prominently in the title
(納品書, 請求書, 見積書, 領収書, ...). We pick the earliest such keyword in the
recognized text and map it to a doc_type used for filtering and export.
"""

# (doc_type, keyword) — order matters only as a tie-break; the earliest match
# in the document wins, so the title keyword dominates.
_CATEGORY_KEYWORDS: list[tuple[str, str]] = [
    ("delivery_note", "納品書"),
    ("invoice", "請求書"),
    ("quotation", "見積書"),
    ("quotation", "御見積書"),
    ("receipt", "領収書"),
    ("order", "発注書"),
    ("order", "注文書"),
    ("inspection", "検収書"),
    ("statement", "取引明細"),
    ("tax_report", "確定申告"),
]

# Human labels (JP) for the categories, for UI/export.
CATEGORY_LABELS_JA: dict[str, str] = {
    "delivery_note": "納品書",
    "invoice": "請求書",
    "quotation": "見積書",
    "receipt": "領収書",
    "order": "発注書",
    "inspection": "検収書",
    "statement": "取引明細書",
    "tax_report": "税務書類",
    "letter": "レター",
    "other": "その他",
}


def detect_category(markdown: str) -> str | None:
    """Return the detected doc_type, or None when nothing matches."""
    if not markdown:
        return None
    best: str | None = None
    best_pos: int | None = None
    for doc_type, keyword in _CATEGORY_KEYWORDS:
        pos = markdown.find(keyword)
        if pos != -1 and (best_pos is None or pos < best_pos):
            best_pos, best = pos, doc_type
    return best
