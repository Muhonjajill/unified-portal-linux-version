import os
from celery import Celery
from celery.schedules import crontab   # <-- add this

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "unified_portal.settings")

app = Celery("unified_portal")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

"""
# --- ADD THIS PART ---
app.conf.beat_schedule = {
    "auto-escalate-every-5-mins": {
        "task": "core.tasks.run_auto_escalation",   # must match your task name
        "schedule": crontab(minute="*/1"),        # every 5 minutes
    },
}
"""