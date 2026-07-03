"""Matching service: normalization-aware exact/fuzzy detection and the
link-as-correction flow."""

import uuid

import pytest
from sqlalchemy import select

from app.models import (
    Correction,
    CorrectionStatus,
    Document,
    DocumentStatus,
    MasterMatch,
    MasterRecord,
    MasterType,
    MatchStatus,
    OcrResult,
    Page,
)
from app.services import storage
from app.services.matching import (
    LinkError,
    _score,
    link_match,
    match_document,
    validate_fields,
)


@pytest.fixture()
def customer_master(db, seed):
    # Session-scoped DB: purge company A's masters so each test starts clean.
    for match in db.scalars(select(MasterMatch)):
        db.delete(match)
    for record in db.scalars(select(MasterRecord)):
        db.delete(record)
    for existing_type in db.scalars(select(MasterType)):
        db.delete(existing_type)
    db.commit()
    master_type = MasterType(
        company_id=seed["company_a"].id,
        name=f"得意先-{uuid.uuid4().hex[:6]}",
        fields=[
            {"key": "name", "label": "名前", "matchable": True, "required": True},
            {"key": "address", "label": "住所", "matchable": True, "required": False},
            {"key": "code", "label": "コード", "matchable": False, "required": False},
        ],
    )
    db.add(master_type)
    db.flush()
    record = MasterRecord(
        company_id=seed["company_a"].id,
        master_type_id=master_type.id,
        data={"name": "株式会社サンプル商事", "address": "東京都港区1-2-3", "code": "C-001"},
    )
    db.add(record)
    db.commit()
    return master_type, record


def _make_document(db, seed, markdown: str):
    document = Document(
        company_id=seed["company_a"].id,
        original_filename=f"m-{uuid.uuid4().hex[:8]}.pdf",
        content_sha256=uuid.uuid4().hex + uuid.uuid4().hex[:32],
        mime_type="application/pdf",
        byte_size=1,
        storage_path="/dev/null",
        status=DocumentStatus.completed.value,
        page_count=1,
    )
    db.add(document)
    db.flush()
    page = Page(
        document_id=document.id, company_id=seed["company_a"].id,
        page_number=1, image_path="/dev/null", status="completed",
    )
    db.add(page)
    db.flush()
    result = OcrResult(
        page_id=page.id, company_id=seed["company_a"].id,
        markdown=markdown, layout_json={"regions": []}, engine="mock", is_current=True,
    )
    db.add(result)
    db.commit()
    return document, page, result


def test_score_exact_and_nfkc():
    assert _score("株式会社サンプル商事", "株式会社サンプル商事 御中") == ("exact", 1.0)
    # Full-width vs half-width is still exact.
    kind, score = _score("C-001", "Ｃ－００１")
    assert kind == "exact" and score == 1.0


def test_score_fuzzy_catches_ocr_misread():
    # OCR misread one character: 商事 → 商亊
    kind, score = _score("株式会社サンプル商事", "株式会社サンプル商亊")
    assert kind == "fuzzy"
    assert score >= 0.82


def test_score_rejects_unrelated():
    assert _score("株式会社サンプル商事", "全然違うテキスト") is None
    # A short value must not fuzzy-match a long paragraph.
    assert _score("東京都", "これはとても長い段落でありマスタ値とは無関係です") is None


def test_match_document_exact_and_table(db, seed, customer_master):
    _, record = customer_master
    document, page, _ = _make_document(
        db, seed,
        "# 請求書\n\n株式会社サンプル商事 御中\n\n| 項目 | 値 |\n| --- | --- |\n| 住所 | 東京都港区1-2-3 |",
    )
    created = match_document(db, document)
    assert created == 2  # name (line) + address (table cell)

    matches = db.scalars(select(MasterMatch).where(MasterMatch.page_id == page.id)).all()
    by_field = {match.field_key: match for match in matches}
    assert by_field["name"].kind == "exact"
    assert by_field["address"].kind == "exact"
    assert all(match.master_record_id == record.id for match in matches)


def test_match_document_fuzzy_misread(db, seed, customer_master):
    document, page, _ = _make_document(db, seed, "株式会社サンプル商亊 御中")  # 事→亊 misread
    match_document(db, document)
    match = db.scalar(select(MasterMatch).where(MasterMatch.page_id == page.id))
    assert match is not None
    assert match.kind == "fuzzy"
    assert match.field_key == "name"


def test_rematch_preserves_decisions(db, seed, customer_master):
    document, page, _ = _make_document(db, seed, "株式会社サンプル商事")
    match_document(db, document)
    match = db.scalar(select(MasterMatch).where(MasterMatch.page_id == page.id))
    match.status = MatchStatus.dismissed.value
    db.commit()

    match_document(db, document)  # re-run
    matches = db.scalars(select(MasterMatch).where(MasterMatch.page_id == page.id)).all()
    assert len(matches) == 1
    assert matches[0].status == MatchStatus.dismissed.value  # decision kept, no dupe


def test_link_match_corrects_markdown_and_records_correction(db, seed, customer_master):
    # Fuzzy case: linking replaces the misread text with the master value.
    document, page, result = _make_document(db, seed, "株式会社サンプル商亊 御中")
    match_document(db, document)
    match = db.scalar(select(MasterMatch).where(MasterMatch.page_id == page.id))

    link_match(db, match, seed["user_a"].id)

    db.refresh(result)
    assert "株式会社サンプル商事" in result.markdown
    assert "商亊" not in result.markdown
    assert match.status == MatchStatus.linked.value
    assert match.linked_by == seed["user_a"].id

    correction = db.scalar(
        select(Correction).where(Correction.page_id == page.id)
    )
    assert correction is not None
    assert correction.status == CorrectionStatus.approved.value  # trusted → flywheel
    assert "商亊" in correction.original_markdown
    assert "商事" in correction.corrected_markdown

    # Assembled document markdown was rewritten with the corrected text.
    md_path = storage.document_markdown_path(document.company_id, document.id)
    assert "株式会社サンプル商事" in md_path.read_text()


def test_link_match_stale_text_conflicts(db, seed, customer_master):
    document, page, result = _make_document(db, seed, "株式会社サンプル商亊")
    match_document(db, document)
    match = db.scalar(select(MasterMatch).where(MasterMatch.page_id == page.id))
    result.markdown = "全く別の内容"  # someone edited meanwhile
    db.commit()
    with pytest.raises(LinkError):
        link_match(db, match, seed["user_a"].id)


def test_validate_fields():
    cleaned = validate_fields(
        [{"key": "Name!", "label": "名前", "matchable": True}]
    )
    assert cleaned[0]["key"] == "name_"
    with pytest.raises(ValueError):
        validate_fields([])
    with pytest.raises(ValueError):
        validate_fields([{"key": "a", "label": "A", "matchable": False}])  # none matchable
    with pytest.raises(ValueError):
        validate_fields([
            {"key": "a", "label": "A", "matchable": True},
            {"key": "a", "label": "B", "matchable": False},
        ])
