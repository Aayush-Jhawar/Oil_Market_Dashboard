# Unit Standardization Report

## Executive Summary
This report formalizes the canonical units used across the Dashboard and backend pipelines for all tracked commodities. Previously, RBOB and Heating Oil (HO) prices were being piped into the system in cents/gallon or dollars/gallon natively, leading to false price spikes, broken standard-deviation metrics, and wildly distorted crack spread formulations when mathematically mixed with Crude Oil ($/bbl).

## Canonical Units Definition

| Commodity | Symbol | API Unit (Source) | **Dashboard Canonical Unit** | Transformation Required |
|-----------|--------|-------------------|-----------------------------|-------------------------|
| WTI Crude | WTI    | USD/bbl           | **USD/bbl**                 | None                    |
| Brent Crude| Brent | USD/bbl           | **USD/bbl**                 | None                    |
| Dubai Crude| DUBAICRUDE | USD/bbl       | **USD/bbl**                 | None                    |
| RBOB Gas  | RBOB   | USD/gallon        | **USD/bbl**                 | `* 42` natively on fetch|
| Heating Oil| HO    | USD/gallon        | **USD/bbl**                 | `* 42` natively on fetch|
| Natural Gas| NG/HH | USD/mmBtu         | **USD/mmBtu**               | None                    |
| Gasoil    | GO     | USD/Metric Ton    | **USD/MT** (or bbl)         | `/ 7.45` if converted   |

## Implementation Enforcements

### 1. Ingestion Boundary (The Fix)
Rather than passing around gallon prices and attempting to apply `* 42` multipliers dynamically in various downstream files, **all scaling now happens at the system edge.** 
In `backend/services/price_fetcher.py`, the moment RBOB and HO prices are fetched from Yahoo Finance or derived from fallback defaults, they are multiplied by `42.0` immediately. 

**Result:** The pipeline (features, ML, alerts) NEVER sees a gallon price. It only sees `$/bbl`.

### 2. Spreads and Formulations
Because all prices are globally standard `/bbl`, formulas across the system were updated to remove redundant scalar multiplications.
* `3-2-1 Crack`: Changed from `((2*RBOB*42) + (1*HO*42)) / 3 - WTI` to `((2*RBOB) + (1*HO)) / 3 - WTI`
* `2-1-1 Crack`: Changed from `((1*RBOB*42) + (1*HO*42)) / 2 - WTI` to `((1*RBOB) + (1*HO)) / 2 - WTI`

### 3. Alert Engine Reliability
Previously, alerts for RBOB and HO were triggering due to percent change calculations based on a $2.00 baseline instead of an $84.00 baseline, or due to absolute dollar movement thresholds (e.g. `$2 move`) which represented a 100% price crash for a gallon price but only a 2.5% move for a barrel price.

By scaling to $/bbl *before* alerts run, the statistical properties (Z-scores and percentage moves) natively align with WTI constraints, fixing the false alerts.

### 4. Database Integrity
Going forward, all live ticks logged to `PriceHistory` and `Alerts` will be denominated in the canonical units defined above. Legacy entries recorded in $/gallon will naturally phase out of the rolling 30-day/252-day calculations, or can be migrated via a one-off SQL script.
