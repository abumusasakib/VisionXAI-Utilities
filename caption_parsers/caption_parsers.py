# ### Abstract Base Class for Caption Parsers

# The `CaptionParser` defines the interface for any class that extracts image-caption mappings from a data file.

import csv
import json
import zipfile
import xml.etree.ElementTree as ET
import os
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from abc import ABC, abstractmethod

# Attempt to import cElementTree for faster XML parsing, fall back to ElementTree
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET


class CaptionParser(ABC):
    """
    Abstract Base Class for caption parsers.

    Defines the common interface for extracting image-caption mappings
    from different file formats (e.g., XLSX, CSV).
    """

    @abstractmethod
    def extract(
        self, file_path: str, images_path: str, validate_images: bool
    ) -> Dict[str, List[str]]:
        """
        Abstract method to extract image-caption mappings from a given file.

        Args:
            file_path (str): The path to the data file (e.g., .xlsx, .csv).
            images_path (str): The base directory where image files are located.
            validate_images (bool): If True, checks if the image file exists on disk
                                    before including its captions in the output.

        Returns:
            Dict[str, List[str]]: A dictionary where keys are absolute image paths
                                  and values are lists of formatted captions.
        """
        pass


# ### XLSX Caption Parser

# The `XLSXCaptionParser` class is responsible for extracting image and caption data from XLSX files. It handles the specific structure of Excel XML files, including shared strings and custom image name formats. It uses cElementTree if available and includes refined print-based progress indicators during row parsing.


