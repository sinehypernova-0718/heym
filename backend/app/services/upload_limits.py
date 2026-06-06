from fastapi import HTTPException, UploadFile, status

from app.config import settings

_BYTES_PER_MB = 1024 * 1024


def configured_upload_limit_bytes() -> int:
    return settings.file_max_size_mb * _BYTES_PER_MB


def _format_size(size_bytes: int) -> str:
    if size_bytes % _BYTES_PER_MB == 0:
        return f"{size_bytes // _BYTES_PER_MB} MB"
    return f"{size_bytes} bytes"


async def read_upload_file_limited(
    file: UploadFile,
    *,
    max_bytes: int | None = None,
) -> bytes:
    limit = configured_upload_limit_bytes() if max_bytes is None else max_bytes
    payload = await file.read(limit + 1)
    if len(payload) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File size exceeds limit ({_format_size(limit)})",
        )
    return payload
