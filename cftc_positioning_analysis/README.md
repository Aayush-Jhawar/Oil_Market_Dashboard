# CFTC positioning vs WTI

One question, asked of two different CFTC trader categories: does extreme positioning predict WTI returns?
Each study lives in its own subfolder and stands on its own. Same method throughout (roll-adjusted
front-month WTI, no look-ahead from the Friday release, 52-week rolling z-score, Newey-West and bootstrap
significance, 2021 to 2026 window).

## The two studies

- **`cftc_or_wti_analysis/`** — Other Reportables. This is the category in the file you were originally
  given (`Data/CFTC 2016-2026 CL.xlsx`), confirmed to be Other Reportables, not Managed Money.
- **`cftc_managed_money_analysis/`** — Managed Money. The real series, pulled from the official CFTC
  archive, which is what the brief was actually meant to study.

Each subfolder contains its own deck (`.pptx`), `speaker_notes.md`, `README.md`, `charts/`, `scripts/`, and
results JSON.

## Why both exist
The file supplied for the project is labelled in vendor code as `CFTC-D_F_CL_OR_NET`, which is Other
Reportables. We verified that against CFTC's published numbers (a 100% match across 545 weeks) and then
pulled the genuine Managed Money series so the intended study could also be done. The two categories are
different groups of traders and they behave differently, so keeping the analyses separate matters.

## The headline contrast (2021 to 2026, same method)
| Test | Managed Money | Other Reportables |
|---|---|---|
| Level predicts next week | No (corr 0.00) | No (corr +0.02) |
| Extreme long, 4 weeks ahead | about -3.6% (fade works, only 2 episodes) | no edge (negative medians) |
| Fast unwind, 4 weeks ahead | about -2.3% (decline continues, momentum) | about +5.6% (rebound, mean reversion) |

Same statistic, opposite sign on the unwind. That is the practical reason the category label matters: a deck
that runs Other Reportables but calls it Managed Money reaches the wrong conclusion for the group it names.

## Shared caveats
2021 to 2026 only (local WTI starts in 2021), so the 2018 build and the 2020 crash are out of sample.
Episode counts are small, especially Managed Money longs (2 episodes). No open interest in the supplied
file. Costs not modelled. Both studies are suggestive, not bankable, and would be strengthened by the full
2016 to 2026 sample.

## Raw data
`Data/cftc_managed_money_wti_2016_2026.csv` holds Managed Money and Other Reportables side by side for all
552 weeks (Dec 2015 to Jun 2026).
