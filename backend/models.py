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


class SpreadAnalysis(Base):
    __tablename__ = "spreads"
    
    id = Column(String, primary_key=True, index=True)
    spread_name = Column(String, index=True)  # e.g., "BRENT-WTI", "GASOLINE-CRACK"
    value = Column(Float)
    avg_5day = Column(Float)
    avg_30day = Column(Float)
    deviation_5day = Column(Float)  # z-score from 5-day average
    deviation_30day = Column(Float)  # z-score from 30-day average
    is_anomaly = Column(Boolean, default=False)
    timestamp = Column(DateTime, server_default=func.now(), index=True)


class Alert(Base):
    __tablename__ = "alerts"
    
    id = Column(String, primary_key=True, index=True)
    alert_type = Column(String, index=True)  # e.g., "spread_anomaly", "volume_spike", "price_move"
    severity = Column(String)  # "warning", "critical"
    message = Column(String)
    symbol = Column(String, nullable=True)
    value = Column(Float, nullable=True)
    threshold = Column(Float, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    is_acknowledged = Column(Boolean, default=False)


class MacroIndicator(Base):
    __tablename__ = "macro_indicators"
    
    id = Column(String, primary_key=True, index=True)
    indicator_name = Column(String, index=True)  # e.g., "DXY", "US_10Y_YIELD"
    value = Column(Float)
    change_pct = Column(Float)
    timestamp = Column(DateTime, server_default=func.now(), index=True)
