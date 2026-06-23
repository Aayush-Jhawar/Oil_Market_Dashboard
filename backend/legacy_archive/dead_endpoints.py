@app.get('/api/cot/history')
async def get_cot_history():
    try:
        return {"status": "success", "data": global_cot, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching COT history: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})




@app.get('/api/steo/balance')
async def get_steo_balance():
    try:
        return {"status": "success", "data": global_steo, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching STEO balance: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})



@app.get('/api/analytics/intraday-volatility')
async def get_intraday_volatility(symbol: str = "WTI", limit: int = 2000):
    """Returns high-frequency intraday prices for plotting volatility profiles."""
    try:
        from services.price_fetcher import PriceFetcher
        data = PriceFetcher.fetch_intraday(symbol, limit=limit)
        return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching intraday volatility: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})



@app.get('/api/analytics/arbitrage-spread')
async def get_arbitrage_spread(limit: int = 2000):
    """Returns the WTI-Brent intraday arbitrage spread."""
    try:
        from services.price_fetcher import PriceFetcher
        data = PriceFetcher.fetch_intraday("WTI-BRENT", limit=limit)
        return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching arbitrage spread: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})




@app.get('/api/seasonality')
async def get_seasonality():
    try:
        data = fetch_seasonality()
        return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching seasonality: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})




@app.post('/api/news/analyze')
async def post_analyze_news(payload: dict):
    try:
        items = payload.get('items', [])
        res = analyze_news_items(items)
        return {"status": "success", "data": res, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error analyzing news: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})




@app.get('/api/prices/instruments')
async def get_price_instruments():
    """Get supported price symbols and instrument mappings"""
    try:
        instruments = [
            {"symbol": symbol, "ticker": PriceFetcher.SYMBOLS.get(symbol)}
            for symbol in PriceFetcher.SYMBOLS
        ]
        return {
            "status": "success",
            "data": instruments,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching instrument list: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )




@app.get("/api/prices/{symbol}")
async def get_price(symbol: str):
    """Get price for a specific symbol"""
    try:
        price_data = PriceFetcher.fetch_symbol(symbol)
        if not price_data:
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
        return {"status": "success", "data": price_data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching price for {symbol}: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )




