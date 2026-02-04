"""Celery application configuration."""

from celery import Celery

from app.config import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "video_material_generator",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Tokyo",
    enable_utc=True,

    # Task execution settings
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3300,  # Soft limit 55 minutes

    # Worker settings
    worker_prefetch_multiplier=1,  # Process one task at a time (GPU tasks)
    worker_concurrency=1,  # Single worker for GPU

    # Result backend settings
    result_expires=86400,  # Results expire after 24 hours

    # Task routes (optional, for future multi-queue setup)
    task_routes={
        "app.workers.tasks.process_video": {"queue": "gpu"},
    },
)
