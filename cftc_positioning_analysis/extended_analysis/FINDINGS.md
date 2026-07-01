# Extended analysis: calendar spread, expiry, and Brent cross-check

Three new studies requested: (1) the C1-C2 calendar spread, (2) an expiry-window check, and (3) redo
everything on Brent. The big takeaway is that the **calendar spread is the robust signal, and it is the
positioning signals, not the spread, that fail to travel from WTI to Brent.**

## Data
- WTI price: local 1-minute front curve (C1, C2, C12), 2021-2026. WTI positioning: CFTC Managed Money.
- Brent price: local ICE Brent settle curve (C1..C31), 2016-2026. Brent positioning: CFTC "Brent Last Day"
  Managed Money (NYMEX cash-settled Brent, code 06765T), 2011-2026. The true ICE BRN Commitments of Traders
  is published by ICE but is gated behind ICE Connect / the developer API, so this NYMEX Brent series is the
  freely-accessible proxy. It is smaller than ICE BRN, but z-scoring normalizes the size and it tracks Brent
  speculative sentiment. Treat Brent positioning as indicative.
- Returns use a de-rolled continuous front-month (roll days detected when C1 and C2 returns diverge, then the
  C2 return is used), so multi-week returns are not contaminated by contract rolls.

## Analysis 1: Calendar spread (C1 minus C2). THE STANDOUT FINDING.
Sorting weeks by the front spread and measuring the next 4-week return:

| Curve state | WTI (2021-2026) | Brent (2016-2026) |
|---|---|---|
| Contango (C1 < C2, oversupplied) | +4.6% (67% hit, n=94) | +3.1% (62% hit, n=181) |
| Flat | +2.0% (n=94) | +2.1% (65% hit, n=181) |
| Backwardation (C1 > C2, tight) | -2.6% (29% hit, n=90) | -0.9% (43% hit, n=177) |

Monotonic on both crudes, and it holds on Brent's independent 543-week sample. So the shape of the curve is a
contrarian signal for flat price: deep contango tends to precede a rally, deep backwardation tends to precede
weakness. Combining with positioning helps on WTI (contango + crowded long = +5.4%, 81% hit, but only n=16);
on Brent the spread does most of the work (both contango cells about +3%).

Positioning and the spread are only weakly linked (correlation 0.18 WTI, 0.23 Brent): funds lean a little
more long when the curve is backwardated.

Caveat: part of this is regime (2020-21 deep contango preceded the recovery; 2022+ backwardation preceded the
decline). The Brent replication over a different, longer sample is what gives it credibility.

## Analysis 2: Expiry window (expiry = 3 business days before the 25th; window expiry-7 to expiry)
- WTI (65 monthly expiries): price softens mildly into expiry, mean -0.34% vs a +0.32% average 7-day move, so
  about -0.7% below normal, but not significant (t=-0.69, p=0.49). It is worse when funds are crowded long
  (-1.37%) than light (+0.65%) going in, and it recovers after expiry (+0.87% in the next week). Read: a mild
  pre-expiry de-risking pressure, amplified by heavy positioning, not a strong standalone effect.
- Brent: no consistent effect. Also note the "3 business days before the 25th" rule is the WTI/NYMEX
  convention; ICE Brent expires on a different schedule, so the Brent expiry numbers here are only a rough
  proxy and should not be read as a real Brent expiry effect.

## Analysis 3: Redo the positioning studies on Brent. THE POSITIONING EDGE DOES NOT TRAVEL.
On Brent's longer 2016-2026 sample, the WTI positioning findings largely vanish:

| Test (next 4 weeks) | WTI (2021-2026) | Brent (2016-2026) |
|---|---|---|
| Crowded long (Z>=2) | -4.3% (0% hit) | +1.3% (52% hit) ~ baseline |
| Light/short (Z<=-2) | +3.5% | +0.6% ~ baseline |
| Fresh crowded long | +7.4% | +1.2% |
| Stale crowded long | -1.6% | +1.5% (no decay) |
| Fast unwind (flow) | -2.6% | +1.5% (opposite sign) |
| Low vol + Low position | +2.2% | +1.2% |

Baseline 4-week return is about +1.4% for both. So on Brent, none of the positioning cuts beat the base rate,
and the staleness and flow patterns do not replicate (some flip sign). The conclusion: the WTI positioning
and staleness results are specific to WTI over 2021-2026 (one regime, few episodes), not a general law. What
travels across both crudes is the curve-shape signal.

## Regime classification (the tradeable edge)
Because single-signal t-stats are weak, we crossed the factors into regimes and kept only cells that beat the
base rate AND agree across both crudes. Crossing curve shape with volatility isolates a clean edge:

| Regime (next 4 weeks) | WTI | Brent |
|---|---|---|
| Contango + High vol | +3.7% (69% hit, n=36) | +4.8% (67% hit, n=109, bootstrap p=0.02) |
| Contango + Low vol | +2.3% | -0.5% |
| Backwardation + Low vol | +1.7% | +1.1% |
| Backwardation + High vol | +0.1% | +0.3% |

The **Contango + High volatility** cell (a stressed, oversupplied tape) is the tradeable long edge: it beats
the ~1.4% base rate by roughly 3 points, agrees on both crudes, and is significant on Brent's larger sample.
Its opposite, backwardation + high vol, is a stand-aside (~0%). Positioning then acts as a secondary confirmer
inside contango (WTI contango + crowded long +5.4%). This is how to get an edge despite low single-factor
t-stats: condition on the regime, and demand cross-instrument replication.

Deliverable: `cftc_positioning_analysis/WTI_Brent_positioning_curve_regime.pptx` (7-slide trading deck).

## Bottom line and recommendation
1. Lead with the curve. The C1-C2 spread (contango vs backwardation) is the strongest, best-powered, and
   cross-validated predictor of forward crude returns here. It deserves a slide.
2. Reframe positioning honestly. Positioning is a weak, regime-dependent, WTI-specific timing signal; it did
   not replicate on Brent. Keep it as context and risk, and say so. This tempers the earlier deep-dive
   equations rather than overturning them: they hold in-sample for WTI 2021-2026 but do not generalize.
3. Expiry and the positioning-spread link are minor. Mention in notes, not as headlines. Flag that the Brent
   expiry rule is a WTI convention.

Scripts: `extended_analysis/scripts/` (build_curves.py, analyze_all.py, expiry.py, plus the z-score and
volatility robustness scripts). Data: `Data/brent_managed_money_cftc.csv`,
`Data/cftc_managed_money_wti_2016_2026.csv`.