class XLSXCaptionParser(CaptionParser):
    """
    A concrete implementation of CaptionParser for XLSX files.

    It expects image names in the first column and captions in the second.
    Can handle files with or without a header row.
    Includes print-based progress indicators for row parsing.
    """

    def __init__(self, has_header: bool = True):
        """
        Initializes the XLSXCaptionParser.

        Args:
            has_header (bool, optional): Specifies if the XLSX file has a header row.
                                         If True, the first row is skipped during parsing. Defaults to True.
        """
        self.has_header = has_header

    def extract(
        self, xlsx_file: str, images_path: str = "", validate_images: bool = False
    ) -> Dict[str, List[str]]:
        """
        Extracts image names and captions from an XLSX file.

        Args:
            xlsx_file (str): The path to the XLSX file.
            images_path (str, optional): Base directory where images are expected.
                                         If provided, image paths will be joined with this. Defaults to "".
            validate_images (bool, optional): If True, checks if the image file exists on disk.
                                              Only adds entries for existing images. Defaults to False.

        Returns:
            Dict[str, List[str]]: A dictionary where keys are image paths and values are lists of captions.
        """
        caption_mapping: Dict[str, List[str]] = {}
        try:
            with zipfile.ZipFile(xlsx_file, "r") as xlsx:
                sheet_file = "xl/worksheets/sheet1.xml"
                shared_strings_file = "xl/sharedStrings.xml"

                # Define the namespace for OpenXML SpreadsheetML to correctly find elements.
                ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

                # Load shared strings; text content in XLSX is often stored in a shared strings table.
                shared_strings: List[str] = []
                if shared_strings_file in xlsx.namelist():
                    with xlsx.open(shared_strings_file) as f:
                        tree = ET.parse(f)
                        shared_strings = [
                            t.text
                            for t in tree.findall(
                                f".//{ns}t"
                            )  # Find all 't' (text) elements within the namespace.
                            if t.text is not None
                        ]

                # If the main worksheet XML isn't found, return an empty mapping.
                if sheet_file not in xlsx.namelist():
                    print(f"Warning: Worksheet '{sheet_file}' not found in {xlsx_file}")
                    return caption_mapping

                with xlsx.open(sheet_file) as f:
                    tree = ET.parse(f)
                    rows = tree.findall(
                        f".//{ns}row"
                    )  # Find all 'row' elements within the namespace.
                    # Determine the starting row based on whether a header is present.
                    start_row = 1 if self.has_header and len(rows) > 0 else 0
                    total_rows = len(
                        rows[start_row:]
                    )  # Calculate total rows to process.

                    print(
                        f"\n➡️  Parsing {os.path.basename(xlsx_file)} ({total_rows} rows)..."
                    )

                    for idx, row in enumerate(rows[start_row:], start=1):
                        # Print progress every 500 rows or at the last row, using carriage return for single line.
                        if idx % 500 == 0 or idx == total_rows:
                            print(
                                f"\r  → Row {idx}/{total_rows}...", end="", flush=True
                            )

                        # Filter for 'c' (cell) elements within the row, ensuring correct tag matching.
                        cells = [el for el in row if el.tag.endswith("c")]
                        if (
                            len(cells) < 2
                        ):  # Ensure there are at least two columns (image name and caption).
                            continue

                        def get_cell_value(cell: ET.Element) -> Optional[str]:
                            """Helper function to extract cell value, handling shared strings."""
                            cell_type = cell.get("t")  # 's' indicates shared string.
                            # Efficiently find the 'v' (value) element among cell children.
                            value_elem = next(
                                (v for v in cell if v.tag.endswith("v")), None
                            )
                            if value_elem is not None and value_elem.text:
                                if cell_type == "s":
                                    try:
                                        idx = int(value_elem.text)
                                        return (
                                            shared_strings[idx]
                                            if 0 <= idx < len(shared_strings)
                                            else None
                                        )
                                    except (ValueError, IndexError):
                                        return None
                                return value_elem.text
                            return None

                        # Extract values from the first two cells (columns).
                        img_name_val = get_cell_value(cells[0])
                        caption_val = get_cell_value(cells[1])

                        if img_name_val:
                            # Clean and normalize image name (remove #index, replace *MG*).
                            if "#" in img_name_val:
                                img_name_val = img_name_val.split("#")[0]
                            img_name_val = img_name_val.replace("*MG*", "IMG_")
                            # Construct full image path.
                            img_path = (
                                os.path.join(images_path, img_name_val)
                                if images_path
                                else img_name_val
                            )

                            # Check for image existence only if validation is requested.
                            if not validate_images or Path(img_path).exists():
                                if caption_val:
                                    # Format caption with start/end tokens.
                                    formatted_caption = (
                                        f"{caption_val.strip()}"
                                    )
                                    # Add caption to the list for the corresponding image path.
                                    caption_mapping.setdefault(img_path, []).append(
                                        formatted_caption
                                    )

        except zipfile.BadZipFile:
            print(f"\nError: {xlsx_file} is not a valid zip file.")
        except Exception as e:
            print(f"\nAn error occurred while processing {xlsx_file}: {e}")

        return caption_mapping


# ### CSV Caption Parser

# The `CSVCaptionParser` class handles the extraction of image and caption data from CSV files. It specifically looks for "caption\_id" and "bengali\_caption" columns and includes detailed print-based progress indicators as well.


