"""Parquet storage: one file per dataset per symbol, idempotent time-keyed upserts.

Files are small (a few MB max), so upsert = read + concat + dedup + atomic
rewrite. Dedup keeps the LAST occurrence so refreshed rows (e.g. a re-fetched
partial period) overwrite older ones.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from research import config


def dataset_path(dataset: str, symbol: str) -> Path:
    if dataset not in config.DATASETS:
        raise KeyError(f"unknown dataset {dataset!r}; add it to research.config.DATASETS")
    return config.WAREHOUSE_DIR / dataset / f"{symbol}.parquet"


def load(dataset: str, symbol: str) -> pd.DataFrame:
    path = dataset_path(dataset, symbol)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def high_water_mark(dataset: str, symbol: str, time_col: str) -> int | None:
    df = load(dataset, symbol)
    if df.empty or time_col not in df.columns:
        return None
    return int(df[time_col].max())


def upsert(dataset: str, symbol: str, rows: list[dict], time_col: str) -> int:
    """Merge rows into the symbol's parquet; returns the count of NEW time keys."""
    path = dataset_path(dataset, symbol)
    if not rows:
        return 0
    new = pd.DataFrame(rows)
    existing = load(dataset, symbol)
    before = set(existing[time_col]) if not existing.empty else set()
    merged = pd.concat([existing, new], ignore_index=True) if not existing.empty else new
    merged = (
        merged.drop_duplicates(subset=[time_col], keep="last")
        .sort_values(time_col)
        .reset_index(drop=True)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    merged.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    return len(set(new[time_col]) - before)
