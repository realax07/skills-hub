import argparse
from app.session import Session
from app.models import Document, DocumentStatus
from app.tasks.convert import convert_document


def main():
    p = argparse.ArgumentParser(description="Повторно конвертировать все FAILED документы")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    with Session() as s:
        for d in s.query(Document).filter(Document.status == DocumentStatus.FAILED):
            print(d.id)
            if not a.dry_run:
                convert_document.delay(d.id)


if __name__ == "__main__":
    main()
