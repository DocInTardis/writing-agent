"""Upload validation helpers.

Extracted from app_v2.py to keep route definitions and utility logic separate.
Imported by app_v2.py and any API flow that needs to receive file uploads.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException, UploadFile

ALLOWED_UPLOAD_EXTS = {
    ".txt", ".md", ".csv", ".json", ".html", ".htm",
    ".pdf", ".doc", ".docx", ".odt", ".rtf",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg",
}
TEXT_UPLOAD_EXTS = {".txt", ".md", ".csv", ".json", ".html", ".htm"}
IMAGE_UPLOAD_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}


def normalize_upload_filename(name: str) -> str:
    base = Path(str(name or "").strip()).name
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", base).strip(" .")
    if not base:
        base = "upload.bin"
    if len(base) > 120:
        stem = Path(base).stem[:80] or "upload"
        suffix = Path(base).suffix[:20]
        base = f"{stem}{suffix}"
    return base


def looks_like_binary_payload(raw: bytes) -> bool:
    if not raw:
        return False
    sample = raw[:4096]
    if b"\x00" in sample:
        return True
    bad = sum(1 for b in sample if (b < 9 or (13 < b < 32)))
    return bad > max(8, len(sample) // 16)


def detect_image_type(raw: bytes) -> str:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a"):
        return "gif"
    if raw.startswith(b"BM"):
        return "bmp"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    if raw[:256].lstrip().startswith(b"<svg") or b"<svg" in raw[:2048]:
        return "svg"
    return ""


def validate_upload_payload(*, suffix: str, raw: bytes) -> None:
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="file too large (max 50MB)")
    if suffix in IMAGE_UPLOAD_EXTS:
        detected = detect_image_type(raw)
        expected = suffix.lstrip(".")
        if expected == "jpg":
            expected = "jpeg"
        if not detected or detected != expected:
            raise HTTPException(
                status_code=400,
                detail="invalid image payload: content does not match extension",
            )
    if suffix in TEXT_UPLOAD_EXTS and looks_like_binary_payload(raw):
        raise HTTPException(status_code=400, detail="invalid text payload: appears to be binary data")


async def read_upload_payload(file: UploadFile) -> tuple[str, str, bytes]:
    if file is None or not (file.filename or "").strip():
        raise HTTPException(status_code=400, detail="file required")
    source_name = normalize_upload_filename(file.filename or "")
    suffix = Path(source_name).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTS:
        raise HTTPException(status_code=400, detail=f"unsupported file type: {suffix or 'unknown'}")
    raw = await file.read()
    validate_upload_payload(suffix=suffix, raw=raw)
    return source_name, suffix, raw
