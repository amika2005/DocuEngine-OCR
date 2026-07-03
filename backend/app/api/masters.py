"""Master data management + OCR match/link endpoints.
Company admins manage types/records; all tenant members can view and link."""

import csv
import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_company_admin, require_company_member
from app.db.session import get_db
from app.events.publisher import publish_event
from app.models import (
    Document,
    MasterMatch,
    MasterRecord,
    MasterType,
    MatchStatus,
    Page,
    User,
)
from app.services import matching
from app.services.audit import log_action

router = APIRouter(prefix="/masters", tags=["masters"])
match_router = APIRouter(tags=["masters"])


# --- Schemas ---

class MasterFieldSchema(BaseModel):
    key: str
    label: str
    matchable: bool = False
    required: bool = False


class MasterTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    fields: list[MasterFieldSchema]


class MasterTypeOut(BaseModel):
    id: uuid.UUID
    name: str
    fields: list[dict]
    records_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class MasterRecordIn(BaseModel):
    data: dict[str, str]


class MasterRecordOut(BaseModel):
    id: uuid.UUID
    master_type_id: uuid.UUID
    data: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class MatchOut(BaseModel):
    id: uuid.UUID
    page_id: uuid.UUID
    master_record_id: uuid.UUID
    master_type_id: uuid.UUID
    master_type_name: str
    field_key: str
    field_label: str
    matched_text: str
    master_value: str
    record_data: dict
    score: float
    kind: str
    status: str


# --- Helpers ---

def _get_type(db: Session, user: User, type_id: uuid.UUID) -> MasterType:
    master_type = db.get(MasterType, type_id)
    if master_type is None or master_type.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Master type not found")
    return master_type


def _get_record(db: Session, user: User, record_id: uuid.UUID) -> MasterRecord:
    record = db.get(MasterRecord, record_id)
    if record is None or record.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Master record not found")
    return record


def _validate_record_data(master_type: MasterType, data: dict) -> dict:
    keys = {field["key"] for field in master_type.fields}
    cleaned = {key: str(value).strip() for key, value in data.items() if key in keys}
    for field in master_type.fields:
        if field.get("required") and not cleaned.get(field["key"]):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"field '{field['label']}' is required"
            )
    return cleaned


# --- Master types ---

@router.get("/types", response_model=list[MasterTypeOut])
def list_types(user: User = Depends(require_company_member), db: Session = Depends(get_db)):
    counts = {
        row[0]: row[1]
        for row in db.execute(
            select(MasterRecord.master_type_id, func.count())
            .where(MasterRecord.company_id == user.company_id)
            .group_by(MasterRecord.master_type_id)
        )
    }
    types = db.scalars(
        select(MasterType)
        .where(MasterType.company_id == user.company_id)
        .order_by(MasterType.created_at)
    ).all()
    return [
        MasterTypeOut(
            id=t.id, name=t.name, fields=t.fields,
            records_count=counts.get(t.id, 0), created_at=t.created_at,
        )
        for t in types
    ]


