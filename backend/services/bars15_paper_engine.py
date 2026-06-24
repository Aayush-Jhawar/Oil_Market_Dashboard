"""
15-Minute DB Paper-Trading Engine
=================================
Drives the paper book from the live 15-minute candle database
(`DB/bars_15min_latest.db`) using the Z-Score mean-reversion rules validated in
`research_journals/`.

Accounting model
----------------
* P&L is measured in **ticks** (1 tick = $0.01), NOT dollars. Nothing is
  multiplied by the contract multiplier — a trade's result is simply how many
  ticks it captured, minus a per-trade slippage charge in ticks.
* There is no notion of account capital / equity / return %; with no capital cap
  those ratios are meaningless. Performance is the cumulative tick curve.
* At most ``MAX_CONCURRENT`` positions are held at once across all instruments.

No-lookahead execution
----------------------
The previous version evaluated the signal and filled on the *same* bar's close —
entering exactly at the z-score extreme and exiting exactly at the rolling mean.
That is look-ahead bias and produced an absurd ~100% win rate. This version
mirrors the backtest engine that produced the journal results: the signal is
computed from the **previous** closed bar and the trade is filled at the
**current** bar's open. The realistic gap between signal and fill is what brings
the win rate down to the journal's true ~85-95% for double flies.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from fractions import Fraction
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PRODUCT_TO_BASE = {"CL": "WTI", "CO": "Brent"}
BASE_TO_PRODUCT = {"WTI": "CL", "Brent": "CO"}

TICK_SIZE = 0.01                  # 1 tick = $0.01
WARMUP_BARS = 20                  # 20-bar rolling window (journal 15-min spec)
STOP_Z = 3.0                      # stop loss at |z| > 3.0
TIMEOUT_BARS = 8                  # force exit after 8 bars (~2h on 15-min)
COOLDOWN_BARS = 4                 # bars to sit out after a stop loss
MAX_CONCURRENT = int(os.getenv("PAPER_MAX_CONCURRENT", "12"))  # portfolio position cap

# Per-trade slippage in TICKS (1 tick per leg crossed, per the journal's 4-tick
# double-fly penalty). Applied once per round-trip trade.
SLIPPAGE_TICKS = {"double_fly": 8.0, "fly": 4.0, "spread": 2.0}


def _entry_threshold(regime: Optional[str]) -> float:
    """Regime-scaled z entry threshold (mirrors ZScoreStrategy)."""
    if regime in ("Backwardation", "Contango"):
        return 2.0
    if regime in ("Extreme_Backwardation", "Extreme_Contango"):
        return 2.5
    return 1.5


def _zscore_series(closes: List[float], window: int = WARMUP_BARS) -> List[Optional[Tuple[float, float, float]]]:
    """Rolling z-score of each close vs the trailing `window` closes (inclusive). Returns list of (z, mean, std)."""
    n = len(closes)
    z: List[Optional[Tuple[float, float, float]]] = [None] * n
    for i in range(window - 1, n):
        w = closes[i - window + 1:i + 1]
        mean = sum(w) / window
        var = sum((x - mean) ** 2 for x in w) / window
        std = var ** 0.5
        z_val = (closes[i] - mean) / std if std > 0 else None
        if z_val is not None:
            z[i] = (z_val, mean, std)
    return z


# Net leg coefficients of each structure in underlying contract-month space.
# spread = c1 - c2 ; fly = c1 - 2*c2 + c3 ; double-fly = c1 - 3*c2 + 3*c3 - c4
_STRUCT_COEFFS = {
    "spread": [1, -1],
    "fly": [1, -2, 1],
    "double_fly": [1, -3, 3, -1],
}


def _exposure_vector(spec: Dict) -> Dict[Tuple[str, int], Fraction]:
    """Net underlying contract-month exposure of a structure, keyed by
    (product, relative_month). Two structures are redundant (one replicates the
    other, e.g. a fly == long M1M2 spread + short M2M3 spread) iff their exposure
    vectors are linearly dependent. Used to keep the open book independent."""
    vec: Dict[Tuple[str, int], Fraction] = {}
    if spec.get("symbol") == "WTI-Brent":
        vec[("CL", 1)] = Fraction(1)
        vec[("CO", 1)] = Fraction(-1)
        return vec
    coeffs = _STRUCT_COEFFS.get(spec.get("type", ""))
    months = spec.get("months") or []
    if not coeffs or len(coeffs) != len(months):
        return vec
    prod = spec["product"]
    for m, c in zip(months, coeffs):
        key = (prod, int(m))
        vec[key] = vec.get(key, Fraction(0)) + Fraction(c)
    return vec


def _in_span(vec: Dict, basis: List[Dict]) -> bool:
    """Exact test: is `vec` a linear combination of the vectors in `basis`?

    Reduces the basis to echelon form (pivots keyed by the max contract leg
    present) and then reduces `vec`; if it cancels to zero it lies in the span —
    i.e. the structure is redundant given what is already open."""
    if not any(v != 0 for v in vec.values()):
        return True

    def lead(d):
        ks = [k for k, val in d.items() if val != 0]
        return max(ks) if ks else None

    pivots: Dict[Tuple[str, int], Dict] = {}
    for row in basis:
        rr = {k: Fraction(v) for k, v in row.items() if v != 0}
        while True:
            lk = lead(rr)
            if lk is None:
                break
            if lk in pivots:
                f = rr[lk] / pivots[lk][lk]
                for k, val in pivots[lk].items():
                    rr[k] = rr.get(k, Fraction(0)) - f * val
                    if rr[k] == 0:
                        del rr[k]
            else:
                pivots[lk] = rr
                break

    tt = {k: Fraction(v) for k, v in vec.items() if v != 0}
    while True:
        lk = lead(tt)
        if lk is None:
            return True
        if lk in pivots:
            f = tt[lk] / pivots[lk][lk]
            for k, val in pivots[lk].items():
                tt[k] = tt.get(k, Fraction(0)) - f * val
                if tt[k] == 0:
                    del tt[k]
        else:
            return False


def _parse_validated_instruments() -> List[Dict]:
    """Translate ZScoreStrategy.VALIDATED_INSTRUMENTS into build specs (CL/CO only)."""
    from services.zscore_strategy import ZScoreStrategy

    specs: List[Dict] = []
    for sym in ZScoreStrategy.VALIDATED_INSTRUMENTS:
        if sym.upper() == "WTI-BRENT":
            specs.append({"symbol": "WTI-Brent", "base": "WTI", "product": "CL", "product2": "CO", "type": "spread", "months": [1]})
            continue

        parts = sym.split("_")
        if len(parts) < 3:
            continue
        base = "Brent" if parts[0].upper() == "BRENT" else parts[0].upper()
        if base not in BASE_TO_PRODUCT:
            continue
        kind = parts[1].upper()
        try:
            months = [int(p) for p in parts[2:]]
        except ValueError:
            continue
        if kind == "DFLY" and len(months) == 4:
            specs.append({"symbol": sym, "base": base, "product": BASE_TO_PRODUCT[base],
                          "type": "double_fly", "months": months})
        elif kind == "FLY" and len(months) == 3:
            specs.append({"symbol": sym, "base": base, "product": BASE_TO_PRODUCT[base],
                          "type": "fly", "months": months})
        elif kind == "SPREAD" and len(months) == 2:
            specs.append({"symbol": sym, "base": base, "product": BASE_TO_PRODUCT[base],
                          "type": "spread", "months": months})
    return specs


def _build_instrument_bars(loader, data, spec) -> Optional[List[Tuple[str, float, float]]]:
    """Return [(timestamp, open, close), ...] for one validated instrument."""
    from backtesting.engine import SpreadConstructor

    if spec["type"] == "spread" and spec["symbol"] == "WTI-Brent":
        sorted_cl = loader.get_sorted_contracts(data, spec["product"])
        sorted_co = loader.get_sorted_contracts(data, spec.get("product2", "CO"))
        if not sorted_cl or not sorted_co:
            return None
        leg1 = data[sorted_cl[0]]
        leg2 = data[sorted_co[0]]
        df = SpreadConstructor.build_spread(leg1, leg2, sorted_cl[0], sorted_co[0])
    else:
        sorted_contracts = loader.get_sorted_contracts(data, spec["product"])
        months = spec["months"]
        if not months or max(months) > len(sorted_contracts):
            return None
        legs = [data[sorted_contracts[m - 1]] for m in months]
        leg_names = [sorted_contracts[m - 1] for m in months]

        if spec["type"] == "double_fly":
            df = SpreadConstructor.build_double_fly(legs[0], legs[1], legs[2], legs[3], *leg_names)
        elif spec["type"] == "fly":
            df = SpreadConstructor.build_fly(legs[0], legs[1], legs[2], *leg_names)
        elif spec["type"] == "spread":
            df = SpreadConstructor.build_spread(legs[0], legs[1], leg_names[0], leg_names[1])
        else:
            return None

    if df is None or df.empty:
        return None
    return [
        (str(idx), float(o), float(c))
        for idx, o, c in zip(df.index, df["open"].astype(float), df["close"].astype(float))
    ]


def _compute_regimes(loader, data) -> Dict[str, Dict]:
    """Classify current regime per base product from the latest term structure."""
    from services.regime_classifier import regime_classifier

    regimes: Dict[str, Dict] = {}
    for product, base in PRODUCT_TO_BASE.items():
        sorted_contracts = loader.get_sorted_contracts(data, product)
        if len(sorted_contracts) < 6:
            continue
        term_structure: Dict[int, float] = {}
        for idx, month_label in [(0, 1), (1, 2), (5, 6), (11, 12)]:
            if idx < len(sorted_contracts):
                df = data[sorted_contracts[idx]]
                if df is not None and not df.empty:
                    term_structure[month_label] = float(df["close"].iloc[-1])
        if 1 in term_structure and 6 in term_structure:
            try:
                regimes[base] = regime_classifier.classify(base, term_structure)
            except Exception as exc:
                logger.warning(f"bars15: regime classify failed for {base}: {exc}")
    return regimes


def _ts_to_epoch(ts: str) -> float:
    try:
        dt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return time.time()


def _minutes_between(ts_a: str, ts_b: str) -> int:
    try:
        a = datetime.strptime(ts_a[:19], "%Y-%m-%d %H:%M:%S")
        b = datetime.strptime(ts_b[:19], "%Y-%m-%d %H:%M:%S")
        return int(abs((b - a).total_seconds()) / 60)
    except Exception:
        return 0


def _structure_fields(sym: str, inst_type: str) -> Tuple[str, str, str]:
    """Mirror the inline close-record naming so roll-closes are consistent."""
    parts = sym.split("_")
    structure = "SPREAD" if inst_type in ("fly", "spread") else "FLY" if inst_type == "double_fly" else inst_type.upper()
    spread_name = "-"
    fly_name = "-"
    if "DFLY" in sym:
        structure = "FLY"
        if len(parts) >= 3:
            fly_name = parts[-1]
    elif "FLY" in sym:
        structure = "FLY"
        if len(parts) >= 3:
            fly_name = parts[-1]
    elif len(parts) >= 3:
        structure = "SPREAD"
        spread_name = parts[-1]
    elif len(parts) == 2:
        structure = "SPREAD"
        spread_name = parts[1]
    return structure, spread_name, fly_name


# ── Frozen engine state (live-market, append-only) ───────────────────────────
# Persists the book's runtime so executed trades are immutable across cycles.
ENGINE_STATE_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "bars15_engine_state.json"
)


def _load_engine_state() -> Dict:
    import json
    try:
        if os.path.exists(ENGINE_STATE_FILE):
            with open(ENGINE_STATE_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"bars15: failed to load engine state: {e}")
    return {}


def _save_engine_state(state: Dict) -> None:
    import json
    try:
        os.makedirs(os.path.dirname(ENGINE_STATE_FILE), exist_ok=True)
        with open(ENGINE_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logger.warning(f"bars15: failed to save engine state: {e}")


def run_replay(db_dir: str, starting_equity: float = 0.0) -> Optional[Dict]:
    """Drive the paper book from the 15-min DB as a LIVE, append-only market.

    The DB is treated as a live feed, not a backtest log: candles at or before the
    persisted high-water mark (`last_processed_ts`) have already executed and are
    frozen — they are never re-evaluated. Each cycle only makes new entry/exit
    decisions on candles newer than that mark, and cumulative ticks / peak /
    max-drawdown carry forward monotonically (drawdown can only deepen, never
    recover via recomputation). Indicators still look back over full history, but
    nothing in the past is re-traded. The first run (no saved state) boots the
    market at the earliest candle and replays forward once until it catches up to
    the present, then runs incrementally from then on.

    `starting_equity` is accepted for call-site compatibility but unused — the
    engine accounts purely in ticks.
    """
    from backtesting.engine import DataLoader

    import yfinance as yf
    import pandas as pd
    
    loader = DataLoader(db_dir=db_dir)
    data = loader.load_all_data()
    if not data:
        logger.warning(f"bars15: no contract tables found in {db_dir}")
        return None

    # ── Roll off expired / stale contracts ───────────────────────────────────
    # A futures contract that has stopped updating (expired / past last-trade)
    # must NOT be treated as a live leg. Otherwise an expired front month — e.g.
    # CL_N26 after its ~20th-of-month expiry — stays "M1" forever: it freezes any
    # spread built on it (the WTI-Brent front spread goes stale) and shifts every
    # relative-month index by one versus the other product. Keep only contracts
    # whose last bar is within one day of the newest bar anywhere in the feed.
    try:
        global_max = max(df.index[-1] for df in data.values()
                         if df is not None and not df.empty)
        grace = pd.Timedelta(days=1)
        live = {k: v for k, v in data.items()
                if v is not None and not v.empty and v.index[-1] >= global_max - grace}
        dropped = sorted(set(data) - set(live))
        if dropped:
            logger.info(f"bars15: rolled off {len(dropped)} expired/stale contract(s): {dropped}")
        if live:
            data = live
    except Exception as e:
        logger.warning(f"bars15: stale-contract roll filter failed: {e}")

    # Fetch Macro Data
    logger.info("bars15: fetching macro data...")
    macro_df = pd.DataFrame()
    try:
        vix_hist = yf.Ticker("^VIX").history(period="60d", interval="15m")
        dxy_hist = yf.Ticker("DX-Y.NYB").history(period="60d", interval="15m")
        if not vix_hist.empty and not dxy_hist.empty:
            vix_hist.index = vix_hist.index.tz_localize(None)
            dxy_hist.index = dxy_hist.index.tz_localize(None)
            macro_df = pd.DataFrame(index=vix_hist.index)
            macro_df['vix'] = vix_hist['Close']
            macro_df['dxy'] = dxy_hist['Close']
            macro_df['vix_ma'] = macro_df['vix'].rolling(16).mean()
            macro_df['dxy_ma'] = macro_df['dxy'].rolling(16).mean()
            macro_df['vix_bullish'] = macro_df['vix'] > macro_df['vix_ma']
            macro_df['dxy_bullish'] = macro_df['dxy'] > macro_df['dxy_ma']
    except Exception as e:
        logger.warning(f"bars15: failed to fetch macro data: {e}")

    regimes = _compute_regimes(loader, data)
    specs = _parse_validated_instruments()

    # ── Build per-instrument bar streams + z-score series ────────────────────
    streams: List[Dict] = []
    for spec in specs:
        bars = _build_instrument_bars(loader, data, spec)
        if not bars or len(bars) < WARMUP_BARS + 2:
            continue
        closes = [b[2] for b in bars]
        streams.append({
            "spec": spec,
            "bars": bars,
            "z": _zscore_series(closes),
            "thr": _entry_threshold(regimes.get(spec["base"], {}).get("regime")),
            "regime": regimes.get(spec["base"], {}),
        })

    if not streams:
        return None

    # ── Global chronological event loop (enforces the concurrent cap) ────────
    events: List[Tuple[str, int, int]] = []
    for si, s in enumerate(streams):
        for i in range(1, len(s["bars"])):
            events.append((s["bars"][i][0], si, i))
    events.sort(key=lambda e: (e[0], e[1]))

    # ── Restore frozen engine state (live-market, append-only) ───────────────
    saved = _load_engine_state()
    sym_to_si = {s["spec"]["symbol"]: si for si, s in enumerate(streams)}

    # Per-instrument high-water mark: each instrument trades on its own clock, so
    # freezing the past is keyed per symbol. A laggy instrument whose new bar
    # carries a timestamp older than another instrument's clock must still be
    # processed — a single global mark would skip it forever.
    saved_hwm: Dict[str, str] = dict(saved.get("hwm") or {})
    _legacy_mark = saved.get("last_processed_ts")   # back-compat with old scalar state
    hwm_si: Dict[int, Optional[str]] = {}
    for si, s in enumerate(streams):
        hwm_si[si] = saved_hwm.get(s["spec"]["symbol"], _legacy_mark)
    new_hwm_si: Dict[int, Optional[str]] = dict(hwm_si)

    cum_ticks = float(saved.get("cum_ticks", 0.0))
    peak = float(saved.get("peak", 0.0))
    max_dd = float(saved.get("max_dd", 0.0))
    persisted_closed: List[Dict] = list(saved.get("closed_trades", []))
    pnl_curve: List[float] = list(saved.get("pnl_curve", [0.0])) or [0.0]
    traded_syms: set = set(saved.get("traded", []))   # symbols ever traded (frozen)

    positions: Dict[int, Dict] = {}
    cooldown: Dict[int, int] = {}
    closed_trades: List[Dict] = []   # trades that CLOSE this cycle (incl. rolls)

    def _roll_close(sym: str, pos: Dict, why: str) -> None:
        """Force-close a position whose instrument has rolled/expired.

        When the front contract a position was built on expires (its bar series
        is gone or the entry bar no longer exists), the position cannot be marked
        on a live instrument any longer. A real desk would roll or close it rather
        than carry a phantom open trade, so we realize it at the last price we
        marked it at, charging the normal exit slippage. The realized P&L folds
        into the frozen ledger and the monotonic drawdown like any other close.
        """
        nonlocal cum_ticks, peak, max_dd
        mark = pos.get("last_mark")
        if mark is None:
            logger.warning(f"bars15: cannot roll-close {sym} ({why}) — no last mark, dropping")
            return
        inst_type = pos.get("instrument_type", "spread")
        entry_price = float(pos["entry_price"])
        gross = (float(mark) - entry_price) / TICK_SIZE
        if pos["direction"] == "SHORT":
            gross = -gross
        slip = SLIPPAGE_TICKS.get(inst_type, 2.0)
        pnl_ticks = round(gross - slip, 1)
        cum_ticks = round(cum_ticks + pnl_ticks, 1)
        pnl_curve.append(cum_ticks)
        peak = max(peak, cum_ticks)
        max_dd = max(max_dd, peak - cum_ticks)
        structure, spread_name, fly_name = _structure_fields(sym, inst_type)
        exit_ts = pos.get("last_mark_ts", pos.get("entry_ts", ""))
        closed_trades.append({
            "entry_time": pos["entry_ts"][5:16] if len(pos.get("entry_ts", "")) >= 16 else pos.get("entry_ts", ""),
            "exit_time": exit_ts[5:16] if len(exit_ts) >= 16 else exit_ts,
            "direction": pos["direction"],
            "symbol": sym,
            "structure": structure,
            "spread": spread_name,
            "fly": fly_name,
            "entry": round(entry_price, 4),
            "exit": round(float(mark), 4),
            "target": pos.get("target_price", 0.0),
            "stop": pos.get("stop_price", 0.0),
            "pnl_dollars": pnl_ticks * 10.0,
            "exit_reason": "ROLL",
            "indicator": "ZSCORE",
            "hold_min": _minutes_between(pos.get("entry_ts", ""), exit_ts),
            "pnl": pnl_ticks,
            "duration_h": round(_minutes_between(pos.get("entry_ts", ""), exit_ts) / 60.0, 2),
            "signal": f"Contract roll ({why})",
            "regime": pos.get("regime", "Unknown"),
            "entry_z": pos.get("entry_z", 0.0),
            "exit_z": 0.0,
            "instrument_type": inst_type,
            "slippage_ticks": slip,
        })
        logger.info(f"bars15: roll-closed {sym} at {mark} ({why}), pnl={pnl_ticks} tk")

    # Re-attach carried-open positions to this cycle's freshly-built bar arrays,
    # rolling off any whose instrument has expired since the last cycle.
    for sym, pos in (saved.get("positions") or {}).items():
        si = sym_to_si.get(sym)
        if si is None:
            _roll_close(sym, pos, "instrument no longer live")
            continue
        bars = streams[si]["bars"]
        entry_i = next((k for k in range(len(bars)) if bars[k][0] == pos.get("entry_ts")), None)
        if entry_i is None:
            _roll_close(sym, pos, "entry bar rolled off")
            continue
        p = dict(pos)
        p["entry_i"] = entry_i
        positions[si] = p
    for sym, cd in (saved.get("cooldown") or {}).items():
        si = sym_to_si.get(sym)
        if si is not None:
            cooldown[si] = int(cd)

    open_count = len(positions)
    bars_processed = 0
    last_bar_ts: Optional[str] = events[-1][0] if events else None
    traded: set = set()              # stream indices that opened a trade this cycle

    for ts, si, i in events:
        # Freeze the past: candles at/before THIS instrument's high-water mark
        # already executed and are immutable.
        h = hwm_si.get(si)
        if h is not None and ts <= h:
            continue
        new_hwm_si[si] = ts          # events are time-sorted -> ends as the max
        bars_processed += 1
        if last_bar_ts is None or ts > last_bar_ts:
            last_bar_ts = ts

        s = streams[si]
        z_tuple = s["z"][i - 1]          # signal from the PREVIOUS closed bar
        if z_tuple is None:
            continue
        z_prev, mean_prev, std_prev = z_tuple
        fill = s["bars"][i][1]          # execute at the CURRENT bar's open
        spec = s["spec"]
        pos = positions.get(si)

        if pos is not None:
            bars_held = i - pos["entry_i"]
            reason = None
            if abs(z_prev) > STOP_Z:
                reason = "Stop Loss"
                cooldown[si] = COOLDOWN_BARS
            elif bars_held >= TIMEOUT_BARS:
                # Time stop: a mean-reversion trade that has not reverted within
                # TIMEOUT_BARS is exited at market. Without this, positions are
                # held indefinitely until they revert, which manufactures an
                # unrealistically high win rate by never realizing slow losers.
                reason = "Timeout"
            elif (pos["direction"] == "LONG" and z_prev >= 0) or \
                 (pos["direction"] == "SHORT" and z_prev <= 0):
                reason = "Mean Reversion Complete"

            if reason:
                gross = (fill - pos["entry_price"]) / TICK_SIZE
                if pos["direction"] == "SHORT":
                    gross = -gross
                slip = SLIPPAGE_TICKS.get(spec["type"], 2.0)
                pnl_ticks = round(gross - slip, 1)
                cum_ticks = round(cum_ticks + pnl_ticks, 1)
                pnl_curve.append(cum_ticks)
                peak = max(peak, cum_ticks)
                max_dd = max(max_dd, peak - cum_ticks)
                sym = spec["symbol"]
                # Parse structure components
                parts = sym.split("_")
                structure = "SPREAD" if spec["type"] == "fly" or spec["type"] == "spread" else "FLY" if spec["type"] == "double_fly" else spec["type"].upper()
                spread_name = "-"
                fly_name = "-"
                if "DFLY" in sym:
                    structure = "FLY"
                    if len(parts) >= 3:
                        fly_name = parts[-1]
                elif "FLY" in sym:
                    structure = "FLY"
                    if len(parts) >= 3:
                        fly_name = parts[-1]
                elif len(parts) >= 3:
                    structure = "SPREAD"
                    spread_name = parts[-1]
                elif len(parts) == 2: # e.g. CO_M1M12
                    structure = "SPREAD"
                    spread_name = parts[1]

                # Map signal to user-friendly term
                exit_reason = "TARGET" if reason == "Mean Reversion Complete" else "STOP" if reason == "Stop Loss" else "TIMEOUT"
                
                # Formats like 06-15 14:30
                try:
                    entry_dt = ts[5:16] if len(ts) >= 16 else ts
                    exit_dt = pos["entry_ts"][5:16] if len(pos["entry_ts"]) >= 16 else pos["entry_ts"]
                except:
                    entry_dt = pos["entry_ts"]
                    exit_dt = ts

                closed_trades.append({
                    "entry_time": pos["entry_ts"][5:16] if len(pos["entry_ts"]) >= 16 else pos["entry_ts"],
                    "exit_time": ts[5:16] if len(ts) >= 16 else ts,
                    "direction": pos["direction"],
                    "symbol": sym,
                    "structure": structure,
                    "spread": spread_name,
                    "fly": fly_name,
                    "entry": round(pos["entry_price"], 4),
                    "exit": round(fill, 4),
                    "target": pos.get("target_price", 0.0),
                    "stop": pos.get("stop_price", 0.0),
                    "pnl_dollars": pnl_ticks * 10.0,
                    "exit_reason": exit_reason,
                    "indicator": "ZSCORE",
                    "hold_min": int(bars_held * 15),
                    # Keep older fields for backward compat or backend debugging
                    "pnl": pnl_ticks,               
                    "duration_h": round(bars_held * 0.25, 2),
                    "signal": reason,
                    "regime": s["regime"].get("regime", "Unknown"),
                    "entry_z": pos["entry_z"],
                    "exit_z": round(z_prev, 3),
                    "instrument_type": spec["type"],
                    "slippage_ticks": slip,
                })
                positions.pop(si, None)
                open_count -= 1
        else:
            if cooldown.get(si, 0) > 0:
                cooldown[si] -= 1
                continue
            if abs(z_prev) > s["thr"] and open_count < MAX_CONCURRENT:
                direction = "SHORT" if z_prev > 0 else "LONG"

                # Gap guard: skip entry if signal bar and fill bar are > 2 hours apart.
                # This catches weekend/holiday data gaps where the fill price is
                # completely detached from the signal context (e.g. 06-14 22:00 trade).
                MAX_GAP_SECONDS = 2 * 3600  # 2 hours
                try:
                    signal_ts = s["bars"][i - 1][0]
                    fill_ts = s["bars"][i][0]
                    from datetime import datetime as _dt
                    _t1 = _dt.strptime(signal_ts[:19], "%Y-%m-%d %H:%M:%S")
                    _t2 = _dt.strptime(fill_ts[:19], "%Y-%m-%d %H:%M:%S")
                    if (_t2 - _t1).total_seconds() > MAX_GAP_SECONDS:
                        logger.debug(
                            f"bars15: gap guard skipped entry for {s['spec']['symbol']} at {fill_ts} "
                            f"(gap={(_t2-_t1).total_seconds()/3600:.1f}h since signal at {signal_ts})"
                        )
                        continue
                except Exception:
                    pass
                
                # Evaluate Macro Filter
                try:
                    ts_prev = s["bars"][i - 1][0]
                    dt_prev = pd.to_datetime(ts_prev)
                    if not macro_df.empty:
                        # Use asof to get the most recent macro reading strictly before or at dt_prev
                        # This mathematically eliminates any lookahead bias.
                        idx = macro_df.index.get_indexer([dt_prev], method='pad')[0]
                        if idx != -1:
                            m_row = macro_df.iloc[idx]
                            vix_bullish = bool(m_row['vix_bullish'])
                            dxy_bullish = bool(m_row['dxy_bullish'])
                            
                            # Risk-On Regime (DXY down, VIX down) -> Bullish for oil -> Block Shorts
                            if direction == "SHORT" and not vix_bullish and not dxy_bullish:
                                continue
                            
                            # Risk-Off Regime (DXY up, VIX up) -> Bearish for oil -> Block Longs
                            if direction == "LONG" and vix_bullish and dxy_bullish:
                                continue
                except Exception as e:
                    pass

                # Redundancy guard: never open a structure that is a linear
                # combination of positions already open. e.g. if the M1M2 and
                # M2M3 spreads are open, the M1M2M3 fly is the same bet (fly =
                # spread1 - spread2) and must not be traded again; likewise a
                # double-fly vs its two constituent flies. Keeps the book's risk
                # factors independent and prevents executing the same trade twice.
                cand_vec = _exposure_vector(spec)
                open_vecs = [_exposure_vector(streams[osi]["spec"]) for osi in positions]
                if _in_span(cand_vec, open_vecs):
                    logger.debug(
                        f"bars15: skipped redundant entry {spec['symbol']} "
                        f"(linearly dependent on open book)"
                    )
                    continue

                # Z=0 is mean (target). Z=STOP_Z is stop.
                target_price = mean_prev

                # Profitability guard: the reversion target must clear the
                # round-trip slippage. If the distance from the fill to the mean is
                # not larger than the slippage charged on the trade, the position
                # cannot make money even on a perfect reversion — so skip the signal.
                entry_slip = SLIPPAGE_TICKS.get(spec["type"], 2.0)
                target_ticks = abs(fill - target_price) / TICK_SIZE
                if target_ticks <= entry_slip:
                    logger.debug(
                        f"bars15: skipped {spec['symbol']} — target {target_ticks:.1f} tk "
                        f"<= slippage {entry_slip} tk"
                    )
                    continue

                if direction == "LONG":
                    stop_price = mean_prev - (STOP_Z * std_prev)
                else:
                    stop_price = mean_prev + (STOP_Z * std_prev)

                positions[si] = {
                    "entry_price": fill,
                    "direction": direction,
                    "entry_i": i,
                    "entry_ts": ts,
                    "entry_z": round(z_prev, 3),
                    "target_price": round(target_price, 4),
                    "stop_price": round(stop_price, 4),
                }
                open_count += 1
                traded.add(si)

    # ── Carry still-open positions (unrealized ticks vs last close) ──────────
    open_positions: List[Dict] = []
    persist_positions: Dict[str, Dict] = {}
    for si, pos in positions.items():
        s = streams[si]
        spec = s["spec"]
        last_close = s["bars"][-1][2]
        gross = (last_close - pos["entry_price"]) / TICK_SIZE
        if pos["direction"] == "SHORT":
            gross = -gross
        open_positions.append({
            "symbol": spec["symbol"],
            "direction": pos["direction"],
            "entry_price": round(pos["entry_price"], 4),
            "current_price": round(last_close, 4),
            "pnl": round(gross, 1),                 # unrealized TICKS
            "duration_h": round((len(s["bars"]) - 1 - pos["entry_i"]) * 0.25, 2),
            "instrument_type": spec["type"],
            "entry_z": pos["entry_z"],
            "entry_time": _ts_to_epoch(pos["entry_ts"]),
            "base_sym": spec["base"],
            "is_manual": False,
        })
        # Freeze the open position by symbol so it survives the next rebuild.
        # `last_mark`/`last_mark_ts` let us fairly price a forced roll-close if the
        # instrument expires before the position exits normally.
        persist_positions[spec["symbol"]] = {
            "entry_price": pos["entry_price"],
            "direction": pos["direction"],
            "entry_ts": pos["entry_ts"],
            "entry_z": pos["entry_z"],
            "target_price": pos.get("target_price", 0.0),
            "stop_price": pos.get("stop_price", 0.0),
            "instrument_type": spec["type"],
            "regime": s["regime"].get("regime", "Unknown"),
            "last_mark": round(last_close, 4),
            "last_mark_ts": s["bars"][-1][0],
        }

    # Fold this cycle's new trades into the frozen ledger (append-only).
    traded_syms |= {streams[si]["spec"]["symbol"] for si in traded}
    all_closed = persisted_closed + closed_trades
    persist_cooldown = {
        streams[si]["spec"]["symbol"]: cd for si, cd in cooldown.items() if cd > 0
    }
    # Persist each instrument's own high-water mark.
    persist_hwm = {
        streams[si]["spec"]["symbol"]: h for si, h in new_hwm_si.items() if h is not None
    }

    _save_engine_state({
        "hwm": persist_hwm,
        "last_processed_ts": last_bar_ts,
        "cum_ticks": round(cum_ticks, 1),
        "peak": round(peak, 1),
        "max_dd": round(max_dd, 1),
        "closed_trades": all_closed[-1000:],
        "pnl_curve": pnl_curve[-2000:],
        "traded": sorted(traded_syms),
        "positions": persist_positions,
        "cooldown": persist_cooldown,
    })

    unrealized = round(sum(p["pnl"] for p in open_positions), 1)
    return {
        "closed_trades": all_closed[-200:],
        "open_positions": open_positions,
        "pnl_curve_ticks": pnl_curve[-1000:],
        "realized_pnl_ticks": round(cum_ticks, 1),
        "unrealized_pnl_ticks": unrealized,
        "total_pnl_ticks": round(cum_ticks + unrealized, 1),
        "max_drawdown_ticks": round(max_dd, 1),
        "max_concurrent": MAX_CONCURRENT,
        "bars_processed": bars_processed,
        "instruments_traded": len(traded_syms),
        "last_bar_ts": last_bar_ts,
    }
