"""LoRA fine-tuning backend for PaddleOCR-VL's ERNIE decoder.

This is the GPU-heavy integration point: it consumes train.jsonl produced by
dataset.py and writes a LoRA adapter directory. It requires the `lora` extra
(paddlenlp/ERNIEKit toolchain) and a CUDA GPU, so imports are deferred and the
run fails cleanly (training_run.status = error) on machines without them.

The proven fallback path is finetune_rec.py (PP-OCRv5 recognition model on
text-line crops) — switch with TRAINER_BACKEND=rec.
"""

import time
from pathlib import Path

DEFAULT_HYPERPARAMS = {
    "lora_rank": 16,
    "lora_alpha": 32,
    "learning_rate": 1e-4,
    "epochs": 2,
    "batch_size": 1,
    "gradient_accumulation_steps": 8,
    "precision": "bf16",
}


class LoraTrainingError(RuntimeError):
    pass


def train_lora_adapter(
    base_model_dir: Path,
    train_jsonl: Path,
    output_dir: Path,
    hyperparams: dict | None = None,
    wall_clock_limit_s: int = 4 * 3600,
) -> Path:
    """Returns the adapter directory. Raises LoraTrainingError on any failure —
    the caller records it on the training run and never touches the active model."""
    params = {**DEFAULT_HYPERPARAMS, **(hyperparams or {})}
    started = time.monotonic()

    try:
        from paddlenlp.peft import LoRAConfig, LoRAModel  # noqa: F401
        from paddlenlp.transformers import AutoModelForCausalLM  # noqa: F401
    except ImportError as exc:
        raise LoraTrainingError(
            "paddlenlp is not installed (trainer image must include the `lora` extra)"
        ) from exc

    if not base_model_dir.exists():
        raise LoraTrainingError(f"base model not found: {base_model_dir}")
    if not train_jsonl.exists():
        raise LoraTrainingError(f"training data not found: {train_jsonl}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # --- ERNIEKit LoRA training loop ---
    # Integration point for the client-server GPU environment. Wire-up:
    #   1. tokenizer + AutoModelForCausalLM.from_pretrained(base_model_dir)
    #   2. LoRAModel(model, LoRAConfig(r=params["lora_rank"], ...))
    #   3. dataset from train_jsonl: (page image, corrected markdown) pairs
    #   4. paddlenlp Trainer with bf16 + gradient accumulation for 8GB VRAM
    #   5. enforce wall_clock_limit_s via a TrainerCallback; save adapter only
    #      on clean completion.
    raise LoraTrainingError(
        "VL LoRA training loop not wired up yet — pending the toolchain spike "
        "(plan Phase 4); use TRAINER_BACKEND=rec meanwhile"
    )

    # unreachable, kept for signature clarity:
    _ = started, wall_clock_limit_s
    return output_dir
