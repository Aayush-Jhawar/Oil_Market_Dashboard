# Paper Trading Integration Audit

**Date:** 2026-06-09
**Auditor:** Antigravity AI

## 1. Current State Evaluation
The paper trading engine (`backend/main.py -> _paper_trading_publisher`) acts as the automated consumption layer for AI predictions. 

**Observation:** The current implementation is strictly limited to outright directional futures.

### Current Logic:
```python
for sym in ["WTI", "Brent", "RBOB"]:
    recs = await loop.run_in_executor(None, get_recent_trade_recommendations, sym, 1)
    if direction in ("LONG", "BUY"):
        signals[sym] = float(conf)
    elif direction in ("SHORT", "SELL"):
        signals[sym] = -float(conf)
```

## 2. Findings
1.  **Spreads/Flies Ignored:** The loop hardcodes `["WTI", "Brent", "RBOB"]`. It completely ignores `3-2-1CRACK`, `WTI-Brent` (RV), Calendar Spreads, and Butterflies.
2.  **No Signal Ranking:** The engine blindly executes the highest confidence outright trades independently. It does not rank signals cross-asset or cross-structure.
3.  **Directional Bias:** It expects `LONG` or `SHORT`. It is not configured to handle `BUY_SPREAD`, `SELL_SPREAD`, `BUY_FLY`, or `SELL_FLY`.

## 3. Redesign: Signal Ranking Engine
To align with professional oil market operations, paper trading must evaluate curve structure alongside outright price direction.

### Proposed Signal Engine Architecture:

**1. Signal Harvesting**
The paper trading publisher will query the `TradeRecommendation` DB table for the latest signals across:
*   Calendar Spreads
*   Butterflies
*   Cracks
*   Relative Value (Brent-WTI)
*   Outrights

**2. Conviction Scoring**
Calculate a unified `Conviction Score` for every signal:
`Conviction = (trade_score * 0.5) + (confidence * 50) + (risk_reward_ratio * 10)`

**3. Hierarchical Ranking**
When allocating capital to a new paper trade, the engine will rank opportunities strictly according to:
1.  Highest conviction Spreads
2.  Highest conviction Flies
3.  Highest conviction Cracks
4.  Relative Value Trades
5.  Outright Directional Trades

**4. Execution Mapping**
*   `SPREAD` and `FLY` signals will map to multi-leg orders in the paper book.
*   `CRACK` signals will execute standard 3:2:1 or 2:1:1 ratios.

## 4. Conclusion
The paper trading system currently acts as a simple directional retail bot. By implementing the hierarchical ranking engine, it will operate as a structural oil trader, deploying capital to curve inefficiencies before taking outright price risk.
