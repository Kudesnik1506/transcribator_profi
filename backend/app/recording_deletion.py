from sqlalchemy.orm import Session

from app.models import ErrorLog, Message, Recording
from app.s3 import delete_media


def purge_recording(db: Session, recording: Recording) -> None:
    # S3 delete first: if it fails, nothing else has happened yet, so a
    # retry is always safe. delete_object on an already-missing key is a
    # no-op success, not an error — safe to call twice for the same key.
    delete_media(recording.s3_key_media)

    db.query(Message).filter_by(recording_id=recording.id).delete()
    db.query(ErrorLog).filter_by(recording_id=recording.id).delete()
    db.delete(recording)
    db.commit()
