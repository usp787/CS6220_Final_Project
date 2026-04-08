"""
rag_validator.py — RAG-based input validation for the Retail Inventory Twin.

Architecture
------------
A small in-process ChromaDB vector store holds ~20 short text documents in
three categories:

  1. item_profile  — one document per trained item (I001–I008) describing its
                     name, category, typical demand range, and seasonal pattern.
  2. schema        — expected CSV column definitions and value constraints.
  3. boundary      — descriptions of out-of-scope data (non-food retail, sensor
                     logs, financial ledgers, etc.).

Each uploaded sales CSV is summarised as a short natural-language string
("columns: … — items: …"), embedded with all-MiniLM-L6-v2, and queried
against the valid-domain documents (item_profile + schema).  The top cosine
similarity score drives the decision:

  ≥ 0.60  →  accepted      — data matches known coffee-shop domain
  0.35–0.59 → warning      — data is borderline; pipeline proceeds with caution
  < 0.35  →  rejected      — data is outside the trained domain; pipeline blocked

A secondary boundary check queries the full corpus.  If an out-of-scope
document is the single best match across the entire store, an explicit domain-
mismatch message is added regardless of the threshold outcome.

Usage
-----
    from rag_validator import validate_sales_csv

    result = validate_sales_csv(csv_bytes, filename="sales_jan_2026.csv")
    # result: {"status": "accepted"|"warning"|"rejected",
    #          "similarity": 0.78,
    #          "top_match": "Latte — hot drink ...",
    #          "message": "...",
    #          "details": [...]}
"""

import io
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ── Thresholds ────────────────────────────────────────────────────────────────
ACCEPT_THRESHOLD = 0.60
WARN_THRESHOLD   = 0.40

# ── Document corpus ───────────────────────────────────────────────────────────
CAT_ITEM     = "item_profile"
CAT_SCHEMA   = "schema"
CAT_BOUNDARY = "boundary"

