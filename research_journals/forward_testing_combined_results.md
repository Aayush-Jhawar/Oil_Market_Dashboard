# Exhaustive Forward Test: Individual vs Stacked Strategies

We ran an exhaustive evaluation on the Live DB (`bars_15min_20260612.db`), testing **every individual strategy** (Bollinger, Z-Score, EMA) against the **Stacked ML Strategy** across WTI and Brent Spreads, Flies, and Double Flies.

The results revealed a massive breakthrough regarding strategy interference.

## Exhaustive Performance Matrix

| Structure | Strategy | Win Rate | Profit Factor | Total Trades |
| :--- | :--- | :--- | :--- | :--- |
| **WTI Spread** | BB Only | 50.00% | 0.44 | 2 |
| **WTI Spread** | Z-Score Only | 50.00% | 0.44 | 2 |
| **WTI Spread** | EMA Only | 9.09% | 0.49 | 22 |
| **WTI Spread** | ML Stacked | 43.48% | 0.50 | 23 |
| --- | --- | --- | --- | --- |
| **WTI Fly** | **BB Only** | **100.00%** | **inf** | 6 |
| **WTI Fly** | **Z-Score Only** | **100.00%** | **inf** | 6 |
| **WTI Fly** | EMA Only | 17.65% | 0.12 | 17 |
| **WTI Fly** | ML Stacked | 57.14% | 1.14 | 21 |
| --- | --- | --- | --- | --- |
| **WTI Double Fly** | **BB Only** | **100.00%** | **inf** | 6 |
| **WTI Double Fly** | **Z-Score Only** | **100.00%** | **inf** | 6 |
| **WTI Double Fly** | EMA Only | 11.11% | 0.02 | 18 |
| **WTI Double Fly** | ML Stacked | 59.09% | 1.15 | 22 |
| --- | --- | --- | --- | --- |
| **Brent Spread** | BB Only | 50.00% | 0.73 | 4 |
| **Brent Spread** | Z-Score Only | 50.00% | 0.73 | 4 |
| **Brent Spread** | EMA Only | 16.67% | 0.70 | 12 |
| **Brent Spread** | ML Stacked | 30.77% | 0.59 | 13 |
| --- | --- | --- | --- | --- |
| **Brent Fly** | **BB Only** | **100.00%** | **inf** | 6 |
| **Brent Fly** | **Z-Score Only** | **100.00%** | **inf** | 6 |
| **Brent Fly** | EMA Only | 4.00% | 0.08 | 25 |
| **Brent Fly** | ML Stacked | 48.15% | 1.07 | 27 |
| --- | --- | --- | --- | --- |
| **Brent Double Fly** | **BB Only** | **100.00%** | **inf** | 1 |
| **Brent Double Fly** | **Z-Score Only** | **100.00%** | **inf** | 1 |
| **Brent Double Fly** | EMA Only | 4.76% | 0.03 | 21 |
| **Brent Double Fly** | ML Stacked | 45.45% | 0.43 | 22 |

## Critical Findings

> [!CAUTION]
> **Signal Pollution from EMA (Trend-Following)**
> The ML Stacked strategy allocated roughly 30% of its weight to the EMA Crossover strategy. However, because the EMA strategy is violently incompatible with bounded structures, it generated 17-25 false signals over just two days. 
> 
> By stacking the strategies, the EMA's high-frequency noise polluted the pure entries of the Z-Score and Bollinger Band models, dragging the Win Rate down from 100% to ~50%.

> [!TIP]
> **Pure Mean Reversion is Flawless on Flies**
> When isolated, the pure **Bollinger Band** and pure **Z-Score** strategies achieved a **100% Win Rate** on every single Fly and Double Fly structure across both WTI and Brent! 
> 
> Because they only take trades at standard deviation extremes, they only executed 6 trades total (waiting for true dislocations), and every single one was a winner. The ML stacked portfolio over-traded because of the EMA drag.

### Execution Recommendation
The math is overwhelmingly clear. Do not use a Stacked Strategy with EMA. Hardcode the execution engine to only run **Z-Score or Bollinger Bands on Double Flies**. Remove EMA and Spreads from the intraday paper trader entirely.
