from sqlalchemy import Column, Float, DateTime, String, Integer, Boolean, JSON
from sqlalchemy.sql import func
from database import Base


class PriceData(Base):
    __tablename__ = "prices"

    id = Column(String, primary_key=True, index=True)
    symbol = Column(String, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    timestamp = Column(DateTime, server_default=func.now(), index=True)


class PriceHistory(Base):
    __tablename__ = "price_history"
    
    id = Column(String, primary_key=True, index=True)
    symbol = Column(String, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    date = Column(String, index=True)  # YYYY-MM-DD format
    timestamp = Column(DateTime, server_default=func.now(), index=True)


class InventoryData(Base):
    __tablename__ = "inventory"

    id = Column(String, primary_key=True, index=True)
    series_id = Column(String, index=True)
    value = Column(Float)
    unit = Column(String)
    period = Column(String)
    timestamp = Column(DateTime, server_default=func.now(), index=True)


class NewsItem(Base):
    __tablename__ = "news"

    id = Column(String, primary_key=True, index=True)
    headline = Column(String)
    source = Column(String)
    sentiment_score = Column(Float, default=0.0)
    sentiment_label = Column(String, default="neutral")  # positive, neutral, negative
    url = Column(String)
    published_at = Column(DateTime, index=True)
    fetched_at = Column(DateTime, server_default=func.now(), index=True)
    relevance_score = Column(Float, default=0.5)
    entities = Column(JSON, default=list)  # geopolitical entities mentioned





class MacroIndicator(Base):
    __tablename__ = "macro_indicators"
    
    id = Column(String, primary_key=True, index=True)
    indicator_name = Column(String, index=True)  # e.g., "DXY", "US_10Y_YIELD"
    value = Column(Float)
    change_pct = Column(Float)
    timestamp = Column(DateTime, server_default=func.now(), index=True)


class BacktestResult(Base):
    __tablename__ = "backtest_results"
    
    id = Column(String, primary_key=True, index=True)
    symbol = Column(String, index=True)
    strategy_name = Column(String)
    parameters = Column(JSON)  # Store configuration like transaction costs, slippage
    metrics = Column(JSON)     # Store dict of Sharpe, Return, Drawdown, etc.
    equity_curve = Column(JSON) # Store daily equity curve
    trade_log = Column(JSON)    # Store trades executed
    created_at = Column(DateTime, server_default=func.now(), index=True)
