import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: uuid.UUID
    original_filename: str
    doc_type: str
    status: str
    page_count: int
    byte_size: int
    batch_id: uuid.UUID | None
    template_id: uuid.UUID | None = None
    extracted_json: dict | None = None
    visibility: str = "shared"
    uploaded_by_user_id: uuid.UUID | None = None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    total: int
    page: int
    page_size: int


class PageOut(BaseModel):
    id: uuid.UUID
    page_number: int
    status: str
    width_px: int
    height_px: int
    error_message: str | None = None

    model_config = {"from_attributes": True}


class OcrResultOut(BaseModel):
    id: uuid.UUID
    markdown: str
    layout_json: dict
    avg_confidence: float | None
    engine: str

    model_config = {"from_attributes": True}


class BatchOut(BaseModel):
    id: uuid.UUID
    total_documents: int
    completed_documents: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CorrectionCreate(BaseModel):
    corrected_markdown: str
    region_index: int | None = None


class CorrectionUpdate(BaseModel):
    corrected_markdown: str


class CorrectionOut(BaseModel):
    id: uuid.UUID
    page_id: uuid.UUID
    ocr_result_id: uuid.UUID
    original_markdown: str
    corrected_markdown: str
    region_index: int | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TrainingRunOut(BaseModel):
    id: uuid.UUID
    status: str
    dataset_stats: dict
    eval_report: dict
    triggered_by: str
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ModelVersionOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    status: str
    metrics: dict
    company_id: uuid.UUID | None
    activated_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
