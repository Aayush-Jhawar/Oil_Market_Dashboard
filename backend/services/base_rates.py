"""
Base-rate engine (Step 5).

Groups event_impact rows by (node_id | basin, channel, severity, anticipated)
and produces:
  - median & IQR move per contract per horizon (T+0, T+1, T+5)
  - hit_rate   = n_fired / n_measured  (only measured=history rows count)
  - false_positive_rate = unexplained_moves / (all_threshold_moves_in_basin)
  - n_measured vs n_modeled shown separately — NEVER mixed in a hit rate

Output: list of base-rate records.
Rendered as: "Hormuz · transport · scare · unanticipated → Brent median +X%
              (IQR a..b), hit rate Y% (n=k measured), fades by T+20."

Guarantee: The API never returns a single predicted price — it returns a
distribution (median + IQR) plus a base rate + false-positive rate.
"""

import statistics
from typing import Any, Dict, List, Optional, Tuple

from services.event_impact_db import (
    get_conn,
    init_db,
    MODELED_PRODUCT_BASINS,
)


# ── Statistical helpers ───────────────────────────────────────────────────────

def _clean(vals: List[Optional[float]]) -> List[float]:
    return [v for v in vals if v is not None]


def _median(vals: List[Optional[float]]) -> Optional[float]:
    c = _clean(vals)
    return round(statistics.median(c), 2) if c else None


