"""Inspect and re-encode memory embeddings.

Usage:
    uv run python scripts/reembed.py --check
    uv run python scripts/reembed.py --model ruri   # cl-nagoya/ruri-v3-30m
    uv run python scripts/reembed.py --model e5     # intfloat/multilingual-e5-small (default)
    uv run python scripts/reembed.py --model ruri --batch-size 64
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path.home() / ".familiar_ai" / "observations.db"

MODEL_ALIASES = {
    "e5": "intfloat/multilingual-e5-small",
    "ruri": "cl-nagoya/ruri-v3-30m",
}

# Known embedding dimensions (for display only)
KNOWN_DIMS = {
    "intfloat/multilingual-e5-small": 384,
    "cl-nagoya/ruri-v3-30m": 256,
}


# ── DB helpers ────────────────────────────────────────────────


def connect(db_path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(db_path), check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA foreign_keys = ON")
    return db


# ── check mode ────────────────────────────────────────────────


def cmd_check(db: sqlite3.Connection) -> None:
    n_obs = db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    n_emb = db.execute("SELECT COUNT(*) FROM obs_embeddings").fetchone()[0]

    print(f"observations : {n_obs}")
    print(f"embeddings   : {n_emb}  (missing: {n_obs - n_emb})")

    if n_emb == 0:
        print("No embeddings stored yet.")
        return

    # Inspect first vector
    first = db.execute("SELECT vector FROM obs_embeddings LIMIT 1").fetchone()
    vec = np.frombuffer(bytes(first["vector"]), dtype=np.float32)
    dim = len(vec)

    # Guess model from dimension
    guesses = [name for name, d in KNOWN_DIMS.items() if d == dim]
    guess_str = f"  → likely {guesses[0]}" if guesses else ""
    print(f"vector dim   : {dim}{guess_str}")

    # Norm sanity (should be ~1.0 if normalize_embeddings=True)
    norm = float(np.linalg.norm(vec))
    print(f"first norm   : {norm:.6f}  (1.0 = normalized)")

    # Sample: most recent 5
    rows = db.execute(
        "SELECT o.content, o.timestamp, o.kind FROM observations o "
        "JOIN obs_embeddings e ON o.id = e.obs_id "
        "ORDER BY o.timestamp DESC LIMIT 5"
    ).fetchall()
    print("\nLatest 5 entries with embeddings:")
    for r in rows:
        print(f"  [{r['kind']:12s}] {r['timestamp'][:16]}  {r['content'][:70]}")


# ── re-encode mode ────────────────────────────────────────────


def _load_model(model_name: str):
    """Return (encode_documents_fn,) — function: list[str] → np.ndarray."""
    from sentence_transformers import SentenceTransformer

    print(f"Loading {model_name} ...")
    t0 = time.perf_counter()
    model = SentenceTransformer(model_name)
    print(f"Loaded in {time.perf_counter() - t0:.2f} s")

    if model_name == "cl-nagoya/ruri-v3-30m":
        def encode(texts: list[str]) -> np.ndarray:
            prefixed = [f"検索文書: {t}" for t in texts]
            return model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)
    else:
        def encode(texts: list[str]) -> np.ndarray:
            prefixed = [f"passage: {t}" for t in texts]
            return model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)

    return encode


def cmd_reembed(db: sqlite3.Connection, model_name: str, batch_size: int) -> None:
    rows = db.execute(
        "SELECT id, content FROM observations ORDER BY timestamp ASC"
    ).fetchall()

    if not rows:
        print("No observations found.")
        return

    print(f"Re-encoding {len(rows)} observations with {model_name} ...")
    encode = _load_model(model_name)

    t0 = time.perf_counter()
    total = len(rows)
    processed = 0

    db.execute("DELETE FROM obs_embeddings")

    for batch_start in range(0, total, batch_size):
        batch = rows[batch_start : batch_start + batch_size]
        texts = [r["content"] for r in batch]
        vecs = encode(texts)

        db.executemany(
            "INSERT INTO obs_embeddings (obs_id, vector) VALUES (?, ?)",
            [(r["id"], vec.astype(np.float32).tobytes()) for r, vec in zip(batch, vecs)],
        )
        db.commit()

        processed += len(batch)
        elapsed = time.perf_counter() - t0
        per_sec = processed / elapsed
        print(f"  {processed}/{total}  ({per_sec:.1f} obs/s)", end="\r")

    print(f"\nDone. {total} embeddings written in {time.perf_counter() - t0:.1f} s.")
    print(f"Vector dim: {vecs.shape[1]}")


# ── main ──────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect / re-encode familiar-ai memory embeddings.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Show DB stats only.")
    group.add_argument("--model", metavar="NAME", help="Re-encode with model (e5 | ruri | full HF name).")
    parser.add_argument("--db", default=str(DB_PATH), help="Path to observations.db.")
    parser.add_argument("--batch-size", type=int, default=32, help="Encode batch size (default 32).")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    db = connect(db_path)

    if args.check:
        cmd_check(db)
    else:
        model_name = MODEL_ALIASES.get(args.model, args.model)
        cmd_reembed(db, model_name, args.batch_size)


if __name__ == "__main__":
    main()
