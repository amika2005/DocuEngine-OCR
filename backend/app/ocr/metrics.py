"""OCR quality metrics, shared by the trainer's eval gate and `make eval`.

CER uses NFKC normalization so full-width/half-width variants (ubiquitous in
Japanese business documents: １２３ vs 123, ｶﾀｶﾅ vs カタカナ) don't count as
errors. Tables are compared as cell grids (precision/recall/F1 over cells) — a
pragmatic stand-in for TEDS that behaves the same for markdown tables."""

import re
import unicodedata


def normalize_ja(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    # OCR-irrelevant whitespace differences are not errors.
    return re.sub(r"\s+", " ", text).strip()


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate = edit distance / reference length."""
    ref = normalize_ja(reference)
    hyp = normalize_ja(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    # Levenshtein with two rows — pages are a few thousand chars, this is fine.
    previous = list(range(len(hyp) + 1))
    for i, ref_char in enumerate(ref, start=1):
        current = [i]
        for j, hyp_char in enumerate(hyp, start=1):
            current.append(
                min(
                    previous[j] + 1,  # deletion
                    current[j - 1] + 1,  # insertion
                    previous[j - 1] + (ref_char != hyp_char),  # substitution
                )
            )
        previous = current
    return previous[-1] / len(ref)


def extract_table_cells(markdown: str) -> list[list[str]]:
    """All cells of all GFM tables in the markdown, row by row."""
    rows: list[list[str]] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [cell.strip() for cell in stripped[1:-1].split("|")]
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue  # separator row
        rows.append([normalize_ja(cell) for cell in cells])
    return rows


def table_cell_f1(reference_md: str, hypothesis_md: str) -> float:
    ref_cells = [cell for row in extract_table_cells(reference_md) for cell in row if cell]
    hyp_cells = [cell for row in extract_table_cells(hypothesis_md) for cell in row if cell]
    if not ref_cells and not hyp_cells:
        return 1.0
    if not ref_cells or not hyp_cells:
        return 0.0
    matched = 0
    remaining = list(hyp_cells)
    for cell in ref_cells:
        if cell in remaining:
            remaining.remove(cell)
            matched += 1
    precision = matched / len(hyp_cells)
    recall = matched / len(ref_cells)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)
