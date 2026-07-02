from app.ocr.assemble import (
    cells_to_markdown,
    document_markdown,
    html_table_to_markdown,
    order_regions,
    page_markdown,
)
from app.ocr.engine import PageResult, Region


def region(x0, y0, x1, y1, markdown, vertical=False):
    return Region(bbox=(x0, y0, x1, y1), kind="text", markdown=markdown, vertical=vertical)


def test_horizontal_reading_order_top_to_bottom_left_to_right():
    result = PageResult(
        regions=[
            region(300, 500, 500, 540, "bottom"),
            region(300, 100, 500, 140, "top-right"),
            region(50, 100, 250, 140, "top-left"),
        ]
    )
    assert page_markdown(result) == "top-left\n\ntop-right\n\nbottom"


def test_vertical_tategaki_reads_right_to_left():
    # A Japanese letter: three vertical columns on one band.
    regions = [
        region(100, 50, 150, 600, "第三列", vertical=True),
        region(400, 50, 450, 600, "第一列", vertical=True),
        region(250, 50, 300, 600, "第二列", vertical=True),
    ]
    ordered = order_regions(regions)
    assert [r.markdown for r in ordered] == ["第一列", "第二列", "第三列"]


def test_empty_regions_are_dropped():
    result = PageResult(regions=[region(0, 0, 10, 10, "  "), region(0, 20, 10, 30, "text")])
    assert page_markdown(result) == "text"


def test_cells_to_markdown_escapes_pipes_and_newlines():
    md = cells_to_markdown([["品目", "金額"], ["A|B", "1\n2"]])
    assert "A\\|B" in md
    assert "1<br>2" in md
    assert md.splitlines()[1] == "| --- | --- |"


def test_cells_to_markdown_pads_ragged_rows():
    md = cells_to_markdown([["a", "b", "c"], ["only-one"]])
    lines = md.splitlines()
    assert lines[2].count("|") == 4  # padded to full width


def test_html_table_to_markdown():
    html = "<table><tr><th>品目</th><th>金額</th></tr><tr><td>コーヒー</td><td>¥500</td></tr></table>"
    md = html_table_to_markdown(html)
    assert md.splitlines()[0] == "| 品目 | 金額 |"
    assert "| コーヒー | ¥500 |" in md


def test_html_table_colspan_preserves_column_count():
    html = "<table><tr><td colspan='2'>合計</td><td>¥7,000</td></tr></table>"
    md = html_table_to_markdown(html)
    assert md.splitlines()[0] == "| 合計 |  | ¥7,000 |"


def test_html_table_fallback_strips_tags():
    assert html_table_to_markdown("<div>плain</div>") == "плain"


def test_document_markdown_joins_pages_with_separator():
    assert document_markdown(["p1", "p2"]) == "p1\n\n---\n\np2"
