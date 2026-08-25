"""Formula-injection neutralization for the Excel exports.

Every cell in `documents_bulk_xlsx` / `document_to_xlsx` ultimately comes from
OCR'd document content or a user-supplied filename — untrusted text an
attacker can shape by crafting a document. A cell whose value begins with
`=`, `+`, `-`, `@`, TAB or CR is executed as a formula the instant the
workbook is opened, so `_sanitize_cell` must neutralize it before it reaches
openpyxl.
"""

import io

from openpyxl import load_workbook

from app.services.export import _sanitize_cell, document_to_xlsx, documents_bulk_xlsx


def test_sanitize_cell_prefixes_formula_looking_strings():
    payload = "=cmd|'/c calc'!A1"
    assert _sanitize_cell(payload) == "'" + payload


def test_sanitize_cell_covers_every_dangerous_prefix():
    for prefix in ("=", "+", "-", "@", "\t", "\r"):
        value = f"{prefix}malicious"
        assert _sanitize_cell(value) == "'" + value


def test_sanitize_cell_leaves_ordinary_text_and_non_strings_untouched():
    assert _sanitize_cell("normal text") == "normal text"
    assert _sanitize_cell("") == ""
    assert _sanitize_cell(None) is None
    assert _sanitize_cell(42) == 42


class _Doc:
    def __init__(self, filename, doc_type="invoice", created_at=None):
        self.original_filename = filename
        self.doc_type = doc_type
        self.created_at = created_at


def test_bulk_xlsx_neutralizes_a_malicious_filename_and_content():
    payload = "=cmd|'/c calc'!A1"
    doc = _Doc(payload)
    data = documents_bulk_xlsx([(doc, payload)])

    wb = load_workbook(io.BytesIO(data))
    ws = wb.active
    # Row 3 is the first data row (row 1 = banner, row 2 = header).
    filename_cell = ws.cell(3, 1).value
    content_cell = ws.cell(3, 4).value
    assert filename_cell.startswith("'")
    assert content_cell.startswith("'")
    # openpyxl strips the leading quote from the *display* value only when the
    # cell is a formula; a text cell keeps it, which is exactly what neutralizes
    # the payload for Excel/LibreOffice on open.
    assert payload in filename_cell
    assert payload in content_cell


def test_document_to_xlsx_neutralizes_malicious_table_and_text_cells(monkeypatch):
    import app.services.export as export_module

    payload_table_row = '| =cmd(1,2,3)!A1 | +HYPERLINK("http://evil") |'
    payload_text = "@SUM(1+1)"
    markdown = f"{payload_table_row}\n\n{payload_text}"

    monkeypatch.setattr(export_module, "_page_markdowns", lambda db, document: [markdown])

    data = document_to_xlsx(db=None, document=_Doc("normal.pdf"))
    wb = load_workbook(io.BytesIO(data))
    sheet = wb["Page 1"]

    table_cell_1 = sheet.cell(1, 1).value
    table_cell_2 = sheet.cell(1, 2).value
    # Row 2 is left blank after the table block before the text line starts.
    text_cell = sheet.cell(3, 1).value

    assert table_cell_1.startswith("'")
    assert table_cell_2.startswith("'")
    assert text_cell.startswith("'")


def test_xlsx_table_cells_turn_br_tags_into_newlines(monkeypatch):
    import app.services.export as export_module

    markdown = "| 品目 | 金額 |\n| --- | --- |\n| マスター管理<br>サーバー監視 | 45,000 |"
    monkeypatch.setattr(export_module, "_page_markdowns", lambda db, document: [markdown])
    data = document_to_xlsx(db=None, document=_Doc("invoice.pdf"))
    wb = load_workbook(io.BytesIO(data))
    cell = wb["Page 1"].cell(2, 1).value
    assert "<br>" not in (cell or "")
    assert "マスター管理\nサーバー監視" == cell
