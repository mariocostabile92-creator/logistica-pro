from dataclasses import dataclass


SUPPORTED_ENTITY_TYPES = {
    "document", "insurance", "damage", "rental", "maintenance", "vehicle",
    "quality_scorecard",
}
SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"}
SUPPORTED_MIME_TYPES = {
    "application/pdf", "image/jpeg", "image/png", "image/webp",
    "video/mp4", "video/quicktime",
}


@dataclass(frozen=True)
class Attachment:
    id: str
    entity_type: str
    entity_id: int
    original_filename: str
    stored_filename: str
    mime_type: str
    size: int
    created_at: str
    created_by: str
    organization_id: str
    storage_path: str
    preview_available: bool
    notes: str | None = None
