import logging
from celery_app import celery_app

# Note: we need to setup the correct path since tasks.py is inside worker/
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# The legacy ML prediction pipeline has been archived to legacy_archive/prediction.
# Import it lazily inside the task (not at module import time) so that:
#   1. importing this module never crashes the Celery worker if the archived
#      ML dependencies are missing, and
#   2. the still-active ingest_daily_market_data task below remains usable.

@celery_app.task(name="worker.tasks.run_daily_prediction_pipeline")
def run_daily_prediction_pipeline(symbol: str = "WTI"):
    """
    Celery task to run the daily ML pipeline:
    1. Fetch latest data
    2. Compute features
    3. Detect regime
    4. Make forecasts
    5. Generate trade signals
    """
    logger.info(f"Starting daily prediction pipeline for {symbol}")
    try:
        from legacy_archive.prediction.daily_runner import run_daily_pipeline
        run_daily_pipeline(symbol)
        logger.info(f"Successfully completed daily pipeline for {symbol}")
    except Exception as e:
        logger.error(f"Failed to run daily pipeline for {symbol}: {e}")
        raise

from services.price_fetcher import PriceFetcher
from services.eia_fetcher import EIAFetcher
from services.macro_fetcher import MacroFetcher, CFTCFetcher

@celery_app.task(name="worker.tasks.ingest_daily_market_data")
def ingest_daily_market_data():
    """
    Data ingestion task that downloads OHLCV, CFTC, EIA, and Macro data
    and saves them to the Postgres database.
    """
    logger.info("Starting daily market data ingestion...")
    try:
        # Ingest price data
        pf = PriceFetcher()
        pf.fetch_and_save_data()
        
        # Ingest EIA fundamentals
        eia = EIAFetcher()
        eia.fetch_and_save_all()
        
        # Ingest Macro
        macro = MacroFetcher()
        macro.fetch_and_save_all()
        
        # Ingest CFTC
        cftc = CFTCFetcher()
        cftc.fetch_and_save_latest()
        
        logger.info("Successfully completed daily market data ingestion.")
    except Exception as e:
        logger.error(f"Error during market data ingestion: {e}")
        raise
