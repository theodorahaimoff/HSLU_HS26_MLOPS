"""Where the pipelines read and write files: a GCS bucket, or a local folder without credentials.

Files are addressed by a key such as ``raw/sake/2026-10-25.csv``. The key is the same in both backends:
``gs://<bucket>/raw/sake/2026-10-25.csv`` or ``data/raw/sake/2026-10-25.csv``.
"""

import os
from pathlib import Path
from typing import Protocol

from src.common.config import ROOT, load_env


class Store(Protocol):
    def write(self, key: str, data: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def list(self, prefix: str) -> list[str]: ...
    def uri(self, key: str) -> str: ...


class LocalStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def write(self, key: str, data: bytes) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()

    def list(self, prefix: str) -> list[str]:
        """All keys below a prefix, e.g. list('raw/sake')."""
        folder = self.root / prefix
        if not folder.exists():
            return []
        return sorted(p.relative_to(self.root).as_posix() for p in folder.rglob("*") if p.is_file())

    def uri(self, key: str) -> str:
        return str(self.root / key)


class GCSStore:
    def __init__(self, bucket: str):
        from google.cloud import storage  # only needed when a bucket is configured

        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket)

    def write(self, key: str, data: bytes) -> None:
        self.bucket.blob(key).upload_from_string(data)

    def read(self, key: str) -> bytes:
        return self.bucket.blob(key).download_as_bytes()

    def exists(self, key: str) -> bool:
        return self.bucket.blob(key).exists()

    def list(self, prefix: str) -> list[str]:
        return sorted(b.name for b in self.client.list_blobs(self.bucket, prefix=prefix.rstrip("/") + "/"))

    def uri(self, key: str) -> str:
        return f"gs://{self.bucket.name}/{key}"


def get_store(offline: bool = False) -> Store:
    """GCS bucket if GCS_BUCKET is set and the run is live, local data/ folder otherwise."""
    load_env()
    bucket = os.getenv("GCS_BUCKET")
    if bucket and not offline:
        return GCSStore(bucket)
    return LocalStore(ROOT / "data")
