import json
import os
import time
from typing import Dict, List, Any, Optional, Set, Tuple
from services.price_fetcher import PriceFetcher
from signal_calc import SignalCalculator
from services.regime_classifier import regime_classifier
from services.zscore_strategy import zscore_strategy
from services.forward_curve import get_curve_as_dict

# ---------------------------------------------------------------------------
# Exchange-Compliant Instrument Registry
# ---------------------------------------------------------------------------
INSTRUMENT_REGISTRY: Dict[str, Dict[str, Any]] = {
    # ── Outrights ─────────────────────────────────────────────────────────
    "WTI":   {"type": "outright", "legs": [("M1", 1)], "total_lots": 1, "margin_credit": 0.0,  "multiplier": 1000},
    "Brent": {"type": "outright", "legs": [("M1", 1)], "total_lots": 1, "margin_credit": 0.0,  "multiplier": 1000},
    "RBOB":  {"type": "outright", "legs": [("M1", 1)], "total_lots": 1, "margin_credit": 0.0,  "multiplier": 1000},
    "HO":    {"type": "outright", "legs": [("M1", 1)], "total_lots": 1, "margin_credit": 0.0,  "multiplier": 1000},
    "NG":    {"type": "outright", "legs": [("M1", 1)], "total_lots": 1, "margin_credit": 0.0,  "multiplier": 10000},
    "GO":    {"type": "outright", "legs": [("M1", 1)], "total_lots": 1, "margin_credit": 0.0,  "multiplier": 1000},

    # ── Calendar Spreads (equidistant, 2 lots: 1+1) ──────────────────────
    "WTI_CAL_SPREAD":   {"type": "spread", "legs": [("M1", 1), ("M2", 1)], "total_lots": 2, "margin_credit": 0.90, "multiplier": 1000, "shared_months": {"WTI": [1, 2]}},
    "BRENT_CAL_SPREAD": {"type": "spread", "legs": [("M1", 1), ("M2", 1)], "total_lots": 2, "margin_credit": 0.90, "multiplier": 1000, "shared_months": {"Brent": [1, 2]}},
    "RBOB_CAL_SPREAD":  {"type": "spread", "legs": [("M1", 1), ("M2", 1)], "total_lots": 2, "margin_credit": 0.90, "multiplier": 1000, "shared_months": {"RBOB": [1, 2]}},
    "HO_CAL_SPREAD":    {"type": "spread", "legs": [("M1", 1), ("M2", 1)], "total_lots": 2, "margin_credit": 0.90, "multiplier": 1000, "shared_months": {"HO": [1, 2]}},

    # ── Flies (equidistant, 4 lots: 1+2+1) ───────────────────────────────
    "WTI_FLY":   {"type": "fly", "legs": [("M1", 1), ("M2", 2), ("M3", 1)], "total_lots": 4, "margin_credit": 0.95, "multiplier": 1000, "shared_months": {"WTI": [1, 2, 3]}},
    "BRENT_FLY": {"type": "fly", "legs": [("M1", 1), ("M2", 2), ("M3", 1)], "total_lots": 4, "margin_credit": 0.95, "multiplier": 1000, "shared_months": {"Brent": [1, 2, 3]}},
    "RBOB_FLY":  {"type": "fly", "legs": [("M1", 1), ("M2", 2), ("M3", 1)], "total_lots": 4, "margin_credit": 0.95, "multiplier": 1000, "shared_months": {"RBOB": [1, 2, 3]}},
    "HO_FLY":    {"type": "fly", "legs": [("M1", 1), ("M2", 2), ("M3", 1)], "total_lots": 4, "margin_credit": 0.95, "multiplier": 1000, "shared_months": {"HO": [1, 2, 3]}},

    # ── Double Flies (equidistant, 8 lots: 1+3+3+1) ──────────────────────
    "WTI_DFLY":   {"type": "double_fly", "legs": [("M1", 1), ("M2", 3), ("M3", 3), ("M4", 1)], "total_lots": 8, "margin_credit": 0.95, "multiplier": 1000, "shared_months": {"WTI": [1, 2, 3, 4]}},
    "BRENT_DFLY": {"type": "double_fly", "legs": [("M1", 1), ("M2", 3), ("M3", 3), ("M4", 1)], "total_lots": 8, "margin_credit": 0.95, "multiplier": 1000, "shared_months": {"Brent": [1, 2, 3, 4]}},
    "RBOB_DFLY":  {"type": "double_fly", "legs": [("M1", 1), ("M2", 3), ("M3", 3), ("M4", 1)], "total_lots": 8, "margin_credit": 0.95, "multiplier": 1000, "shared_months": {"RBOB": [1, 2, 3, 4]}},
    "HO_DFLY":    {"type": "double_fly", "legs": [("M1", 1), ("M2", 3), ("M3", 3), ("M4", 1)], "total_lots": 8, "margin_credit": 0.95, "multiplier": 1000, "shared_months": {"HO": [1, 2, 3, 4]}},

    # ── Crack Spreads (3 lots: 2 product + 1 crude, or 1+1+1) ────────────
    "3-2-1CRACK":  {"type": "crack", "legs": [("RBOB", 2), ("HO", 1), ("WTI", 3)], "total_lots": 3, "margin_credit": 0.85, "multiplier": 1000},
    "GASCRACK":    {"type": "crack", "legs": [("RBOB", 1), ("WTI", 1)],           "total_lots": 2, "margin_credit": 0.85, "multiplier": 1000},
    "DIESELCRACK": {"type": "crack", "legs": [("HO", 1), ("WTI", 1)],             "total_lots": 2, "margin_credit": 0.85, "multiplier": 1000},

    # ── Relative Value / Inter-Commodity Spreads ──────────────────────────
    "WTI-Brent": {"type": "rv", "legs": [("WTI", 1), ("Brent", 1)], "total_lots": 2, "margin_credit": 0.80, "multiplier": 1000},
    "DUB-WTI":   {"type": "rv", "legs": [("DUBAICRUDE", 1), ("WTI", 1)], "total_lots": 2, "margin_credit": 0.70, "multiplier": 1000},
}

