"""Export OCR results as PDF or Excel.

Single-document PDF/Excel are built from the per-page markdown (same content
the UI shows). The bulk Excel export lays many documents' extracted template
fields into one polished sheet (one row per document).
"""

import html
import io
import re
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, OcrResult, Page


def documents_bulk_xlsx(documents: Iterable[Document], title: str = "抽出一覧") -> bytes:
    """One polished sheet: title banner, JP headers, one row per document with
    its extracted template fields (union of field labels across the set)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    from app.services.classify import CATEGORY_LABELS_JA

    documents = list(documents)

    # Column set: fixed (file, category, date) + the union of extracted field
    # labels, in the order they first appear.
    field_labels: list[str] = []
    seen: set[str] = set()
    rows: list[tuple[Document, dict[str, str]]] = []
    for doc in documents:
        extracted = doc.extracted_json or {}
        values = {
            f.get("label", f.get("key", "")): (f.get("value") or "")
            for f in extracted.get("fields", [])
        }
        for label in values:
            if label and label not in seen:
                seen.add(label)
                field_labels.append(label)
        rows.append((doc, values))

    headers = ["ファイル名", "区分", "登録日"] + field_labels
    ncols = len(headers)

    thin = Side(style="thin", color="B4C6E7")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    wb = Workbook()
    ws = wb.active
    ws.title = "抽出一覧"

    # Title banner (merged, dark blue).
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    banner = ws.cell(1, 1, title)
    banner.font = Font(bold=True, size=13, color="FFFFFF")
    banner.fill = PatternFill("solid", fgColor="1F4E78")
    banner.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 28

    # Header row.
    header_fill = PatternFill("solid", fgColor="DDEBF7")
    for col, text in enumerate(headers, start=1):
        cell = ws.cell(2, col, text)
        cell.font = Font(bold=True, color="1F4E78")
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[2].height = 22

    # Data rows.
    for r, (doc, values) in enumerate(rows, start=3):
        category = CATEGORY_LABELS_JA.get(doc.doc_type or "", doc.doc_type or "")
        created = doc.created_at.strftime("%Y/%m/%d") if doc.created_at else ""
        line = [doc.original_filename, category, created] + [
            values.get(label, "") for label in field_labels
        ]
        for col, value in enumerate(line, start=1):
            cell = ws.cell(r, col, value)
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=True)
        if r % 2 == 1:  # subtle zebra striping
            for col in range(1, ncols + 1):
                ws.cell(r, col).fill = PatternFill("solid", fgColor="F5F9FF")

    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 12
    for i in range(4, ncols + 1):
        ws.column_dimensions[get_column_letter(i)].width = 22
    ws.freeze_panes = "A3"

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()

_TABLE_SEP = re.compile(r"^\|[\s\-:|]+\|$")
_IMAGE_LINE = re.compile(r"^!\[([^\]]*)\]\((.+)\)$")


def _split_blocks(markdown: str) -> list[tuple[str, list]]:
    """Markdown → [('table', rows), ('text', line), ('image', [alt, src]), …]."""
    blocks: list[tuple[str, list]] = []
    table: list[list[str]] = []
    for line in markdown.splitlines():
        line = line.rstrip()
        if line.startswith("|") and line.endswith("|") and len(line) > 1:
            if _TABLE_SEP.match(line):
                continue
            cells = [c.strip().replace("\\|", "|") for c in line[1:-1].split("|")]
            table.append(cells)
            continue
        if table:
            blocks.append(("table", table))
            table = []
        image = _IMAGE_LINE.match(line.strip())
        if image:
            blocks.append(("image", [image.group(1), image.group(2)]))
        elif line.strip():
            blocks.append(("text", [line.strip()]))
    if table:
        blocks.append(("table", table))
    return blocks


def _page_markdowns(db: Session, document: Document) -> list[str]:
    pages = db.scalars(
        select(Page).where(Page.document_id == document.id).order_by(Page.page_number)
    ).all()
    out = []
    for page in pages:
        result = db.scalar(
            select(OcrResult).where(OcrResult.page_id == page.id, OcrResult.is_current)
        )
        out.append(result.markdown if result else "")
    return out


# --- PDF ---

_PDF_CSS = """
body { font-size: 10px; }
h2 { font-size: 13px; margin: 0 0 6px 0; }
p { margin: 0 0 4px 0; }
table { border-collapse: collapse; margin: 4px 0 8px 0; width: 100%; }
td { border: 0.5px solid #999; padding: 2px 4px; font-size: 9px; }
tr:first-child td { background-color: #eef1f5; font-weight: bold; }
"""


def document_to_pdf(db: Session, document: Document) -> bytes:
    import fitz

    pdf = fitz.open()
    margin = 36
    for number, markdown in enumerate(_page_markdowns(db, document), start=1):
        parts: list[str] = []
        for kind, content in _split_blocks(markdown):
            if kind == "table":
                rows = "".join(
                    "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in row) + "</tr>"
                    for row in content
                )
                parts.append(f"<table>{rows}</table>")
            elif kind == "image":
                parts.append(f'<p><img src="{content[1]}" height="90"></p>')
            else:
                parts.append(f"<p>{html.escape(content[0])}</p>")
        body = "".join(parts) or "<p>—</p>"

        # insert_htmlbox flows overflowing content into extra pages.
        remaining = body
        while True:
            page = pdf.new_page()  # A4
            rect = fitz.Rect(margin, margin, page.rect.width - margin, page.rect.height - margin)
            spare, _scale = page.insert_htmlbox(rect, remaining, css=_PDF_CSS)
            if spare >= 0:
                break
            # Content did not fit even after shrinking — extremely long page.
            # insert_htmlbox already truncates; avoid an infinite loop.
            break
    pdf.subset_fonts()  # embed only the glyphs actually used (~3.5MB → ~KBs)
    data = pdf.tobytes(garbage=3, deflate=True)
    pdf.close()
    return data


# --- Excel ---

def document_to_xlsx(db: Session, document: Document) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    thin = Side(style="thin", color="AAAAAA")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", fgColor="EEF1F5")

    workbook = Workbook()
    workbook.remove(workbook.active)
    for number, markdown in enumerate(_page_markdowns(db, document), start=1):
        sheet = workbook.create_sheet(f"Page {number}")
        row_index = 1
        max_width = 1
        for kind, content in _split_blocks(markdown):
            if kind == "table":
                first = True
                for cells in content:
                    for col_index, cell in enumerate(cells, start=1):
                        c = sheet.cell(row=row_index, column=col_index, value=cell)
                        c.border = border
                        c.alignment = Alignment(wrap_text=True, vertical="top")
                        if first:
                            c.fill = header_fill
                            c.font = Font(bold=True)
                    max_width = max(max_width, len(cells))
                    row_index += 1
                    first = False
                row_index += 1  # blank row after each table
            elif kind == "image":
                # Embed the barcode/QR crop as a floating image anchored to the
                # current row.
                try:
                    import base64

                    from openpyxl.drawing.image import Image as XLImage

                    b64 = content[1].split(",", 1)[1]
                    img_stream = io.BytesIO(base64.b64decode(b64))
                    picture = XLImage(img_stream)
                    picture.anchor = f"A{row_index}"
                    sheet.add_image(picture)
                    row_index += 6  # leave vertical space for the image
                except Exception:
                    sheet.cell(row=row_index, column=1, value=f"[{content[0] or 'code'}]")
                    row_index += 1
            else:
                sheet.cell(row=row_index, column=1, value=content[0])
                row_index += 1
        for col in range(1, max_width + 1):
            sheet.column_dimensions[sheet.cell(row=1, column=col).column_letter].width = 28
    if not workbook.sheetnames:
        workbook.create_sheet("Page 1")
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