@app.get("/api/prices/spread/historical")
async def get_spread_historical():
    """Get historical and intraday WTI-Brent spread"""
    try:
        from services.data_loader import get_intraday_prices
        intraday = get_intraday_prices("WTI-Brent", max_points=120)
        historical = PriceFetcher.fetch_historical("WTI-Brent", "3mo")
        return {
            "status": "success",
            "data": {
                "intraday": intraday,
                "historical": historical
            }
        }
    except Exception as e:
        logger.error(f"Error fetching WTI-Brent spread: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})




@app.get('/api/eia/weekly-history')
async def get_eia_weekly_history():
    """Get the latest 52 weeks of EIA series data."""
    try:
        if not os.getenv("EIA_API_KEY"):
            # Mock 52-week history
            import random
            history = {
                "crude_level": [{"period": f"2023-W{i:02d}", "value": 420000 + random.randint(-5000, 5000)} for i in range(1, 53)],
                "gasoline_level": [{"period": f"2023-W{i:02d}", "value": 220000 + random.randint(-2000, 2000)} for i in range(1, 53)],
                "distillate_level": [{"period": f"2023-W{i:02d}", "value": 115000 + random.randint(-1000, 1000)} for i in range(1, 53)]
            }
            return {"status": "success", "data": history, "timestamp": datetime.now().isoformat(), "mocked": True}

        history = {}
        with ThreadPoolExecutor(max_workers=min(10, len(EIAFetcher.SERIES))) as executor:
            future_to_name = {
                executor.submit(EIAFetcher.fetch_series_history, series_id, length=52): name
                for name, series_id in EIAFetcher.SERIES.items()
            }
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    values = future.result()
                    history[name] = values or []
                except Exception as e:
                    logger.error(f"Error fetching history for {name}: {e}")
                    history[name] = []

        return {
            "status": "success",
            "data": history,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching EIA weekly history: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )




@app.get("/api/news/bulletin")
async def get_news_bulletin():
    """Get top 10 NLP-scored news items"""
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(NewsFetcher.fetch_all_news)
            try:
                news = future.result(timeout=10)
            except FuturesTimeoutError:
                logger.error("News fetch timeout")
                return JSONResponse(status_code=503, content={"status": "error", "message": "News fetch timeout"})
        
        return {"status": "success", "data": news, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )




@app.get("/api/news/sentiment/trend")
async def get_sentiment_trend():
    """Get sentiment trend (5-day exponentially-decayed average)"""
    try:
        news = NewsFetcher.fetch_all_news()
        trend = NewsFetcher.calculate_sentiment_trend(news)
        return {
            "status": "success",
            "data": {
                "sentiment_trend": round(trend, 3),
                "news_count": len(news),
                "timestamp": datetime.now().isoformat(),
            },
        }
    except Exception as e:
        logger.error(f"Error calculating sentiment trend: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )




@app.get("/api/diagnostics/dxy")
async def get_dxy_diagnostics():
    """Run a test DXY fetch and return diagnostic details"""
    try:
        from services.price_fetcher import PriceFetcher, _DXY_DIAGNOSTICS
        import asyncio
        loop = asyncio.get_event_loop()
        # Trigger an active fetch to update the diagnostics
        await loop.run_in_executor(None, PriceFetcher._fetch_price_from_ticker, "DXY", "DX-Y.NYB")
        return {"status": "success", "data": _DXY_DIAGNOSTICS}
    except Exception as e:
        logger.error(f"Error in DXY diagnostics: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})




@app.get("/api/analytics/structure")
async def get_market_structure(symbol: str = "WTI"):
    """Get full curve data, calculated spreads, flies, and z-scores."""
    try:
        from services.curve_analytics import get_market_structure_analytics
        data = get_market_structure_analytics(symbol)
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(f"Error fetching market structure analytics: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})





        closes = [float(h['close']) for h in hist]
        highs = [float(h['high']) for h in hist]
        lows = [float(h['low']) for h in hist]

        ema_list = {}
        for p in [int(x) for x in ema_periods.split(',') if x.strip().isdigit()]:
            series = SignalCalculator.ema_series(closes, p)
            # align timestamps
            ema_list[f'ema_{p}'] = [round(x, 4) if x is not None else None for x in series]

        atr_series = SignalCalculator.calculate_atr(hist, atr_period)
        # atr_series can also contain None values for the initial period padding
        atr_series = [round(x, 4) if x is not None else None for x in atr_series]

        boll = SignalCalculator.calculate_bollinger_bands(closes, period=20, sigma=2.0) if closes else {
            "upper": 0.0,
            "middle": 0.0,
            "lower": 0.0,
            "width": 0.0,
            "position": "middle",
        }
        vol = SignalCalculator.calculate_realized_volatility(closes)

        return {
            'status': 'success',
            'data': {
                'symbol': symbol,
                'historical': hist,
                'ema_series': ema_list,
                'atr_series': atr_series,
                'bollinger': boll,
                'realized_vol_pct': vol,
                'timestamp': datetime.now().isoformat(),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Error generating indicators for {symbol}: {e}')
        return JSONResponse(status_code=500, content={'status': 'error', 'message': str(e)})




















@app.get("/api/news/sentiment-summary")
async def get_sentiment_summary():
    """Get overall market sentiment from latest news"""
    try:
        summary = NewsFetcher.get_sentiment_summary()
        return {
            "status": "success",
            "data": summary,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching sentiment summary: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})




@app.get("/api/news/finbert-status")
async def get_finbert_status():
    """Return FinBERT availability and a lightweight service check."""
    try:
        enabled = bool(os.getenv("HF_API_KEY"))
        if not enabled:
            # Return mock status if not configured
            result = {
                "enabled": False,
                "status": "online (mocked)",
                "message": "HF_API_KEY missing - using mock sentiment",
                "last_test": {"score": 0.65, "label": "positive"},
                "timestamp": datetime.now().isoformat(),
            }
            return {"status": "success", "data": result, "timestamp": datetime.now().isoformat()}

        result = {
            "enabled": enabled,
            "status": "online",
            "message": "FinBERT configured",
            "last_test": None,
            "timestamp": datetime.now().isoformat(),
        }
        score, label = SentimentAnalyzer.analyze_finbert(
            "Energy market outlook checking FinBERT live status"
        )
        result["last_test"] = {
            "score": score,
            "label": label,
        }
        return {"status": "success", "data": result, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error checking FinBERT status: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})




@app.get("/api/news/by-entity/{entity}")
async def get_news_by_entity(entity: str):
    """Get news filtered by geopolitical entity"""
    try:
        news = NewsFetcher.fetch_all_news(max_articles_per_source=15)
        filtered = [n for n in news if entity.lower() in [e.lower() for e in n.get("entities", [])]]
        return {
            "status": "success",
            "data": filtered,
            "entity": entity,
            "count": len(filtered),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching news by entity: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})




@app.get("/api/spreads/calendar")
async def get_calendar_spreads():
    """Get calendar spreads derived from historical Brent data where available.

    Uses real WTI 3-month history to approximate near-dated calendar spreads.
    Labels data as 'estimated' since real exchange calendar spread data requires
    CME/ICE API access.
    """
    try:
        wti_hist = PriceFetcher.fetch_historical("WTI", "3mo") or []
        if len(wti_hist) >= 30:
            # Estimate M1-M2 from avg rolling 21D vs 42D price difference
            closes = [float(h["close"]) for h in wti_hist]
            m1_avg = sum(closes[-21:]) / 21
            m2_avg = sum(closes[-42:-21]) / 21 if len(closes) >= 42 else m1_avg
            m3_avg = sum(closes[-63:-42]) / 21 if len(closes) >= 63 else m2_avg
            m1_m2  = round(m1_avg - m2_avg, 3)
            m2_m3  = round(m2_avg - m3_avg, 3)
            m3_m4  = round(m2_m3 * 0.8, 3)  # estimated
            curve_shape = "BACKWARDATION" if m1_m2 > 0 else "CONTANGO"
            data_source = "historical_estimated"
        else:
            m1_m2, m2_m3, m3_m4 = None, None, None
            curve_shape = "INITIALIZING"
            data_source = "insufficient_data"

        return {
            "status": "success",
            "data": {
                "M1_M2":       m1_m2,
                "M2_M3":       m2_m3,
                "M3_M4":       m3_m4,
                "curve_shape": curve_shape,
                "data_source": data_source,
                "note":        "Estimated from rolling price averages. Real calendar spreads require CME/ICE API.",
                "timestamp":   datetime.now().isoformat(),
            }
        }
    except Exception as e:
        logger.error(f"Error fetching calendar spreads: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )




@app.get("/api/spreads/crack")
async def get_crack_spreads():
    """Get crack spread calculations"""
    try:
        prices = PriceFetcher.fetch_all_prices()

        rbob_data = prices.get("RBOB")
        ho_data = prices.get("HO")
        wti_data = prices.get("WTI")
        brent_data = prices.get("Brent")
        go_data = prices.get("GO")

        if not (rbob_data and ho_data and wti_data and brent_data):
            raise HTTPException(status_code=503, detail="Insufficient price data for crack spread computation")

        cracks = SignalCalculator.calculate_crack_spreads(
            rbob=float(rbob_data["close"]),
            ulsd=float(ho_data["close"]),
            wti=float(wti_data["close"]),
            brent=float(brent_data["close"]),
            go_per_mt=float(go_data["close"]) if go_data else None,
        )
        return {"status": "success", "data": cracks}
    except Exception as e:
        logger.error(f"Error calculating crack spreads: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )




@app.get('/api/signals/multi-factor')
async def get_multi_factor_signals(symbols: str = 'WTI,Brent,RBOB,HO'):
    """Full multi-factor signal breakdown for each symbol.

    Returns 12-factor normalized scores, regime detection, relative strength
    ranking, and per-symbol action signals.
    """
    try:
        symbol_list = [s.strip() for s in symbols.split(',') if s.strip()]

        # Fetch shared data once
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_macro  = executor.submit(MacroFetcher.fetch_all_macro)
            future_news   = executor.submit(NewsFetcher.fetch_all_news)
            macro  = future_macro.result()
            news   = future_news.result()

        news_sentiment = NewsFetcher.calculate_sentiment_trend(news)

        # EIA anchor
        eia_anchor = None
        try:
            if os.getenv("EIA_API_KEY"):
                eia_raw = EIAFetcher.fetch_all_eia_data()
                crude = eia_raw.get("crude_level", {})
                eia_anchor = {"crude_inventory": {
                    "current_value": crude.get("current_value"),
                    "wow_change":    crude.get("wow_change"),
                }}
        except Exception:
            pass

        # CFTC
        cftc_data = None
        try:
            cftc_raw = CFTCFetcher.fetch_latest()
            if cftc_raw and cftc_raw.get("WTI", {}).get("mm_net_long") is not None:
                cftc_data = cftc_raw
        except Exception:
            pass

        # Per-symbol signals
        symbol_prices: dict = {}
        results = []
        for sym in symbol_list:
            hist = PriceFetcher.fetch_historical(sym, "3mo") or []
            closes = [float(h["close"]) for h in hist]
            if closes:
                symbol_prices[sym] = closes

            mf = compute_multi_factor_score(
                symbol=sym,
                candles=hist,
                macro=macro,
                eia_data=eia_anchor,
                cftc_data=cftc_data,
            )
            # Inject news into sub_scores
            sub = mf.get("sub_scores", {})
            sub["news_sentiment"] = round(news_sentiment, 3)

            # Additional technical indicators
            prices = closes
            rsi  = SignalCalculator.calculate_rsi(prices, 14) if prices else None
            macd = SignalCalculator.calculate_macd(prices) if prices else {}
            roc  = SignalCalculator.calculate_momentum_roc(prices, 14) if prices else None
            zsc  = SignalCalculator.calculate_price_zscore(prices, 20) if prices else None
            results.append({
                **mf,
                "sub_scores":    sub,
                "rsi_14":        rsi,
                "macd":          macd,
                "roc_14":        roc,
                "price_zscore":  zsc,
            })

        # Relative strength ranking
        rs_scores = calculate_relative_strength(symbol_prices, period=20)

        return {
            "status": "success",
            "data": {
                "symbols":            results,
                "relative_strength":  rs_scores,
                "news_sentiment":     round(news_sentiment, 3),
                "macro_snapshot": {
                    "dxy":            macro.get("dxy"),
                    "dxy_change":     macro.get("dxy_change"),
                    "spx_change":     macro.get("spx_change"),
                    "vix":            macro.get("vix"),
                    "us_10y_yield":   macro.get("us_10y_yield"),
                },
                "timestamp":          datetime.now().isoformat(),
            },
        }
    except Exception as e:
        logger.error(f"Error computing multi-factor signals: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})




@app.get('/api/analytics/covmatrix')
async def get_covmatrix(symbols: str = 'WTI,Brent,RBOB,HO'):
    """Return EWMA correlation matrix for requested symbols."""
    try:
        symbol_list = [s.strip() for s in symbols.split(',') if s.strip()]
        if not symbol_list:
            symbol_list = ['WTI', 'Brent', 'RBOB', 'HO']
        returns_data = {}
        for sym in symbol_list:
            hist = PriceFetcher.fetch_historical(sym, '3mo') or []
            closes = pd.Series([float(h['close']) for h in hist])
            if len(closes) > 1:
                returns_data[sym] = closes.pct_change().dropna()
            else:
                returns_data[sym] = pd.Series(dtype=float)
        min_len = min((len(v) for v in returns_data.values()), default=0)
        if min_len < 2:
            # fallback: synthetic diagonal
            n = len(symbol_list)
            correlation = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
            return {"status": "success", "data": {"symbols": symbol_list, "correlation": correlation}}
        returns_df = pd.DataFrame({sym: returns_data[sym].values[-min_len:] for sym in symbol_list})
        cov = ewma_cov_matrix(returns_df)
        # convert cov to correlation
        std_devs = cov.values.diagonal() ** 0.5
        corr_values = []
        for i in range(len(symbol_list)):
            row = []
            for j in range(len(symbol_list)):
                denom = std_devs[i] * std_devs[j]
                val = float(cov.iloc[i, j] / denom) if denom > 0 else (1.0 if i == j else 0.0)
                row.append(round(min(1.0, max(-1.0, val)), 4))
            corr_values.append(row)
        return {
            "status": "success",
            "data": {"symbols": symbol_list, "correlation": corr_values},
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error computing covmatrix: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})




@app.get("/api/debug/intraday")
def debug_intraday():
    return {"latest": _latest_intraday}




@app.post("/api/v1/backtest/run")
async def run_backtest(req: BacktestRequest, db: Session = Depends(get_db)):
    """Run a new backtest simulation."""
    try:
        from prediction.validation.walk_forward import run_walk_forward_validation
        from prediction.features.feature_matrix import build_historical_feature_matrix
        from services.price_fetcher import PriceFetcher
        import pandas as pd
        import uuid
        
        # 1. Fetch data
        wti_hist = PriceFetcher.fetch_historical(req.symbol, "10y")
        if not wti_hist:
            raise HTTPException(status_code=400, detail="Insufficient historical data")
            
        prices_df = pd.DataFrame(wti_hist)
        if "timestamp" in prices_df.columns:
            prices_df["date"] = pd.to_datetime(prices_df["timestamp"])
            prices_df.set_index("date", inplace=True)
        elif "date" in prices_df.columns:
            prices_df["date"] = pd.to_datetime(prices_df["date"])
            prices_df.set_index("date", inplace=True)
        
        # 2. Compute features
        feature_matrix = build_historical_feature_matrix(prices_df)
        
        # 3. Run validation & backtest engine
        results = run_walk_forward_validation(
            feature_matrix, 
            prices_df, 
            req.horizon_days, 
            symbol=req.symbol
        )
        
        if "error" in results:
            raise HTTPException(status_code=400, detail=results["error"])
            
        backtest_data = results["backtest"]
        
        # 4. Save to DB
        from models import BacktestResult
        new_result = BacktestResult(
            id=str(uuid.uuid4()),
            symbol=req.symbol,
            strategy_name=f"Ensemble_HMM_walk_forward_{req.horizon_days}d",
            parameters=req.model_dump(),
            metrics=backtest_data["metrics"],
            equity_curve=backtest_data["equity_curve"],
            trade_log=backtest_data["trade_log"]
        )
        db.add(new_result)
        db.commit()
        
        return {
            "status": "success", 
            "data": {
                "id": new_result.id,
                "metrics": backtest_data["metrics"]
            }
        }
    except Exception as e:
        logger.error(f"Error running backtest: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

class MultiBacktestRequest(BaseModel):
    symbols: list[str] = ["WTI", "Brent", "RBOB", "HO"]
    initial_capital: float = 1000000.0
    horizon_days: int = 5
    expanding: bool = True



@app.post("/api/v1/backtest/multi")
async def run_multi_backtest(req: MultiBacktestRequest):
    """Run a multi-asset backtest simulation."""
    try:
        from prediction.validation.multi_asset_backtest import run_multi_asset_backtest
        
        results = run_multi_asset_backtest(
            symbols=req.symbols,
            initial_capital=req.initial_capital,
            horizon_days=req.horizon_days,
            expanding=req.expanding
        )
        
        if "error" in results:
            raise HTTPException(status_code=400, detail=results["error"])
            
        return {
            "status": "success",
            "data": results
        }
    except Exception as e:
        logger.error(f"Error running multi-asset backtest: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})



@app.get("/api/v1/backtest/results")
async def get_backtest_results(db: Session = Depends(get_db)):
    """Fetch all stored backtest results."""
    try:
        from models import BacktestResult
        results = db.query(BacktestResult).order_by(BacktestResult.created_at.desc()).all()
        return {
            "status": "success",
            "data": [{
                "id": r.id,
                "symbol": r.symbol,
                "strategy_name": r.strategy_name,
                "parameters": r.parameters,
                "metrics": r.metrics,
                "created_at": r.created_at.isoformat()
            } for r in results]
        }
    except Exception as e:
        logger.error(f"Error fetching backtest results: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})



@app.get("/api/v1/backtest/results/{result_id}")
async def get_backtest_result_by_id(result_id: str, db: Session = Depends(get_db)):
    """Fetch a specific backtest result including full equity curve."""
    try:
        from models import BacktestResult
        result = db.query(BacktestResult).filter(BacktestResult.id == result_id).first()
        if not result:
            raise HTTPException(status_code=404, detail="Backtest result not found")
            
        return {
            "status": "success",
            "data": {
                "id": result.id,
                "symbol": result.symbol,
                "strategy_name": result.strategy_name,
                "parameters": result.parameters,
                "metrics": result.metrics,
                "equity_curve": result.equity_curve,
                "trade_log": result.trade_log,
                "created_at": result.created_at.isoformat()
            }
        }
    except Exception as e:
        logger.error(f"Error fetching backtest result {result_id}: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})




@app.get("/api/backtest/runs")
async def get_backtest_runs():
    """List all backtest runs."""
    try:
        from backtesting.trade_journal import TradeJournal
        journal = TradeJournal()
        runs = journal.get_backtest_ids()
        return {"status": "success", "data": runs, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error listing backtest runs: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})




@app.get("/api/backtest/analytics")
async def get_backtest_analytics(backtest_id: str = None):
    """Get full analytics for the latest or specified backtest run."""
    try:
        from backtesting.trade_journal import TradeJournal
        from backtesting.analytics import BacktestAnalytics
        journal = TradeJournal()
        trades = journal.get_trades(backtest_id=backtest_id, limit=5000)
        if not trades:
            return {"status": "success", "data": BacktestAnalytics([]).summary(), "timestamp": datetime.now().isoformat()}
        analytics = BacktestAnalytics(trades)
        return {"status": "success", "data": analytics.summary(), "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error computing analytics: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})




@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# Mount static frontend files if available (Must be at the end to avoid intercepting API routes)
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")



@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}




