"""
flatten_dataset.py

Flattens custom category-organized image captioning datasets (such as `image_captioning_dataset`)
into a unified standard format matching `Bangla Image Captioning`:

Output Directory Structure:
  <output_dir>/
    ├── captioning.xlsx    (Combined dataset Excel file)
    └── image/             (All copied / moved images in a flat folder)

Uses `dataset_directory_tree/caption_parsers.py` to extract all image-caption pairs across sub-categories.
"""

import argparse
import os
import pathlib
import sys
import shutil
from typing import Dict, List

# Add root VisionXAI-Utilities directory to sys.path to import caption_parsers package
UTILITIES_DIR = pathlib.Path(__file__).resolve().parent.parent

if str(UTILITIES_DIR) not in sys.path:
    sys.path.insert(0, str(UTILITIES_DIR))

try:
    from caption_parsers import collect_all_caption_data
except ImportError:
    print(f"ERROR: Could not import `collect_all_caption_data` from {UTILITIES_DIR}")
    sys.exit(1)


# Default dataset paths
DEFAULT_INPUT_DIR = pathlib.Path(
    r"D:\courses\graduate project\xai new project\final project"
    r"\VisionXAI-ModelTraining\data\image_captioning_dataset"
)

DEFAULT_OUTPUT_DIR = pathlib.Path(
    r"D:\courses\graduate project\xai new project\final project"
    r"\VisionXAI-ModelTraining\data\image_captioning_dataset_flattened"
)


def export_to_xlsx(caption_map: Dict[str, List[str]], output_xlsx: pathlib.Path) -> None:
    """
    Exports image-caption mapping to a standard XLSX file (2 columns: filename, caption).
    Uses pandas / openpyxl if available; falls back to openpyxl.
    """
    rows = []
    for img_path, captions in caption_map.items():
        filename = os.path.basename(img_path)
        for cap in captions:
            rows.append((filename, cap))

    try:
        import pandas as pd
        df = pd.DataFrame(rows, columns=["filename", "caption"])
        df.to_excel(output_xlsx, index=False)
        print(f"✅ Created Excel file with {len(rows)} rows: {output_xlsx}")
    except ImportError:
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(["filename", "caption"])
            for r in rows:
                ws.append(list(r))
            wb.save(output_xlsx)
            print(f"✅ Created Excel file with openpyxl ({len(rows)} rows): {output_xlsx}")
        except ImportError:
            print("⚠️ Neither pandas nor openpyxl is installed. Cannot write .xlsx file directly.")
            print("    Please install openpyxl or pandas via: pip install openpyxl pandas")
            sys.exit(1)


def flatten_dataset(
    input_dir: pathlib.Path,
    output_dir: pathlib.Path,
    mode: str = "copy",
    validate_images: bool = True
) -> None:
    """
    Collects captions from `input_dir` using `collect_all_caption_data`,
    flattens images into `<output_dir>/image/`, and writes `<output_dir>/captioning.xlsx`.
    """
    if not input_dir.exists():
        print(f"ERROR: Input directory does not exist: {input_dir}")
        sys.exit(1)

    print(f"🔍 Collecting captions from: {input_dir}")
    caption_map = collect_all_caption_data(str(input_dir), validate_images=validate_images)
    print(f"\n📊 Extracted {len(caption_map)} unique images with captions.")

    if not caption_map:
        print("⚠️ No valid image-caption mappings found.")
        return

    images_out_dir = output_dir / "image"
    images_out_dir.mkdir(parents=True, exist_ok=True)
    output_xlsx = output_dir / "captioning.xlsx"

    print(f"📂 Flattening images into: {images_out_dir} (Mode: {mode.upper()})")

    new_caption_map: Dict[str, List[str]] = {}
    copied_count = 0

    for src_path_str, captions in caption_map.items():
        src_path = pathlib.Path(src_path_str)
        if not src_path.exists() and validate_images:
            continue

        dest_path = images_out_dir / src_path.name

        # If a name collision occurs (different sub-category folders having same filename), disambiguate
        if dest_path.exists() and dest_path.resolve() != src_path.resolve():
            stem = src_path.stem
            suffix = src_path.suffix
            counter = 1
            while dest_path.exists():
                dest_path = images_out_dir / f"{stem}_{counter}{suffix}"
                counter += 1

        if not dest_path.exists():
            if mode == "copy":
                shutil.copy2(src_path, dest_path)
            elif mode == "move":
                shutil.move(src_path, dest_path)
            elif mode == "symlink":
                os.symlink(src_path, dest_path)
            copied_count += 1

        new_caption_map[str(dest_path)] = captions

    print(f"✅ Processed {copied_count} image files into {images_out_dir}")

    # Export merged captions to single XLSX file
    export_to_xlsx(new_caption_map, output_xlsx)
    print(f"\n🎉 Flattening complete!")
    print(f"   Structure: {output_dir}")
    print(f"   ├── captioning.xlsx")
    print(f"   └── image/ ({len(new_caption_map)} images)")


def main():
    parser = argparse.ArgumentParser(
        description="Flatten sub-category dataset folders into standard single-folder format (captioning.xlsx + image/)"
    )
    parser.add_argument(
        "--input-dir",
        "-i",
        type=pathlib.Path,
        default=DEFAULT_INPUT_DIR,
        help=f"Input dataset directory (default: {DEFAULT_INPUT_DIR})"
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=pathlib.Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for flattened dataset (default: {DEFAULT_OUTPUT_DIR})"
    )
    parser.add_argument(
        "--mode",
        "-m",
        choices=["copy", "move", "symlink"],
        default="copy",
        help="File operation mode for images: copy, move, or symlink (default: copy)"
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Disable image existence validation during caption parsing"
    )

    args = parser.parse_args()
    flatten_dataset(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        mode=args.mode,
        validate_images=not args.no_validate
    )


if __name__ == "__main__":
    main()
