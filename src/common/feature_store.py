"""Versioned Parquet feature store (the course FAQ's "poor man's feature store").

Layout, in the bucket or under data/:

    feature_store/features/version=<run date>/features.parquet
    feature_store/features/version=<run date>/manifest.json

The feature pipeline writes a new version per run; the training and inference pipelines read the
latest one, or a fixed version for a reproducible run.
"""

import io
import json

import pandas as pd

from src.common.storage import Store

FEATURES_PREFIX = "feature_store/features"
LABEL_COLUMNS = ["y_rate", "y_yoy"]


def write_version(store: Store, version: str, features: pd.DataFrame, manifest: dict) -> str:
    """Write one feature version and its manifest. A second write with the same version overwrites it."""
    folder = f"{FEATURES_PREFIX}/version={version}"
    buffer = io.BytesIO()
    features.to_parquet(buffer, index=False)
    store.write(f"{folder}/features.parquet", buffer.getvalue())
    store.write(f"{folder}/manifest.json", json.dumps(manifest, indent=2, default=str).encode())
    return store.uri(folder)


def feature_versions(store: Store) -> list[str]:
    """All stored versions, oldest first, e.g. ['2026-10-25', '2026-11-02']."""
    keys = store.list(FEATURES_PREFIX)
    return sorted({k.split("version=", 1)[1].split("/", 1)[0] for k in keys if k.endswith("features.parquet")})


def load_features(store: Store, version: str | None = None) -> pd.DataFrame:
    """Read one feature version, the latest by default."""
    versions = feature_versions(store)
    if not versions:
        raise FileNotFoundError(f"no feature versions under {store.uri(FEATURES_PREFIX)}")
    version = version or versions[-1]
    return pd.read_parquet(io.BytesIO(store.read(f"{FEATURES_PREFIX}/version={version}/features.parquet")))


def load_manifest(store: Store, version: str | None = None) -> dict:
    version = version or feature_versions(store)[-1]
    return json.loads(store.read(f"{FEATURES_PREFIX}/version={version}/manifest.json"))
