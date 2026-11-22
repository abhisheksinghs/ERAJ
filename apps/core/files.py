"""Uploaded-file checks shared by HR documents and learning files (ADR-009, ADR-011):
extension allow-list, real content (magic bytes) and size; stored under a random name;
served only through authenticated, scoped endpoints."""
from __future__ import annotations

import os
import uuid

from django.utils.deconstruct import deconstructible
from rest_framework import serializers

TYPES = {
    ".pdf": ("application/pdf", [b"%PDF"]),
    ".jpg": ("image/jpeg", [b"\xff\xd8\xff"]),
    ".jpeg": ("image/jpeg", [b"\xff\xd8\xff"]),
    ".png": ("image/png", [b"\x89PNG"]),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", [b"PK\x03\x04"]),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", [b"PK\x03\x04"]),
}
DOCS = (".pdf", ".jpg", ".jpeg", ".png")
LEARNING = (".pdf", ".jpg", ".jpeg", ".png", ".docx", ".pptx")


def check_upload(f, *, allowed=DOCS, max_mb: int = 5):
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in allowed:
        raise serializers.ValidationError(f"Upload one of: {', '.join(e.strip('.').upper() for e in allowed)}.")
    if f.size > max_mb * 1024 * 1024:
        raise serializers.ValidationError(f"The file is larger than {max_mb} MB.")
    head = f.read(8)
    f.seek(0)
    if not any(head.startswith(m) for m in TYPES[ext][1]):
        raise serializers.ValidationError("The file's contents don't match its type.")
    return f


def content_type(name: str) -> str:
    return TYPES.get(os.path.splitext(name)[1].lower(), ("application/octet-stream", []))[0]


@deconstructible
class random_path:  # noqa: N801 — used like a function: upload_to=random_path("learning")
    def __init__(self, prefix: str):
        self.prefix = prefix

    def __call__(self, instance, filename: str) -> str:
        ext = os.path.splitext(filename)[1].lower()
        return f"{self.prefix}/{getattr(instance, 'branch_id', None) or 'x'}/{uuid.uuid4().hex}{ext}"

    def __eq__(self, other):
        return isinstance(other, random_path) and other.prefix == self.prefix


def download(fieldfile, name: str, ctype: str):
    from django.http import FileResponse

    resp = FileResponse(fieldfile.open("rb"), content_type=ctype or "application/octet-stream")
    resp["Content-Disposition"] = f'attachment; filename="{name or "file"}"'
    resp["X-Content-Type-Options"] = "nosniff"
    return resp