_DOCUMENTS: List[Tuple[str, str]] = [
    # ── Known item profiles (I001–I008) ───────────────────────────────────────
    (CAT_ITEM, "Espresso — hot drink — coffee shop beverage — "
               "daily sales 20 to 35 units, demand peaks in winter, "
               "strongly negatively correlated with temperature, item_id I001"),
    (CAT_ITEM, "Latte — hot milk coffee drink — coffee shop beverage — "
               "daily sales 35 to 55 units, demand peaks in cold months, "
               "moderately sensitive to temperature, item_id I002"),
    (CAT_ITEM, "Cappuccino — hot espresso milk foam drink — coffee shop beverage — "
               "daily sales 25 to 40 units, peaks in winter season, item_id I003"),
    (CAT_ITEM, "Americano — hot diluted espresso drink — coffee shop beverage — "
               "daily sales 18 to 30 units, mild seasonal variation, item_id I004"),
    (CAT_ITEM, "Green Tea — warm herbal tea drink — tea beverage at coffee shop — "
               "daily sales 15 to 25 units, mild seasonal pattern, item_id I005"),
    (CAT_ITEM, "Muffin — baked pastry food — coffee shop snack item — "
               "daily sales 20 to 35 units, low temperature sensitivity, item_id I006"),
    (CAT_ITEM, "Croissant — baked French pastry — coffee shop food item — "
               "daily sales 15 to 28 units, low seasonal variation, item_id I007"),
    (CAT_ITEM, "Sandwich — prepared cold meal — coffee shop food item — "
               "daily sales 12 to 22 units, slightly higher demand in warm weather, item_id I008"),

    # ── Schema definitions ────────────────────────────────────────────────────
    (CAT_SCHEMA, "Sales transaction CSV columns: transaction_id, date, item_id, "
                 "item_name, quantity. Each row is one sales record for a food or beverage item."),
    (CAT_SCHEMA, "Date column format YYYY-MM-DD. item_id values are I001 through I008. "
                 "quantity is an integer count of units sold per day per item."),
    (CAT_SCHEMA, "Stock snapshot CSV columns: item_id, item_name, current_stock. "
                 "Represents current on-hand unit inventory per coffee shop item."),
    (CAT_SCHEMA, "Expected item names: Espresso, Latte, Cappuccino, Americano, Green Tea, "
                 "Muffin, Croissant, Sandwich. All are coffee shop food and drink products."),

    # ── Domain boundary examples (out-of-scope) ───────────────────────────────
    (CAT_BOUNDARY, "Auto parts retail inventory: columns part_number, vehicle_model, "
                   "SKU, wholesale_price, supplier_id. Non-food, non-beverage industrial domain."),
    (CAT_BOUNDARY, "Electronics store catalog: products laptop, smartphone, tablet, "
                   "HDMI cable, charger, USB hub. Consumer electronics, not food service."),
    (CAT_BOUNDARY, "Gaming and consumer electronics retail: products Xbox, PlayStation, "
                   "Nintendo Switch, gaming headset, controller, gaming monitor. "
                   "Video game hardware, not food or beverage."),
    (CAT_BOUNDARY, "Apple and computing devices retail: products iPad, iPhone, MacBook, "
                   "Surface, Apple Watch, AirPods. Personal computing devices, "
                   "not food service inventory."),
    (CAT_BOUNDARY, "IoT sensor log: columns timestamp, sensor_id, temperature_reading, "
                   "pressure_value, humidity_percent, device_status. Machine telemetry, not sales."),
    (CAT_BOUNDARY, "Financial ledger: columns account_number, debit, credit, balance, "
                   "transaction_type, currency_code. Accounting data, not retail inventory."),
    (CAT_BOUNDARY, "Hospital medical supply: items surgical_gloves, syringe, bandage, "
                   "IV_bag, medication_code, dosage_unit. Medical domain, not food or beverage."),
    (CAT_BOUNDARY, "Clothing apparel retail: columns product_id, size, color, fabric_type, "
                   "brand, price, units_sold, return_rate. Fashion retail, not food service."),
    (CAT_BOUNDARY, "Real estate transactions: columns property_id, address, sale_price, "
                   "square_footage, bedrooms, bathrooms, listing_date. Not retail inventory."),
]

# ── Lazy-initialised singletons ───────────────────────────────────────────────
_lock       = threading.Lock()
_collection: Optional[Any]  = None          # chromadb Collection
_ef:         Optional[Any]  = None          # embedding function (kept for querying)
_init_error: Optional[str]  = None          # set if initialisation failed


def _resolve_embedding_model_path() -> str:
    """
    Prefer a locally cached Hugging Face snapshot of all-MiniLM-L6-v2.

    Loading by model name can trigger a metadata request to Hugging Face even
    when the model is already cached, which breaks in offline or restricted
    network environments. If a cached snapshot exists, return its filesystem
    path so SentenceTransformer loads purely from local files.
    """
    cache_root = (
        Path.home()
        / ".cache"
        / "huggingface"
        / "hub"
        / "models--sentence-transformers--all-MiniLM-L6-v2"
        / "snapshots"
    )
    if cache_root.exists():
        snapshots = sorted(p for p in cache_root.iterdir() if p.is_dir())
        if snapshots:
            return str(snapshots[-1])

    # Fallback to the hub model name if no local snapshot is available.
    return "all-MiniLM-L6-v2"


