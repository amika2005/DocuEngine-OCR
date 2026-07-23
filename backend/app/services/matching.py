"""Master-data matching: finds master-record field values inside OCR output and
turns confirmed matches into instant, trusted corrections.

Matching units are the natural reading chunks of a business document — markdown
lines and GFM table cells. Comparison is NFKC-normalized (full/half-width safe)
via the shared metrics in app/ocr/metrics.py:
  - normalized equality or containment → exact (score 1.0, green ✓)
  - similarity = 1 − CER ≥ FUZZY_THRESHOLD → fuzzy (amber ~) — this is the case
    that catches OCR misreads of known customers/products.
"""

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Correction,
    CorrectionStatus,
    Document,
    MasterMatch,
    MasterRecord,
    MasterType,
    MatchKind,
    MatchStatus,
    OcrResult,
    Page,
)
from app.ocr import assemble
from app.ocr.metrics import cer, extract_table_cells, normalize_ja
from app.services import storage

FUZZY_THRESHOLD = 0.82
MIN_VALUE_LENGTH = 2


def _candidate_units(markdown: str) -> list[str]:
    """Lines, whitespace-separated line tokens, and table cells — deduplicated.
    Tokens matter for fuzzy matching: an invoice line like
    「株式会社サンプル商亊 御中」 must let the company-name token match on its
    own, without 御中 diluting the similarity."""
    units: list[str] = []

    def add_with_tokens(text: str) -> None:
        text = text.strip()
        if not text:
            return
        units.append(text)
        tokens = text.split()
        if len(tokens) > 1:
            units.extend(token for token in tokens if len(token) >= MIN_VALUE_LENGTH)

    for line in markdown.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped and not stripped.startswith("|") and not stripped.startswith("!["):
            add_with_tokens(stripped)
    for row in extract_table_cells(markdown):
        for cell in row:
            add_with_tokens(cell)

    seen: set[str] = set()
    unique = []
    for unit in units:
        if unit not in seen:
            seen.add(unit)
            unique.append(unit)
    return unique


def _matchable_values(master_type: MasterType, record: MasterRecord) -> list[tuple[str, str]]:
    """(field_key, value) pairs for the type's matchable fields."""
    matchable_keys = [
        field["key"] for field in master_type.fields if field.get("matchable")
    ]
    pairs = []
    for key in matchable_keys:
        value = str(record.data.get(key, "") or "").strip()
        if len(normalize_ja(value)) >= MIN_VALUE_LENGTH:
            pairs.append((key, value))
    return pairs


def _score(value: str, unit: str) -> tuple[str, float] | None:
    """Return (kind, score) if the master value matches this text unit."""
    norm_value = normalize_ja(value)
    norm_unit = normalize_ja(unit)
    if not norm_value or not norm_unit:
        return None
    if norm_value == norm_unit or norm_value in norm_unit:
        return MatchKind.exact.value, 1.0
    # Fuzzy only against comparably-sized units — a name won't "fuzzy match"
    # a whole paragraph.
    if len(norm_unit) > len(norm_value) * 2 + 6:
        return None
    similarity = 1.0 - cer(norm_value, norm_unit)
    if similarity >= FUZZY_THRESHOLD:
        return MatchKind.fuzzy.value, round(similarity, 4)
    return None


def _alias_candidates(
    master_type: MasterType, record: MasterRecord
) -> list[tuple[str, str, str]]:
    """(field_key, alias_text, canonical_value) learned for this record, limited
    to the type's matchable fields. Aliases are confirmed OCR spellings, so they
    match by exact equality only."""
    matchable_keys = {f["key"] for f in master_type.fields if f.get("matchable")}
    out: list[tuple[str, str, str]] = []
    for alias in record.aliases or []:
        field_key = alias.get("field_key")
        text = str(alias.get("text", "") or "").strip()
        if field_key not in matchable_keys or len(normalize_ja(text)) < MIN_VALUE_LENGTH:
            continue
        canonical = str(record.data.get(field_key, "") or "").strip()
        if len(normalize_ja(canonical)) < MIN_VALUE_LENGTH:
            continue
        out.append((field_key, text, canonical))
    return out


