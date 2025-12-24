import argparse
import sys
from pathlib import Path

from PIL import Image

try:
    from .cleanup_core import CancelledError, cleanup_background
except ImportError:
    from cleanup_core import CancelledError, cleanup_background


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


def _iter_input_files(input_path: Path, recursive: bool) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if not input_path.is_dir():
        return []

    if recursive:
        candidates = (path for path in input_path.rglob("*") if path.is_file())
    else:
        candidates = (path for path in input_path.iterdir() if path.is_file())

    files = [path for path in candidates if path.suffix.lower() in SUPPORTED_EXTENSIONS]
    return sorted(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Batch-process images using I2g cleanup_core.")
    parser.add_argument("--input", required=True, help="Input file or directory path.")
    parser.add_argument("--output-dir", required=True, help="Output directory path.")
    parser.add_argument("--threshold", type=int, default=20, help="Outline threshold (default: 20).")
    parser.add_argument("--dilation", type=int, default=50, help="Dilation passes (default: 50).")
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively scan subdirectories when input is a directory.",
    )

    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    if not input_path.exists():
        print(f"ERROR: input path does not exist: {input_path}", file=sys.stderr)
        return 1

    files = _iter_input_files(input_path, recursive=args.recursive)
    if not files:
        print(
            f"ERROR: no supported image files found in: {input_path} "
            f"(supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))})",
            file=sys.stderr,
        )
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    processed = 0
    succeeded = 0
    failed = 0

    for file_path in files:
        processed += 1
        try:
            image = Image.open(file_path).convert("RGBA")
            cleaned, _ = cleanup_background(
                image,
                outline_threshold=args.threshold,
                fill_tolerance=80,
                dilation_passes=args.dilation,
            )
            if input_path.is_dir() and args.recursive:
                rel = file_path.relative_to(input_path)
                out_path = output_dir / rel.parent / f"{file_path.stem}_cleaned.png"
                out_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                out_path = output_dir / f"{file_path.stem}_cleaned.png"
            cleaned.save(out_path, "PNG")
            succeeded += 1
        except Exception as e:
            failed += 1
            print(f"ERROR: failed to process {file_path.name}: {e}", file=sys.stderr)

    print(f"Processed: {processed} | Succeeded: {succeeded} | Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
