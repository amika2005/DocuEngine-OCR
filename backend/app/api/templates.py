"""OCR extraction templates: company admins define per-document-type field
schemas; scans that pick a template get structured field extraction."""

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_company_admin, require_company_member
from app.db.session import get_db
from app.events.publisher import publish_event
from app.models import Document, Template, User
from app.services.audit import log_action

router = APIRouter(prefix="/templates", tags=["templates"])

FIELD_TYPES = ("text", "date", "number", "amount")
_SLUG_RE = re.compile(r"[^a-z0-9_]")


class TemplateFieldSchema(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=255)
    description: str = ""
    type: str = "text"
    required: bool = False


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    doc_type: str = "other"
    description: str = ""
    fields: list[TemplateFieldSchema] = Field(min_length=1)


class TemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    doc_type: str
    description: str | None
    fields: list[dict]
    documents_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


def _get_template(db: Session, user: User, template_id: uuid.UUID) -> Template:
    template = db.get(Template, template_id)
    if template is None or template.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    return template


def _clean_fields(fields: list[TemplateFieldSchema]) -> list[dict]:
    cleaned = []
    seen: set[str] = set()
    for field in fields:
        key = _SLUG_RE.sub("_", field.key.strip().lower())
        if not key:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "every field needs a key")
        if key in seen:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"duplicate field key: {key}")
        if field.type not in FIELD_TYPES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"type must be one of {FIELD_TYPES}"
            )
        seen.add(key)
        cleaned.append(
            {
                "key": key,
                "label": field.label.strip(),
                "description": field.description.strip(),
                "type": field.type,
                "required": field.required,
            }
        )
    return cleaned


def _counts(db: Session, company_id: uuid.UUID) -> dict:
    return {
        row[0]: row[1]
        for row in db.execute(
            select(Document.template_id, func.count())
            .where(Document.company_id == company_id, Document.template_id.is_not(None))
            .group_by(Document.template_id)
        )
    }


@router.get("", response_model=list[TemplateOut])
def list_templates(user: User = Depends(require_company_member), db: Session = Depends(get_db)):
    counts = _counts(db, user.company_id)
    templates = db.scalars(
        select(Template)
        .where(Template.company_id == user.company_id)
        .order_by(Template.created_at)
    ).all()
    return [
        TemplateOut(
            id=t.id, name=t.name, doc_type=t.doc_type, description=t.description,
            fields=t.fields, documents_count=counts.get(t.id, 0), created_at=t.created_at,
        )
        for t in templates
    ]


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(
    body: TemplateIn,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    if db.scalar(
        select(Template).where(
            Template.company_id == admin.company_id, Template.name == body.name
        )
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "A template with this name exists")
    template = Template(
        company_id=admin.company_id,
        name=body.name,
        doc_type=body.doc_type,
        description=body.description,
        fields=_clean_fields(body.fields),
        created_by=admin.id,
    )
    db.add(template)
    db.flush()
    log_action(db, "template.create", company_id=admin.company_id, actor_user_id=admin.id,
               target_type="template", target_id=str(template.id))
    db.commit()
    publish_event(admin.company_id, "templates.changed", {"action": "created"})
    return TemplateOut(
        id=template.id, name=template.name, doc_type=template.doc_type,
        description=template.description, fields=template.fields,
        documents_count=0, created_at=template.created_at,
    )


@router.patch("/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: uuid.UUID,
    body: TemplateIn,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    template = _get_template(db, admin, template_id)
    template.name = body.name
    template.doc_type = body.doc_type
    template.description = body.description
    template.fields = _clean_fields(body.fields)
    log_action(db, "template.update", company_id=admin.company_id, actor_user_id=admin.id,
               target_type="template", target_id=str(template.id))
    db.commit()
    publish_event(admin.company_id, "templates.changed", {"action": "updated"})
    counts = _counts(db, admin.company_id)
    return TemplateOut(
        id=template.id, name=template.name, doc_type=template.doc_type,
        description=template.description, fields=template.fields,
        documents_count=counts.get(template.id, 0), created_at=template.created_at,
    )


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: uuid.UUID,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    template = _get_template(db, admin, template_id)
    db.delete(template)  # documents keep their extracted_json; template_id → NULL
    log_action(db, "template.delete", company_id=admin.company_id, actor_user_id=admin.id,
               target_type="template", target_id=str(template_id))
    db.commit()
    publish_event(admin.company_id, "templates.changed", {"action": "deleted"})