def _build_store() -> None:
    """
    Build the ChromaDB in-memory vector store once.
    Called the first time validate_sales_csv() is invoked.
    Populates module-level _collection and _ef.
    """
    global _collection, _ef, _init_error

    try:
        import chromadb
        from chromadb.utils.embedding_functions import (
            SentenceTransformerEmbeddingFunction,
        )
    except ImportError as exc:
        _init_error = (
            f"RAG dependencies not installed: {exc}. "
            "Run: pip install sentence-transformers chromadb"
        )
        return

    try:
        model_ref = _resolve_embedding_model_path()
        _ef = SentenceTransformerEmbeddingFunction(
            model_name=model_ref,
            device="cpu",
        )

        client = chromadb.EphemeralClient()
        _collection = client.create_collection(
            name="inventory_domain",
            embedding_function=_ef,
            metadata={"hnsw:space": "cosine"},
        )

        ids       = [f"doc_{i}" for i in range(len(_DOCUMENTS))]
        texts     = [doc for _, doc in _DOCUMENTS]
        metadatas = [{"category": cat} for cat, _ in _DOCUMENTS]

        _collection.add(documents=texts, ids=ids, metadatas=metadatas)

    except Exception as exc:
        _init_error = f"Failed to build RAG vector store: {exc}"


def _get_store():
    """Return the initialised collection, building it on first call (thread-safe)."""
    global _collection, _init_error
    if _collection is None and _init_error is None:
        with _lock:
            if _collection is None and _init_error is None:
                _build_store()
    return _collection, _init_error


# ── Query builders ────────────────────────────────────────────────────────────

def _build_column_query(df: pd.DataFrame, filename: str) -> str:
    """
    Column-structure query — used to validate schema compatibility.
    Example: "CSV columns: transaction_id, date, item_id, item_name, quantity"
    """
    cols = ", ".join(df.columns.tolist())
    return f"CSV file with columns: {cols}"


def _build_item_query(df: pd.DataFrame) -> str:
    """
    Item-content query — used for domain similarity and boundary detection.
    Focuses on the actual item names without the column vocabulary, which
    would otherwise dominate the embedding and mask domain mismatches.

    Example: "items sold: Espresso, Latte, Muffin, Croissant"
    """
    item_names: List[str] = []
    if "item_name" in df.columns:
        item_names = df["item_name"].dropna().astype(str).unique()[:5].tolist()

    item_str = ", ".join(item_names) if item_names else "unknown products"
    return f"items sold in this dataset: {item_str}"


# ── Main validation function ──────────────────────────────────────────────────