class CSVCaptionParser(CaptionParser):
    """
    A concrete implementation of CaptionParser for CSV files.

    It expects image names in a column named "caption_id" and
    captions in a column named "bengali_caption".
    Includes print-based progress indicators for row parsing.
    """

    def extract(
        self, csv_file_path: str, images_path: str = "", validate_images: bool = True
    ) -> Dict[str, List[str]]:
        """
        Extracts image names and captions from a CSV file.

        Args:
            csv_file_path (str): The path to the CSV file.
            images_path (str, optional): Base directory where images are expected.
                                         If provided, image paths will be joined with this. Defaults to "".
            validate_images (bool, optional): If True, checks if the image file exists on disk.
                                              Only adds entries for existing images. Defaults to True.

        Returns:
            Dict[str, List[str]]: A dictionary where keys are image paths and values are lists of captions.
        """
        caption_mapping: Dict[str, List[str]] = {}
        try:
            with open(csv_file_path, newline="", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)  # Reads CSV into dictionary rows.

                # Reading all rows into a list to get total count. For very large CSVs,
                # this might be memory intensive. An alternative is to count lines first.
                rows = list(reader)  # Load all rows into memory to get total count.
                total_rows = len(rows)

                csv_dir = os.path.dirname(os.path.abspath(csv_file_path))
                print(
                    f"\n➡️  Parsing {os.path.basename(csv_file_path)} (folder: {csv_dir}, {total_rows} rows)..."
                )
                processed_rows_count = 0  # Counter for successfully processed rows
                for idx, row in enumerate(rows, start=1):
                    # Print progress every 10,000 rows or at the last row, using carriage return.
                    if idx % 10000 == 0 or idx == total_rows:
                        print(f"\r  → Row {idx}/{total_rows}...", end="", flush=True)

                    img_name = row.get("caption_id")
                    caption_bn = row.get("bengali_caption")

                    if img_name and caption_bn:
                        # Remove any '#index' suffix from the image name.
                        if "#" in img_name:
                            img_name = img_name.split("#")[0]
                        # Construct full image path.
                        img_path = (
                            os.path.join(images_path, img_name)
                            if images_path
                            else img_name
                        )

                        if validate_images and not Path(img_path).exists():
                            continue  # Skip if image validation is on and file not found.

                        # Add caption to the list for the corresponding image path.
                        # Ensure caption_bn is a string before strip()
                        caption_mapping.setdefault(img_path, []).append(
                            f"{str(caption_bn).strip()}"
                        )
                        processed_rows_count += 1  # Increment counter for valid entries
            # Final update for the progress line after the loop
            print(
                f"\r  → Finished parsing {os.path.basename(csv_file_path)}. Total valid entries: {processed_rows_count}.",
                flush=True,
            )
        except FileNotFoundError:
            print(f"Error: CSV file not found at {csv_file_path}")
        except Exception as e:
            # Print newline before error message to avoid overwriting progress line
            print(f"\nAn error occurred while processing {csv_file_path}: {e}")

        return caption_mapping


# ### JSON Caption Parser

# The `JSONCaptionParser` is a concrete implementation designed to parse specific JSON file structures, extracting filenames and their associated captions. It expects a list of objects, each with a 'filename' and a 'caption' (which is itself a list of strings).


class JSONCaptionParser(CaptionParser):
    """
    A concrete implementation of CaptionParser for JSON files.

    This parser expects a JSON file containing a list of objects, where each object
    has a 'filename' key (for the image name) and a 'caption' key (which is a list of captions).
    Example JSON structure:
    [
        {"filename": "image1.jpg", "caption": ["caption for image1", "another caption"]},
        {"filename": "image2.jpg", "caption": ["caption for image2"]}
    ]
    """

    def extract(
        self, file_path: str, images_path: str = "", validate_images: bool = True
    ) -> Dict[str, List[str]]:
        """
        Extracts image filenames and their associated captions from a JSON file.

        Args:
            file_path (str): The full path to the JSON caption file.
            images_path (str, optional): The base directory where images referenced in the JSON
                                         are located. This path is prepended to filenames from the JSON.
                                         Defaults to "".
            validate_images (bool, optional): If True, checks if the image file exists on disk
                                              before adding its captions to the mapping. Defaults to True.

        Returns:
            Dict[str, List[str]]: A dictionary mapping absolute image paths to a list of their captions.
                                  Captions are formatted with leading/trailing spaces.
        """
        caption_mapping: Dict[str, List[str]] = {}
        print(f"\n➡️  Parsing JSON: {os.path.basename(file_path)}...")
        try:
            with open(file_path, encoding="utf8") as caption_file:
                caption_data = json.load(caption_file)

                # Ensure caption_data is iterable (e.g., a list of dictionaries)
                if not isinstance(caption_data, list):
                    print(
                        f"Warning: JSON file {file_path} does not contain a list at its root. Skipping."
                    )
                    return caption_mapping

                for idx, item in enumerate(caption_data):
                    if idx % 1000 == 0:
                        print(
                            f"\r  → Processing JSON item {idx}...", end="", flush=True
                        )

                    if (
                        not isinstance(item, dict)
                        or "filename" not in item
                        or "caption" not in item
                    ):
                        print(
                            f"Warning: Skipping malformed JSON item in {file_path}: {item}"
                        )
                        continue

                    # Construct the full image path
                    img_name_from_json = item["filename"].strip()
                    img_name_abs = os.path.join(images_path, img_name_from_json)

                    # Ensure captions is a list, even if it's a single string
                    raw_captions = item["caption"]
                    if not isinstance(raw_captions, list):
                        raw_captions = [raw_captions]  # Convert single string to list

                    # Format captions
                    formatted_captions = [
                        str(caption).strip() + " "
                        for caption in raw_captions
                        if caption is not None
                    ]

                    # Validate image existence if required
                    if not validate_images or Path(img_name_abs).exists():
                        if formatted_captions:  # Only add if there are valid captions
                            caption_mapping[img_name_abs] = formatted_captions
                    else:
                        # print(f"Warning: Image not found for {img_name_abs}. Skipping.")
                        pass  # Suppress warning for missing images during non-validation pass

            print(
                f"\r  → Finished parsing {os.path.basename(file_path)}. Total valid entries: {len(caption_mapping)}.",
                flush=True,
            )

        except json.JSONDecodeError as e:
            print(f"\nError: Invalid JSON format in {file_path}: {e}")
        except Exception as e:
            print(f"\nError reading JSON file {file_path}: {e}")

        return caption_mapping


