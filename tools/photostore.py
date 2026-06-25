"""Pluggable storage for user try-on photos.

Keeps the raw, privacy-sensitive user images OUT of the app process so the
backend can run stateless / horizontally scaled (the previous in-process
`USER_PHOTOS` dict forced every request for a session onto one box and lost all
photos on restart).

Backends, chosen by the `PHOTO_STORE` env var:
  - "memory" (default): the original in-process dict. Fine for local dev / a
    single process; cleared on restart.
  - "s3": a private S3 bucket, one object per session. `boto3` is imported
    lazily so memory mode needs no AWS deps. Retention is a BUCKET LIFECYCLE
    rule (expire objects after ~1 day) — handled in AWS, not here — so raw
    photos auto-delete and never accumulate.

Env for s3:
    PHOTO_STORE=s3
    PHOTO_S3_BUCKET=kapruka-user-photos
    PHOTO_S3_PREFIX=user-photos/        # optional, default "user-photos/"
    PHOTO_S3_REGION=ap-south-1          # optional, else AWS_REGION / default chain

The store API is intentionally synchronous and dependency-light; async callers
wrap `get`/`put` in `asyncio.to_thread` so the S3 network call never blocks the
event loop. This module must NOT import FastAPI — `fittingroom/tryon.py` imports
it, and the agent graph (adk web) imports tryon.
"""

import os
from typing import Optional, Tuple

# (raw bytes, content type e.g. "image/jpeg")
Photo = Tuple[bytes, str]


class PhotoStore:
    """Interface: store and retrieve one photo per chat session."""

    def put(self, session_id: str, data: bytes, content_type: str) -> None:
        raise NotImplementedError

    def get(self, session_id: str) -> Optional[Photo]:
        raise NotImplementedError

    def delete(self, session_id: str) -> None:
        raise NotImplementedError


class InMemoryPhotoStore(PhotoStore):
    """Original behaviour: a process-local dict. Cleared on restart."""

    def __init__(self) -> None:
        self._photos: dict[str, Photo] = {}

    def put(self, session_id: str, data: bytes, content_type: str) -> None:
        self._photos[session_id] = (data, content_type)

    def get(self, session_id: str) -> Optional[Photo]:
        return self._photos.get(session_id)

    def delete(self, session_id: str) -> None:
        self._photos.pop(session_id, None)


class S3PhotoStore(PhotoStore):
    """One private S3 object per session: `{prefix}{session_id}`.

    No server-side retention logic — set a bucket lifecycle rule to expire the
    prefix after ~1 day. The IAM role needs s3:PutObject / s3:GetObject (and
    s3:DeleteObject if you call delete) on `arn:aws:s3:::<bucket>/<prefix>*`.
    """

    def __init__(self, bucket: str, prefix: str = "user-photos/",
                 region: Optional[str] = None) -> None:
        import boto3  # lazy: only needed when PHOTO_STORE=s3
        self._bucket = bucket
        self._prefix = prefix
        self._s3 = boto3.client("s3", region_name=region or os.getenv("AWS_REGION"))

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"

    def put(self, session_id: str, data: bytes, content_type: str) -> None:
        self._s3.put_object(
            Bucket=self._bucket,
            Key=self._key(session_id),
            Body=data,
            ContentType=content_type,
        )

    def get(self, session_id: str) -> Optional[Photo]:
        try:
            resp = self._s3.get_object(Bucket=self._bucket, Key=self._key(session_id))
        except Exception:
            # NoSuchKey (expired / never uploaded) or any read failure → no photo.
            # Callers already handle None as the "no_photo" status.
            return None
        data = resp["Body"].read()
        ctype = resp.get("ContentType") or "image/jpeg"
        return (data, ctype)

    def delete(self, session_id: str) -> None:
        try:
            self._s3.delete_object(Bucket=self._bucket, Key=self._key(session_id))
        except Exception:
            pass


def _build_store() -> PhotoStore:
    backend = os.getenv("PHOTO_STORE", "memory").lower()
    if backend == "s3":
        bucket = os.getenv("PHOTO_S3_BUCKET")
        if not bucket:
            raise RuntimeError("PHOTO_STORE=s3 requires PHOTO_S3_BUCKET to be set.")
        return S3PhotoStore(
            bucket,
            os.getenv("PHOTO_S3_PREFIX", "user-photos/"),
            os.getenv("PHOTO_S3_REGION"),
        )
    if backend not in ("memory", ""):
        raise RuntimeError(f"Unknown PHOTO_STORE={backend!r} (use 'memory' or 's3').")
    return InMemoryPhotoStore()


# Process-wide singleton, built from env at import time.
photo_store: PhotoStore = _build_store()
