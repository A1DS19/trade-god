"""Shared event-study harness for the intraday edge-hunt (Phase 2a).

PRE-REGISTERED PROTOCOL (2026-07-15, committed before any real-data run —
see docs/superpowers/plans/2026-07-15-intraday-edge-hunt.md):
- Data: klines_15m only, strictly before TRAIN_END (study.py). OOS data
  (>= 2025-07-01) is never loaded in Phase 2a.
- Survivor rule per family: SURVIVOR iff for >= one pre-declared
  (extreme bucket, horizon) pair ALL of:
    1. edge in the hypothesized direction > ROUND_TRIP, where
       edge = bucket mean forward return - pooled middle-bucket mean
       (abs_mode families use mean |forward return| instead);
    2. descriptive |t| of the bucket >= MIN_T (forward returns overlap
       across adjacent bars, inflating t — hence 3.0, and treat as a
       ranking device, not a hypothesis test);
    3. bucket count >= MIN_COUNT;
    4. split-half: the edge has the hypothesized sign in BOTH halves of
       the train window.
  Hypothesized sign 0 = data-determined: the full-train edge sign is the
  direction, and all four conditions still bind (used by time-of-day).
- Multiple testing: 6 families x <=5 horizons x <=24 extreme buckets; the
  t>=3 + cost hurdle + split-half stack is the guard, and EVERY tested
  pair is reported in checks.csv, not only the passes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from research.siglib.events import event_study

ROUND_TRIP = 0.0016
MIN_T = 3.0
MIN_COUNT = 500


@dataclass(frozen=True)
class FamilySpec:
    name: str
    build: object                      # callable: data dict -> bucket panel
    extreme: dict                      # bucket label -> hypothesized sign (+1/-1/0)
    middle: list | None                # baseline buckets; None = all others
    horizons_bars: tuple
    abs_mode: bool = False


def cut_panel(panel: pd.DataFrame, edges: list, labels: list) -> pd.DataFrame:
    stacked = panel.stack()
    buckets = pd.cut(stacked, bins=edges, labels=labels,
                     include_lowest=True).astype(object)
    return buckets.unstack().reindex(index=panel.index, columns=panel.columns)


def _bucket_means(stats: pd.DataFrame, horizon: int) -> pd.DataFrame:
    return stats[stats["horizon_hours"] == horizon].set_index("bucket")


def _edge(rows: pd.DataFrame, bucket: str, middle: list | None) -> float | None:
    if bucket not in rows.index:
        return None
    base_labels = (middle if middle is not None
                   else [b for b in rows.index if b != bucket])
    base = rows.loc[[b for b in base_labels if b in rows.index]]
    if base.empty or float(base["count"].sum()) == 0:
        return None
    base_mean = float((base["mean"] * base["count"]).sum() / base["count"].sum())
    return float(rows.loc[bucket, "mean"]) - base_mean


def evaluate_family(
    spec: FamilySpec,
    close_panel: pd.DataFrame,
    bucket_panel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Full-train event study + split-half check per (extreme bucket, horizon)."""
    mid = len(close_panel.index) // 2
    halves = (close_panel.index[:mid], close_panel.index[mid:])

    stats = event_study(close_panel, bucket_panel,
                        horizons_hours=spec.horizons_bars, absolute=spec.abs_mode)
    half_stats = [
        event_study(close_panel.loc[ix], bucket_panel.loc[ix],
                    horizons_hours=spec.horizons_bars, absolute=spec.abs_mode)
        for ix in halves
    ]

    rows = []
    for h in spec.horizons_bars:
        full = _bucket_means(stats, h)
        h1, h2 = (_bucket_means(hs, h) for hs in half_stats)
        for bucket, hyp in spec.extreme.items():
            edge = _edge(full, bucket, spec.middle)
            if edge is None:
                # Pre-registered pair with no computable edge (bucket never
                # fires, or baseline pool empty) — still report it, so a
                # mis-specified FamilySpec can't hide as a 0-row REJECTED.
                in_full = bucket in full.index
                rows.append({
                    "family": spec.name, "bucket": bucket, "horizon_bars": h,
                    "count": int(full.loc[bucket, "count"]) if in_full else 0,
                    "t_stat": (float(full.loc[bucket, "t_stat"])
                               if in_full else float("nan")),
                    "edge": float("nan"), "edge_h1": None, "edge_h2": None,
                    "direction": int(hyp) if hyp != 0 else 0,
                    "passes": False,
                })
                continue
            e1 = _edge(h1, bucket, spec.middle)
            e2 = _edge(h2, bucket, spec.middle)
            count = int(full.loc[bucket, "count"])
            t = float(full.loc[bucket, "t_stat"])
            direction = int(hyp) if hyp != 0 else int(np.sign(edge) or 1)
            passes = (
                edge * direction > ROUND_TRIP
                and abs(t) >= MIN_T
                and count >= MIN_COUNT
                and e1 is not None and e1 * direction > 0
                and e2 is not None and e2 * direction > 0
            )
            rows.append({
                "family": spec.name, "bucket": bucket, "horizon_bars": h,
                "count": count, "t_stat": t, "edge": edge,
                "edge_h1": e1, "edge_h2": e2,
                "direction": direction, "passes": bool(passes),
            })
    checks = pd.DataFrame(rows, columns=[
        "family", "bucket", "horizon_bars", "count", "t_stat", "edge",
        "edge_h1", "edge_h2", "direction", "passes",
    ])
    verdict = "SURVIVOR" if bool(checks["passes"].any()) else "REJECTED"
    return stats, checks, verdict
