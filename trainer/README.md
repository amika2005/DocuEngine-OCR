# DocuEngine trainer

Consumes the `training` Celery queue. Nightly (or manually triggered) runs:

1. export approved corrections → train/holdout dataset
2. LoRA fine-tune of the OCR model (per-company adapter)
3. eval gate: CER + table-cell F1 on holdout + golden set, vs the active model
4. pass → `candidate` model version awaiting human activation in the web UI

The actual LoRA training backend (`finetune_vl_lora.py`) requires the `lora`
extra and GPU; everything else (dataset build, metrics, gate, promotion) is
plain Python and covered by tests.
