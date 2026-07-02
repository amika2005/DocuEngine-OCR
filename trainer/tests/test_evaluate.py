from trainer.evaluate import (
    EvalReport,
    GateConfig,
    apply_gate,
    cer,
    extract_table_cells,
    normalize_ja,
    table_cell_f1,
)


def test_cer_zero_for_identical():
    assert cer("請求書 合計 ¥7,000", "請求書 合計 ¥7,000") == 0.0


def test_cer_nfkc_fullwidth_halfwidth_equivalence():
    # Full-width digits / half-width katakana are the same content in JA docs.
    assert cer("金額123 カタカナ", "金額１２３ ｶﾀｶﾅ") == 0.0


def test_cer_counts_substitutions():
    assert cer("abc", "abd") == 1 / 3


def test_cer_empty_reference():
    assert cer("", "") == 0.0
    assert cer("", "junk") == 1.0


def test_extract_table_cells_skips_separator():
    md = "| 品目 | 金額 |\n| --- | --- |\n| A | ¥100 |"
    assert extract_table_cells(md) == [["品目", "金額"], ["A", "¥100"]]


def test_table_cell_f1():
    ref = "| a | b |\n| --- | --- |\n| c | d |"
    assert table_cell_f1(ref, ref) == 1.0
    half = "| a | b |\n| --- | --- |\n| x | y |"
    assert 0 < table_cell_f1(ref, half) < 1
    assert table_cell_f1(ref, "no table at all") == 0.0
    assert table_cell_f1("plain text", "plain text") == 1.0  # no tables anywhere


def _report(**overrides):
    base = dict(
        baseline_holdout_cer=0.10,
        candidate_holdout_cer=0.08,
        baseline_golden_cer=0.05,
        candidate_golden_cer=0.05,
        baseline_golden_table_f1=0.90,
        candidate_golden_table_f1=0.90,
    )
    base.update(overrides)
    return EvalReport(**base)


def test_gate_passes_on_improvement_without_regression():
    report = apply_gate(_report())
    assert report.passed, report.reason


def test_gate_fails_on_insufficient_improvement():
    report = apply_gate(_report(candidate_holdout_cer=0.0999))
    assert not report.passed
    assert "improvement" in report.reason


def test_gate_fails_on_golden_cer_regression():
    report = apply_gate(_report(candidate_golden_cer=0.07))
    assert not report.passed
    assert "golden set CER" in report.reason


def test_gate_fails_on_golden_table_regression():
    report = apply_gate(_report(candidate_golden_table_f1=0.80))
    assert not report.passed
    assert "table F1" in report.reason


def test_gate_config_margins_respected():
    lenient = GateConfig(min_relative_cer_improvement=0.0)
    report = apply_gate(_report(candidate_holdout_cer=0.0999), lenient)
    assert report.passed


def test_normalize_collapses_whitespace():
    assert normalize_ja("a  b\n c") == "a b c"
