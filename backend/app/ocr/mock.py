"""Deterministic engine for tests, CI, and development machines without models.
Emits plausible Japanese-invoice-shaped markdown derived from the file name so
end-to-end flows (upload → queue → result → correction) are fully exercisable."""

from pathlib import Path

from app.ocr.engine import OcrEngine, PageResult, Region


class MockEngine(OcrEngine):
    name = "mock"

    def parse_page(self, image_path: Path) -> PageResult:
        stem = Path(image_path).stem
        return PageResult(
            regions=[
                Region(bbox=(50, 40, 550, 80), kind="title", markdown="# 請求書", confidence=0.99),
                Region(
                    bbox=(50, 100, 550, 140),
                    kind="text",
                    markdown=f"株式会社サンプル 御中 (mock page: {stem})",
                    confidence=0.97,
                ),
                Region(
                    bbox=(50, 160, 550, 320),
                    kind="table",
                    markdown=(
                        "| 品目 | 数量 | 単価 | 金額 |\n"
                        "| --- | --- | --- | --- |\n"
                        "| サンプル品目A | 2 | ¥1,000 | ¥2,000 |\n"
                        "| サンプル品目B | 1 | ¥5,000 | ¥5,000 |"
                    ),
                    confidence=0.93,
                ),
                Region(
                    bbox=(300, 340, 550, 380),
                    kind="text",
                    markdown="合計: ¥7,000 (税込)",
                    confidence=0.95,
                ),
            ]
        )
