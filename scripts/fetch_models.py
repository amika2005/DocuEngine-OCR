"""Downloads OCR model weights on an internet-connected build machine and
rewrites models/manifest.json with real sha256 digests. Run before bundle.sh;
client installs never download anything.

    pip install huggingface_hub
    python scripts/fetch_models.py
"""

import hashlib
import json
import sys
from pathlib import Path

MODELS_DIR = Path(__file__).parent.parent / "models"

# HuggingFace repos for the shipped weights (all Apache-2.0).
SOURCES = {
    "paddleocr-vl": "PaddlePaddle/PaddleOCR-VL",
    "pp-doclayoutv2": "PaddlePaddle/PP-DocLayoutV2",
    "pp-ocrv5": "PaddlePaddle/PP-OCRv5_server_rec",
    "doc-orientation": "PaddlePaddle/PP-LCNet_x1_0_doc_ori",
}


def sha256_dir(path: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(path.rglob("*")):
        if file.is_file():
            digest.update(file.relative_to(path).as_posix().encode())
            digest.update(file.read_bytes())
    return digest.hexdigest()


def main() -> int:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("pip install huggingface_hub first", file=sys.stderr)
        return 1

    manifest_path = MODELS_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    for entry in manifest["models"]:
        local_dir = MODELS_DIR / entry["path"]
        repo = SOURCES.get(entry["path"])
        if repo is None:
            print(f"skip {entry['path']}: no source configured")
            continue
        print(f"downloading {repo} -> {local_dir}")
        snapshot_download(repo_id=repo, local_dir=local_dir)
        entry["sha256"] = sha256_dir(local_dir)
        print(f"  sha256={entry['sha256']}")

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"updated {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
