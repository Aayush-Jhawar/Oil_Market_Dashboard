import logging
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from services.backtest.metrics import calculate_metrics

logger = logging.getLogger(__name__)

class Portfolio:
    def __init__(self, initial_capital: float = 1_000_000.0):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, float] = {}  # symbol -> quantity
        self.position_prices: Dict[str, float] = {} # symbol -> average entry price
        self.contract_multipliers: Dict[str, float] = {"WTI": 1000.0, "Brent": 1000.0, "RBOB": 420.0, "HO": 420.0, "NG": 10000.0}
        
        self.equity_history: List[Dict] = []
        self.trade_log: List[Dict] = []
        
    def get_total_equity(self, current_prices: Dict[str, float]) -> float:
        equity = self.cash
        for sym, qty in self.positions.items():
            if sym in current_prices:
                price = current_prices[sym]
            else:
                fallback = self.position_prices.get(sym, 0.0)
                price = fallback * self.contract_multipliers.get(sym, 1.0)
            equity += qty * price
        return equity
        
    def record_state(self, date: pd.Timestamp, current_prices: Dict[str, float]):
        self.equity_history.append({
            "date": date,
            "equity": self.get_total_equity(current_prices),
            "cash": self.cash
        })
        
class BacktestEngine:
    def __init__(self, 
                 initial_capital: float = 1_000_000.0,
                 transaction_cost_per_trade: float = 3.5, # $3.5 commission per contract
                 slippage_per_trade: float = 10.0, # $10 slippage per contract
                 contract_multipliers: Optional[Dict[str, float]] = None,
                 target_annual_volatility: float = 0.05, # 5% annualized vol target
                 max_drawdown_limit: float = 0.10, # 10% max drawdown kill switch
                 ):
        self.initial_capital = initial_capital
        self.transaction_cost = transaction_cost_per_trade
        self.slippage = slippage_per_trade
        self.contract_multipliers = contract_multipliers or {"WTI": 1000.0, "Brent": 1000.0, "RBOB": 420.0, "HO": 420.0, "NG": 10000.0}
        self.target_annual_vol = target_annual_volatility
        self.max_drawdown_limit = max_drawdown_limit
        self._peak_equity = initial_capital
        self._kill_switch_active = False
        
        self.portfolio = Portfolio(initial_capital)
        
    def _calculate_volatilities(self, price_dict: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        """Calculate 20-day rolling daily volatility for each asset."""
        vols = {}
        for sym, df in price_dict.items():
            returns = df['close'].pct_change()
            # 20-day rolling std, min_periods=5
            vols[sym] = returns.rolling(window=20, min_periods=5).std()
        return vols
        
    def run(self, predictions_dict: Dict[str, pd.DataFrame], price_dict: Dict[str, pd.DataFrame]) -> Dict:
        """
        Run the historical simulation across multiple assets.
        
        Args:
            predictions_dict: Dict mapping symbol -> DataFrame of predictions
            price_dict: Dict mapping symbol -> DataFrame of prices
        """
        logger.info("Starting multi-asset historical simulation...")
        
        # 1. Compute rolling volatilities
        vols_dict = self._calculate_volatilities(price_dict)
        
        # 2. Align all dates
        # Get the union of all dates across all price dataframes
        all_dates = pd.DatetimeIndex([])
        for df in price_dict.values():
            all_dates = all_dates.union(df.index)
        all_dates = all_dates.sort_values()
        
        # Target daily dollar risk for the portfolio
        target_daily_risk = self.initial_capital * (self.target_annual_vol / np.sqrt(252))
        
        for i in range(len(all_dates) - 1):
            current_date = all_dates[i]
            next_date = all_dates[i+1]
            
            # ── Drawdown Kill Switch ─────────────────────────────────────────
            current_equity = self.portfolio.get_total_equity(
                {sym: df.loc[current_date, 'close'] * self.contract_multipliers.get(sym, 1.0)
                 for sym, df in price_dict.items() if current_date in df.index}
            )
            self._peak_equity = max(self._peak_equity, current_equity)
            current_drawdown = (self._peak_equity - current_equity) / self._peak_equity if self._peak_equity > 0 else 0
            
            if current_drawdown > self.max_drawdown_limit and not self._kill_switch_active:
                self._kill_switch_active = True
                logger.warning(
                    f"KILL SWITCH ACTIVATED on {current_date}: "
                    f"Drawdown {current_drawdown:.1%} > {self.max_drawdown_limit:.1%} limit. "
                    f"Halving all positions."
                )
            elif current_drawdown < self.max_drawdown_limit * 0.5:
                # Reset kill switch when drawdown recovers to half the limit
                self._kill_switch_active = False
            
            # Determine active symbols on current_date
            active_symbols = [sym for sym, preds in predictions_dict.items() if current_date in preds.index]
            
            # Daily risk budget per active asset (equal risk contribution)
            if active_symbols:
                risk_per_asset = target_daily_risk / len(active_symbols)
            else:
                risk_per_asset = 0
            
            # Kill switch: halve risk budget
            if self._kill_switch_active:
                risk_per_asset *= 0.5
                
            current_close_prices = {}
            for sym, df in price_dict.items():
                if current_date in df.index:
                    current_close_prices[sym] = df.loc[current_date, 'close'] * self.contract_multipliers.get(sym, 1.0)
            
            # Iterate through all configured assets
            for sym in self.contract_multipliers.keys():
                # Get current and target positions
                current_position = self.portfolio.positions.get(sym, 0)
                target_position = 0
                
                exec_price = None
                close_price = None
                
                # Check if we have data for the next day to execute and M2M
                if sym in price_dict and next_date in price_dict[sym].index:
                    next_row = price_dict[sym].loc[next_date]
                    exec_price = next_row['open']
                    close_price = next_row['close']
                    
                if sym in active_symbols and exec_price is not None:
                    pred_row = predictions_dict[sym].loc[current_date]
                    signal = pred_row['prediction_label']
                    
                    # Compute position size using volatility targeting
                    current_price_val = price_dict[sym].loc[current_date, 'close']
                    daily_vol = vols_dict[sym].loc[current_date]
                    
                    if pd.isna(daily_vol) or daily_vol == 0 or current_price_val <= 5.0:
                        # Fallback if no vol data or price is dangerously close to zero
                        position_size_contracts = 1
                    else:
                        # dollar_vol_per_contract = price * multiplier * daily_vol
                        dollar_vol_per_contract = current_price_val * self.contract_multipliers.get(sym, 1.0) * daily_vol
                        
                        # Number of contracts to meet the risk budget
                        position_size_contracts = int(np.floor(risk_per_asset / dollar_vol_per_contract))
                        
                        # Hard cap leverage: Maximum 1 contract per $1M AUM
                        total_equity = self.portfolio.get_total_equity(current_close_prices)
                        max_contracts_per_million = 1
                        max_contracts = int(np.floor((total_equity / 1_000_000.0) * max_contracts_per_million))
                        
                        # Apply cap and ensure at least 1 contract if active
                        position_size_contracts = min(position_size_contracts, max_contracts)
                        position_size_contracts = max(1, position_size_contracts) 
                    
                    if signal in ['UP', 'WIDEN']:
                        target_position = position_size_contracts
                    elif signal in ['DOWN', 'NARROW']:
                        target_position = -position_size_contracts
                
                # If we have no execution price next day, we must force liquidation (or hold if impossible)
                # For simplicity, if we can't execute, we just carry over position and use old M2M
                if exec_price is None:
                    continue
                    
                contracts_to_trade = target_position - current_position
                
                if contracts_to_trade != 0:
                    multiplier = self.contract_multipliers.get(sym, 1.0)
                    trade_value_notional = contracts_to_trade * exec_price * multiplier
                    
                    # Multi-leg cost multiplier
                    legs = 1
                    if "FLY" in sym:
                        legs = 4
                    elif "CRACK" in sym:
                        legs = 3
                    elif "SPREAD" in sym:
                        legs = 2
                        
                    cost = abs(contracts_to_trade) * self.transaction_cost * legs
                    slip = abs(contracts_to_trade) * self.slippage * legs
                    
                    # Deduct costs and slippage from cash
                    self.portfolio.cash -= (cost + slip)
                    
                    # Update cash for the underlying asset transaction
                    self.portfolio.cash -= trade_value_notional
                    
                    # Update position
                    self.portfolio.positions[sym] = target_position
                    if target_position != 0:
                        self.portfolio.position_prices[sym] = exec_price
                    else:
                        self.portfolio.position_prices[sym] = 0.0
                        
                    self.portfolio.trade_log.append({
                        "date": next_date,
                        "symbol": sym,
                        "action": "BUY" if contracts_to_trade > 0 else "SELL",
                        "qty": abs(contracts_to_trade),
                        "price": exec_price,
                        "cost": cost,
                        "slippage": slip
                    })
                
                # Update current_close_prices for M2M record at next_date
                if close_price is not None:
                    current_close_prices[sym] = close_price * self.contract_multipliers.get(sym, 1.0)
            
            # Record state at the end of the next day
            self.portfolio.record_state(next_date, current_close_prices)
            
        # Calculate metrics
        if not self.portfolio.equity_history:
            return {"error": "No equity history generated"}
            
        equity_df = pd.DataFrame(self.portfolio.equity_history).set_index("date")
        equity_curve = equity_df["equity"]
        
        metrics = calculate_metrics(equity_curve, self.initial_capital)
        
        # Serialize equity history for frontend
        equity_history_serializable = []
        for rec in self.portfolio.equity_history:
            equity_history_serializable.append({
                "date": rec["date"].strftime("%Y-%m-%d"),
                "equity": round(rec["equity"], 2),
                "cash": round(rec["cash"], 2)
            })
            
        return {
            "metrics": metrics,
            "equity_curve": equity_history_serializable,
            "trade_log": [
                {
                    **t, 
                    "date": t["date"].strftime("%Y-%m-%d"),
                    "price": round(t["price"], 2),
                    "cost": round(t["cost"], 2),
                    "slippage": round(t["slippage"], 2)
                } for t in self.portfolio.trade_log
            ]
        }
