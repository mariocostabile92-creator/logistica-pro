from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.config import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    MAX_UPLOAD_SIZE_BYTES,
)


def validate_upload(file: UploadFile, content: bytes) -> None:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Formato file non supportato. Usa .xlsx, .xls o .csv.")
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Tipo MIME non valido per il file caricato.")
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File troppo grande.")
    if not content:
        raise HTTPException(status_code=400, detail="File vuoto.")


async def read_validated_upload(file: UploadFile) -> bytes:
    """Read at most one byte beyond the accepted limit before validation."""
    content = await file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    validate_upload(file, content)
    return content
