from fastapi import APIRouter, Depends
from app.deps import db, require_admin
from app.models import Document, DocumentStatus
from app.tasks.convert import convert_document

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


@router.post("/documents/{doc_id}/retry")
def retry(doc_id: str, session=Depends(db)):
    doc = session.get(Document, doc_id)
    doc.status = DocumentStatus.UPLOADED
    session.commit()
    convert_document.delay(doc.id)
    return {"queued": True}
