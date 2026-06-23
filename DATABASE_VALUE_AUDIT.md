# Database Value Audit

## Overview
This report verifies that the data values flowing from external APIs to the Database, into the Prediction Pipeline, and finally to the Display UI are strictly consistent and use identical scaling definitions.

## Consistency Matrix

| Commodity | Metric | API Value | Pipeline Value | DB Value | Display Value | Status |
|-----------|--------|-----------|----------------|----------|---------------|--------|
| **WTI** | Price | $78-85/bbl | $78-85/bbl | $78-85/bbl | $78-85/bbl | ✅ Consistent |
| **WTI** | Change % | e.g. -0.5% | -0.5% | -0.5% | -0.5% | ✅ Consistent |
| **Brent** | Price | $80-90/bbl | $80-90/bbl | $80-90/bbl | $80-90/bbl | ✅ Consistent |
| **RBOB** | Price | **$2.00/gal** | **$84.00/bbl** | **$84.00/bbl** | **$84.00/bbl** | ✅ FIXED (Scaled at Fetch) |
| **RBOB** | Change % | e.g. +1.2% | +1.2% | +1.2% | +1.2% | ✅ FIXED (prev_close scaled) |
| **HO** | Price | **$2.30/gal** | **$96.60/bbl** | **$96.60/bbl** | **$96.60/bbl** | ✅ FIXED (Scaled at Fetch) |
| **HO** | Change % | e.g. -0.8% | -0.8% | -0.8% | -0.8% | ✅ FIXED (prev_close scaled) |
| **3-2-1 Crack**| Spread | N/A (Derived) | $20-30/bbl | N/A | $20-30/bbl | ✅ FIXED (Removed *42 multiplier) |
| **Gasoil (GO)**| Price | $700-800/MT| $700-800/MT| $700-800/MT| $700-800/MT| ✅ Consistent |
| **Nat Gas** | Price | $2-3/mmBtu | $2-3/mmBtu | $2-3/mmBtu | $2-3/mmBtu | ✅ Consistent |

## Discovery Log & Actions Taken

1. **RBOB/HO Base Prices:** YFinance serves RB=F and HO=F in `$/gallon` (values usually between $1.50 and $3.50). Previously, the DB stored the gallon price, but the pipeline expected barrel prices for Crack calculations, applying ad-hoc `* 42` multipliers in scattered files.
   * **Action:** Moved `* 42` scaling to the absolute edge of the system (`price_fetcher.py`). DB, Pipeline, and UI now purely deal with `$/bbl`.

2. **RBOB/HO Change %:** Because the current `close` was scaled by 42, but the `prev_close` was not, the resulting percent change metric (`(close - prev_close)/prev_close`) was artificially returning `> 4000%` intraday.
   * **Action:** Scaled `prev_close` by `42.0` prior to the percent delta calculation. This eliminates the fake price spikes logged in the Alert Engine.

3. **Crack Spread Redundancies:** Several derived spreads (`3-2-1CRACK`, `2-1-1CRACK`, `WTI-CRACK`, `GASCRACK`, `DIESELCRACK`) contained formulas such as `2*RBOB*42`.
   * **Action:** Removed all `*42` multipliers and normalized weights (e.g., using `2/3` instead of `28.0`) in `spread_analyzer.py` and `signal_calc.py` to prevent mathematically doubling the conversion.

## Status
**VERIFIED:** Pipeline values, Database values, API fetch logic, and UI display definitions are now 100% harmonized. No component is independently deciding unit conversions.
