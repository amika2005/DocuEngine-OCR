"""Golden-set evaluation: run the configured OCR engine over every sample and
report CER + table-cell F1 against hand-verified expected markdown.

    make eval                        # uses OCR_ENGINE from the environment
    python -m app.ocr.eval_golden ../scripts/golden_set

Each sample is a directory containing `input.pdf` (or .png/.jpg/.tiff) and
`expected.md`. Exit code 1 if any sample exceeds the CER threshold, so this can
gate CI on machines with models installed."""

import sys
import tempfile
from pathlib import Path

from app.ocr import assemble
from app.ocr.engine import get_engine
from app.ocr.metrics import cer, table_cell_f1
from app.ocr.preprocess import rasterize

CER_THRESHOLD = 0.15


def evaluate_sample(sample_dir: Path) -> tuple[float, float]:
    inputs = [
        path
        for pattern in ("input.pdf", "input.png", "input.jpg", "input.jpeg", "input.tiff")
        for path in [sample_dir / pattern]
        if path.exists()
    ]
    if not inputs:
        raise FileNotFoundError(f"{sample_dir}: no input.* file")
    expected = (sample_dir / "expected.md").read_text(encoding="utf-8")

    engine = get_engine()
    with tempfile.TemporaryDirectory() as tmp:
        pages = rasterize(inputs[0], Path(tmp))
        markdown = assemble.document_markdown(
            [assemble.page_markdown(engine.parse_page(page.path)) for page in pages]
        )
    return cer(expected, markdown), table_cell_f1(expected, markdown)


def main(golden_dir: str) -> int:
    root = Path(golden_dir)
    samples = sorted(path for path in root.iterdir() if path.is_dir())
    if not samples:
        print(f"no samples in {root}")
        return 1

    failures = 0
    print(f"{'sample':40} {'CER':>8} {'tableF1':>8}")
    for sample in samples:
        sample_cer, sample_f1 = evaluate_sample(sample)
        flag = ""
        if sample_cer > CER_THRESHOLD:
            failures += 1
            flag = "  << FAIL"
        print(f"{sample.name:40} {sample_cer:8.4f} {sample_f1:8.4f}{flag}")
    print(f"\n{len(samples) - failures}/{len(samples)} samples within CER {CER_THRESHOLD}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "../scripts/golden_set"))