_PREFERENCE_ORDER = {"double_fly": 4, "fly": 3, "spread": 2, "crack": 2, "rv": 2, "outright": 1}

def _get_registry_entry(symbol: str) -> Dict[str, Any]:
    if symbol in INSTRUMENT_REGISTRY:
        return INSTRUMENT_REGISTRY[symbol]
        
    if "_DFLY_" in symbol or "_FLY_" in symbol:
        parts = symbol.split("_")
        base = parts[0]
        is_dfly = "DFLY" in parts[1]
        try:
            months = [int(p) for p in parts[2:]]
            if is_dfly and len(months) == 4:
                return {
                    "type": "double_fly", 
                    "legs": [(f"M{m}", 1 if i in (0,3) else 3) for i, m in enumerate(months)],
                    "total_lots": 8, "margin_credit": 0.95, "multiplier": 1000,
                    "shared_months": {base: months}
                }
            elif not is_dfly and len(months) == 3:
                return {
                    "type": "fly", 
                    "legs": [(f"M{m}", 1 if i in (0,2) else 2) for i, m in enumerate(months)],
                    "total_lots": 4, "margin_credit": 0.95, "multiplier": 1000,
                    "shared_months": {base: months}
                }
        except ValueError:
            pass
    return {}

def _get_leg_fingerprint(symbol: str) -> Set[Tuple[str, int]]:
    reg = _get_registry_entry(symbol)
    shared = reg.get("shared_months", {})
    result = set()
    for underlying, months in shared.items():
        for m in months:
            result.add((underlying, m))
    return result

def _has_leg_overlap(sym_a: str, sym_b: str) -> bool:
    fp_a = _get_leg_fingerprint(sym_a)
    fp_b = _get_leg_fingerprint(sym_b)
    if not fp_a or not fp_b:
        return False
    return bool(fp_a & fp_b)

