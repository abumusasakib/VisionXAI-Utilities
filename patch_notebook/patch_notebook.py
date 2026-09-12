"""
patch_notebook.py
General-purpose utility for programmatically querying, modifying, replacing,
inserting, deleting, and appending cells in Jupyter Notebook (.ipynb) files.

Supports both preset patch recipes (e.g. VisionXAI model training patch) and
generic CLI / API operations (find & replace snippet, insert cell, append cell, delete cell, list cells).
"""

import argparse
import ast
import json
import os
import pathlib
import sys
from typing import Any, Dict, List, Optional, Sequence, Union


# ---------------------------------------------------------------------------
# Core Jupyter Notebook Utilities
# ---------------------------------------------------------------------------

def create_cell(cell_type: str, source: Union[str, List[str]], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build a standard Jupyter notebook cell dict."""
    if isinstance(source, str):
        # Format string as list of lines with trailing newline except last if needed
        source_lines = [line + "\n" for line in source.split("\n")]
        if source_lines and source_lines[-1] == "\n":
            source_lines.pop()
        elif source_lines and not source.endswith("\n"):
            source_lines[-1] = source_lines[-1].rstrip("\n")
    else:
        source_lines = source

    cell = {
        "cell_type": cell_type,
        "metadata": metadata or {},
        "source": source_lines,
    }
    if cell_type == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
    return cell


def code_cell(source: Union[str, List[str]], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Helper to build a code cell."""
    return create_cell("code", source, metadata)


def markdown_cell(source: Union[str, List[str]], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Helper to build a markdown cell."""
    return create_cell("markdown", source, metadata)


def load_notebook(path: Union[str, pathlib.Path]) -> Dict[str, Any]:
    """Load a Jupyter notebook JSON structure."""
    path = pathlib.Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Notebook file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_notebook(nb: Dict[str, Any], path: Union[str, pathlib.Path]) -> None:
    """Save a Jupyter notebook JSON structure formatted with 1-space indentation."""
    path = pathlib.Path(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)


def find_cells_by_snippet(cells: List[Dict[str, Any]], snippet: str) -> List[int]:
    """Return indices of all cells whose source contains the target snippet."""
    matches = []
    for i, cell in enumerate(cells):
        src = "".join(cell.get("source", []))
        if snippet in src:
            matches.append(i)
    return matches


def find_cell_by_snippet(cells: List[Dict[str, Any]], snippet: str) -> int:
    """Return index of the first cell whose source contains the target snippet, or -1 if not found."""
    matches = find_cells_by_snippet(cells, snippet)
    return matches[0] if matches else -1


# ---------------------------------------------------------------------------
# Generic Cell Manipulation Operations
# ---------------------------------------------------------------------------

def replace_cell_source(
    cells: List[Dict[str, Any]],
    target_snippet: str,
    new_source: Union[str, List[str]],
    cell_type: Optional[str] = None
) -> int:
    """Replace source of first cell matching snippet. Returns line index replaced."""
    idx = find_cell_by_snippet(cells, target_snippet)
    if idx == -1:
        raise ValueError(f"Snippet not found in any cell: {target_snippet!r}")
    
    if cell_type:
        cells[idx]["cell_type"] = cell_type
        if cell_type == "code" and "outputs" not in cells[idx]:
            cells[idx]["outputs"] = []
            cells[idx]["execution_count"] = None
    
    new_cell = create_cell(cells[idx]["cell_type"], new_source, cells[idx].get("metadata"))
    cells[idx] = new_cell
    return idx


def insert_cell(
    cells: List[Dict[str, Any]],
    cell: Dict[str, Any],
    target_snippet: Optional[str] = None,
    position: str = "after",
    index: Optional[int] = None
) -> int:
    """
    Insert cell relative to target_snippet (position="before" or "after") or at explicit index.
    Returns index where cell was inserted.
    """
    if index is not None:
        insert_idx = max(0, min(index, len(cells)))
    elif target_snippet is not None:
        found_idx = find_cell_by_snippet(cells, target_snippet)
        if found_idx == -1:
            raise ValueError(f"Target snippet for insertion not found: {target_snippet!r}")
        insert_idx = found_idx + 1 if position == "after" else found_idx
    else:
        insert_idx = len(cells)  # Default append

    cells.insert(insert_idx, cell)
    return insert_idx


def delete_cells_by_snippet(cells: List[Dict[str, Any]], snippet: str) -> int:
    """Delete all cells matching snippet. Returns count of deleted cells."""
    indices = find_cells_by_snippet(cells, snippet)
    for idx in reversed(indices):
        cells.pop(idx)
    return len(indices)


def cell_source(cell: Dict[str, Any]) -> str:
    """Return a cell's source as one string."""
    return "".join(cell.get("source", []))


def safe_text(text: str, ascii_only: bool = False) -> str:
    """Return printable text, optionally replacing non-ASCII characters."""
    if not ascii_only:
        return text
    return text.encode("ascii", errors="replace").decode("ascii")


def parse_index_list(value: str) -> List[int]:
    """
    Parse comma-separated cell indices and ranges.

    Examples:
        "69,75,78"
        "69-80"
        "69,75-80"
    """
    indices = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            if end < start:
                start, end = end, start
            indices.update(range(start, end + 1))
        else:
            indices.add(int(part))
    return sorted(indices)


def find_cells_by_snippets(
    cells: List[Dict[str, Any]],
    snippets: Sequence[str],
    match_mode: str = "any",
    cell_type: Optional[str] = None,
    case_sensitive: bool = True,
) -> List[int]:
    """Find cell indices matching any/all snippets, optionally filtered by cell type."""
    if not snippets:
        return []
    needles = list(snippets)
    if not case_sensitive:
        needles = [s.lower() for s in needles]

    matches = []
    for idx, cell in enumerate(cells):
        if cell_type and cell.get("cell_type") != cell_type:
            continue
        src = cell_source(cell)
        haystack = src if case_sensitive else src.lower()
        checks = [needle in haystack for needle in needles]
        if (match_mode == "all" and all(checks)) or (match_mode == "any" and any(checks)):
            matches.append(idx)
    return matches


def print_cell(
    idx: int,
    cell: Dict[str, Any],
    ascii_only: bool = False,
    max_chars: Optional[int] = None,
    line_numbers: bool = False,
) -> None:
    """Print a notebook cell in a readable diagnostic format."""
    src = cell_source(cell)
    if max_chars is not None:
        src = src[:max_chars]
    src = safe_text(src, ascii_only=ascii_only)
    print(f"=== Cell {idx} ({cell.get('cell_type', 'unknown')}) ===")
    if line_numbers:
        for line_no, line in enumerate(src.splitlines(), start=1):
            print(f"{line_no:03}: {line}")
    else:
        print(src)
    print("=" * 40)


def show_cells(
    cells: List[Dict[str, Any]],
    indices: Sequence[int],
    ascii_only: bool = False,
    max_chars: Optional[int] = None,
    line_numbers: bool = False,
) -> None:
    """Print selected notebook cells by index."""
    for idx in indices:
        if idx < 0 or idx >= len(cells):
            print(f"⚠️  Skipping out-of-range cell index: {idx}")
            continue
        print_cell(idx, cells[idx], ascii_only=ascii_only, max_chars=max_chars, line_numbers=line_numbers)


def list_function_definitions(cells: List[Dict[str, Any]], ascii_only: bool = False) -> List[Dict[str, Any]]:
    """Return and print Python function/class definitions found in code cells."""
    found = []
    for idx, cell in enumerate(cells):
        if cell.get("cell_type") != "code":
            continue
        src = cell_source(cell)
        definitions = []
        for line_no, line in enumerate(src.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith(("def ", "async def ", "class ")):
                definitions.append((line_no, stripped))
        if definitions:
            found.append({"cell": idx, "definitions": definitions})
            print(f"Cell {idx}:")
            for line_no, definition in definitions:
                print(f"  L{line_no}: {safe_text(definition, ascii_only=ascii_only)}")
    return found


def compile_code_cells(cells: List[Dict[str, Any]], allow_magics: bool = True) -> List[Dict[str, Any]]:
    """
    Parse every code cell with ast.parse and return syntax errors.

    Jupyter magic-only cells can be skipped with allow_magics=True.
    """
    errors = []
    for idx, cell in enumerate(cells):
        if cell.get("cell_type") != "code":
            continue
        src = cell_source(cell)
        stripped = src.lstrip()
        if allow_magics and (stripped.startswith("%") or stripped.startswith("!")):
            continue
        try:
            ast.parse(src)
        except SyntaxError as exc:
            line = ""
            lines = src.splitlines()
            if exc.lineno and 1 <= exc.lineno <= len(lines):
                line = lines[exc.lineno - 1]
            errors.append({
                "cell": idx,
                "line": exc.lineno,
                "offset": exc.offset,
                "message": exc.msg,
                "source_line": line,
            })
    return errors


def replace_cell_at_index(
    cells: List[Dict[str, Any]],
    index: int,
    new_source: Union[str, List[str]],
    cell_type: Optional[str] = None,
) -> int:
    """Replace a cell by explicit index. Returns the replaced index."""
    if index < 0 or index >= len(cells):
        raise IndexError(f"Cell index out of range: {index}")
    target_type = cell_type or cells[index].get("cell_type", "code")
    cells[index] = create_cell(target_type, new_source, cells[index].get("metadata"))
    return index


# ---------------------------------------------------------------------------
# VisionXAI Model Training Patch Recipe (Preset)
# ---------------------------------------------------------------------------

LAYERNORM_MARKDOWN = markdown_cell([
    "### CNN Encoder — Formal Architecture\n",
    "\n",
    "Implements the formal spec from `model_architecture.tex`:\n",
    "\n",
    "$$\\mathbf{F} = \\text{LayerNorm}(\\text{ReLU}(W_{\\text{enc}} \\cdot \\mathbf{X} + b_{\\text{enc}}))$$\n",
    "\n",
    "- Input:  $\\mathbf{X} \\in \\mathbb{R}^{B \\times K \\times 2048}$ — InceptionV3 spatial features ($K=64$ ROIs)\n",
    "- Output: $\\mathbf{F} \\in \\mathbb{R}^{B \\times K \\times d'}$ — projected ROI embeddings ($d'=256$)\n",
    "\n",
    "**LayerNorm toggle**: Set `USE_LAYER_NORM = True` (formal spec default). "
    "If LayerNorm hurts convergence, switch to `False` and retrain to compare validation loss.",
])

CNN_ENCODER_CELL = code_cell([
    "# ── LayerNorm toggle for CNN_Encoder ──────────────────────────────────────\n",
    "# True  = matches formal spec: F = LayerNorm(ReLU(W·X + b))  [recommended]\n",
    "# False = original code (ReLU only); switch if LayerNorm hurts convergence\n",
    "USE_LAYER_NORM = True\n",
    "\n",
    "\n",
    "class CNN_Encoder(tf.keras.Model):\n",
    "    \"\"\"\n",
    "    ROI Feature Encoder — matches model_architecture.tex formal spec.\n",
    "\n",
    "    Forward pass:\n",
    "        F = LayerNorm(ReLU(W_enc · X + b_enc))   [if USE_LAYER_NORM=True]\n",
    "        F = ReLU(W_enc · X + b_enc)               [if USE_LAYER_NORM=False]\n",
    "\n",
    "    Shapes:\n",
    "        Input  X : (B, K=64, 2048)  — InceptionV3 last-conv spatial features\n",
    "        Output F : (B, K=64, d'=embedding_dim)  — projected ROI embeddings\n",
    "    \"\"\"\n",
    "\n",
    "    def __init__(self, embedding_dim, use_layer_norm=USE_LAYER_NORM):\n",
    "        super(CNN_Encoder, self).__init__()\n",
    "        self.use_layer_norm = use_layer_norm\n",
    "        # Linear projection: (B, 64, 2048) → (B, 64, embedding_dim)\n",
    "        self.fc = tf.keras.layers.Dense(embedding_dim, name=\"roi_projection\")\n",
    "        if use_layer_norm:\n",
    "            # Normalise across embedding_dim to stabilise training\n",
    "            self.layer_norm = tf.keras.layers.LayerNormalization(\n",
    "                axis=-1, name=\"roi_layer_norm\"\n",
    "            )\n",
    "        print(f\"🔧 CNN_Encoder: LayerNorm={'ON ✅' if use_layer_norm else 'OFF ❌'}\")\n",
    "\n",
    "    def call(self, x):\n",
    "        x = self.fc(x)              # (B, 64, embedding_dim) — linear proj\n",
    "        x = tf.nn.relu(x)           # ReLU non-linearity\n",
    "        if self.use_layer_norm:\n",
    "            x = self.layer_norm(x)  # LayerNorm (formal spec)\n",
    "        return x",
])

ENCODER_DECODER_INSTANTIATION_CELL = code_cell([
    "encoder = CNN_Encoder(embedding_dim)\n",
    "decoder = RNN_Decoder(embedding_dim, units, vocab_size)",
])

PRETRAINED_MARKDOWN = markdown_cell([
    "---\n",
    "## 🔁 Pretrained Warm-Start: keras-io/image-captioning\n",
    "\n",
    "Weights from the English **keras-io/image-captioning** model (trained on MS-COCO) are grafted\n",
    "into the Bengali encoder/decoder at **model initialization** as a warm-start.\n",
    "\n",
    "### Transfer Map\n",
    "\n",
    "| Layer | Action | Reason |\n",
    "|---|---|---|\n",
    "| `CNN_Encoder.fc` | ✅ GRAFT | Vocabulary-agnostic ROI projection |\n",
    "| `Attention.W1 / W2 / V` | ✅ GRAFT | Image alignment — no vocab dependency |\n",
    "| `Decoder.gru` | ✅ GRAFT | Recurrent weights; shape is vocab-independent |\n",
    "| `Decoder.fc1` | ✅ GRAFT | Hidden projection; shape is vocab-independent |\n",
    "| `Decoder.embedding` | 🔄 REINIT | Bengali vocab (~22k) ≠ English vocab (5k) |\n",
    "| `Decoder.fc2` | 🔄 REINIT | Bengali vocab (~22k) ≠ English vocab (5k) |\n",
    "\n",
    "### Setup\n",
    "\n",
    "1. Download `decoder/model.h5` from "
    "[keras-io/image-captioning on HuggingFace](https://huggingface.co/keras-io/image-captioning)\n",
    "2. Place it at `pretrained/decoder_model.h5` **relative to this notebook**",
])

PRETRAINED_PATH_CELL = code_cell([
    "# ════════════════════════════════════════════════════════════════════════════\n",
    "# 🔁 PRETRAINED WARM-START: keras-io/image-captioning weights\n",
    "# Place decoder/model.h5 at:  <notebook_dir>/pretrained/decoder_model.h5\n",
    "# Download from: https://huggingface.co/keras-io/image-captioning\n",
    "# ════════════════════════════════════════════════════════════════════════════\n",
    "import os\n",
    "\n",
    "# Resolve relative path from this notebook's directory\n",
    "try:\n",
    "    _NOTEBOOK_DIR = os.path.dirname(os.path.abspath(__file__))\n",
    "except NameError:\n",
    "    # __file__ not defined in Jupyter; use current working directory\n",
    "    _NOTEBOOK_DIR = os.getcwd()\n",
    "\n",
    "PRETRAINED_H5_PATH = os.path.join(_NOTEBOOK_DIR, \"pretrained\", \"decoder_model.h5\")\n",
    "\n",
    "if os.path.exists(PRETRAINED_H5_PATH):\n",
    "    print(f\"✅ Pretrained weights found at: {PRETRAINED_H5_PATH}\")\n",
    "    pretrained_available = True\n",
    "else:\n",
    "    print(f\"⚠️  Pretrained weights NOT found at: {PRETRAINED_H5_PATH}\")\n",
    "    print(\"    Please download decoder/model.h5 from:\")\n",
    "    print(\"    https://huggingface.co/keras-io/image-captioning\")\n",
    "    print(\"    and place it at: pretrained/decoder_model.h5 (relative to notebook)\")\n",
    "    pretrained_available = False",
])

GRAFT_FUNCTION_CELL = code_cell([
    "def graft_pretrained_weights(\n",
    "    encoder_bn,\n",
    "    decoder_bn,\n",
    "    h5_path=PRETRAINED_H5_PATH,\n",
    "    verbose=True,\n",
    "):\n",
    "    \"\"\"\n",
    "    Transfer vocabulary-agnostic weights from the keras-io English model\n",
    "    to the Bengali encoder / decoder, skipping vocab-dependent layers.\n",
    "\n",
    "    Vocabulary-AGNOSTIC  → transfer directly (shape-matched):\n",
    "        CNN_Encoder.fc              (2048 → 256)\n",
    "        BahdanauAttention.W1/W2/V   (image alignment scoring)\n",
    "        RNN_Decoder.gru             (recurrent gates; shape is vocab-independent)\n",
    "        RNN_Decoder.fc1             (hidden projection)\n",
    "\n",
    "    Vocabulary-DEPENDENT → skip / reinitialize from scratch:\n",
    "        RNN_Decoder.embedding       (vocab_size × embedding_dim — size differs)\n",
    "        RNN_Decoder.fc2             (hidden_units × vocab_size — size differs)\n",
    "    \"\"\"\n",
    "    if not os.path.exists(h5_path):\n",
    "        print(\"⚠️  No pretrained H5 found — skipping weight grafting.\")\n",
    "        return False\n",
    "\n",
    "    try:\n",
    "        en_model = tf.keras.models.load_model(h5_path, compile=False)\n",
    "        if verbose:\n",
    "            print(\"📦 English pretrained model loaded:\")\n",
    "            en_model.summary()\n",
    "    except Exception as e:\n",
    "        print(f\"⚠️  Could not load pretrained model: {e}\")\n",
    "        return False\n",
    "\n",
    "    # Build Bengali model with a dummy forward pass so all weights are created\n",
    "    _dummy_img = tf.zeros((1, 64, 2048), dtype=tf.float32)\n",
    "    _dummy_cap = tf.zeros((1, 1), dtype=tf.int32)\n",
    "    _dummy_h   = decoder_bn.reset_state(1)\n",
    "    _enc_out   = encoder_bn(_dummy_img)\n",
    "    _          = decoder_bn(_dummy_cap, _enc_out, _dummy_h)\n",
    "\n",
    "    # Layers whose names contain these strings are vocab-dependent → skip\n",
    "    VOCAB_DEPENDENT_KEYWORDS = (\"embedding\", \"fc2\", \"dense_4\", \"dense_5\")\n",
    "\n",
    "    # Agnostic target layers in the Bengali model (ordered by expected match)\n",
    "    agnostic_targets = [\n",
    "        (\"CNN_Encoder.fc\",    encoder_bn.fc),\n",
    "        (\"Attention.W1\",      decoder_bn.attention.W1),\n",
    "        (\"Attention.W2\",      decoder_bn.attention.W2),\n",
    "        (\"Attention.V\",       decoder_bn.attention.V),\n",
    "        (\"Decoder.gru\",       decoder_bn.gru),\n",
    "        (\"Decoder.fc1\",       decoder_bn.fc1),\n",
    "    ]\n",
    "\n",
    "    transferred, skipped, unmatched = [], [], []\n",
    "\n",
    "    for en_layer in en_model.layers:\n",
    "        en_weights = en_layer.get_weights()\n",
    "        if not en_weights:\n",
    "            continue  # non-parametric layer\n",
    "\n",
    "        # Skip vocab-dependent layers by name heuristic\n",
    "        if any(kw in en_layer.name for kw in VOCAB_DEPENDENT_KEYWORDS):\n",
    "            skipped.append(en_layer.name)\n",
    "            continue\n",
    "\n",
    "        # Match by weight shapes (exact match required for all weight tensors)\n",
    "        matched = False\n",
    "        for label, bn_layer in agnostic_targets:\n",
    "            try:\n",
    "                bn_weights = bn_layer.get_weights()\n",
    "                if (\n",
    "                    len(en_weights) == len(bn_weights)\n",
    "                    and all(e.shape == b.shape for e, b in zip(en_weights, bn_weights))\n",
    "                ):\n",
    "                    bn_layer.set_weights(en_weights)\n",
    "                    transferred.append(f\"{en_layer.name:20s} → {label}\")\n",
    "                    matched = True\n",
    "                    break\n",
    "            except Exception:\n",
    "                pass\n",
    "\n",
    "        if not matched:\n",
    "            unmatched.append(en_layer.name)\n",
    "\n",
    "    if verbose:\n",
    "        print(f\"\\n✅ Transferred {len(transferred)} layer(s):\")\n",
    "        for t in transferred:\n",
    "            print(f\"   • {t}\")\n",
    "        if skipped:\n",
    "            print(f\"⏭️  Skipped (vocab-dependent): {skipped}\")\n",
    "        if unmatched:\n",
    "            print(f\"❓ Unmatched (no shape fit):  {unmatched}\")\n",
    "\n",
    "    del en_model\n",
    "    return len(transferred) > 0",
])

GRAFTING_TRIGGER_CELL = code_cell([
    "# ── Apply pretrained warm-start weights at initialization ────────────────────\n",
    "# Weights are ALWAYS applied (no checkpoint check).\n",
    "# Bengali-specific layers (embedding, fc2) are reinitialized.\n",
    "# Fine-tuning on the Bengali dataset will update ALL parameters from here.\n",
    "\n",
    "if pretrained_available:\n",
    "    print(\"🔁 Applying pretrained warm-start weights...\")\n",
    "    graft_success = graft_pretrained_weights(encoder, decoder, verbose=True)\n",
    "    if graft_success:\n",
    "        print(\"\\n✅ Warm-start complete.\")\n",
    "        print(\"   Grafted: CNN_Encoder.fc | Attention W1/W2/V | GRU | fc1\")\n",
    "        print(\"   Fresh:   embedding (Bengali vocab) | fc2 (Bengali vocab)\")\n",
    "        print(\"   Fine-tuning will adapt all layers to Bengali captions.\")\n",
    "    else:\n",
    "        print(\"⚠️  Grafting failed — proceeding with random initialization.\")\n",
    "else:\n",
    "    print(\"ℹ️  No pretrained weights found — training from random initialization.\")\n",
    "    print(\"    Place decoder_model.h5 at pretrained/decoder_model.h5 to enable warm-start.\")",
])

EVALUATE_FALLBACK_CELL = code_cell([
    "# ─────────────────────────────────────────────────────────────────────────────\n",
    "# 🛡️ Robust Inference: evaluate_with_fallback()\n",
    "# ─────────────────────────────────────────────────────────────────────────────\n",
    "# Wraps evaluate() and detects degenerate outputs (empty result or highly\n",
    "# repetitive tokens). Falls back to temperature-sampled decoding for diversity.\n",
    "\n",
    "def evaluate_with_fallback(image_path, max_retries=2, repetition_threshold=0.66):\n",
    "    \"\"\"\n",
    "    Generate a Bengali caption with automatic fallback decoding.\n",
    "\n",
    "    Primary strategy : greedy argmax (deterministic, stable metrics).\n",
    "    Fallback strategy: temperature-sampled decode (more diverse output).\n",
    "\n",
    "    A result is considered degenerate if:\n",
    "        • it is empty (no tokens generated before <end>), OR\n",
    "        • more than `repetition_threshold` fraction of tokens are identical\n",
    "          (e.g. the model repeats the same word over and over).\n",
    "\n",
    "    Args:\n",
    "        image_path           : path to the input image file.\n",
    "        max_retries          : how many sampled attempts to make before giving up.\n",
    "        repetition_threshold : fraction-of-tokens that trigger the repetition check.\n",
    "                               E.g. 0.66 means >66% identical tokens = degenerate.\n",
    "\n",
    "    Returns:\n",
    "        result       : list[str] — generated Bengali tokens.\n",
    "        attn_plot    : np.ndarray — attention weights for each token.\n",
    "        used_fallback: bool — True if the sampled fallback was used.\n",
    "    \"\"\"\n",
    "    def _is_degenerate(tokens):\n",
    "        if not tokens:\n",
    "            return True\n",
    "        unique_ratio = len(set(tokens)) / len(tokens)\n",
    "        return unique_ratio < (1.0 - repetition_threshold)\n",
    "\n",
    "    # --- Primary: greedy decode ---\n",
    "    result, attn = evaluate(image_path, sampling=False)\n",
    "\n",
    "    if not _is_degenerate(result):\n",
    "        return result, attn, False   # ✅ Good output, no fallback needed\n",
    "\n",
    "    # --- Fallback: sampled decode ---\n",
    "    degenerate_reason = \"empty\" if not result else \"repetitive\"\n",
    "    print(f\"⚠️  Greedy output is {degenerate_reason}: {result}\")\n",
    "    print(f\"    Falling back to sampled decoding (max {max_retries} attempts)...\")\n",
    "\n",
    "    for attempt in range(1, max_retries + 1):\n",
    "        result, attn = evaluate(image_path, sampling=True)\n",
    "        if not _is_degenerate(result):\n",
    "            print(f\"    ✅ Fallback succeeded on attempt {attempt}: {' '.join(result)}\")\n",
    "            return result, attn, True\n",
    "        print(f\"    Attempt {attempt} still degenerate: {result}\")\n",
    "\n",
    "    # All fallback attempts exhausted — return last sampled result anyway\n",
    "    print(\"    ⚠️  All fallback attempts exhausted. Returning last sampled result.\")\n",
    "    return result, attn, True",
])


def patch_visionxai_notebook(target_notebook_path: pathlib.Path) -> None:
    """Recipe: Patches VisionXAI image captioning notebook with architecture and fallback cells."""
    nb = load_notebook(target_notebook_path)
    cells = nb["cells"]
    original_len = len(cells)

    # 1. Replace CNN_Encoder cell
    cnn_idx = find_cell_by_snippet(cells, "class CNN_Encoder(tf.keras.Model):")
    if cnn_idx == -1:
        raise ValueError("Could not find CNN_Encoder cell in target notebook.")

    cells.insert(cnn_idx, LAYERNORM_MARKDOWN)
    cells[cnn_idx + 1] = CNN_ENCODER_CELL
    print(f"✅ Replaced CNN_Encoder cell at index {cnn_idx + 1}")

    # 2. Replace encoder/decoder instantiation cell & insert warm-start cells
    inst_idx = find_cell_by_snippet(cells, "encoder = CNN_Encoder(embedding_dim)")
    if inst_idx == -1:
        raise ValueError("Could not find encoder instantiation cell in target notebook.")

    cells[inst_idx] = ENCODER_DECODER_INSTANTIATION_CELL
    print(f"✅ Replaced encoder/decoder instantiation cell at index {inst_idx}")

    insert_at = inst_idx + 1
    for new_cell in reversed([
        PRETRAINED_MARKDOWN,
        PRETRAINED_PATH_CELL,
        GRAFT_FUNCTION_CELL,
        GRAFTING_TRIGGER_CELL,
    ]):
        cells.insert(insert_at, new_cell)

    print(f"✅ Inserted pretrained warm-start cells after index {inst_idx}")

    # 3. Insert evaluate_with_fallback after evaluate()
    eval_idx = find_cell_by_snippet(cells, "def evaluate(image_path, sampling=False):")
    if eval_idx == -1:
        raise ValueError("Could not find evaluate() cell in target notebook.")

    cells.insert(eval_idx + 1, EVALUATE_FALLBACK_CELL)
    print(f"✅ Inserted evaluate_with_fallback() cell after index {eval_idx}")

    # Save
    save_notebook(nb, target_notebook_path)
    print(f"\n🎉 Notebook patched: {original_len} → {len(nb['cells'])} cells")
    print(f"   Saved to: {target_notebook_path}")


# ---------------------------------------------------------------------------
# Command Line Interface (CLI)
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Universal Jupyter Notebook Patch & Modification Utility"
    )
    subparsers = parser.add_subparsers(dest="command", help="Mode of operation")

    # Subcommand: VisionXAI Recipe Patch
    recipe_parser = subparsers.add_parser("visionxai", help="Run the VisionXAI captioning model notebook patch recipe")
    recipe_parser.add_argument("--notebook", "-n", type=pathlib.Path, required=True, help="Path to the target notebook .ipynb file")

    # Subcommand: List cells
    list_parser = subparsers.add_parser("list", help="List cells and snippet summaries from a notebook")
    list_parser.add_argument("--notebook", "-n", type=pathlib.Path, required=True, help="Path to notebook")

    # Subcommand: Replace cell
    replace_parser = subparsers.add_parser("replace", help="Replace cell content matching target snippet")
    replace_parser.add_argument("--notebook", "-n", type=pathlib.Path, required=True, help="Path to notebook")
    replace_parser.add_argument("--target", "-t", required=True, help="Snippet to locate the target cell")
    replace_parser.add_argument("--content", "-c", help="New content string or file path")
    replace_parser.add_argument("--content-file", type=pathlib.Path, help="File containing new cell content")
    replace_parser.add_argument("--cell-type", choices=["code", "markdown"], default="code", help="Cell type")

    # Subcommand: Insert cell
    insert_parser = subparsers.add_parser("insert", help="Insert a new cell into a notebook")
    insert_parser.add_argument("--notebook", "-n", type=pathlib.Path, required=True, help="Path to notebook")
    insert_parser.add_argument("--target", "-t", help="Target snippet relative to which cell will be inserted")
    insert_parser.add_argument("--position", choices=["before", "after"], default="after", help="Insert before or after target snippet")
    insert_parser.add_argument("--index", type=int, help="Explicit 0-indexed position to insert cell")
    insert_parser.add_argument("--content", "-c", help="Content string for the cell")
    insert_parser.add_argument("--content-file", type=pathlib.Path, help="File containing cell content")
    insert_parser.add_argument("--cell-type", choices=["code", "markdown"], default="code", help="Cell type")

    # Subcommand: Delete cell
    delete_parser = subparsers.add_parser("delete", help="Delete cells containing target snippet")
    delete_parser.add_argument("--notebook", "-n", type=pathlib.Path, required=True, help="Path to notebook")
    delete_parser.add_argument("--target", "-t", required=True, help="Snippet matching cells to delete")

    # Subcommand: Search cells
    search_parser = subparsers.add_parser("search", help="Search cells by one or more snippets")
    search_parser.add_argument("--notebook", "-n", type=pathlib.Path, required=True, help="Path to notebook")
    search_parser.add_argument("--target", "-t", action="append", required=True, help="Snippet to search for; repeat for multiple snippets")
    search_parser.add_argument("--mode", choices=["any", "all"], default="any", help="Match any or all snippets")
    search_parser.add_argument("--cell-type", choices=["code", "markdown"], help="Restrict search to one cell type")
    search_parser.add_argument("--ignore-case", action="store_true", help="Case-insensitive search")
    search_parser.add_argument("--ascii", action="store_true", help="Replace non-ASCII characters in output")
    search_parser.add_argument("--max-chars", type=int, default=500, help="Maximum source characters to print per matching cell")
    search_parser.add_argument("--line-numbers", action="store_true", help="Print line numbers")

    # Subcommand: Show selected cells
    show_parser = subparsers.add_parser("show", help="Print selected cells by index or index range")
    show_parser.add_argument("--notebook", "-n", type=pathlib.Path, required=True, help="Path to notebook")
    show_parser.add_argument("--indices", "-i", required=True, help="Cell indices/ranges, e.g. 69,75-80")
    show_parser.add_argument("--ascii", action="store_true", help="Replace non-ASCII characters in output")
    show_parser.add_argument("--max-chars", type=int, help="Maximum source characters to print per cell")
    show_parser.add_argument("--line-numbers", action="store_true", help="Print line numbers")

    # Subcommand: List function/class definitions
    funcs_parser = subparsers.add_parser("functions", help="List function/class definitions in code cells")
    funcs_parser.add_argument("--notebook", "-n", type=pathlib.Path, required=True, help="Path to notebook")
    funcs_parser.add_argument("--ascii", action="store_true", help="Replace non-ASCII characters in output")

    # Subcommand: Validate code cells by parsing Python syntax
    validate_parser = subparsers.add_parser("validate", help="Validate notebook JSON and compile Python code cells")
    validate_parser.add_argument("--notebook", "-n", type=pathlib.Path, required=True, help="Path to notebook")
    validate_parser.add_argument("--strict-magics", action="store_true", help="Do not skip magic/shell cells")
    validate_parser.add_argument("--ascii", action="store_true", help="Replace non-ASCII characters in output")

    # Subcommand: Replace cell by explicit index
    replace_index_parser = subparsers.add_parser("replace-index", help="Replace cell content by explicit cell index")
    replace_index_parser.add_argument("--notebook", "-n", type=pathlib.Path, required=True, help="Path to notebook")
    replace_index_parser.add_argument("--index", "-i", type=int, required=True, help="0-indexed cell number to replace")
    replace_index_parser.add_argument("--content", "-c", help="New content string")
    replace_index_parser.add_argument("--content-file", type=pathlib.Path, help="File containing new cell content")
    replace_index_parser.add_argument("--cell-type", choices=["code", "markdown"], help="Override cell type")

    # Legacy flag compatibility: if running with just --notebook
    parser.add_argument("--notebook", "-n", type=pathlib.Path, help="Target notebook path (runs visionxai recipe by default if specified without subcommand)")

    args = parser.parse_args()

    # Route command
    if args.command == "visionxai" or (args.command is None and args.notebook):
        target_nb = args.notebook or getattr(args, "notebook", None)
        if not target_nb:
            print("ERROR: Please specify target notebook path using --notebook / -n")
            sys.exit(1)
        patch_visionxai_notebook(target_nb)

    elif args.command == "list":
        nb = load_notebook(args.notebook)
        print(f"Notebook: {args.notebook} ({len(nb['cells'])} cells)\n" + "-" * 50)
        for i, cell in enumerate(nb["cells"]):
            src = "".join(cell.get("source", []))
            first_line = src.strip().split("\n")[0] if src.strip() else "<EMPTY>"
            print(f"[{i:3d}] ({cell['cell_type']:8s}) {first_line[:70]}")

    elif args.command == "replace":
        nb = load_notebook(args.notebook)
        content = args.content
        if args.content_file:
            content = args.content_file.read_text(encoding="utf-8")
        if not content:
            print("ERROR: Must provide --content or --content-file")
            sys.exit(1)

        try:
            replaced_idx = replace_cell_source(nb["cells"], args.target, content, args.cell_type)
            save_notebook(nb, args.notebook)
            print(f"✅ Replaced cell at index {replaced_idx} in {args.notebook}")
        except Exception as e:
            print(f"ERROR: {e}")
            sys.exit(1)

    elif args.command == "insert":
        nb = load_notebook(args.notebook)
        content = args.content
        if args.content_file:
            content = args.content_file.read_text(encoding="utf-8")
        if not content:
            print("ERROR: Must provide --content or --content-file")
            sys.exit(1)

        cell = create_cell(args.cell_type, content)
        try:
            inserted_idx = insert_cell(nb["cells"], cell, target_snippet=args.target, position=args.position, index=args.index)
            save_notebook(nb, args.notebook)
            print(f"✅ Inserted {args.cell_type} cell at index {inserted_idx} in {args.notebook}")
        except Exception as e:
            print(f"ERROR: {e}")
            sys.exit(1)

    elif args.command == "delete":
        nb = load_notebook(args.notebook)
        try:
            count = delete_cells_by_snippet(nb["cells"], args.target)
            save_notebook(nb, args.notebook)
            print(f"✅ Deleted {count} cell(s) matching {args.target!r} in {args.notebook}")
        except Exception as e:
            print(f"ERROR: {e}")
            sys.exit(1)

    elif args.command == "search":
        nb = load_notebook(args.notebook)
        matches = find_cells_by_snippets(
            nb["cells"],
            args.target,
            match_mode=args.mode,
            cell_type=args.cell_type,
            case_sensitive=not args.ignore_case,
        )
        print(f"Notebook: {args.notebook}")
        print(f"Matched cells: {matches}")
        show_cells(
            nb["cells"],
            matches,
            ascii_only=args.ascii,
            max_chars=args.max_chars,
            line_numbers=args.line_numbers,
        )

    elif args.command == "show":
        nb = load_notebook(args.notebook)
        show_cells(
            nb["cells"],
            parse_index_list(args.indices),
            ascii_only=args.ascii,
            max_chars=args.max_chars,
            line_numbers=args.line_numbers,
        )

    elif args.command == "functions":
        nb = load_notebook(args.notebook)
        list_function_definitions(nb["cells"], ascii_only=args.ascii)

    elif args.command == "validate":
        nb = load_notebook(args.notebook)
        errors = compile_code_cells(nb["cells"], allow_magics=not args.strict_magics)
        print(f"Notebook: {args.notebook}")
        print(f"Cells: {len(nb['cells'])}")
        print(f"Syntax errors: {len(errors)}")
        for error in errors:
            print(
                f"Cell {error['cell']} line {error['line']} offset {error['offset']}: "
                f"{error['message']}"
            )
            print(safe_text(error["source_line"], ascii_only=args.ascii))
        if errors:
            sys.exit(1)

    elif args.command == "replace-index":
        nb = load_notebook(args.notebook)
        content = args.content
        if args.content_file:
            content = args.content_file.read_text(encoding="utf-8")
        if content is None:
            print("ERROR: Must provide --content or --content-file")
            sys.exit(1)
        try:
            replaced_idx = replace_cell_at_index(nb["cells"], args.index, content, args.cell_type)
            save_notebook(nb, args.notebook)
            print(f"✅ Replaced cell at index {replaced_idx} in {args.notebook}")
        except Exception as e:
            print(f"ERROR: {e}")
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
