"""The promotion gate. Metrics themselves (CER with JA-aware NFKC
normalization, table-cell F1) live in the backend at app/ocr/metrics.py and are
re-exported here for trainer code and tests."""

from dataclasses import dataclass

from app.ocr.metrics import (  # noqa: F401 — re-exported API
    cer,
    extract_table_cells,
    normalize_ja,
    table_cell_f1,
)


@dataclass
class GateConfig:
    # Candidate must improve holdout CER by at least this relative margin...
    min_relative_cer_improvement: float = 0.02
    # ...while the golden set must not regress beyond these absolute limits.
    max_golden_cer_regression: float = 0.005
    max_golden_table_f1_regression: float = 0.01


@dataclass
class EvalReport:
    baseline_holdout_cer: float
    candidate_holdout_cer: float
    baseline_golden_cer: float
    candidate_golden_cer: float
    baseline_golden_table_f1: float
    candidate_golden_table_f1: float
    passed: bool = False
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "holdout_cer": {"baseline": self.baseline_holdout_cer, "candidate": self.candidate_holdout_cer},
            "golden_cer": {"baseline": self.baseline_golden_cer, "candidate": self.candidate_golden_cer},
            "golden_table_f1": {
                "baseline": self.baseline_golden_table_f1,
                "candidate": self.candidate_golden_table_f1,
            },
            "passed": self.passed,
            "reason": self.reason,
        }


def apply_gate(report: EvalReport, config: GateConfig | None = None) -> EvalReport:
    """Promotion rule: real improvement on held-out corrections AND no
    regression on the fixed golden set. Anything else is rejected."""
    config = config or GateConfig()

    if report.baseline_holdout_cer <= 0:
        improvement = 0.0
    else:
        improvement = (
            report.baseline_holdout_cer - report.candidate_holdout_cer
        ) / report.baseline_holdout_cer

    if improvement < config.min_relative_cer_improvement:
        report.passed = False
        report.reason = (
            f"holdout CER improvement {improvement:.3%} below required "
            f"{config.min_relative_cer_improvement:.3%}"
        )
        return report

    golden_cer_regression = report.candidate_golden_cer - report.baseline_golden_cer
    if golden_cer_regression > config.max_golden_cer_regression:
        report.passed = False
        report.reason = f"golden set CER regressed by {golden_cer_regression:.4f}"
        return report

    golden_f1_regression = report.baseline_golden_table_f1 - report.candidate_golden_table_f1
    if golden_f1_regression > config.max_golden_table_f1_regression:
        report.passed = False
        report.reason = f"golden set table F1 regressed by {golden_f1_regression:.4f}"
        return report

    report.passed = True
    report.reason = f"holdout CER improved {improvement:.3%}, golden set stable"
    return report
