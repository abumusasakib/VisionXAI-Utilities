import os
import zipfile
import xml.etree.ElementTree as ET
import csv
from pathlib import Path
from collections import defaultdict
import statistics

# Import caption parsing utilities
from caption_parsers import collect_all_caption_data

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}

# Helpers
def is_image_file(filename):
    return os.path.splitext(filename)[1].lower() in IMAGE_EXTENSIONS

def get_extension(filename):
    return os.path.splitext(filename)[1].lower()

def extract_referenced_images_from_xlsx(filepath):
    referenced_images = set()
    try:
        with zipfile.ZipFile(filepath, "r") as xlsx:
            sheet_file = "xl/worksheets/sheet1.xml"
            shared_strings_file = "xl/sharedStrings.xml"

            # Load shared strings
            shared_strings = []
            if shared_strings_file in xlsx.namelist():
                with xlsx.open(shared_strings_file) as f:
                    tree = ET.parse(f)
                    shared_strings = [
                        t.text for t in tree.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
                    ]

            if sheet_file not in xlsx.namelist():
                return referenced_images

            with xlsx.open(sheet_file) as f:
                tree = ET.parse(f)
                rows = tree.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row")[1:]

                for row in rows:
                    cells = row.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c")
                    if len(cells) < 1:
                        continue

                    cell = cells[0]
                    cell_type = cell.get("t")
                    value_elem = cell.find(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")

                    if value_elem is not None:
                        if cell_type == "s":
                            idx = int(value_elem.text)
                            val = shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
                        else:
                            val = value_elem.text
                        if val:
                            img_name = val.split("#")[0].replace("*MG*", "IMG_").strip()
                            referenced_images.add(img_name)
    except Exception as e:
        print(f"[XLSX] Error reading {filepath}: {e}")
    return referenced_images

def extract_referenced_images_from_csv(filepath):
    referenced_images = set()
    try:
        with open(filepath, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                val = row.get("caption_id", "")
                if val:
                    img_name = val.split("#")[0].strip()
                    referenced_images.add(img_name)
    except Exception as e:
        print(f"[CSV] Error reading {filepath}: {e}")
    return referenced_images

def print_tree_and_count(path, prefix="", output_lines=None, all_images=None):
    try:
        items = sorted(os.listdir(path))
    except PermissionError:
        output_lines.append(prefix + "└── [Permission Denied]")
        return

    image_counter = defaultdict(int)
    other_files = []

    for item in items:
        full_path = os.path.join(path, item)
        if os.path.isdir(full_path):
            connector = "└── " if item == items[-1] else "├── "
            output_lines.append(prefix + connector + item + "/")
            new_prefix = prefix + ("    " if item == items[-1] else "│   ")
            print_tree_and_count(full_path, new_prefix, output_lines, all_images)
        else:
            if is_image_file(item):
                ext = get_extension(item)
                image_counter[ext] += 1
                all_images.add(item)
            else:
                connector = "└── " if item == items[-1] else "├── "
                output_lines.append(prefix + connector + item)

    if image_counter:
        for ext, count in sorted(image_counter.items()):
            output_lines.append(prefix + f"[{ext} files: {count}]")

def generate_tree_and_stats(folder_path, output_filename="directory_tree.md"):
    """Generate a markdown report containing the directory tree and dataset-level image/caption statistics.

    Enhancements:
    - Uses the caption parsers to extract captions for each dataset found under `folder_path`.
    - Computes per-dataset: images on disk, images referenced in captions, referenced & found, referenced but missing, unused images, and caption-count distribution (min/median/avg/max).
    - Adds top images by number of captions for quick inspection.
    """
    if not os.path.isdir(folder_path):
        print(f"Invalid folder path: {folder_path}")
        return

    output_lines = []
    output_lines.append(f"# 📁 Directory Tree of `{os.path.basename(folder_path)}`\n")
    output_lines.append(os.path.basename(folder_path) + "/")

    # Gather a global set of images on disk (basenames)
    all_images_on_disk = set()
    print_tree_and_count(folder_path, "", output_lines, all_images_on_disk)

    # Per-dataset caption statistics (treat each top-level subdirectory as a dataset)
    output_lines.append("\n---")
    output_lines.append("## 🔢 Dataset caption statistics by top-level folder")

    for item in sorted(os.listdir(folder_path)):
        dataset_path = os.path.join(folder_path, item)
        if not os.path.isdir(dataset_path):
            continue

        # Images on disk for this dataset (basenames)
        images_in_dataset = set()
        for root, _, files in os.walk(dataset_path):
            for f in files:
                if is_image_file(f):
                    images_in_dataset.add(f)

        # Collect referenced captions (all rows) and validated captions (image exists)
        try:
            captions_all = collect_all_caption_data(dataset_path, validate_images=False)
            captions_valid = collect_all_caption_data(dataset_path, validate_images=True)
        except Exception as e:
            print(f"Error parsing captions for {dataset_path}: {e}")
            captions_all = {}
            captions_valid = {}

        # Normalize captions by basename and count captions per image
        captions_count_all = {os.path.basename(k): len(v) for k, v in captions_all.items()}
        captions_count_valid = {os.path.basename(k): len(v) for k, v in captions_valid.items()}

        total_images_disk = len(images_in_dataset)
        total_images_referenced = len(captions_count_all)  # referenced rows in files
        validated_images_referenced = len(captions_count_valid)  # those with image present

        referenced_found_in_dataset = set(captions_count_all.keys()) & images_in_dataset
        validated_found_in_dataset = set(captions_count_valid.keys()) & images_in_dataset

        referenced_missing = set(captions_count_all.keys()) - images_in_dataset
        validated_missing = set(captions_count_valid.keys()) - images_in_dataset

        # Also check whether validated images exist elsewhere in the scanned tree
        validated_found_global = set(captions_count_valid.keys()) & all_images_on_disk
        validated_found_elsewhere = validated_found_global - images_in_dataset

        unused_images = images_in_dataset - set(captions_count_all.keys())

        # Use validated counts to compute caption-count statistics
        counts = list(captions_count_valid.values())
        if counts:
            avg = sum(counts) / len(counts)
            med = statistics.median(counts)
            mn = min(counts)
            mx = max(counts)
        else:
            avg = med = mn = mx = 0

        output_lines.append(f"\n### {item}/")
        output_lines.append(f"Images on disk: {total_images_disk}")
        output_lines.append(f"Images referenced in caption files: {total_images_referenced}")
        output_lines.append(f"Images referenced with existing file (validated): {validated_images_referenced}")
        output_lines.append(f"Referenced & found in this dataset: {len(referenced_found_in_dataset)}")
        output_lines.append(f"Validated & found in this dataset: {len(validated_found_in_dataset)}")
        output_lines.append(f"Validated & found elsewhere in tree: {len(validated_found_elsewhere)}")
        output_lines.append(f"Referenced but missing in this dataset: {len(referenced_missing)}")
        output_lines.append(f"Validated but missing in this dataset: {len(validated_missing)}")
        output_lines.append(f"Unused images (not referenced): {len(unused_images)}")
        output_lines.append(
            f"Caption counts per image (min/median/avg/max) [VALIDATED]: {mn}/{med}/{avg:.2f}/{mx}"
        )

        # Top images by validated caption count
        if captions_count_valid:
            top_images = sorted(captions_count_valid.items(), key=lambda x: -x[1])[:10]
            output_lines.append("Top images by caption count (validated):")
            for name, cnt in top_images:
                status = " (found)" if name in images_in_dataset else " (missing)"
                output_lines.append(f" - {name}: {cnt}{status}")

    # Now compute overall statistics using the caption parsers across the whole folder
    try:
        all_captions_map = collect_all_caption_data(folder_path, validate_images=False)
        validated_all_captions_map = collect_all_caption_data(folder_path, validate_images=True)
    except Exception as e:
        print(f"Error parsing captions for {folder_path}: {e}")
        all_captions_map = {}
        validated_all_captions_map = {}

    normalized_images = {os.path.basename(img) for img in all_images_on_disk}
    normalized_caption_images = {os.path.basename(k) for k in all_captions_map.keys()}
    validated_caption_images = {os.path.basename(k) for k in validated_all_captions_map.keys()}

    referenced_found = normalized_caption_images & normalized_images
    referenced_missing = normalized_caption_images - normalized_images
    validated_found = validated_caption_images & normalized_images
    validated_missing = validated_caption_images - normalized_images
    unused_images = normalized_images - normalized_caption_images

    output_lines.append("\n---")
    output_lines.append(f"📷 Total images found on disk: {len(normalized_images)}")
    output_lines.append(f"📝 Total images referenced in captions (any row): {len(normalized_caption_images)}")
    output_lines.append(f"📝 Total referenced and validated (image exists): {len(validated_caption_images)}")
    output_lines.append(f"✅ Referenced & found: {len(referenced_found)}")
    output_lines.append(f"✅ Validated & found: {len(validated_found)}")
    output_lines.append(f"❌ Referenced but missing: {len(referenced_missing)}")
    output_lines.append(f"❌ Validated but missing: {len(validated_missing)}")
    output_lines.append(f"📦 Unused images (not referenced): {len(unused_images)}")
    output_lines.append("---")

    # Save report
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"\n✅ Directory tree and stats saved to `{output_filename}`")


# === Example usage ===
folder_path = input("Enter the folder path to scan: ").strip()
generate_tree_and_stats(folder_path)
