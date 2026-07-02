"""Fallback fine-tune path: PP-OCRv5 recognition model on text-line crops.

Cheaper and lower-risk than VL LoRA (well-trodden PaddleOCR training recipe);
improves character recognition only, not layout. Selected with
TRAINER_BACKEND=rec."""

from pathlib import Path

from trainer.finetune_vl_lora import LoraTrainingError


def train_rec_model(
    base_model_dir: Path,
    train_jsonl: Path,
    output_dir: Path,
    hyperparams: dict | None = None,
    wall_clock_limit_s: int = 4 * 3600,
) -> Path:
    try:
        import paddle  # noqa: F401
    except ImportError as exc:
        raise LoraTrainingError("paddlepaddle is not installed in the trainer image") from exc

    if not train_jsonl.exists():
        raise LoraTrainingError(f"training data not found: {train_jsonl}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Integration point (plan Phase 4): convert correction pairs to PaddleOCR
    # rec format (text-line crops + labels via layout_json bboxes), then drive
    # PaddleOCR's train.py with the japan_PP-OCRv5_rec config, seeded from
    # base_model_dir, capped at wall_clock_limit_s.
    raise LoraTrainingError(
        "rec fine-tune loop not wired up yet — pending the Phase 4 toolchain spike"
    )
