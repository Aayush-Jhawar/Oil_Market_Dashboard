"""Training CLI for the composite-score model harness.

    python -m ml.train                         # all symbols, all horizons
    python -m ml.train --symbols WTI,Brent     # subset
    python -m ml.train --horizons 5d --dry-run # evaluate, don't write artifacts

For each (symbol, horizon): build the supervised frame, walk-forward horse-race
the candidates, select the best, refit it on all data, and persist artifacts +
OOS predictions + a leaderboard manifest (and a best-effort model_metadata row).
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

from ml.paths import SYMBOLS, HORIZONS, HORIZONS as _H
from ml.data import build_supervised
from ml.harness import walk_forward_eval, select_best
from ml.models import make_candidate, feature_importances, LGBM_PARAMS
from ml import store

logger = logging.getLogger(__name__)


def train_one(symbol: str, horizon: str, dry_run: bool = False):
    X, y_dir, fwd_ret = build_supervised(symbol, horizon)
    if X.empty:
        logger.warning("skip %s/%s: no supervised data", symbol, horizon)
        return None

    results = walk_forward_eval(X, y_dir, fwd_ret, _H[horizon])
    if not results:
        logger.warning("skip %s/%s: walk-forward produced nothing", symbol, horizon)
        return None

    best_name, underperforms = select_best(results)

    # Refit the winner on ALL rows for live serving.
    final = make_candidate(best_name)
    final.fit(X, y_dir)
    top_feats = feature_importances(final, list(X.columns))
    # sort + keep top 15
    top_feats = dict(sorted(top_feats.items(), key=lambda kv: kv[1], reverse=True)[:15])
    results[best_name]["top_features"] = top_feats

    training_end = str(X.index[-1].date())
    entry = store.build_manifest_entry(
        symbol, horizon, results, best_name, underperforms,
        n_samples=len(X), n_features=X.shape[1], training_end_date=training_end,
    )

    if not dry_run:
        trained_at = datetime.now(timezone.utc).isoformat()
        store.save_model_artifact(symbol, horizon, final, list(X.columns),
                                  best_name, training_end, trained_at)
        store.save_oos(symbol, horizon, results[best_name]["oos"])
        store.mirror_to_model_metadata(entry, trained_at,
                                       LGBM_PARAMS if best_name == "lightgbm" else {"model": best_name})
    return entry


def main():
    ap = argparse.ArgumentParser(description="Train composite-score models.")
    ap.add_argument("--symbols", default=",".join(SYMBOLS))
    ap.add_argument("--horizons", default=",".join(HORIZONS.keys()))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    horizons = [h.strip() for h in args.horizons.split(",") if h.strip()]

    entries = []
    print(f"\nTraining {len(symbols)} symbols x {len(horizons)} horizons "
          f"{'(DRY RUN)' if args.dry_run else ''}\n")
    hdr = f"{'symbol':7} {'hz':4} {'best':9} {'acc':>6} {'base':>6} {'prec_hc':>8} {'brier':>6} {'win%':>6} {'flag':>5}"
    print(hdr); print("-" * len(hdr))
    for sym in symbols:
        for hz in horizons:
            e = train_one(sym, hz, dry_run=args.dry_run)
            if not e:
                print(f"{sym:7} {hz:4} {'-- skipped --'}")
                continue
            entries.append(e)
            b = e["candidates"][e["best_model"]]
            phc = f"{b['precision_high_conf']:.3f}" if b["precision_high_conf"] is not None else "  n/a"
            win = f"{b['win_rate']:.3f}" if b["win_rate"] is not None else "  n/a"
            flag = "WEAK" if e["underperforms_random"] else "ok"
            print(f"{sym:7} {hz:4} {e['best_model']:9} {b['accuracy']:6.3f} {b['base_rate']:6.3f} "
                  f"{phc:>8} {b['brier']:6.3f} {win:>6} {flag:>5}")

    if entries and not args.dry_run:
        generated_at = datetime.now(timezone.utc).isoformat()
        path = store.write_manifest(entries, generated_at)
        print(f"\nWrote {len(entries)} entries -> {path}")
    print()


if __name__ == "__main__":
    main()