def _best_matches_for_record(
    units: list[str], master_type: MasterType, record: MasterRecord
) -> dict[str, tuple[str, float, str, str, bool]]:
    """Per matchable field, the single best match against the page's text units.
    Returns {field_key: (kind, score, matched_text, master_value, is_alias)}.
    A learned alias (exact, previously human-confirmed) outranks a canonical
    fuzzy match, so a known misread resolves cleanly."""
    best: dict[str, tuple[str, float, str, str, bool]] = {}

    def consider(
        field_key: str, kind: str, score: float, matched_text: str,
        master_value: str, is_alias: bool,
    ) -> None:
        current = best.get(field_key)
        if current is None or score > current[1]:
            best[field_key] = (kind, score, matched_text, master_value, is_alias)

    for field_key, value in _matchable_values(master_type, record):
        for unit in units:
            scored = _score(value, unit)
            if scored is None:
                continue
            kind, score = scored
            matched_text = (
                value
                if kind == MatchKind.exact.value and normalize_ja(value) != normalize_ja(unit)
                else unit
            )
            consider(field_key, kind, score, matched_text, value, False)
            if score >= 1.0:
                break
    for field_key, alias_text, canonical in _alias_candidates(master_type, record):
        norm_alias = normalize_ja(alias_text)
        for unit in units:
            if norm_alias == normalize_ja(unit):
                consider(field_key, MatchKind.exact.value, 1.0, unit, canonical, True)
                break
    return best


def match_document(db: Session, document: Document) -> int:
    """(Re)compute suggested matches for every page of a document.
    Linked and dismissed matches are preserved. Returns match count."""
    types = {
        master_type.id: master_type
        for master_type in db.scalars(
            select(MasterType).where(MasterType.company_id == document.company_id)
        )
    }
    if not types:
        return 0
    records = db.scalars(
        select(MasterRecord).where(MasterRecord.company_id == document.company_id)
    ).all()
    if not records:
        return 0

    pages = db.scalars(select(Page).where(Page.document_id == document.id)).all()
    created = 0
    auto_linked_pages: set[uuid.UUID] = set()
    for page in pages:
        result = db.scalar(
            select(OcrResult).where(OcrResult.page_id == page.id, OcrResult.is_current)
        )
        if result is None:
            continue

        # Refresh suggestions; keep human decisions (linked/dismissed).
        existing = db.scalars(
            select(MasterMatch).where(MasterMatch.page_id == page.id)
        ).all()
        decided = set()
        for match in existing:
            if match.status == MatchStatus.suggested.value:
                db.delete(match)
            else:
                decided.add((match.master_record_id, match.field_key, match.matched_text))
        db.flush()

        units = _candidate_units(result.markdown)
        for record in records:
            master_type = types.get(record.master_type_id)
            if master_type is None:
                continue
            for field_key, (kind, score, matched_text, master_value, is_alias) in (
                _best_matches_for_record(units, master_type, record).items()
            ):
                if (record.id, field_key, matched_text) in decided:
                    continue
                match = MasterMatch(
                    company_id=document.company_id,
                    page_id=page.id,
                    ocr_result_id=result.id,
                    master_record_id=record.id,
                    master_type_id=record.master_type_id,
                    field_key=field_key,
                    matched_text=matched_text,
                    master_value=master_value,
                    score=score,
                    kind=kind,
                )
                # A learned alias is a spelling the user already confirmed for
                # this record — re-apply it automatically (no re-linking). Only
                # do so if the text is still present; a prior auto-link on this
                # page may have already consumed it.
                if is_alias:
                    if not _apply_master_value(result, matched_text, master_value):
                        continue
                    match.status = MatchStatus.linked.value
                    match.linked_at = datetime.now(timezone.utc)
                    auto_linked_pages.add(page.id)
                db.add(match)
                created += 1
    db.commit()
    for page_id in auto_linked_pages:
        rewrite_document_markdown(db, page_id)
    return created


class LinkError(Exception):
    pass


def _apply_master_value(result: OcrResult, matched_text: str, master_value: str) -> bool:
    """Replace matched_text with master_value in the result markdown and any
    region markdown. Returns False if the text is no longer present (nothing to
    do when the two are already equal)."""
    if matched_text == master_value:
        return True
    if matched_text not in result.markdown:
        return False
    result.markdown = result.markdown.replace(matched_text, master_value)
    # Keep region markdown in sync so region-level corrections stay coherent.
    regions = (result.layout_json or {}).get("regions", [])
    for region in regions:
        if matched_text in region.get("markdown", ""):
            region["markdown"] = region["markdown"].replace(matched_text, master_value)
    if regions:
        result.layout_json = {**result.layout_json, "regions": regions}
    return True


