# AI Forecasting Strategy & Accuracy Audit

This document details the complete out-of-sample performance statistics for every instrument across outrights, calendar spreads, cracks, and butterflies. All models were tested individually utilizing their respective specific mathematical implementations (e.g. Dynamic Kalman Filters for pairs, LightGBM/HMM for outrights) using our 60/20/20 expanding window methodology.

## Consolidated Performance Matrix

| Symbol | Model Type | Accuracy | High Conf Accuracy | Trade Freq | Total PnL | Ann. Return | Ann. Vol | Sharpe | Max DD | Win Rate | Profit Factor |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| WTI | HMM + LightGBM Ensemble | 53.4% | 56.7% | 85.6% | 6.2% | 1.1% | 6.8% | 0.16 | -13.1% | 47.0% | 1.08 |
| Brent | HMM + LightGBM Ensemble | 57.2% | 62.1% | 86.3% | -5.3% | -1.0% | 7.7% | -0.13 | -16.8% | 46.6% | 0.97 |
| RBOB | HMM + LightGBM Ensemble | 47.3% | 36.2% | 83.6% | 9.8% | 0.9% | 7.3% | 0.13 | -23.5% | 51.1% | 1.08 |
| HO | HMM + LightGBM Ensemble | 51.8% | 52.0% | 83.2% | -38.1% | -8.5% | 8.7% | -0.97 | -41.0% | 38.3% | 0.73 |
| NG | HMM + LightGBM Ensemble | 51.9% | 53.7% | 91.5% | 33.1% | 2.9% | 6.5% | 0.44 | -9.6% | 49.5% | 1.22 |
| WTI_CAL_SPREAD | Kalman Spread / SpreadModel | 57.4% | 48.0% | 75.9% | -18.6% | -3.8% | 13.5% | -0.28 | -26.3% | 40.8% | 0.89 |
| BRENT_CAL_SPREAD | Kalman Spread / SpreadModel | 54.8% | 39.2% | 65.2% | 29.6% | 4.9% | 19.5% | 0.25 | -18.0% | 43.3% | 1.47 |
| WTI_FLY | Kalman Spread / SpreadModel | 66.2% | 53.1% | 68.8% | -194.3% | nan% | 76.5% | nan | -194.3% | 53.5% | 0.17 |
| BRENT_FLY | Kalman Spread / SpreadModel | 53.2% | 35.7% | 46.2% | -174.7% | nan% | 111.2% | nan | -175.1% | 58.1% | 0.34 |
| HO_FLY | Kalman Spread / SpreadModel | 86.1% | 48.4% | 10.7% | -9.9% | -1.9% | 1.1% | -1.71 | -10.0% | 11.3% | 0.04 |
| 3-2-1CRACK | Kalman Spread / SpreadModel | 49.2% | 48.2% | 95.8% | 0.7% | 0.1% | 0.9% | 0.14 | -1.2% | 46.9% | 1.08 |
| GASCRACK | Kalman Spread / SpreadModel | 57.0% | 55.0% | 94.7% | 11.3% | 2.0% | 9.0% | 0.22 | -16.3% | 49.4% | 1.13 |
| DIESELCRACK | Kalman Spread / SpreadModel | 52.8% | 51.1% | 95.8% | -0.6% | -0.1% | 1.2% | -0.09 | -2.2% | 48.7% | 0.96 |