# ### TXT Caption Parser

class TXTCaptionParser(CaptionParser):
    """
    Parser for TXT caption files.
    Supports common formats like hash-separated and triple-space separated lines.
    """

    def extract(
        self, file_path: str, images_path: str = "", validate_images: bool = True
    ) -> Dict[str, List[str]]:
        caption_mapping: Dict[str, List[str]] = {}
        print(f"\n➡️  Parsing TXT: {os.path.basename(file_path)}...")

        try:
            with open(file_path, "r", encoding="utf-8") as file:
                for line_num, line in enumerate(file, start=1):
                    line = line.strip()
                    if not line:
                        continue

                    # Detect delimiter automatically
                    if "   " in line:
                        parts = line.split("   ", 1)
                    elif " #" in line:
                        parts = line.split(" #", 1)
                    elif "#" in line:
                        parts = line.split("#", 1)
                    else:
                        continue

                    if len(parts) < 2:
                        continue

                    img_name = parts[0].strip()
                    caption = parts[1].strip()

                    if not img_name or not caption:
                        continue

                    img_path_abs = os.path.join(images_path, img_name)

                    if not validate_images or Path(img_path_abs).exists():
                        caption_mapping.setdefault(img_path_abs, []).append(caption)

                    if line_num % 1000 == 0:
                        print(f"\r  → Processed {line_num} lines...", end="", flush=True)

            print(f"\r  → Finished parsing {os.path.basename(file_path)}. Total valid entries: {len(caption_mapping)}.", flush=True)

        except FileNotFoundError:
            print(f"❌ File not found: {file_path}")
        except Exception as e:
            print(f"⚠️ Error reading TXT file {file_path}: {e}")

        return caption_mapping


# ### Data Collector

# The `collect_all_caption_data` function orchestrates the process of finding and parsing caption files across a given directory structure. It intelligently determines the correct parser and image directory for different file types.


