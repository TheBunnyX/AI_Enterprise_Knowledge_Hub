import os
from celery import Celery
celery=Celery('hub',broker=os.getenv('CELERY_BROKER_URL','redis://localhost:6379/0'))
celery.conf.update(task_acks_late=True,task_reject_on_worker_lost=True,worker_prefetch_multiplier=1,task_track_started=True,timezone='Asia/Bangkok',task_routes={'hub.tasks.maintenance_task':{'queue':'ops'},'hub.tasks.backup_task':{'queue':'ops'},'hub.tasks.restore_task':{'queue':'ops'}},beat_schedule={'maintenance':{'task':'hub.tasks.maintenance_task','schedule':60.0}})
@celery.task
def execute_task(id):
    from .jobs import execute
    execute(id)
@celery.task
def ingest_task(id):
    from .jobs import schedule_ingest
    schedule_ingest(id)
@celery.task
def media_task(id):
    from .jobs import schedule_media
    schedule_media(id)
@celery.task
def backup_task(id):
    from .backups import create_snapshot
    create_snapshot(id)
@celery.task
def restore_task(id):
    from .backups import restore_live
    restore_live(id)
@celery.task
def maintenance_task():
    from .jobs import recover,maintenance
    if maintenance():return
    from .backups import automatic_backup
    from .openrouter_sync import run_auto_sync
    try:run_auto_sync()  # self-throttled to every 5 minutes and only when an admin switched it on
    except Exception:pass
    recover();automatic_backup()
    try:
        from .sync import run_due
        run_due()  # each source decides by its own interval whether it is due
    except Exception:pass
    try:
        from .jobs import redis_client
        if redis_client().set('hub:cleanup',1,nx=True,ex=3600):  # hourly, whichever worker gets there first
            from .cleanup import run
            run()
    except Exception:pass  # housekeeping must never stop recovery or backups
