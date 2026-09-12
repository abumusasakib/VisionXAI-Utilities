# VisionXAI Utilities

This repository contains a collection of Python utilities designed to assist with various data processing and management tasks for computer vision and AI projects. Each utility is organized in its own directory for clarity and modularity.

## Utilities Overview

### 1. clipboard_whitespace_clean

- **Directory:** `clipboard_whitespace_clean/`
- **File:** `clipboard_clean.py`
- **Description:**
  - Cleans up whitespace from clipboard contents. Useful for quickly sanitizing copied text data.

### 2. dataset_directory_tree

- **Directory:** `dataset_directory_tree/`
- **File:** `dataset_directory_tree.py`
- **Description:**
  - Parses datasets and provides tools for organizing, analyzing, and visualizing dataset directory structures.
- **Additional:**
  - `directory_tree.md`: Documentation or visualization of the dataset directory structure.

### 3. caption_parsers

- **Directory:** `caption_parsers/`
- **File:** `caption_parsers.py`, `__init__.py`
- **Description:**
  - Dedicated modular package providing object-oriented caption parsers (`XLSXCaptionParser`, `CSVCaptionParser`, `JSONCaptionParser`, `TXTCaptionParser`) and dataset walker (`collect_all_caption_data`).
  - Used as a dependency by `dataset_directory_tree` and `flatten_dataset`.

### 4. filter_images

- **Directory:** `filter_images/`
- **File:** `filter_images.py`
- **Description:**
  - Filters images in a directory based on specified criteria (e.g., size, format, or custom rules).

### 5. patch_notebook

- **Directory:** `patch_notebook/`
- **File:** `patch_notebook.py`
- **Description:**
  - Universal Jupyter notebook (`.ipynb`) programmatic modification utility and Python module.
  - Supports both general-purpose notebook operations (list, insert, replace, delete, append cells) and project-specific patch recipes (such as the VisionXAI model training patch).

### 5. flatten_dataset

- **Directory:** `flatten_dataset/`
- **File:** `flatten_dataset.py`
- **Description:**
  - Flattens sub-category directory structures (such as `image_captioning_dataset`) into a standardized single-folder structure (`captioning.xlsx` + `image/` directory), matching the format of standard datasets like `Bangla Image Captioning`.
  - Leverages `caption_parsers.py` to extract all captions across nested sub-folders.

---

## Usage

Each utility can be run independently. Navigate to the respective directory and execute the Python script. For example:

```powershell
cd clipboard_whitespace_clean
python clipboard_clean.py
```

### `flatten_dataset` Usage

```powershell
cd flatten_dataset
python flatten_dataset.py -i "D:\path\to\image_captioning_dataset" -o "D:\path\to\image_captioning_dataset_flattened" --mode copy
```

### `patch_notebook` Operations

1. **List cells in any notebook:**

   ```powershell
   python patch_notebook.py list -n "path/to/notebook.ipynb"
   ```

2. **Search cells by snippets:**

   ```powershell
   python patch_notebook.py search -n "path/to/notebook.ipynb" -t "import torch" --mode all
   ```

3. **Show specific cells by index/range:**

   ```powershell
   python patch_notebook.py show -n "path/to/notebook.ipynb" -i "0-5,10"
   ```

4. **List Python function and class definitions:**

   ```powershell
   python patch_notebook.py functions -n "path/to/notebook.ipynb"
   ```

5. **Validate syntax of code cells:**

   ```powershell
   python patch_notebook.py validate -n "path/to/notebook.ipynb"
   ```

6. **Insert a new code or markdown cell:**

   ```powershell
   python patch_notebook.py insert -n "path/to/notebook.ipynb" -t "target snippet" --position after -c "print('hello')" --cell-type code
   ```

7. **Replace cell matching a snippet:**

   ```powershell
   python patch_notebook.py replace -n "path/to/notebook.ipynb" -t "def old_func():" --content-file "new_code.py"
   ```

8. **Replace cell by explicit index:**

   ```powershell
   python patch_notebook.py replace-index -n "path/to/notebook.ipynb" -i 12 --content-file "new_code.py"
   ```

9. **Delete matching cells:**

   ```powershell
   python patch_notebook.py delete -n "path/to/notebook.ipynb" -t "deprecated_code"
   ```

10. **Run VisionXAI patch recipe:**

    ```powershell
    python patch_notebook.py visionxai -n "d:\path\to\bangla_image_caption.ipynb"
    ```

11. **Python Library API Usage:**

    ```python
    from patch_notebook import load_notebook, save_notebook, insert_cell, replace_cell_source, code_cell

    nb = load_notebook("my_notebook.ipynb")
    insert_cell(nb["cells"], code_cell("import tensorflow as tf"), index=0)
    save_notebook(nb, "my_notebook.ipynb")
    ```

Refer to the source code of each script for specific usage instructions and configurable options.

## Requirements

- Recommended Python version: Python 3.8.5+
- Additional dependencies may be required for specific utilities. Please check the script headers or use `pip install -r requirements.txt` within each utility directory if available.

## License

This project is provided for educational and research purposes.
