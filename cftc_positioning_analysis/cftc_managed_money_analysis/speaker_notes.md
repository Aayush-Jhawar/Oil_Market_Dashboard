# Speaker notes: WTI Managed Money positioning study

Real CFTC Managed Money, 2021 to 2026, local roll-adjusted front-month WTI. Same method as the Other
Reportables study. Plain English on the slides, detail and numbers here.

## Slide 1: Verdict
The level does not time direction. Crowded longs and fast unwinds both precede WTI weakness. This is the
opposite of the Other Reportables result, and it uses the genuine Managed Money series pulled from CFTC.

## Slide 2: Method
- Signal: real CFTC Managed Money net (Disaggregated, futures-only, WTI contract 067651), from
  publicreporting.cftc.gov. We confirmed the supplied file was Other Reportables first (100% match over 545
  weeks), so we sourced the real Managed Money series.
- Price: roll-adjusted continuous front-month WTI from local one-minute data, 2021 to 2026.
- No look-ahead: forward returns start at the first close on or after the Friday release.
- Extremes: 52-week rolling z-score, absolute z of 2 or more, long and short separate. Flow: the 4-week
  change in net, decile-ranked. Significance: Newey-West (HAC) standard errors and block-bootstrap p-values.
- Caveat: only 6 extreme-long weeks across 2 episodes in this window. Underpowered on the long side.

## Slide 3: The level
- Window net range: -38,154 to 382,611. (Full-history Managed Money peaked at 483,829 in early 2018, which
  is why this category looks nothing like the supplied file, whose maximum is 339,702.)
- Contemporaneous correlation of level with price: +0.15. Predictive correlation with the next week: 0.00.
- Forward returns vs the base rate (+0.54 / +1.11 / +2.15% at 1 / 2 / 4 weeks):

| Bucket | Horizon | n | episodes | Mean | Median | Hit+ | Excess | HAC t | Boot p |
|---|---|---|---|---|---|---|---|---|---|
| Extreme LONG | 1w | 6 | 2 | +0.7% | +1.2% | 67% | +0.1% | 0.09 | 0.944 |
| Extreme LONG | 2w | 6 | 2 | -0.1% | -0.7% | 50% | -1.3% | -0.74 | 0.511 |
| Extreme LONG | 4w | 6 | 2 | -3.6% | -3.6% | 0% | -5.7% | -4.48 | 0.000 |
| Extreme SHORT | 1w | 27 | 11 | +0.9% | +0.4% | 56% | +0.3% | 0.46 | 0.642 |
| Extreme SHORT | 2w | 27 | 11 | +1.8% | +1.5% | 56% | +0.7% | 0.53 | 0.596 |
| Extreme SHORT | 4w | 27 | 11 | +3.7% | +2.7% | 63% | +1.6% | 0.68 | 0.486 |

The extreme-long 4-week cell is strongly negative and significant on paper (every one of the 6 weeks fell),
but it rests on 2 episodes, so the low p-value overstates the confidence. The short side is not significant.

## Slide 4: The flow (capitulation)
4-week change in Managed Money net, decile-ranked. Fastest unwind is the most negative change.

| Flow bucket | 1w | 2w | 4w |
|---|---|---|---|
| Fastest unwind | -1.1% (34% hit, boot p=0.048) | -2.1% (28% hit, p=0.023) | -2.3% (28% hit, p=0.033) |
| Fastest build | +0.2% | +0.4% | +0.2% |

For Managed Money, a fast unwind precedes continued weakness (momentum). For Other Reportables the same
test gave a rebound of about +5.6% at 4 weeks. Same statistic, opposite sign, because the two trader groups
behave differently around extremes.

## Slide 5: Conclusion and the Other Reportables contrast
- Extreme long: Managed Money weakens (fade the crowd works, on 2 episodes); Other Reportables shows no edge.
- Fast unwind: Managed Money keeps declining (momentum); Other Reportables rebounds (mean reversion).
- Both groups: the level alone does not predict the next week.
- Crowding and risk: in this short window the 6 extreme-long weeks had lower forward volatility (2.2% vs a
  10.6% baseline) and no 10%-plus drawdowns, with a Levene p of 0.047. That is the opposite of the
  full-sample expectation (crowded longs usually raise risk), and it is a small-sample artifact: those 6
  weeks sat in a calm but steadily declining stretch around the 2022 top. Do not lean on it.
- Desk use: treat an extreme Managed Money long, or a fast unwind, as a caution or short-bias flag alongside
  fundamentals, not a buy signal. The move is mostly post-release, so it is actionable. Costs not modelled.

## To make this robust
Rebuild on the full 2016 to 2026 sample (needs WTI prices back to 2016) to recover the 2018 build and the
2020 crash. That is where Managed Money reached its real extremes, and it is the only way to properly test
the long-side and crowding results that are underpowered in the 2021 to 2026 window.
