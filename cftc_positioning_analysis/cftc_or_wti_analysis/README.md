# WTI Other-Reportables positioning study

Question: does CFTC positioning predict WTI returns?

Answer in one line: the positioning level does not time direction, the 4-week change does, and crowding
flags risk. In other words, use positioning as context and a risk overlay, not as a buy or sell trigger.

> Series note: the supplied file (`Data/CFTC 2016-2026 CL.xlsx`, code `CFTC-D_F_CL_OR_NET`) is CFTC
> Other Reportables net, not Managed Money. We verified this to the exact contract against CFTC's
> published values on five dates. Everything here is labelled Other Reportables.

## Deliverables
- `WTI_OtherReportables_positioning_study_v2.pptx`: the current 5-slide deck (humanised, with the flow and
  risk findings). The earlier `..._study.pptx` is the first version and can be deleted.
- `speaker_notes.md`: methodology and every statistic, plus a section comparing this study to the
  Managed-Money deck we were shown.
- `charts/`: the five source charts.
- `scripts/`: the reproducible pipeline.
- `results.json`: the computed numbers.

## What we found
Window: 2021 to 2026, 282 weekly observations (local WTI starts in 2021, and we used true WTI rather than a
Brent stand-in).

1. The level is noise on a forward basis. Correlation with next week's return is +0.02 (p = 0.75). Extreme
   longs have no upside (negative medians). Extreme shorts bounced in this window, but the result fails a
   multiple-comparison correction and rests on 10 episodes.
2. The change is the signal. After the fastest 4-week unwind (capitulation), WTI rebounds about +5.6% over
   the next month (72% hit, bootstrap p = 0.04, HAC t = 2.0). This is the one robust directional result, and
   it matches the full-sample version on the other deck.
3. Crowding is a risk gauge. Forward 4-week volatility roughly doubles after an extreme long (10.6% to
   21.4%). Our short window cannot certify it on its own, but the direction is clear and the full-sample
   evidence is strong.
4. Tradeability: the capitulation rebound and the short bounce both happen mostly after the Friday release
   (about 70% of the move), so they are at least actionable. Costs are not modelled.

## Method, briefly
Cleaned the CFTC weekly series (548 to 545 rows after de-duplication). Built a roll-adjusted continuous
front-month WTI from the local one-minute `CL_data.csv` (65 clean rolls). Joined each observation to the
first WTI close on or after the Friday release date (the no-look-ahead anchor). Signals: net level,
week-over-week change, and a 52-week rolling z-score and percentile, computed on the full 2016 to 2026
history and then restricted to the priced window. Extremes flagged at absolute z of 2 or more, long and
short separate, counted as episodes. Forward returns at 1, 2 and 4 weeks tested against the unconditional
base rate, with Newey-West (HAC) standard errors and block-bootstrap p-values. A decay probe compares the
untradeable pre-release move with the tradeable post-release move.

## Caveats
Other Reportables, not Managed Money. 2021 to 2026 only, so the 2018 and 2020 extremes are out of sample.
No open interest in the local file. Small episode counts. Costs not modelled. Suggestive, not bankable.

## Reproduce
Run the scripts in order from `scripts/`: `step1_3_build.py`, `step4_6_analysis.py`, `make_charts.py`,
`make_flow_chart.py`, `build_deck.py`. They read the raw inputs from `Data/` and write intermediates next
to themselves. `comparison.py` reproduces the comparison against the Managed-Money deck.