def collect_all_caption_data(
    base_dir: str, validate_images: bool = True
) -> Dict[str, List[str]]:
    """
    Walks through a base directory to find and extract caption data from XLSX and CSV files.
    It identifies different types of caption files based on their names and extensions
    and uses the appropriate parser.

    Args:
        base_dir (str): The root directory to start searching for files.
        validate_images (bool, optional): If True, validates image paths during extraction. Defaults to True.

    Returns:
        Dict[str, List[str]]: A consolidated dictionary of all found image-caption mappings.
    """
    all_captions: Dict[str, List[str]] = {}
    xlsx_parser = XLSXCaptionParser(has_header=True)
    csv_parser = CSVCaptionParser()
    banglaview_xlsx_parser = XLSXCaptionParser(
        has_header=False
    )  # BanglaView has no header
    json_parser = JSONCaptionParser()
    txt_parser = TXTCaptionParser()

    # Walk through the directory tree.
    print(f"🔍 Scanning directories in {base_dir}...")
    for root, dirs, files in os.walk(base_dir):
        # Indicate current directory being scanned.
        # This can be noisy for deep hierarchies, consider removing for very large datasets.
        # print(f"  📂 In directory: {root}")

        for file in files:
            lower_file = file.lower()
            file_path = os.path.join(root, file)
            captions: Dict[str, List[str]] = {}
            img_dir: str = ""

            # --- BNATURE: 'test.txt' lists test images; captions live in 'caption/caption.txt'; images in 'Pictures/' ---
            if lower_file == "test.txt":
                bnature_caption_dir = os.path.dirname(file_path)
                bnature_root = os.path.normpath(os.path.join(bnature_caption_dir, ".."))
                pictures_dir = os.path.join(bnature_root, "Pictures")
                captions_file = os.path.join(bnature_caption_dir, "caption.txt")

                test_image_names: List[str] = []
                try:
                    with open(file_path, "r", encoding="utf-8") as tf:
                        for ln in tf:
                            ln = ln.strip()
                            if ln:
                                test_image_names.append(ln)
                except Exception:
                    test_image_names = []

                cap_map: Dict[str, List[str]] = {}
                if os.path.exists(captions_file):
                    try:
                        with open(captions_file, "r", encoding="utf-8") as cf:
                            for ln in cf:
                                ln = ln.strip()
                                if not ln:
                                    continue
                                # support multiple delimiters used in this dataset
                                if "   " in ln:
                                    imgname, cap = ln.split("   ", 1)
                                elif " #" in ln:
                                    imgname, cap = ln.split(" #", 1)
                                elif "#" in ln:
                                    imgname, cap = ln.split("#", 1)
                                else:
                                    parts = ln.split(None, 1)
                                    if len(parts) < 2:
                                        continue
                                    imgname, cap = parts[0], parts[1]
                                imgname = imgname.strip()
                                cap = cap.strip()
                                if imgname and cap:
                                    cap_map.setdefault(imgname, []).append(cap)
                    except Exception:
                        pass

                for imgname in test_image_names:
                    caps = cap_map.get(imgname, [])
                    if not caps:
                        continue
                    img_path = os.path.join(pictures_dir, imgname)
                    if (not validate_images) or os.path.exists(img_path):
                        captions[os.path.abspath(img_path)] = caps

            # --- BNLIT: test-annotation files containing ground-truth captions ---
            elif ("test-annotation" in lower_file and "bnlit" in lower_file) or lower_file.startswith(
                "test-annotation-bangla natural language image to text"
            ):
                bnlit_root = os.path.dirname(file_path)
                resized_folder = "Bangla Natural Language Image to Text (BNLIT)-Preprocessing and Resizing Dataset-resized-500_375"
                images_dir = os.path.join(bnlit_root, resized_folder)
                if not os.path.isdir(images_dir):
                    if os.path.isdir(bnlit_root):
                        images_dir = bnlit_root
                    else:
                        images_dir = os.path.normpath(os.path.join(bnlit_root, ".."))

                try:
                    with open(file_path, "r", encoding="utf-8") as af:
                        for ln in af:
                            ln = ln.strip()
                            if not ln:
                                continue
                            if " #" in ln:
                                imgname, cap = ln.split(" #", 1)
                            elif "#" in ln:
                                imgname, cap = ln.split("#", 1)
                            else:
                                parts = ln.split(None, 1)
                                if len(parts) < 2:
                                    continue
                                imgname, cap = parts[0], parts[1]
                            imgname = imgname.strip()
                            cap = cap.strip()
                            img_path = os.path.join(images_dir, imgname)
                            if (not validate_images) or os.path.exists(img_path):
                                captions.setdefault(os.path.abspath(img_path), []).append(cap)
                except Exception:
                    pass

            # --- Generic TXT file parsing (skip huge train/val/caption lists) ---
            elif lower_file.endswith(".txt"):
                if any(skip_word in lower_file for skip_word in ["train", "validation", "val", "caption"]):
                    continue
                captions = txt_parser.extract(file_path, images_path=root, validate_images=validate_images)

            # Process general XLSX files containing "captioning" in their name.
            elif lower_file.endswith(".xlsx") and "captioning" in lower_file:
                # Check if this file is part of the custom category-organized dataset ('image_captioning_dataset')
                # vs the standard 'Bangla Image Captioning' dataset.
                if "image_captioning_dataset" in root:
                    # Custom dataset: check for 'image' or 'images' subfolder first (flattened),
                    # otherwise fallback to root (images stored directly alongside captioning.xlsx in each sub-category folder)
                    img_dir = os.path.join(root, "image")
                    if not os.path.exists(img_dir):
                        img_dir = os.path.join(root, "images")
                        if not os.path.exists(img_dir):
                            img_dir = root
                else:
                    # Standard Bangla Image Captioning: check for 'image' subfolder or fallback to root
                    img_dir = os.path.join(root, "image")
                    if not os.path.exists(img_dir):
                        img_dir = os.path.join(root, "images")
                        if not os.path.exists(img_dir):
                            img_dir = root

                # print(f"Parsing XLSX: {file_path}") # This print is inside the parser's extract method
                captions = xlsx_parser.extract(
                    file_path, images_path=img_dir, validate_images=validate_images
                )




            # Process CSV files containing "ban-cap" in their name.
            elif lower_file.endswith(".csv") and "ban-cap" in lower_file:
                # BAN-Cap references images stored in the Flickr 8k Dataset folder which
                # may be a sibling of the dataset folder being scanned. Search upward for it.
                candidate = os.path.join(base_dir, "Flickr 8k Dataset", "Images")
                img_dir = None
                if os.path.exists(candidate):
                    img_dir = candidate
                else:
                    parent = os.path.abspath(base_dir)
                    # Walk up ancestors to look for a sibling 'Flickr 8k Dataset/Images'.
                    while True:
                        new_parent = os.path.dirname(parent)
                        if not new_parent or new_parent == parent:
                            break
                        parent = new_parent
                        candidate = os.path.join(parent, "Flickr 8k Dataset", "Images")
                        if os.path.exists(candidate):
                            img_dir = candidate
                            break
                if img_dir is None:
                    img_dir = base_dir  # Final fallback
                # print(f"Parsing CSV: {file_path}") # This print is inside the parser's extract method
                captions = csv_parser.extract(
                    file_path, images_path=img_dir, validate_images=validate_images
                )

            # Process the specific "banglaview_dataset.xlsx" file.
            elif lower_file == "banglaview_dataset.xlsx":
                # Specific image directory structure for BanglaView.
                img_dir = os.path.join(base_dir, "flickr30k_images", "flickr30k_images")
                if not os.path.exists(img_dir):
                    print(
                        f"Warning: BanglaView image directory not found at {img_dir}. Skipping."
                    )
                    continue
                # print(f"Parsing BanglaView XLSX: {file_path}") # This print is inside the parser's extract method
                # BanglaView XLSX is known to have no header.
                captions = banglaview_xlsx_parser.extract(
                    file_path, images_path=img_dir, validate_images=validate_images
                )
            # Process the BanglaLekhaImageCaptions dataset.
            elif lower_file.endswith(".json") and "captions" in lower_file:
                # First check 'images' subdirectory relative to current file's root
                img_dir = os.path.join(root, "images")
                if not os.path.exists(img_dir):
                    # Fallback to a specific path relative to base_dir if not found locally
                    img_dir = os.path.join(base_dir, "rxxch9vw59.2", "images")
                captions = json_parser.extract(
                    file_path, images_path=img_dir, validate_images=validate_images
                )
            else:
                continue  # Skip files that don't match any known caption format.

            if captions:
                all_captions.update(
                    captions
                )  # Merge new captions into the main dictionary.

    return all_captions
