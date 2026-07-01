# Synthesis: our findings vs the independent 2019-2021 study

A friend's report analysed CFTC Managed Money + CME settlements over 2019-2021 (price ends 2021). We ran the
same questions on complementary data: local WTI 2021-2026 and Brent 2016-2026, plus the CFTC structural
columns to 2026. This is an independent cross-check, not a copy. Where we agree, the finding is robust across
samples and markets; where we differ, the earlier result is regime-specific.

## Where we agree (robust across samples)
- **Managed Money is coincident / trend-following.** Change in net vs same-week return: +0.19 (p=0.002) on our
  WTI 2021-2026, versus their +0.212 on 2019-2021. It confirms moves; it does not predict them.
- **MM positioning extremes give no robust forward edge.** Both studies find the apparent "crash after bearish
  extremes" is outlier clustering around 2020, not a repeatable signal (means collapse to benign medians).
- **Concentration / crowding is informative and matches exactly.** Per-firm long book peaked summer 2020
  (~8,130 contracts/firm); the short side is at its sample maximum now, 2026 (~4,520/firm) — a small,
  squeeze-prone group. Same conclusion, same data.
- **Rising price on rising open interest is the best continuation regime** on WTI (+3.0%, 56% hit), echoing
  their 70% hit-rate result.
- **The roll is invisible to COT.** A front-month roll is net- and spread-neutral, so weekly positioning cannot
  see it; the roll's risk lives in the CL1-CL2 spread. We confirm positioning into expiry is unremarkable, and
  adopt their framing.

## Where we differ (their result is regime-specific)
- **Other Reportables is NOT durably contrarian.** They found OR net negatively rank-correlated with forward
  returns (-0.224) on 2019-2021. On our WTI 2021-2026 it is *positive* (Spearman +0.14, p=0.02) and null on
  Brent. The MM-vs-OR "sign flip" disappears out of sample. The 2019-2021 contrarian tilt is a COVID-window
  effect, not a standing property.
- **The conviction-vs-covering flow gap shrinks** from +10.3% vs +1.2% (their window) to +2.2% vs +1.7% (ours).
- **The OI x price regime does not fully replicate on Brent** (there, liquidation weeks lead), so treat it as
  WTI colour.

## What we add
- **Cross-instrument validation.** Testing on Brent (independent, 543 weeks) is the key robustness filter, and
  it is what exposes the positioning signals as WTI/regime-specific.
- **The term-structure signal, reframed.** Contango is rare (WTI 18% of weeks, episodic: 2016/2020). The
  usable, always-available, cross-validated signal is the opposite tail: **deep backwardation precedes weak
  forward returns** (WTI -2.6%, Brent -0.9% over 4 weeks, bootstrap p<0.01). Fade deep backwardation; do not
  chase contango.
- **Volatility x positioning regimes were tested and give no usable, cross-validated edge** (positioning is
  flat on both crudes; no vol x position cell agrees across WTI and Brent).

## Bottom line
Positioning is a momentum / context and risk gauge, not a contrarian timing signal. The durable, tradeable
information is the term structure (fade deep backwardation), structural crowding (short side squeeze-prone
now), and open-interest trend confirmation. Deck:
`cftc_positioning_analysis/WTI_Brent_positioning_structure_trading.pptx` (8 slides). This supersedes the
earlier contango-framed deck.
