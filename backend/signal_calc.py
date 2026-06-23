from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SignalCalculator:
    """Calculate composite trading signals"""

    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> Optional[float]:
        """Calculate exponential moving average"""
        if len(prices) < period:
            return None

        k = 2 / (period + 1)
        # Standard EMA starts with SMA of first `period` prices
        ema = sum(prices[:period]) / period
        for price in prices[period:]:
            ema = price * k + ema * (1 - k)
        return ema

    @staticmethod
    def calculate_ema_trend(ema20: Optional[float], ema50: Optional[float]) -> float:
        """Calculate EMA trend score (-1 to +1)"""
        if ema20 is None or ema50 is None:
            return 0.0

        if ema20 > ema50:
            return 1.0  # Bullish
        elif ema20 < ema50:
            return -1.0  # Bearish
        else:
            return 0.0  # Neutral

    @staticmethod
    def calculate_bollinger_bands(
        prices: List[float], period: int = 20, sigma: float = 2.0
    ) -> Dict:
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            return {}

        recent = prices[-period:]
        sma = sum(recent) / period
        variance = sum((p - sma) ** 2 for p in recent) / period
        std = variance ** 0.5
        width = 2 * sigma * std

        return {
            "upper": sma + sigma * std,
            "middle": sma,
            "lower": sma - sigma * std,
            "width": width,
            "position": "upper" if prices[-1] > sma + std else "lower" if prices[-1] < sma - std else "middle",
        }

    @staticmethod
    def ema_series(prices: List[float], period: int) -> List[float]:
        """Return EMA series aligned with prices (None for first period-1 values)"""
        if len(prices) < period:
            return [None] * len(prices)
        k = 2 / (period + 1)
        emas: List[float] = [None] * (period - 1)
        
        # Standard EMA starts with SMA of the first `period` prices
        ema = sum(prices[:period]) / period
        emas.append(ema)
        
        for price in prices[period:]:
            ema = price * k + ema * (1 - k)
            emas.append(ema)
        return emas

    @staticmethod
    def calculate_atr(candles: List[Dict], period: int = 14) -> List[float]:
        """Calculate ATR series from candles (each with high, low, close). Returns list of ATR aligned with candles (None for initial values)."""
        if not candles:
            return []
        trs: List[float] = []
        prev_close = None
        for c in candles:
            high = float(c.get('high', 0))
            low = float(c.get('low', 0))
            if prev_close is None:
                tr = high - low
            else:
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
            prev_close = float(c.get('close', prev_close or 0))

        # Simple moving average ATR for first ATR value, then Wilder's smoothing
        atrs: List[float] = []
        if len(trs) < 1:
            return atrs
        if len(trs) < period:
            # return rolling average partials
            for i in range(len(trs)):
                window = trs[: i + 1]
                atrs.append(sum(window) / len(window))
            return atrs

        # initial ATR = SMA of first period TRs
        initial_atr = sum(trs[:period]) / period
        atrs = [None] * (period - 1)  # type: ignore
        atrs.append(initial_atr)

        # Wilder smoothing
        prev_atr = initial_atr
        for tr in trs[period:]:
            prev_atr = (prev_atr * (period - 1) + tr) / period
            atrs.append(prev_atr)

        # fill any remaining leading None with first computed average for consistency
        return [float(x) if x is not None else float(atrs[period - 1]) for x in atrs]

    @staticmethod
    def calculate_realized_volatility(prices: List[float], window: int = 20) -> float:
        """Calculate annualized realized volatility"""
        if len(prices) < 2:
            return 0.0

        recent = prices[-window:]
        returns = [(recent[i] - recent[i - 1]) / recent[i - 1] for i in range(1, len(recent))]
        variance = sum(r**2 for r in returns) / len(returns)
        daily_vol = variance ** 0.5
        annual_vol = daily_vol * (252 ** 0.5)  # 252 trading days/year
        return annual_vol * 100

    @staticmethod
    def get_vol_regime(annual_vol: float) -> str:
        """Classify volatility regime"""
        if annual_vol < 20:
            return "LOW"
        elif annual_vol < 35:
            return "ELEVATED"
        else:
            return "HIGH-VOL"

    @staticmethod
    def calculate_position_sizing(
        base_size: int,
        composite_score: float,
        vol_regime: str,
        cftc_extreme: bool = False,
    ) -> Dict:
        """Calculate suggested position size with modifiers"""
        # Score modifier: -100→+100 maps to 0→1 scaling
        score_scalar = max(0.1, (composite_score + 100) / 200)

        # Vol regime modifier
        vol_scalar = {
            "LOW": 1.0,
            "ELEVATED": 0.85,
            "HIGH-VOL": 0.75,
        }.get(vol_regime, 1.0)

        # CFTC crowded positioning modifier
        cftc_scalar = 0.5 if cftc_extreme else 1.0

        suggested_size = int(base_size * score_scalar * vol_scalar * cftc_scalar)

        return {
            "base_size": base_size,
            "suggested_size": suggested_size,
            "score_scalar": round(score_scalar, 2),
            "vol_scalar": round(vol_scalar, 2),
            "cftc_scalar": round(cftc_scalar, 2),
            "modifiers": [
                f"Score ×{score_scalar:.2f}",
                f"{vol_regime} vol ×{vol_scalar:.2f}",
                "Crowded long ×0.5" if cftc_extreme else None,
            ],
        }

    @staticmethod
    def calculate_composite_score(
        ema_trend: float,
        news_sentiment: float,
        cftc_z_score: float,
        eia_surprise: float,
        seasonality: float,
    ) -> Dict:
        """Calculate composite score from sub-scores"""
        # Weights: EMA 40%, News 20%, CFTC 20%, EIA 10%, Seasonality 10%
        composite = (
            ema_trend * 0.4
            + news_sentiment * 0.2
            + (cftc_z_score * -1) * 0.2  # Inverted for contrarian signal
            + eia_surprise * 0.1
            + seasonality * 0.1
        )

        # Normalize to -100 to +100
        composite_score = composite * 100

        # Determine regime
        if composite_score > 30:
            regime = "BULLISH"
        elif composite_score < -30:
            regime = "BEARISH"
        else:
            regime = "NEUTRAL"

        return {
            "composite_score": round(composite_score, 1),
            "regime": regime,
            "sub_scores": {
                "ema_trend": round(ema_trend, 2),
                "news_sentiment": round(news_sentiment, 2),
                "cftc_positioning": round(cftc_z_score * -1, 2),
                "eia_surprise": round(eia_surprise, 2),
                "seasonality": round(seasonality, 2),
            },
            "weights": {
                "ema_trend": 0.4,
                "news_sentiment": 0.2,
                "cftc_positioning": 0.2,
                "eia_surprise": 0.1,
                "seasonality": 0.1,
            },
            "timestamp": datetime.now().isoformat(),
        }

    @staticmethod
    def calculate_crack_spreads(
        rbob: float,
        ulsd: float,
        wti: float,
        brent: float,
        go_per_mt: float | None = None,
    ) -> Dict:
        """Calculate crack spreads"""
        # 3:2:1 Crack Spread ($/bbl)
        # RBOB and ULSD in $/gal, already converted to $/bbl
        rbob_bbl = rbob
        ulsd_bbl = ulsd
        crack_321 = (2 * rbob_bbl + 1 * ulsd_bbl - 3 * wti) / 3
        crack_532 = (3 * rbob_bbl + 2 * ulsd_bbl - 5 * wti) / 5

        # Brent-GO Crack Spread ($/bbl)
        # GO in $/mt, convert to $/bbl (1 MT ≈ 7.45 barrels)
        crack_brent_go = None
        crack_11_gasoil = None
        if go_per_mt is not None:
            go_per_bbl = go_per_mt / 7.45
            crack_brent_go = go_per_bbl - brent
            crack_11_gasoil = crack_brent_go

        # CL-Brent spread
        cl_brent_spread = wti - brent

        return {
            "crack_321": round(crack_321, 2),
            "crack_532": round(crack_532, 2),
            "crack_11_gasoil": round(crack_11_gasoil, 2) if crack_11_gasoil is not None else None,
            "crack_brent_go": round(crack_brent_go, 2) if crack_brent_go is not None else None,
            "cl_brent_spread": round(cl_brent_spread, 2),
            "timestamp": datetime.now().isoformat(),
        }

    @staticmethod
    def calculate_correlation(prices1: List[float], prices2: List[float]) -> Optional[float]:
        """Calculate Pearson correlation coefficient"""
        if len(prices1) < 2 or len(prices2) < 2:
            return None

        n = min(len(prices1), len(prices2))
        prices1 = prices1[-n:]
        prices2 = prices2[-n:]

        mean1 = sum(prices1) / n
        mean2 = sum(prices2) / n

        numerator = sum((prices1[i] - mean1) * (prices2[i] - mean2) for i in range(n))
        sum_sq1 = sum((p - mean1) ** 2 for p in prices1)
        sum_sq2 = sum((p - mean2) ** 2 for p in prices2)

        denominator = (sum_sq1 * sum_sq2) ** 0.5

        if denominator == 0:
            return None

        return numerator / denominator

    @staticmethod
    def calculate_rolling_beta(prices_dependent: List[float], prices_independent: List[float]) -> Optional[float]:
        """Calculate rolling beta (90-day regression)"""
        if len(prices_dependent) < 90 or len(prices_independent) < 90:
            return None

        dep = prices_dependent[-90:]
        indep = prices_independent[-90:]

        # Returns
        dep_returns = [(dep[i] - dep[i - 1]) / dep[i - 1] for i in range(1, len(dep))]
        indep_returns = [(indep[i] - indep[i - 1]) / indep[i - 1] for i in range(1, len(indep))]

        # Covariance and variance
        n = len(dep_returns)
        mean_dep = sum(dep_returns) / n
        mean_indep = sum(indep_returns) / n

        covariance = sum(
            (dep_returns[i] - mean_dep) * (indep_returns[i] - mean_indep) for i in range(n)
        ) / n
        variance = sum((indep_returns[i] - mean_indep) ** 2 for i in range(n)) / n

        if variance == 0:
            return None

        return covariance / variance

    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
        """Calculate Relative Strength Index"""
        if len(prices) < period + 1:
            return None
            
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        for i in range(period, len(prices) - 1):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            
        if avg_loss == 0:
            return 100.0
            
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
        """Calculate MACD"""
        if len(prices) < slow + signal:
            return {"macd": None, "signal": None, "histogram": None}
            
        fast_ema = SignalCalculator.ema_series(prices, fast)
        slow_ema = SignalCalculator.ema_series(prices, slow)
        
        macd_line = []
        for f, s in zip(fast_ema, slow_ema):
            if f is not None and s is not None:
                macd_line.append(f - s)
            else:
                macd_line.append(None)
                
        # Calculate signal line
        valid_macd = [x for x in macd_line if x is not None]
        if len(valid_macd) < signal:
            return {"macd": None, "signal": None, "histogram": None}
            
        signal_line_valid = SignalCalculator.ema_series(valid_macd, signal)
        signal_line = [None] * (len(macd_line) - len(valid_macd)) + signal_line_valid
        
        macd_val = macd_line[-1]
        sig_val = signal_line[-1]
        hist_val = macd_val - sig_val if macd_val is not None and sig_val is not None else None
        
        return {
            "macd": macd_val,
            "signal": sig_val,
            "histogram": hist_val
        }

    @staticmethod
    def calculate_momentum_roc(prices: List[float], period: int = 14) -> Optional[float]:
        """Calculate Rate of Change"""
        if len(prices) <= period:
            return None
        return ((prices[-1] - prices[-(period+1)]) / prices[-(period+1)]) * 100

    @staticmethod
    def calculate_price_zscore(prices: List[float], period: int = 20) -> Optional[float]:
        """Calculate Price Z-Score"""
        if len(prices) < period:
            return None
        recent = prices[-period:]
        mean = sum(recent) / period
        variance = sum((p - mean) ** 2 for p in recent) / period
        std = variance ** 0.5
        if std == 0:
            return 0.0
        return (prices[-1] - mean) / std
