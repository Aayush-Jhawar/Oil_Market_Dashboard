# WTI Managed Money positioning study (the real series)

This folder redoes the positioning study on the genuine CFTC **Managed Money** category, which we pulled
from the official CFTC archive (publicreporting.cftc.gov), rather than the supplied file. The supplied file
turned out to be **Other Reportables** (a different trader group), confirmed by a 100% match across 545
weeks and a clear mismatch against Managed Money.

Window: 2021 to 2026, 282 weekly observations, paired with the local roll-adjusted front-month WTI (your
earlier choice). Methods are identical to the Other Reportables study.

## Headline
For real Managed Money, the positioning level still does not time direction, but crowded longs and fast
unwinds both come before WTI weakness. That is the mirror image of Other Reportables. The category label
genuinely flips the trading conclusion.

## What we found (2021-2026)
- **Level vs next week:** correlation 0.00. No directional timing from the level, same as every version of
  this test.
- **Extreme long (only 6 weeks, 2 episodes):** WTI fell about **-3.6% over 4 weeks, with all 6 weeks
  down** (HAC t = -4.5, bootstrap p < 0.001). The textbook "fade the crowded long" appears for Managed
  Money. It is striking but rests on just 2 episodes, so treat it as suggestive.
- **Extreme short (27 weeks, 11 episodes):** mildly positive (+3.7% at 4 weeks) but not significant.
- **Fast unwind (capitulation):** WTI **keeps falling**, about -1.1% / -2.1% / -2.3% at 1 / 2 / 4 weeks
  (bootstrap p around 0.03 to 0.05). This is momentum, the **opposite** of Other Reportables, where the
  same test produced a +5.6% rebound.

## Managed Money vs Other Reportables (same window, same method)
| Test | Managed Money | Other Reportables |
|---|---|---|
| Level predicts next week | No (corr 0.00) | No (corr +0.02) |
| Extreme long, 4 weeks | -3.6% (fade works, 2 episodes) | no edge (negative medians) |
| Fast unwind, 4 weeks | -2.3% (decline continues, momentum) | +5.6% (rebound, mean reversion) |

The opposite sign on the unwind is the key point. If a deck runs Other Reportables but calls it Managed
Money, its capitulation conclusion is backwards for the real Managed Money group.

## Important caveat
This window has only 2 extreme-long Managed Money episodes, so the long-side and crowding results are
underpowered. The crowding-versus-volatility test even flips here (the 6 extreme-long weeks happened to be
calm but steadily declining, around the 2022 top), which is a small-sample artifact. To trust the long-side
and crowding findings, rebuild on the full 2016 to 2026 sample, which needs WTI prices back to 2016.

## Files
- `WTI_ManagedMoney_DEEP_positioning.pptx`: **the main, polished, self-explanatory deck** (5 slides) with
  the staleness finding, the volatility x position grid, and the conclusion equations. Start here.
- `WTI_ManagedMoney_positioning_study.pptx`: the earlier, plainer 5-slide deck.
- `mm_deep_results.json`: numbers behind the deep deck (grid, persistence, extremes).
- `speaker_notes.md`: methodology and all numbers.
- `charts/`: the three source charts.
- `scripts/`: the pipeline (`fetch_mm.py` pulls the data; `mm_analysis.py` runs the stats;
  `make_charts_mm.py` and `build_deck_mm.py` build the visuals and the deck).
- `Data/cftc_managed_money_wti_2016_2026.csv` (in the project Data folder): the raw Managed Money series.