@router.post("/types", response_model=MasterTypeOut, status_code=status.HTTP_201_CREATED)
def create_type(
    body: MasterTypeIn,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    try:
        fields = matching.validate_fields([field.model_dump() for field in body.fields])
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if db.scalar(
        select(MasterType).where(
            MasterType.company_id == admin.company_id, MasterType.name == body.name
        )
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "A master type with this name exists")
    master_type = MasterType(
        company_id=admin.company_id, name=body.name, fields=fields, created_by=admin.id
    )
    db.add(master_type)
    db.flush()
    log_action(db, "master_type.create", company_id=admin.company_id, actor_user_id=admin.id,
               target_type="master_type", target_id=str(master_type.id))
    db.commit()
    publish_event(admin.company_id, "masters.changed", {"action": "type_created"})
    return MasterTypeOut(
        id=master_type.id, name=master_type.name, fields=master_type.fields,
        records_count=0, created_at=master_type.created_at,
    )


@router.patch("/types/{type_id}", response_model=MasterTypeOut)
def update_type(
    type_id: uuid.UUID,
    body: MasterTypeIn,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    master_type = _get_type(db, admin, type_id)
    try:
        master_type.fields = matching.validate_fields(
            [field.model_dump() for field in body.fields]
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    master_type.name = body.name
    db.commit()
    publish_event(admin.company_id, "masters.changed", {"action": "type_updated"})
    records = db.scalar(
        select(func.count()).select_from(MasterRecord).where(
            MasterRecord.master_type_id == master_type.id
        )
    )
    return MasterTypeOut(
        id=master_type.id, name=master_type.name, fields=master_type.fields,
        records_count=records, created_at=master_type.created_at,
    )


@router.delete("/types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_type(
    type_id: uuid.UUID,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    master_type = _get_type(db, admin, type_id)
    db.delete(master_type)  # records + matches cascade
    log_action(db, "master_type.delete", company_id=admin.company_id, actor_user_id=admin.id,
               target_type="master_type", target_id=str(type_id))
    db.commit()
    publish_event(admin.company_id, "masters.changed", {"action": "type_deleted"})


# --- Records ---

@router.get("/types/{type_id}/records")
def list_records(
    type_id: uuid.UUID,
    q: str | None = None,
    page: int = 1,
    page_size: int = 25,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    master_type = _get_type(db, user, type_id)
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    records = db.scalars(
        select(MasterRecord)
        .where(MasterRecord.master_type_id == master_type.id)
        .order_by(MasterRecord.created_at.desc())
    ).all()
    if q:
        needle = q.lower()
        records = [
            record for record in records
            if any(needle in str(value).lower() for value in record.data.values())
        ]
    total = len(records)
    window = records[(page - 1) * page_size : page * page_size]
    return {
        "items": [MasterRecordOut.model_validate(r, from_attributes=True) for r in window],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post(
    "/types/{type_id}/records",
    response_model=MasterRecordOut,
    status_code=status.HTTP_201_CREATED,
)
def create_record(
    type_id: uuid.UUID,
    body: MasterRecordIn,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    master_type = _get_type(db, admin, type_id)
    record = MasterRecord(
        company_id=admin.company_id,
        master_type_id=master_type.id,
        data=_validate_record_data(master_type, body.data),
        created_by=admin.id,
    )
    db.add(record)
    db.commit()
    publish_event(admin.company_id, "masters.changed", {"action": "record_created"})
    return record


@router.patch("/records/{record_id}", response_model=MasterRecordOut)
def update_record(
    record_id: uuid.UUID,
    body: MasterRecordIn,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    record = _get_record(db, admin, record_id)
    master_type = db.get(MasterType, record.master_type_id)
    record.data = _validate_record_data(master_type, body.data)
    db.commit()
    publish_event(admin.company_id, "masters.changed", {"action": "record_updated"})
    return record


@router.delete("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(
    record_id: uuid.UUID,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    record = _get_record(db, admin, record_id)
    db.delete(record)
    db.commit()
    publish_event(admin.company_id, "masters.changed", {"action": "record_deleted"})


@router.post("/types/{type_id}/import")
async def import_csv(
    type_id: uuid.UUID,
    file: UploadFile,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    """CSV bulk import. Header row = field keys (as defined on the type).
    Duplicate rows (identical data to an existing record) are skipped."""
    master_type = _get_type(db, admin, type_id)
    raw = await file.read()
    text = raw.decode("utf-8-sig", errors="replace")  # BOM-tolerant (Excel)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CSV has no header row")

    known_keys = {field["key"] for field in master_type.fields}
    header_keys = [key.strip() for key in reader.fieldnames]
    if not any(key in known_keys for key in header_keys):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"CSV header must use the field keys: {sorted(known_keys)}",
        )

    existing = {
        tuple(sorted(record.data.items()))
        for record in db.scalars(
            select(MasterRecord).where(MasterRecord.master_type_id == master_type.id)
        )
    }
    created = 0
    skipped = 0
    errors: list[str] = []
    for line_number, row in enumerate(reader, start=2):
        try:
            data = _validate_record_data(
                master_type, {k.strip(): (v or "") for k, v in row.items() if k}
            )
        except HTTPException as exc:
            errors.append(f"line {line_number}: {exc.detail}")
            continue
        signature = tuple(sorted(data.items()))
        if not any(data.values()) or signature in existing:
            skipped += 1
            continue
        existing.add(signature)
        db.add(
            MasterRecord(
                company_id=admin.company_id,
                master_type_id=master_type.id,
                data=data,
                created_by=admin.id,
            )
        )
        created += 1
    log_action(db, "master.import_csv", company_id=admin.company_id, actor_user_id=admin.id,
               target_type="master_type", target_id=str(type_id),
               detail={"created": created, "skipped": skipped})
    db.commit()
    publish_event(admin.company_id, "masters.changed", {"action": "imported"})
    return {"created": created, "skipped": skipped, "errors": errors[:20]}


# --- Matches (mounted without the /masters prefix) ---

@match_router.get("/pages/{page_id}/matches", response_model=list[MatchOut])
def page_matches(
    page_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    page = db.get(Page, page_id)
    if page is None or page.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Page not found")
    rows = db.execute(
        select(MasterMatch, MasterRecord, MasterType)
        .join(MasterRecord, MasterMatch.master_record_id == MasterRecord.id)
        .join(MasterType, MasterMatch.master_type_id == MasterType.id)
        .where(
            MasterMatch.page_id == page.id,
            MasterMatch.status != MatchStatus.dismissed.value,
        )
        .order_by(MasterMatch.score.desc())
    ).all()
    out = []
    for match, record, master_type in rows:
        labels = {field["key"]: field["label"] for field in master_type.fields}
        out.append(
            MatchOut(
                id=match.id,
                page_id=match.page_id,
                master_record_id=record.id,
                master_type_id=master_type.id,
                master_type_name=master_type.name,
                field_key=match.field_key,
                field_label=labels.get(match.field_key, match.field_key),
                matched_text=match.matched_text,
                master_value=match.master_value,
                record_data=record.data,
                score=match.score,
                kind=match.kind,
                status=match.status,
            )
        )
    return out


def _get_match(db: Session, user: User, match_id: uuid.UUID) -> MasterMatch:
    match = db.get(MasterMatch, match_id)
    if match is None or match.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Match not found")
    return match


@match_router.post("/matches/{match_id}/link")
def link(
    match_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    match = _get_match(db, user, match_id)
    try:
        matching.link_match(db, match, user.id)
    except matching.LinkError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    log_action(db, "master.link", company_id=user.company_id, actor_user_id=user.id,
               target_type="master_match", target_id=str(match.id))
    db.commit()
    page = db.get(Page, match.page_id)
    publish_event(user.company_id, "matches.changed", {"action": "linked"})
    publish_event(user.company_id, "corrections.changed", {"action": "master_link"})
    if page:
        publish_event(
            user.company_id, f"document.{page.document_id}.status", {"status": "updated"}
        )
    return {"status": "linked"}


@match_router.post("/matches/{match_id}/dismiss")
def dismiss(
    match_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    match = _get_match(db, user, match_id)
    matching.dismiss_match(db, match)
    publish_event(user.company_id, "matches.changed", {"action": "dismissed"})
    return {"status": "dismissed"}


@match_router.post("/documents/{document_id}/rematch", status_code=status.HTTP_202_ACCEPTED)
def rematch_document(
    document_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)
    if document is None or document.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    from app.tasks.ocr_tasks import match_masters

    match_masters.apply_async(args=[str(document.id)])
    return {"status": "queued"}
