import enum
from sqlalchemy import Column, String, Integer, Enum, DateTime, func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    CONVERTING = "converting"
    READY = "ready"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True)
    owner_id = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.UPLOADED)
    pages = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