def _learn_alias(db: Session, match: MasterMatch) -> None:
    """Remember the confirmed OCR text as an alias of the master record, so the
    same misread auto-links to the canonical value next time. Only genuine
    variants are stored (not text already equal to the canonical value)."""
    text = match.matched_text.strip()
    norm = normalize_ja(text)
    if len(norm) < MIN_VALUE_LENGTH or norm == normalize_ja(match.master_value):
        return
    record = db.get(MasterRecord, match.master_record_id)
    if record is None:
        return
    if norm == normalize_ja(str(record.data.get(match.field_key, "") or "")):
        return
    aliases = list(record.aliases or [])
    for alias in aliases:
        if alias.get("field_key") == match.field_key and (
            normalize_ja(str(alias.get("text", "") or "")) == norm
        ):
            return
    aliases.append({"field_key": match.field_key, "text": text})
    record.aliases = aliases  # reassign so the JSON change is tracked


def link_match(db: Session, match: MasterMatch, user_id: uuid.UUID) -> None:
    """Confirm a match: replace the OCR text with the trusted master value,
    rewrite the assembled document markdown, record an auto-approved correction
    so the training flywheel learns from it, and remember the OCR spelling as an
    alias so the same misread auto-links from now on."""
    if match.status == MatchStatus.linked.value:
        return
    result = db.get(OcrResult, match.ocr_result_id)
    if result is None:
        raise LinkError("OCR result no longer exists")

    original_markdown = result.markdown
    if match.matched_text != match.master_value:
        if not _apply_master_value(result, match.matched_text, match.master_value):
            raise LinkError("matched text no longer present — re-run matching")
        db.add(
            Correction(
                company_id=match.company_id,
                page_id=match.page_id,
                ocr_result_id=result.id,
                user_id=user_id,
                original_markdown=original_markdown,
                corrected_markdown=result.markdown,
                status=CorrectionStatus.approved.value,
            )
        )
        _learn_alias(db, match)

    match.status = MatchStatus.linked.value
    match.linked_by = user_id
    match.linked_at = datetime.now(timezone.utc)
    db.flush()

    rewrite_document_markdown(db, match.page_id)
    db.commit()


def dismiss_match(db: Session, match: MasterMatch) -> None:
    match.status = MatchStatus.dismissed.value
    db.commit()


def match_for_field_value(matches: list[MasterMatch], value: str) -> MasterMatch | None:
    """Pick the best MasterMatch that corresponds to an extracted field value.

    Extracted field values come from the same OCR text that match_document
    scans, so a field usually maps to an existing match on the same page. We
    compare against both matched_text (pre-link) and master_value (post-link,
    since link_match rewrites the OCR text to the master value) so the link
    state is stable before and after linking. Highest score wins.
    """
    norm_value = normalize_ja(value)
    if len(norm_value) < MIN_VALUE_LENGTH:
        return None
    best: MasterMatch | None = None
    for match in matches:
        targets = (normalize_ja(match.matched_text), normalize_ja(match.master_value))
        if any(norm_value == t or norm_value in t or t in norm_value for t in targets if t):
            if best is None or match.score > best.score:
                best = match
    return best


def rewrite_document_markdown(db: Session, page_id: uuid.UUID) -> None:
    """Reassemble the document-level markdown file after a page's result
    changed (master link or an inline result edit)."""
    page = db.get(Page, page_id)
    if page is None:
        return
    document = db.get(Document, page.document_id)
    if document is None:
        return
    pages = db.scalars(
        select(Page).where(Page.document_id == document.id).order_by(Page.page_number)
    ).all()
    markdowns = []
    for current_page in pages:
        result = db.scalar(
            select(OcrResult).where(
                OcrResult.page_id == current_page.id, OcrResult.is_current
            )
        )
        markdowns.append(result.markdown if result else "")
    storage.save_bytes(
        storage.document_markdown_path(document.company_id, document.id),
        assemble.document_markdown(markdowns).encode(),
    )


_SLUG_RE = re.compile(r"[^a-z0-9_]")


def validate_fields(fields: list[dict]) -> list[dict]:
    """Normalize/validate a master type's field definitions. An empty list is
    allowed — the fields are then inferred from the header row of the first
    bulk import."""
    cleaned = []
    seen_keys: set[str] = set()
    for field in fields:
        key = str(field.get("key", "")).strip().lower()
        key = _SLUG_RE.sub("_", key)
        label = str(field.get("label", "")).strip()
        if not key or not label:
            raise ValueError("every field needs a key and a label")
        if key in seen_keys:
            raise ValueError(f"duplicate field key: {key}")
        seen_keys.add(key)
        cleaned.append(
            {
                "key": key,
                "label": label,
                "matchable": bool(field.get("matchable", False)),
                "required": bool(field.get("required", False)),
            }
        )
    if cleaned and not any(field["matchable"] for field in cleaned):
        raise ValueError("at least one field must be matchable")
    return cleaned
