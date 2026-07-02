"""Generates the synthetic golden-set starter sample (a simple Japanese invoice
PDF) plus its expected markdown. Real scanned documents should be added by hand
as the set grows — this exists so a fresh clone has at least one working sample.

    cd backend && uv run python ../scripts/generate_golden_samples.py
"""

from pathlib import Path

import fitz

GOLDEN = Path(__file__).parent / "golden_set"

INVOICE_LINES = [
    (72, 60, "請求書", 20),
    (72, 100, "株式会社サンプル商事 御中", 12),
    (380, 100, "請求番号: INV-2026-001", 10),
    (380, 118, "発行日: 2026年7月2日", 10),
    (72, 160, "品目            数量    単価      金額", 11),
    (72, 180, "コピー用紙 A4      10    ¥500    ¥5,000", 11),
    (72, 200, "トナー TN-29J       2  ¥8,000   ¥16,000", 11),
    (72, 240, "小計: ¥21,000    消費税(10%): ¥2,100    合計: ¥23,100", 11),
    (72, 300, "お支払期限: 2026年7月31日", 10),
]

EXPECTED_MD = """# 請求書

株式会社サンプル商事 御中

請求番号: INV-2026-001
発行日: 2026年7月2日

| 品目 | 数量 | 単価 | 金額 |
| --- | --- | --- | --- |
| コピー用紙 A4 | 10 | ¥500 | ¥5,000 |
| トナー TN-29J | 2 | ¥8,000 | ¥16,000 |

小計: ¥21,000 消費税(10%): ¥2,100 合計: ¥23,100

お支払期限: 2026年7月31日
"""


def main() -> None:
    sample = GOLDEN / "sample-001-invoice"
    sample.mkdir(parents=True, exist_ok=True)

    pdf = fitz.open()
    page = pdf.new_page()  # A4 default
    for x, y, text, size in INVOICE_LINES:
        page.insert_text((x, y), text, fontsize=size, fontname="japan")
    pdf.save(sample / "input.pdf")
    (sample / "expected.md").write_text(EXPECTED_MD, encoding="utf-8")
    print(f"wrote {sample}")


if __name__ == "__main__":
    main()
