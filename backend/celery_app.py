from celery import Celery

celery_app = Celery(
    "quant_tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1"
)