def validate_sales_csv(
    content: bytes,
    filename: str = "upload.csv",
    n_results: int = 3,
) -> Dict[str, Any]:
    """
    Validate a sales CSV using a two-query RAG strategy.

    Two separate embeddings are used to prevent column vocabulary from
    masking domain mismatches:

      Query A — column query  → compared against schema + item_profile docs
                                to confirm structure is compatible.
      Query B — item query    → compared against item_profile docs only
                                to confirm content belongs to the trained domain.
                                Also used for boundary detection (full corpus).

    The reported similarity is the item-query similarity against item profiles,
    which best reflects whether the uploaded data is in-domain.

    Parameters
    ----------
    content  : raw bytes of the uploaded CSV file
    filename : original filename (used in messages)
    n_results: number of top documents to retrieve per sub-query

    Returns
    -------
    dict with keys:
      status      : "accepted" | "warning" | "rejected"
      similarity  : float, item-query cosine similarity against item profiles
      top_match   : str, highest-scoring item profile document
      message     : str, human-readable decision reason
      details     : list of dicts describing top-3 retrieved documents
    """
    # ── Parse CSV ─────────────────────────────────────────────────────────────
    try:
        df = pd.read_csv(io.BytesIO(content), nrows=50)
    except Exception as exc:
        return {
            "status":     "rejected",
            "similarity": 0.0,
            "top_match":  "",
            "message":    f"Cannot parse CSV: {exc}",
            "details":    [],
        }

    col_query  = _build_column_query(df, filename)
    item_query = _build_item_query(df)

    # ── Initialise vector store ───────────────────────────────────────────────
    collection, init_error = _get_store()
    if init_error:
        return {
            "status":     "warning",
            "similarity": -1.0,
            "top_match":  "",
            "message":    f"RAG validation unavailable ({init_error}); schema-only check applied.",
            "details":    [],
        }

    # ── Query A: schema structure check (column query vs schema+item docs) ────
    schema_results = collection.query(
        query_texts=[col_query],
        n_results=min(n_results, 12),
        where={"category": {"$in": [CAT_ITEM, CAT_SCHEMA]}},
    )
    schema_sim = round(1.0 - schema_results["distances"][0][0], 4) \
        if schema_results["distances"][0] else 0.0

    # ── Query B-1: domain check (item query vs item profiles only) ────────────
    item_results = collection.query(
        query_texts=[item_query],
        n_results=min(n_results, 8),           # 8 item profile docs
        where={"category": CAT_ITEM},
    )
    item_sims = [round(1.0 - d, 4) for d in item_results["distances"][0]]
    item_docs = item_results["documents"][0]

    top_item_sim = item_sims[0] if item_sims else 0.0
    top_item_doc = item_docs[0] if item_docs else ""

    details = [
        {"document": doc, "category": meta["category"], "similarity": sim}
        for doc, meta, sim in zip(
            item_results["documents"][0],
            item_results["metadatas"][0],
            item_sims,
        )
    ]

    # ── Query B-2: boundary check (item query vs full corpus, top-1) ─────────
    boundary_flag = False
    boundary_doc  = ""
    boundary_sim  = 0.0
    full_results  = collection.query(query_texts=[item_query], n_results=1)
    if full_results["documents"][0]:
        best_meta     = full_results["metadatas"][0][0]
        best_sim      = round(1.0 - full_results["distances"][0][0], 4)
        if best_meta["category"] == CAT_BOUNDARY and best_sim >= WARN_THRESHOLD:
            boundary_flag = True
            boundary_doc  = full_results["documents"][0][0]
            boundary_sim  = best_sim

    # ── Combine signals ───────────────────────────────────────────────────────
    # Primary signal: item-query similarity against item profiles.
    # Schema similarity is a secondary supporting signal.
    # Use the lower of the two as the conservative estimate.
    top_sim = min(top_item_sim, schema_sim)

    # ── Apply decision thresholds ─────────────────────────────────────────────
    if top_sim >= ACCEPT_THRESHOLD and not boundary_flag:
        status  = "accepted"
        message = (
            f"Domain check passed (item similarity {top_item_sim:.2f}, "
            f"schema similarity {schema_sim:.2f}). "
            f"Best item match: \"{top_item_doc[:80]}…\""
        )

    elif boundary_flag:
        # Best global match is an out-of-scope document — hard reject regardless of
        # item similarity score, because the boundary check is a stronger signal.
        status  = "rejected"
        message = (
            f"Domain mismatch — item content most closely matches an out-of-scope "
            f"document (similarity {boundary_sim:.2f}): \"{boundary_doc[:80]}…\". "
            f"Best coffee-shop item similarity: {top_item_sim:.2f}. "
            "Upload is outside the trained coffee-shop domain and has been blocked."
        )

    elif top_sim >= WARN_THRESHOLD:
        status  = "warning"
        message = (
            f"Low item-domain similarity ({top_item_sim:.2f} < {ACCEPT_THRESHOLD}). "
            f"Best match: \"{top_item_doc[:80]}…\". "
            "Item names may not belong to the trained coffee-shop domain."
        )

    else:
        status  = "rejected"
        message = (
            f"Domain check failed — item similarity {top_item_sim:.2f} < {WARN_THRESHOLD}. "
            "Uploaded items do not resemble the trained coffee-shop product set. "
            "Expected: Espresso, Latte, Cappuccino, Americano, Green Tea, "
            "Muffin, Croissant, Sandwich."
        )

    return {
        "status":     status,
        "similarity": top_item_sim,           # report item similarity as primary metric
        "top_match":  top_item_doc,
        "message":    message,
        "details":    details[:3],
    }
