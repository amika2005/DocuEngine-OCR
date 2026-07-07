import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_company_admin, require_company_member
from app.db.session import get_db
from app.events.publisher import publish_event
from app.models import (
    Company,
    Correction,
    CorrectionStatus,
    OcrResult,
    Page,
    User,
)
from app.schemas.document import CorrectionCreate, CorrectionOut, CorrectionUpdate
from app.services.audit import log_action

router = APIRouter(tags=["corrections"])


def _get_correction(db: Session, user: User, correction_id: uuid.UUID) -> Correction:
    correction = db.get(Correction, correction_id)
    if correction is None or correction.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Correction not found")
    return correction


@router.post(
    "/pages/{page_id}/corrections",
    response_model=CorrectionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_correction(
    page_id: uuid.UUID,
    body: CorrectionCreate,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    page = db.get(Page, page_id)
    if page is None or page.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Page not found")
    result = db.scalar(
        select(OcrResult).where(OcrResult.page_id == page.id, OcrResult.is_current)
    )
    if result is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Page has no OCR result to correct")

    if body.region_index is not None:
        regions = result.layout_json.get("regions", [])
        if not 0 <= body.region_index < len(regions):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "region_index out of range")
        original = regions[body.region_index]["markdown"]
    else:
        original = result.markdown

    correction = Correction(
        company_id=user.company_id,
        page_id=page.id,
        ocr_result_id=result.id,
        user_id=user.id,
        original_markdown=original,
        corrected_markdown=body.corrected_markdown,
        region_index=body.region_index,
        status=CorrectionStatus.draft.value,
    )
    db.add(correction)

    # A whole-page correction is applied immediately: the visible result and
    # the assembled document markdown change to what the user typed. The
    # correction row keeps the original for the training flywheel.
    if body.region_index is None and body.corrected_markdown != original:
        from app.services.matching import rewrite_document_markdown

        result.markdown = body.corrected_markdown
        db.flush()
        rewrite_document_markdown(db, page.id)

    db.commit()
    publish_event(user.company_id, "corrections.changed", {"action": "created"})
    if body.region_index is None:
        publish_event(
            user.company_id, f"document.{page.document_id}.status", {"status": "updated"}
        )
    return correction


@router.put("/corrections/{correction_id}", response_model=CorrectionOut)
def update_correction(
    correction_id: uuid.UUID,
    body: CorrectionUpdate,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    correction = _get_correction(db, user, correction_id)
    if correction.status not in (CorrectionStatus.draft.value, CorrectionStatus.submitted.value):
        raise HTTPException(status.HTTP_409_CONFLICT, "Correction can no longer be edited")
    correction.corrected_markdown = body.corrected_markdown
    db.commit()
    return correction


@router.post("/corrections/{correction_id}/submit", response_model=CorrectionOut)
def submit_correction(
    correction_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    correction = _get_correction(db, user, correction_id)
    if correction.status != CorrectionStatus.draft.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only drafts can be submitted")
    # Companies can skip the review queue: submissions then approve instantly.
    company = db.get(Company, user.company_id)
    require_approval = company.settings.get("require_correction_approval", True)
    correction.status = (
        CorrectionStatus.submitted.value if require_approval else CorrectionStatus.approved.value
    )
    log_action(db, "correction.submit", company_id=user.company_id, actor_user_id=user.id,
               target_type="correction", target_id=str(correction.id))
    db.commit()
    publish_event(user.company_id, "corrections.changed", {"action": "submitted"})
    return correction


@router.get("/corrections", response_model=list[CorrectionOut])
def list_corrections(
    status_filter: str | None = None,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    query = select(Correction).where(Correction.company_id == user.company_id)
    if status_filter:
        query = query.where(Correction.status == status_filter)
    return db.scalars(query.order_by(Correction.created_at.desc()).limit(200)).all()


@router.post("/corrections/{correction_id}/approve", response_model=CorrectionOut)
def approve_correction(
    correction_id: uuid.UUID,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    correction = _get_correction(db, admin, correction_id)
    if correction.status != CorrectionStatus.submitted.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only submitted corrections can be approved")
    correction.status = CorrectionStatus.approved.value
    log_action(db, "correction.approve", company_id=admin.company_id, actor_user_id=admin.id,
               target_type="correction", target_id=str(correction.id))
    db.commit()
    publish_event(admin.company_id, "corrections.changed", {"action": "approved"})
    return correction


@router.post("/corrections/{correction_id}/reject", response_model=CorrectionOut)
def reject_correction(
    correction_id: uuid.UUID,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    correction = _get_correction(db, admin, correction_id)
    if correction.status != CorrectionStatus.submitted.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only submitted corrections can be rejected")
    correction.status = CorrectionStatus.rejected.value
    log_action(db, "correction.reject", company_id=admin.company_id, actor_user_id=admin.id,
               target_type="correction", target_id=str(correction.id))
    db.commit()
    publish_event(admin.company_id, "corrections.changed", {"action": "rejected"})
    return correction
