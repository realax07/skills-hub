import uuid
from fastapi import APIRouter, UploadFile, HTTPException, Depends
from app.models import Document, DocumentStatus
from app.storage import put, presigned
from app.tasks.convert import convert_document
from app.deps import db, current_user

router = APIRouter(prefix="/documents")
MAX_SIZE = 20 * 1024 * 1024
ALLOWED = {".docx", ".odt", ".rtf"}


@router.post("", status_code=202)
async def upload(file: UploadFile, user=Depends(current_user), session=Depends(db)):
    ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED:
        raise HTTPException(415, "unsupported")
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(413, "too large")
    doc = Document(id=str(uuid.uuid4()), owner_id=user.id, filename=file.filename)
    put(f"src/{doc.id}{ext}", data)
    session.add(doc)
    session.commit()
    convert_document.delay(doc.id)
    return {"id": doc.id, "status": doc.status}


@router.get("/{doc_id}")
def get_document(doc_id: str, user=Depends(current_user), session=Depends(db)):
    doc = session.get(Document, doc_id)
    if not doc or doc.owner_id != user.id:
        raise HTTPException(404)
    out = {"id": doc.id, "status": doc.status, "pages": doc.pages}
    if doc.status == DocumentStatus.READY:
        out["url"] = presigned(f"pdf/{doc.id}.pdf")
    return out
