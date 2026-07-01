# Speaker notes: WTI Other-Reportables positioning study

Plain English sits on the slides. The detail and the math sit here.

---

## Slide 1: Question and verdict
The question is whether conditioning on CFTC Other Reportables positioning shifts the forward WTI
return distribution relative to the unconditional base rate (not relative to zero).

The short answer has three parts:
1. The positioning **level** does not forecast direction. Its correlation with the next week's return
   is +0.02 (p = 0.75), and extreme readings of the level do not beat the base rate.
2. The 4-week **change** does carry signal. After the fastest unwind (capitulation), WTI rebounds about
   +5.6% over the next month, with a 72% hit rate (block-bootstrap p = 0.04, HAC t = 2.0).
3. Crowding behaves like a **risk** gauge. Forward 4-week volatility roughly doubles after an extreme
   long reading (10.6% to 21.4% in this window).

One label correction sits underneath all of this: the file is CFTC Other Reportables, not Managed Money.

---

## Slide 2: Data and method

### Series identity (this is the one that gates everything)
The file's `actual` column was checked against CFTC's published Disaggregated futures-only values for WTI
(contract 067651, "WTI-PHYSICAL"). It matches **Other Reportables net** to the exact contract on every
date tested, and it does not match Managed Money:

| Date | File `actual` | CFTC Managed-Money net | CFTC Other-Reportables net |
|------|------|------|------|
| 2016-01-05 | 134,741 | 49,436 | 134,741 (match) |
| 2018-01-23 | 238,138 | 478,557 | 238,138 (match) |
| 2020-04-21 | 339,702 | 247,478 | 339,702 (match) |
| 2022-03-08 | 126,828 | 234,837 | 126,828 (match) |
| 2026-06-16 | 28,255 | 96,228 | 28,255 (match) |

So the vendor code `CFTC-D_F_CL_OR_NET` reads as Disaggregated, Futures-only, CL (WTI), OR (Other
Reportables), net. The whole deck is labelled Other Reportables. The identity was confirmed with five
direct CFTC lookups. No price or positioning data was pulled online.

### Cleaning
548 rows became 545 after dropping three exact duplicates (2026-05-12, 2026-05-19, 2026-05-26), then
sorted ascending. `date` is the Tuesday as-of; `releasedate` is publication (gap of 3 days at the median,
7 at the most). The `estimates` column is empty and was ignored.

### Price series: roll-adjusted continuous front-month WTI (NYMEX CL)
Built from the local one-minute file `CL_data.csv`. The daily close is the last print per US Eastern date,
spanning 2021-01-03 to 2026-05-22 (1,676 trading days). The roll-adjusted return is `c1_t / c1_(t-1) - 1`
on normal days, and `c1_t / c2_(t-1) - 1` on a roll day, because the previous day's second month is the
contract that becomes the new front. All 65 rolls were standard. The continuous index is the cumulative
product of those returns. This removes roll gaps so multi-week returns are clean. The window is 2021 to
2026 because local WTI starts in 2021 (only Brent reaches 2016 locally), which excludes the 2018 long
build and the 2020 crash, including the all-time Other Reportables maximum of 339,702 on 2020-04-21.

### No look-ahead
Each observation is joined to the first WTI close on or after its Friday release date (call it P0), using a
forward as-of merge with a 7-day tolerance. The tolerance leaves pre-2021 observations unpriced, which is
correct. Every forward return starts at P0, never at the Tuesday as-of date.

### Signals
The net level, the week-over-week change (flow), a 52-week rolling z-score (52-week minimum, sample
standard deviation), and a rolling percentile. These were computed on the full 2016 to 2026 series and
then restricted to the priced window, so the 2021 signals have a genuine 2020 look-back and there is no
full-sample leakage. Open interest is not in the local file, so the signals use the net level rather than a
share of open interest. The priced window has 282 weeks.

### Significance
Conditional returns are compared with the unconditional base rate. Standard errors use Newey-West (HAC)
to handle the overlap from weekly-sampled multi-week returns, with lags set to the horizon. P-values use a
circular block bootstrap (block length equal to the horizon, 5,000 draws), which respects the clustering of
extreme weeks into a handful of episodes.

---

## Slide 3: The level
Extreme definition: rolling absolute z of 2 or more, long and short kept separate. An episode is a run of
consecutive extreme weeks, merging runs separated by a single non-extreme week.

- Extreme LONG (z of +2 or more): 8 weeks across 4 episodes (late 2023, early 2026).
- Extreme SHORT (z of -2 or less): 18 weeks across 10 episodes (spread over 2021 to 2026).
- Decile robustness (top and bottom rolling decile): long 21 weeks / 7 episodes, short 77 weeks / 27 episodes.

Forward returns from the post-release close (simple returns, adjusted index), against the base rate of
+0.54% / +1.11% / +2.15% at 1 / 2 / 4 weeks:

| Bucket | Horizon | n weeks | n episodes | Mean | Median | Hit+ | Excess | HAC t | Boot p |
|---|---|---|---|---|---|---|---|---|---|
| Extreme LONG | 1w | 8 | 4 | +3.6% | -0.6% | 38% | +3.1% | 0.66 | 0.546 |
| Extreme LONG | 2w | 8 | 4 | +2.2% | -4.8% | 38% | +1.1% | 0.16 | 0.882 |
| Extreme LONG | 4w | 8 | 4 | +0.6% | -6.1% | 12% | -1.6% | -0.25 | 0.833 |
| Extreme SHORT | 1w | 18 | 10 | +2.1% | +2.5% | 83% | +1.5% | 1.98 | 0.063 |
| Extreme SHORT | 2w | 18 | 10 | +4.0% | +4.9% | 78% | +2.9% | 2.26 | 0.041 |
| Extreme SHORT | 4w | 18 | 10 | +4.1% | +5.8% | 67% | +2.0% | 0.70 | 0.479 |

Read: extreme longs have no upside (the positive means are driven by a couple of outliers, the medians are
negative). Extreme shorts did bounce, strongest at two weeks, but the only nominally significant cell
(short, 2 weeks, p = 0.041) does not survive a six-test multiple-comparison correction (Bonferroni alpha
of about 0.008), and it leans on 10 episodes. The contemporaneous correlation of the level with price is
weak here (-0.09), and on a forward basis the level is noise (predictive correlation +0.019, p = 0.75).

---

## Slide 4: The change and the risk

### Flow (the rate-of-change signal)
The 4-week change in Other Reportables net, ranked into deciles. The bottom decile is the fastest unwind
(capitulation); the top decile is the fastest build.

| Flow bucket | n | 1w | 2w | 4w |
|---|---|---|---|---|
| Fastest unwind | 29 | +2.2% (79% hit, boot p=0.012) | +2.9% (72% hit, p=0.122) | +5.6% (72% hit, boot p=0.042, HAC t=2.04) |
| Neutral | 56 | +1.1% | +0.5% | +1.5% |
| Fastest build | 29 | +1.3% | +1.6% | +2.6% |

The fastest unwind is the one robust directional result in the data: significant at 1 week (p = 0.012) and
4 weeks (p = 0.042). A naive t-stat reads 4.1, but that overstates because the 4-week windows overlap; the
HAC t of 2.0 and the bootstrap p of 0.04 are the honest numbers, and they line up with the full-sample
version on the friend's deck (+3.7%, t = 2.14, p = 0.037).

### Crowding and risk (the distribution, not the mean)
Forward 4-week returns conditional on an extreme long, against the all-weeks baseline:

- Standard deviation: baseline 10.6%, after extreme long 21.4% (it roughly doubles).
- Probability of a 4-week drop worse than 10%: baseline 7%, after extreme long 12%.
- Levene test of equal variance (extreme long vs baseline): W = 0.80, p = 0.37.

The direction is the same as the friend's full-sample result (12.8% to 24.9%, p < 0.001), but our 2021 to
2026 window only has 8 extreme-long weeks, so the variance test is underpowered here and does not reach
significance on its own. The full-sample evidence is what certifies it.

---

## Slide 5: Conclusion and desk use

### Decay probe (where the move happens)
Pre-release is the Tuesday-to-Friday move, before the data is public, so it is not tradeable. Post-release is
the Friday-to-plus-one-week move. The share is pre divided by (pre plus post).

| Bucket | Pre (Tue to Fri) | Post (Fri to +1wk) | Pre-share |
|---|---|---|---|
| Extreme SHORT | +0.87% | +2.05% | 30% (so 70% post, tradeable) |
| Extreme LONG | +5.75% | +3.61% | 61% (mostly pre, and n is only 8) |
| Unconditional | +0.46% | +0.54% | 46% |

The short-side bounce, and the capitulation rebound, both land mostly after the Friday release, so they are
at least actionable. Costs are not modelled.

### Caveats
The series is Other Reportables, a residual category of reportable traders (smaller funds, locals, wealthy
individuals) with a weaker behavioural story than Managed Money. The window is 2021 to 2026 only, so the
2018 and 2020 extremes are out of sample. There is no open interest in the local file. Episode counts are
small. The level's short-side bounce fails a multiple-comparison correction. Treat the results as
suggestive, not bankable.

### To extend (out of scope here)
Rebuild with true WTI back to 2016 to recover the 2018 long build and the 2020 crash, add open interest for
share-of-open-interest signals, and bring in additional CFTC categories for a commercial-versus-managed-money
divergence study.

---

## How this compares to the Managed-Money deck we were shown
The two studies reach the same core conclusion: positioning is a risk and inflection gauge, not a
level-based timing trigger. Where they overlap, the numbers agree (no level edge; capitulation is the real
directional signal; crowded longs carry more risk). Three differences are worth noting:

1. That deck is labelled Managed Money, but its positioning series appears to top out near 340k, which is
   the Other Reportables maximum (339,702), whereas real WTI Managed-Money net was above 478k in
   January 2018. That strongly suggests it used the same Other Reportables file under a Managed-Money label,
   which is the exact pitfall the brief warned about. The statistics still hold for whatever series it is.
2. That deck uses the full 2016 to 2026 sample with FRED WTI spot; this one uses 2021 to 2026 with local
   roll-adjusted front-month WTI. The longer sample is better powered for the variance and capitulation
   tests, which is why its Levene p is below 0.001 while ours is not.
3. The short-side bounce shows up in our 2021 to 2026 window but washes out over the full sample, so it is
   most likely a feature of this regime rather than a durable edge.
