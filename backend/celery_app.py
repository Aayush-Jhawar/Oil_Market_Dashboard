import os
from celery import Celery
from celery.schedules import crontab

# Configure Redis as broker and backend
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/0")

celery_app = Celery(
    "worker",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["worker.tasks"]
)

# Optional configuration, see the Celery application user guide.
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # task_always_eager=True  # useful for local debugging without running worker
)

# Setup Celery Beat schedules
celery_app.conf.beat_schedule = {
    # e.g., run the daily pipeline at 23:00 UTC
    "run-daily-pipeline": {
        "task": "worker.tasks.run_daily_prediction_pipeline",
        "schedule": crontab(hour=23, minute=0),
    },
    "ingest-market-data": {
        "task": "worker.tasks.ingest_daily_market_data",
        "schedule": crontab(hour="*", minute=0),  # Top of every hour
    }
}
