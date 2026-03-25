#!/usr/bin/env python3
"""
Download and convert the NLLB-200 translation model for Observer.

Downloads facebook/nllb-200-distilled-600M from HuggingFace Hub and converts
it to CTranslate2 int8 format for fast CPU inference without PyTorch at runtime.

Usage:
    python scripts/download_nllb.py                  # Download + convert (default: int8)
    python scripts/download_nllb.py --quantization float16   # For GPU with float16
    python scripts/download_nllb.py --check           # Check if model is ready
    python scripts/download_nllb.py --output /path    # Custom output directory

Requires (install-time only):
    pip install transformers torch sentencepiece ctranslate2

These are NOT needed at runtime — only ctranslate2 and sentencepiece are.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_MODEL = "facebook/nllb-200-distilled-600M"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "models" / "nllb-200-distilled-600M-ct2"
DEFAULT_QUANTIZATION = "int8"

REQUIRED_FILES = ["model.bin", "vocabulary.json", "shared_vocabulary.json"]
SP_MODEL_NAME = "sentencepiece.bpe.model"


def check_model(output_dir: Path) -> bool:
    """Check if a valid CT2 model exists at the given path."""
    if not output_dir.exists():
        return False
    has_model = (output_dir / "model.bin").exists()
    has_sp = (output_dir / SP_MODEL_NAME).exists()
    return has_model and has_sp


def find_converter() -> str | None:
    """Find ct2-transformers-converter, checking the current venv first."""
    # Check alongside the running Python (works inside a venv)
    bin_dir = Path(sys.executable).parent
    candidate = bin_dir / "ct2-transformers-converter"
    if candidate.exists():
        return str(candidate)
    # Fall back to system PATH
    return shutil.which("ct2-transformers-converter")


def check_build_deps() -> list:
    """Check which build-time dependencies are missing."""
    missing = []
    try:
        import ctranslate2  # noqa: F401
    except ImportError:
        missing.append("ctranslate2")
    try:
        import transformers  # noqa: F401
    except ImportError:
        missing.append("transformers")
    try:
        import torch  # noqa: F401
    except ImportError:
        missing.append("torch")
    try:
        import sentencepiece  # noqa: F401
    except ImportError:
        missing.append("sentencepiece")
    return missing


def download_sentencepiece(model_name: str, output_dir: Path) -> bool:
    """Download the sentencepiece model from HuggingFace."""
    sp_dest = output_dir / SP_MODEL_NAME
    if sp_dest.exists():
        print(f"  sentencepiece model already exists: {sp_dest}")
        return True

    try:
        from huggingface_hub import hf_hub_download
        print(f"  Downloading {SP_MODEL_NAME} from {model_name}...")
        downloaded = hf_hub_download(
            repo_id=model_name,
            filename=SP_MODEL_NAME,
            local_dir=str(output_dir),
        )
        # hf_hub_download may place it in a subdir; copy to expected location
        dl_path = Path(downloaded)
        if dl_path != sp_dest and dl_path.exists():
            shutil.copy2(dl_path, sp_dest)
        print(f"  Saved: {sp_dest}")
        return True
    except ImportError:
        # Fallback: use transformers tokenizer to save it
        try:
            from transformers import AutoTokenizer
            print(f"  Extracting {SP_MODEL_NAME} via transformers tokenizer...")
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            sp_path = tokenizer.vocab_file
            if sp_path and Path(sp_path).exists():
                shutil.copy2(sp_path, sp_dest)
                print(f"  Saved: {sp_dest}")
                return True
        except Exception as e:
            print(f"  Warning: Could not extract sentencepiece model: {e}")
    return False


def convert_model(model_name: str, output_dir: Path, quantization: str, converter: str = "ct2-transformers-converter") -> bool:
    """Convert HuggingFace model to CTranslate2 format."""
    print(f"\n  Converting {model_name} to CTranslate2 ({quantization})...")
    print("  This downloads ~1.2 GB and may take a few minutes...\n")

    cmd = [
        converter,
        "--model", model_name,
        "--output_dir", str(output_dir),
        "--quantization", quantization,
        "--force",
    ]

    try:
        result = subprocess.run(cmd, check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"\n  Conversion failed: {e}")
        return False
    except FileNotFoundError:
        print("\n  ct2-transformers-converter not found.")
        print("  Install with: pip install ctranslate2")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Download and convert NLLB-200 model for Observer"
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"HuggingFace model name (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help=f"Output directory (default: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--quantization", default=DEFAULT_QUANTIZATION,
        choices=["int8", "int8_float16", "float16", "float32"],
        help=f"Quantization type (default: {DEFAULT_QUANTIZATION})"
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Check if model is already installed"
    )
    args = parser.parse_args()

    # Check mode
    if args.check:
        if check_model(args.output):
            print(f"NLLB model ready at {args.output}")
            model_bin = args.output / "model.bin"
            size_mb = model_bin.stat().st_size / (1024 * 1024)
            print(f"  model.bin: {size_mb:.0f} MB")
            print(f"  sentencepiece: {'found' if (args.output / SP_MODEL_NAME).exists() else 'MISSING'}")
            return 0
        else:
            print(f"NLLB model NOT found at {args.output}")
            print(f"  Run: python scripts/download_nllb.py")
            return 1

    # Check if already installed
    if check_model(args.output):
        print(f"NLLB model already installed at {args.output}")
        model_bin = args.output / "model.bin"
        size_mb = model_bin.stat().st_size / (1024 * 1024)
        print(f"  model.bin: {size_mb:.0f} MB")
        print("  To re-download, delete the directory and run again.")
        return 0

    print("=" * 60)
    print("NLLB-200 Model Download & Conversion")
    print("=" * 60)
    print(f"  Model:        {args.model}")
    print(f"  Output:       {args.output}")
    print(f"  Quantization: {args.quantization}")
    print()

    # Check build dependencies
    missing = check_build_deps()
    if missing:
        print("Missing build-time dependencies:")
        for dep in missing:
            print(f"  - {dep}")
        print()
        print("Install them with:")
        print(f"  pip install {' '.join(missing)}")
        print()
        print("Note: transformers and torch are only needed for conversion,")
        print("not at runtime. You can uninstall them after conversion:")
        print("  pip uninstall transformers torch")
        return 1

    converter = find_converter()
    if not converter:
        print("ct2-transformers-converter not found.")
        print("Install with: pip install ctranslate2")
        return 1

    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)

    # Convert model
    if not convert_model(args.model, args.output, args.quantization, converter):
        return 1

    # Download sentencepiece model
    if not download_sentencepiece(args.model, args.output):
        print("\nWarning: sentencepiece model not found.")
        print("Translation may not work without it.")

    # Verify
    if check_model(args.output):
        print()
        print("=" * 60)
        print("NLLB model installed successfully!")
        print("=" * 60)
        model_bin = args.output / "model.bin"
        size_mb = model_bin.stat().st_size / (1024 * 1024)
        print(f"  Location: {args.output}")
        print(f"  Size:     {size_mb:.0f} MB")
        print()
        print("You can now uninstall the build-time dependencies:")
        print("  pip uninstall transformers torch")
        print()
        print("Observer only needs ctranslate2 and sentencepiece at runtime.")
        return 0
    else:
        print("\nModel verification failed. Check the output above for errors.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