class PaperTradingBook:
    def __init__(self, state_file: str = "paper_state.json"):
        self.state_file = state_file
        self.equity = float(os.getenv("PAPER_STARTING_EQUITY", "100000"))
        self.starting_equity = self.equity
        self.signal_threshold = float(os.getenv("PAPER_SIGNAL_THRESHOLD", "0.3"))
        
        self.open_positions: List[Dict[str, Any]] = []
        self.closed_trades: List[Dict[str, Any]] = []
        # Performance is accounted purely in TICKS (1 tick = $0.01). There is no
        # capital / equity / return-% concept — with no capital cap those ratios
        # are meaningless. pnl_curve_ticks is the cumulative realized tick curve.
        self.pnl_curve_ticks: List[float] = [0.0]
        self.realized_pnl_ticks = 0.0
        self.max_drawdown_ticks = 0.0
        self.max_concurrent = int(os.getenv("PAPER_MAX_CONCURRENT", "12"))

        # Legacy dollar fields retained only for the (unused) manual process_tick
        # path; not reported by get_state.
        self.equity_curve: List[float] = [self.equity]
        self.peak_equity = self.equity
        self.max_drawdown = 0.0

        self.daily_pnl = 0.0
        self.streak_losses: Dict[str, int] = {}
        self.instrument_paused: Dict[str, bool] = {}
        # Telemetry describing the 15-min candle replay that last drove the book.
        self.bars_processed = 0
        self.instruments_traded = 0
        self.last_bar_ts: Optional[str] = None
        # Calendar day (UTC) the daily counters belong to. Used to reset the
        # daily loss-limit / streak-pause kill-switches at the day boundary so
        # they behave as "daily" controls rather than permanent freezes.
        self.current_day = self._today_str()

        self.load_state()

    @staticmethod
    def _today_str(ts: Optional[float] = None) -> str:
        if ts is None:
            ts = time.time()
        return time.strftime("%Y-%m-%d", time.gmtime(ts))

    def _maybe_roll_day(self, current_time: float = None):
        """Reset daily kill-switches when the calendar day changes."""
        day = self._today_str(current_time)
        if day != self.current_day:
            self.current_day = day
            self.daily_pnl = 0.0
            self.streak_losses = {}
            self.instrument_paused = {}

    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    self.open_positions = data.get("open_positions", [])
                    self.closed_trades = data.get("closed_trades", [])
                    self.pnl_curve_ticks = data.get("pnl_curve_ticks", [0.0]) or [0.0]
                    self.realized_pnl_ticks = data.get("realized_pnl_ticks", 0.0)
                    self.max_drawdown_ticks = data.get("max_drawdown_ticks", 0.0)
                    self.max_concurrent = data.get("max_concurrent", self.max_concurrent)
                    self.bars_processed = data.get("bars_processed", 0)
                    self.instruments_traded = data.get("instruments_traded", 0)
                    self.last_bar_ts = data.get("last_bar_ts")
                    # Restore daily kill-switch state so a process restart does not
                    # silently wipe the daily loss limit / instrument pauses.
                    self.daily_pnl = data.get("daily_pnl", 0.0)
                    self.streak_losses = data.get("streak_losses", {})
                    self.instrument_paused = data.get("instrument_paused", {})
                    self.current_day = data.get("current_day", self.current_day)
                    # If the persisted day is stale, roll counters forward immediately.
                    self._maybe_roll_day()
            except Exception as e:
                print(f"Error loading paper state: {e}")

    def save_state(self):
        try:
            with open(self.state_file, "w") as f:
                json.dump({
                    "open_positions": self.open_positions,
                    "closed_trades": self.closed_trades,
                    "pnl_curve_ticks": self.pnl_curve_ticks,
                    "realized_pnl_ticks": self.realized_pnl_ticks,
                    "max_drawdown_ticks": self.max_drawdown_ticks,
                    "max_concurrent": self.max_concurrent,
                    "bars_processed": self.bars_processed,
                    "instruments_traded": self.instruments_traded,
                    "last_bar_ts": self.last_bar_ts,
                    "daily_pnl": self.daily_pnl,
                    "streak_losses": self.streak_losses,
                    "instrument_paused": self.instrument_paused,
                    "current_day": self.current_day,
                }, f)
        except Exception as e:
            print(f"Error saving paper state: {e}")

        # Auto-export closed trades to CSV so the log file is always current
        try:
            import csv
            csv_file = self.state_file.replace(".json", "_log.csv")
            closed = self.closed_trades
            if closed:
                all_keys: list = []
                seen: set = set()
                for trade in closed:
                    for k in trade.keys():
                        if k not in seen:
                            all_keys.append(k)
                            seen.add(k)
                with open(csv_file, "w", newline="") as cf:
                    writer = csv.DictWriter(cf, fieldnames=all_keys, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(closed)
        except Exception as e:
            print(f"Error saving paper trade CSV: {e}")


    def _recalc_max_drawdown(self):
        self.max_drawdown = 0.0
        peak = self.equity_curve[0] if self.equity_curve else self.starting_equity
        for eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0
            if dd > self.max_drawdown:
                self.max_drawdown = dd

    def _would_create_duplicate(self, candidate_symbol: str) -> bool:
        for pos in self.open_positions:
            if pos.get("closed"):
                continue
            existing_sym = pos["symbol"]
            if existing_sym == candidate_symbol:
                return True
            if _has_leg_overlap(candidate_symbol, existing_sym):
                return True
        return False

    def process_tick(self, current_prices: Dict[str, float], signals: Dict[str, float], current_time: float = None):
        if current_time is None:
            current_time = time.time()

        # Reset daily loss-limit / streak-pause controls at the day boundary.
        self._maybe_roll_day(current_time)

        unrealized_pnl = 0.0
        
        # ── Compute Regimes ──
        regime_info_map = {}
        for base in ["WTI", "Brent", "HO", "GO"]:
            try:
                curve = get_curve_as_dict(base)
                numeric_curve = {int(k[1:]): v for k, v in curve.items() if k.startswith("M") and k[1:].isdigit()}
                regime_info_map[base] = regime_classifier.classify(base, numeric_curve)
            except Exception:
                pass
        
        # ── Process Existing Positions ──
        for pos in self.open_positions:
            sym = pos["symbol"]
            base_sym = sym.split("_")[0]
            if base_sym.upper() == "BRENT": base_sym = "Brent"
            
            if sym in current_prices:
                pos["current_price"] = current_prices[sym]
                
                price_diff = pos["current_price"] - pos["entry_price"]
                if pos["direction"] == "SHORT":
                    price_diff = -price_diff
                    
                reg = _get_registry_entry(sym)
                mult = reg.get("multiplier", 1000)
                pos["pnl"] = price_diff * pos.get("units", 1.0) * mult
                pos["duration_h"] = (current_time - pos["entry_time"]) / 3600.0
                unrealized_pnl += pos["pnl"]
                
                # Check for validated Z-Score execution
                if zscore_strategy._is_validated(sym):
                    regime_info = regime_info_map.get(base_sym, {})
                    res = zscore_strategy.tick(sym, pos["current_price"], pos, regime_info)
                    
                    if res["action"] == zscore_strategy.SIGNAL_EXIT:
                        self.close_position(pos, "Mean Reversion Complete", current_time, exit_z=res["z_score"])
                    elif res["action"] == zscore_strategy.SIGNAL_STOP:
                        self.close_position(pos, "Stop Loss", current_time, exit_z=res["z_score"])
                    elif res["action"] == zscore_strategy.SIGNAL_TIMEOUT_EXIT:
                        self.close_position(pos, "Timeout", current_time, exit_z=res["z_score"])
                else:
                    # Legacy Logic Bounds
                    sl = pos.get("stop_loss_price")
                    tp = pos.get("take_profit_price")
                    sl_hit = False
                    tp_hit = False
                    if pos["direction"] == "LONG":
                        if sl and pos["current_price"] <= sl: sl_hit = True
                        if tp and pos["current_price"] >= tp: tp_hit = True
                    else:
                        if sl and pos["current_price"] >= sl: sl_hit = True
                        if tp and pos["current_price"] <= tp: tp_hit = True
                        
                    if sl_hit:
                        self.close_position(pos, "Stop Loss Hit", current_time)
                    elif tp_hit:
                        self.close_position(pos, "Take Profit Hit", current_time)
                    else:
                        signal = signals.get(sym, 0.0)
                        exit_long = pos["direction"] == "LONG" and signal < -0.2
                        exit_short = pos["direction"] == "SHORT" and signal > 0.2
                        if exit_long or exit_short:
                            self.close_position(pos, "Signal Weakened/Reversed", current_time)

        self.open_positions = [p for p in self.open_positions if not p.get("closed", False)]
        
        # ── Process New Signals ──
        # Process validated Z-Score pairs first
        for sym, price in current_prices.items():
            if any(p["symbol"] == sym for p in self.open_positions):
                continue
            if self._would_create_duplicate(sym):
                continue
                
            base_sym = sym.split("_")[0]
            if base_sym.upper() == "BRENT": base_sym = "Brent"
            
            if zscore_strategy._is_validated(sym):
                regime_info = regime_info_map.get(base_sym, {})
                res = zscore_strategy.tick(sym, price, None, regime_info)
                
                if res["action"] == zscore_strategy.SIGNAL_LONG:
                    self.open_position(sym, "LONG", price, res["threshold"], current_time, entry_z=res["z_score"])
                elif res["action"] == zscore_strategy.SIGNAL_SHORT:
                    self.open_position(sym, "SHORT", price, res["threshold"], current_time, entry_z=res["z_score"])

        # Process legacy signals
        def _signal_priority(sym_sig):
            sym, sig = sym_sig
            reg = _get_registry_entry(sym)
            return _PREFERENCE_ORDER.get(reg.get("type", "outright"), 1)
        
        sorted_signals = sorted(signals.items(), key=_signal_priority, reverse=True)
        for sym, signal in sorted_signals:
            if sym not in current_prices or zscore_strategy._is_validated(sym):
                continue
            if any(p["symbol"] == sym for p in self.open_positions):
                continue
            if self._would_create_duplicate(sym):
                continue
                
            if signal > self.signal_threshold:
                self.open_position(sym, "LONG", current_prices[sym], signal, current_time)
            elif signal < -self.signal_threshold:
                self.open_position(sym, "SHORT", current_prices[sym], signal, current_time)

        # Update equity curve
        current_total_equity = self.equity + unrealized_pnl
        _denom = abs(current_total_equity) if current_total_equity != 0 else 1.0
        if not self.equity_curve or abs(self.equity_curve[-1] - current_total_equity) / _denom > 0.0001:
            self.equity_curve.append(current_total_equity)
            if len(self.equity_curve) > 1000:
                self.equity_curve = self.equity_curve[-1000:]
            
            if current_total_equity > self.peak_equity:
                self.peak_equity = current_total_equity
            
            dd = (self.peak_equity - current_total_equity) / self.peak_equity if self.peak_equity > 0 else 0
            if dd > self.max_drawdown:
                self.max_drawdown = dd
                
            self.save_state()

    def open_position(self, symbol: str, direction: str, price: float, signal_val: float, current_time: float, entry_z: float = 0.0, custom_units: float = None, custom_sl: float = None, custom_tp: float = None, is_manual: bool = False):
        # Reset daily controls if the calendar day rolled over since the last action.
        self._maybe_roll_day(current_time)

        # Risk Limits — cap concurrent positions across the whole book.
        if len([p for p in self.open_positions if not p.get("closed")]) >= self.max_concurrent:
            return

        # Daily loss limit, denominated in ticks.
        if self.daily_pnl <= -2000:
            return

        if self.instrument_paused.get(symbol, False):
            return

        reg = _get_registry_entry(symbol)
        total_lots = reg.get("total_lots", 1)
        mult = reg.get("multiplier", 1000)
        inst_type = reg.get("type", "outright")

        # Universal lot sizing: 1 structure unit by default, honoring a manual override.
        units = float(custom_units) if custom_units else 1.0

        sl_price, tp_price = None, None
        if not zscore_strategy._is_validated(symbol):
            atr = max(abs(price) * 0.02, 0.05)
            sl_dist = 1.5 * atr
            tp_dist = 3.0 * atr
            sl_price = price - sl_dist if direction == "LONG" else price + sl_dist
            tp_price = price + tp_dist if direction == "LONG" else price - tp_dist
            if custom_sl is not None: sl_price = custom_sl
            if custom_tp is not None: tp_price = custom_tp

        self.open_positions.append({
            "symbol": symbol,
            "direction": direction,
            "entry_price": price,
            "current_price": price,
            "stop_loss_price": sl_price,
            "take_profit_price": tp_price,
            "units": units,
            "total_lots": total_lots,
            "instrument_type": inst_type,
            "size_usd": abs(units * price * mult),
            "pnl": 0.0,
            "entry_time": current_time,
            "duration_h": 0.0,
            "signal": f"{signal_val:.2f}",
            "is_manual": is_manual,
            "entry_z": entry_z,
            "base_sym": symbol.split("_")[0]
        })

    def close_position(self, pos: Dict[str, Any], exit_reason: str, current_time: float, exit_z: float = 0.0):
        inst_type = pos.get("instrument_type", "outright")

        # Slippage in TICKS (1 tick per leg crossed).
        slippage_ticks_map = {"spread": 2.0, "fly": 4.0, "double_fly": 8.0, "crack": 3.0, "outright": 1.0}
        slippage = slippage_ticks_map.get(inst_type, 1.0)

        # P&L in TICKS (1 tick = $0.01); nothing multiplied by a contract size.
        gross_ticks = (pos.get("current_price", pos["entry_price"]) - pos["entry_price"]) / 0.01
        if pos["direction"] == "SHORT":
            gross_ticks = -gross_ticks
        final_pnl = round(gross_ticks - slippage, 1)
        self.realized_pnl_ticks = round(self.realized_pnl_ticks + final_pnl, 1)
        self.pnl_curve_ticks.append(self.realized_pnl_ticks)
        self.daily_pnl += final_pnl
        pos["closed"] = True

        sym = pos["symbol"]
        if final_pnl < 0:
            self.streak_losses[sym] = self.streak_losses.get(sym, 0) + 1
            if self.streak_losses[sym] >= 3:
                self.instrument_paused[sym] = True
                print(f"HUMAN_REVIEW_REQUIRED: 3-loss streak on {sym}")
        else:
            self.streak_losses[sym] = 0

        base_sym = pos.get("base_sym", "WTI")
        if base_sym.upper() == "BRENT": base_sym = "Brent"
        regime = regime_classifier.state.get(base_sym, {}).get("current_regime", "Unknown")

        # Lowercase keys to match the frontend trade-log schema
        # (symbol/direction/entry/exit/pnl/duration_h/signal).
        self.closed_trades.append({
            "symbol": sym,
            "direction": pos["direction"],
            "entry": pos["entry_price"],
            "exit": pos["current_price"],
            "pnl": final_pnl,
            "duration_h": (current_time - pos["entry_time"]) / 3600.0,
            "signal": exit_reason,
            "regime": regime,
            "entry_z": pos.get("entry_z", 0.0),
            "exit_z": exit_z,
            "instrument_type": inst_type,
            "slippage_ticks": slippage,
        })
        
        if len(self.closed_trades) > 200:
            self.closed_trades = self.closed_trades[-200:]

    def apply_replay(self, state: Dict[str, Any]):
        """Ingest a deterministic replay produced from the 15-min candle DB.

        The 15-min engine rebuilds the full strategy ledger each cycle, so this
        overwrites the strategy-driven book with the replay result and persists it.
        Manual positions (is_manual) opened via the API are preserved and carried
        forward so a manual trade is not wiped by the next replay cycle.
        """
        manual_positions = [p for p in self.open_positions if p.get("is_manual")]

        self.open_positions = list(state.get("open_positions", [])) + manual_positions
        self.closed_trades = list(state.get("closed_trades", []))
        self.pnl_curve_ticks = list(state.get("pnl_curve_ticks", [0.0])) or [0.0]
        self.realized_pnl_ticks = float(state.get("realized_pnl_ticks", 0.0))
        self.max_drawdown_ticks = float(state.get("max_drawdown_ticks", 0.0))
        self.max_concurrent = int(state.get("max_concurrent", self.max_concurrent))

        # Telemetry: which candles drove this book.
        self.bars_processed = int(state.get("bars_processed", 0))
        self.instruments_traded = int(state.get("instruments_traded", 0))
        self.last_bar_ts = state.get("last_bar_ts")

        self.save_state()

    def close_position_by_symbol(self, symbol: str, exit_reason: str = "Manual Close", current_time: float = None):
        if current_time is None:
            current_time = time.time()
        for pos in self.open_positions:
            if pos["symbol"] == symbol and not pos.get("closed", False):
                self.close_position(pos, exit_reason, current_time)
        self.open_positions = [p for p in self.open_positions if not p.get("closed", False)]
        self.save_state()

    def get_state(self) -> Dict[str, Any]:
        # Everything is in TICKS. No sharpe, no equity, no return-% (no capital cap).
        closed = self.closed_trades
        realized_ticks = round(sum(t.get("pnl", 0.0) for t in closed), 1)
        unrealized_ticks = round(sum(p.get("pnl", 0.0) for p in self.open_positions), 1)

        valid_trades = [t for t in closed if t.get("pnl", 0.0) != 0]
        wins = sum(1 for t in valid_trades if t.get("pnl", 0.0) > 0)
        win_rate = (wins / len(valid_trades) * 100) if valid_trades else 0.0

        open_count = len([p for p in self.open_positions if not p.get("closed")])

        return {
            "total_pnl_ticks": round(realized_ticks + unrealized_ticks, 1),
            "realized_pnl_ticks": realized_ticks,
            "unrealized_pnl_ticks": unrealized_ticks,
            "win_rate": win_rate,
            "max_drawdown_ticks": round(getattr(self, "max_drawdown_ticks", 0.0), 1),
            "open_count": open_count,
            "max_concurrent": getattr(self, "max_concurrent", 12),
            "total_trades": len(closed),
            "open_positions": self.open_positions,
            "closed_trades": closed,
            "pnl_curve_ticks": getattr(self, "pnl_curve_ticks", [0.0]),
            "bars_processed": getattr(self, "bars_processed", 0),
            "instruments_traded": getattr(self, "instruments_traded", 0),
            "last_bar_ts": getattr(self, "last_bar_ts", None),
            "data_source": "bars_15min_latest.db",
        }

paper_book = PaperTradingBook()
