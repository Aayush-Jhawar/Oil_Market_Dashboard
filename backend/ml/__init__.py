"""Fresh, lean, transparent multi-model harness for the composite score.

Trains 2-3 candidate models per (symbol, horizon) on 5 years of daily price
history, walk-forward validates them, selects the best, and serves a live
directional score. Kept deliberately separate from `legacy_archive.prediction`
(which is stale and heavy); we REUSE only its point-in-time feature builders
and the pure walk-forward primitives.
"""