def _iqr(vals: List[Optional[float]]) -> Optional[List[float]]:
    c = sorted(_clean(vals))
    if len(c) < 2:
        return None
    q1 = c[max(0, len(c) // 4 - 1)]
    q3 = c[min(len(c) - 1, (3 * len(c)) // 4)]
    return [round(q1, 2), round(q3, 2)]


def _agg(rows: List[Dict], col: str) -> Dict[str, Any]:
    vals = [r.get(col) for r in rows]
    m    = _median(vals)
    iq   = _iqr(vals)
    n    = len(_clean(vals))
    return {"median": m, "iqr": iq, "n": n}


# ── Main aggregator ───────────────────────────────────────────────────────────

def compute_base_rates(
    group_by: str = "node_id",   # "node_id" | "basin"
    min_n: int = 1,              # omit groups with fewer than min_n measured rows
) -> List[Dict]:
    """
    Step 5: grouped base-rate output.

    group_by='node_id'  → fine-grained per-node view (use for node drill-down).
    group_by='basin'    → coarser Atlantic / MiddleEast_Dubai / Asia / Russia_Urals.

    Honesty rules:
    - measured (source_tag='history') and modeled (source_tag='prior') are kept
      in separate counters; hit_rate is computed on measured rows ONLY.
    - Modeled-product cells (crack/arb for Asia/MiddleEast/Russia basins) are
      returned with median=None and a 'modeled' flag — excluded from hit rates.
    - false_positive_rate = unexplained_moves / (threshold_moves + unexplained)
      computed globally (basin-level breakdown would need 20+ years of daily data).
    """
    init_db()

    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute("""
            SELECT *
            FROM event_impact
            WHERE node_id IS NOT NULL
              AND source_tag IN ('history', 'prior')
            ORDER BY event_date ASC
        """).fetchall()]

        unexplained_total = conn.execute(
            "SELECT COUNT(*) FROM unexplained_moves"
        ).fetchone()[0]

    if not rows:
        return []

    # Total threshold moves (coded + unexplained) for FPR denominator
    coded_threshold = sum(
        1 for r in rows if r.get("magnitude_class") in ("surge", "crash")
    )
    all_threshold = coded_threshold + unexplained_total
    global_fpr = (
        round(unexplained_total / all_threshold, 3) if all_threshold else None
    )

    # ── Group rows ────────────────────────────────────────────────────────────
    groups: Dict[Tuple, List[Dict]] = {}
    for r in rows:
        group_key   = r.get(group_by) or "unknown"
        channel     = r.get("channel")    or "unknown"
        severity    = r.get("severity")   or "unknown"
        anticipated = bool(r.get("anticipated", 0))
        key         = (group_key, channel, severity, anticipated)
        groups.setdefault(key, []).append(r)

    results: List[Dict] = []

    for (group_key, channel, severity, anticipated), group_rows in groups.items():

        measured = [r for r in group_rows if r.get("source_tag") == "history"]
        n_measured = len(measured)

        if n_measured < min_n:
            continue   # not enough data to report a meaningful rate

        n_total  = len(group_rows)
        n_modeled = n_total - n_measured
        n_fired  = sum(1 for r in measured if r.get("fired"))
        hit_rate = round(n_fired / n_measured, 3) if n_measured else None

        # Determine representative basin (use first row as sample)
        basin = group_rows[0].get("basin")
        products_modeled = basin in MODELED_PRODUCT_BASINS

        # ── Horizon aggregates on measured rows ───────────────────────────────
        wti_t0  = _agg(measured, "wti_t0")
        wti_t1  = _agg(measured, "wti_t1")
        wti_t5  = _agg(measured, "wti_t5")
        wti_t20 = _agg(measured, "wti_t20")

        brent_t0  = _agg(measured, "brent_t0")
        brent_t1  = _agg(measured, "brent_t1")
        brent_t5  = _agg(measured, "brent_t5")
        brent_t20 = _agg(measured, "brent_t20")

        if products_modeled:
            # Arb/crack are modeled (no live Dubai/gasoil); exclude from measured rate
            _modeled_cell: Dict = {"median": None, "iqr": None, "n": 0, "modeled": True}
            arb_t0 = arb_t5   = _modeled_cell
            crack_t0 = crack_t5 = _modeled_cell
        else:
            arb_t0   = _agg(measured, "arb_t0")
            arb_t5   = _agg(measured, "arb_t5")
            crack_t0 = _agg(measured, "distillate_crack_t0")
            crack_t5 = _agg(measured, "distillate_crack_t5")

        # ── Human-readable label ──────────────────────────────────────────────
        ant_str = "anticipated" if anticipated else "unanticipated"
        label   = f"{group_key} · {channel} · {severity} · {ant_str}"

        # Describe best observed move for the label (Brent or WTI lead)
        brent_med = brent_t0.get("median") or brent_t5.get("median")
        if brent_med is not None:
            sign_str = f"+{brent_med:.1f}%" if brent_med > 0 else f"{brent_med:.1f}%"
            brent_iq = brent_t0.get("iqr") or brent_t5.get("iqr")
            iq_str   = f" (IQR {brent_iq[0]:.1f}..{brent_iq[1]:.1f})" if brent_iq else ""
            hr_str   = f", hit rate {hit_rate*100:.0f}%" if hit_rate is not None else ""
            n_str    = f" (n={n_measured} measured)"
            description = f"Brent median {sign_str}{iq_str}{hr_str}{n_str}"
        else:
            description = f"n={n_measured} measured, {n_modeled} modeled"

        results.append({
            "group_key":          group_key,
            "group_by":           group_by,
            "channel":            channel,
            "severity":           severity,
            "anticipated":        anticipated,
            "basin":              basin,
            "label":              label,
            "description":        description,
            "n_total":            n_total,
            "n_measured":         n_measured,
            "n_modeled":          n_modeled,
            "n_fired":            n_fired,
            "hit_rate":           hit_rate,
            "false_positive_rate":global_fpr,
            "products_modeled":   products_modeled,
            # Horizon distributions (measured only)
            "wti_t0":   wti_t0,   "wti_t1":   wti_t1,
            "wti_t5":   wti_t5,   "wti_t20":  wti_t20,
            "brent_t0": brent_t0, "brent_t1": brent_t1,
            "brent_t5": brent_t5, "brent_t20":brent_t20,
            "arb_t0":   arb_t0,   "arb_t5":   arb_t5,
            "distillate_crack_t0": crack_t0,
            "distillate_crack_t5": crack_t5,
            # Analog list (IDs of constituent events)
            "event_ids": [r["event_id"] for r in group_rows],
        })

    # Sort: most measured data first for priority display
    results.sort(key=lambda r: r["n_measured"], reverse=True)
    return results


def get_node_base_rate(
    node_id: str,
    channel: Optional[str] = None,
    severity: Optional[str] = None,
) -> Optional[Dict]:
    """
    Return the most specific base-rate record for a single node,
    optionally filtered by channel and severity.
    Returns None if no measured data exists.
    """
    all_rates = compute_base_rates(group_by="node_id", min_n=1)
    candidates = [
        r for r in all_rates
        if r["group_key"] == node_id
        and (channel is None or r["channel"] == channel)
        and (severity is None or r["severity"] == severity)
    ]
    if not candidates:
        return None
    # Prefer unanticipated (separates base rates per spec)
    candidates.sort(key=lambda r: (r["anticipated"], -r["n_measured"]))
    return candidates[0]
