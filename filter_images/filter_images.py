import zipfile
import xml.etree.ElementTree as ET
import os
import shutil
from pathlib import Path
from PIL import Image

# Define dataset and Excel file paths
dx = "/data/train/Bangla Image Captioning/captioning bangla language/"
IMAGES_PATH = Path(dx) / "image"
XLSX_FILE_PATH = Path(dx) / "captioning.xlsx"

# Define the output folder for unreferenced images
OUTPUT_FOLDER = IMAGES_PATH.parent / "unreferenced_images"
OUTPUT_FOLDER.mkdir(exist_ok=True)  # Ensure output directory exists

# Resolution filter (change as needed)
MIN_WIDTH = 256
MIN_HEIGHT = 256


def extract_xlsx_data(xlsx_file, sheet_index=1):
    """Extracts image filenames referenced in the given XLSX file."""
    caption_mapping = {}
    
    with zipfile.ZipFile(xlsx_file, "r") as xlsx:
        sheet_files = [f for f in xlsx.namelist() if f.startswith("xl/worksheets/sheet") and f.endswith(".xml")]
        shared_strings_file = "xl/sharedStrings.xml"

        # Load shared strings if available
        if shared_strings_file in xlsx.namelist():
            with xlsx.open(shared_strings_file) as f:
                shared_strings_tree = ET.parse(f)
                shared_strings = [elem.text for elem in shared_strings_tree.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")]
        else:
            shared_strings = []

        # Ensure sheet index is valid
        if sheet_index > len(sheet_files) or sheet_index < 1:
            raise ValueError(f"Sheet index {sheet_index} out of range. Available sheets: {len(sheet_files)}")
            
        sheet_file = sheet_files[sheet_index - 1]

        with xlsx.open(sheet_file) as f:
            sheet_tree = ET.parse(f)
            rows = sheet_tree.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row")
            
            for row in rows[1:]:  # Skip header row if it exists
                cells = row.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c")
                if len(cells) < 2:
                    continue  # Skip rows with insufficient cells
                
                img_name_cell = cells[0]
                img_name_val = None

                cell_type = img_name_cell.get('t')
                value_elem = img_name_cell.find(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")

                if value_elem is not None:
                    if cell_type == 's':  # Shared string
                        str_index = int(value_elem.text)
                        img_name_val = shared_strings[str_index] if 0 <= str_index < len(shared_strings) else None
                    else:  # Direct value
                        img_name_val = value_elem.text

                if img_name_val:
                    img_name_val = img_name_val.replace('*MG*', 'IMG_')  # Fix naming inconsistencies
                    caption_mapping[img_name_val] = True  # Store referenced image filenames as keys

    return caption_mapping


def filter_images_by_resolution(images, min_width, min_height):
    """Filters images based on minimum resolution."""
    valid_images = set()
    
    for img_path in images:
        try:
            with Image.open(img_path) as img:
                width, height = img.size
                if width >= min_width and height >= min_height:
                    valid_images.add(img_path.name)
        except Exception as e:
            print(f"Skipping {img_path.name} due to error: {e}")
    
    return valid_images


def main():
    # Step 1: Get all image filenames in the dataset
    all_images_in_dataset = {img for img in IMAGES_PATH.iterdir() if img.is_file()}

    # Step 2: Get referenced image filenames from the Excel sheet
    referenced_images = extract_xlsx_data(XLSX_FILE_PATH)

    # Step 3: Find unreferenced images
    unreferenced_images = {img for img in all_images_in_dataset if img.name not in referenced_images}
    print(f"Total unreferenced images before filtering: {len(unreferenced_images)}")

    # Step 4: Filter images based on resolution
    filtered_images = filter_images_by_resolution(unreferenced_images, MIN_WIDTH, MIN_HEIGHT)
    print(f"Total unreferenced images after resolution filtering: {len(filtered_images)}")

    # Step 5: Copy unreferenced images to the new folder
    for img_name in filtered_images:
        src_path = IMAGES_PATH / img_name
        dest_path = OUTPUT_FOLDER / img_name
        shutil.copy2(src_path, dest_path)

    print(f"Copied {len(filtered_images)} unreferenced images to {OUTPUT_FOLDER}")


if __name__ == "__main__":
    main()
