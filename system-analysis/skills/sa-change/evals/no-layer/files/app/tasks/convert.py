import os
import httpx
from celery import Celery
from app.models import Document, DocumentStatus
from app.session import Session
from app.storage import put
from app.notify import notify_failure

celery = Celery("converter", broker=os.getenv("REDIS_URL"))
celery.conf.beat_schedule = {
    "cleanup-old": {"task": "app.tasks.convert.cleanup", "schedule": 86400.0},
}


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def convert_document(self, doc_id: str):
    with Session() as s:
        doc = s.get(Document, doc_id)
        doc.status = DocumentStatus.CONVERTING
        s.commit()
        try:
            r = httpx.post(os.environ["CONVERTER_URL"] + "/convert", json={"key": f"src/{doc_id}"}, timeout=120)
            r.raise_for_status()
        except httpx.HTTPError as e:
            if self.request.retries >= 3:
                doc.status = DocumentStatus.FAILED
                s.commit()
                notify_failure(doc_id, str(e))
                return
            raise self.retry(exc=e)
        put(f"pdf/{doc_id}.pdf", r.content)
        doc.status = DocumentStatus.READY
        doc.pages = int(r.headers.get("x-pages", 0))
        s.commit()


@celery.task
def cleanup():
    # удаляет документы старше 30 дней (TODO: и файлы в S3 тоже)
    pass
