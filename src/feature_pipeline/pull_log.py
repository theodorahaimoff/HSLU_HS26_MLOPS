"""Store every pull with its download date (D5).

Every pull is recorded in ``raw/pull_log.csv`` with its download date and a SHA-256 hash. The file itself is
only written when its hash is new, as ``raw/<source>/<download date>.csv``. A new SAKE hash is the
retraining trigger (D4).
"""

import hashlib
import io

import pandas as pd

from src.common.storage import Store
from src.feature_pipeline.config import PULL_LOG
from src.feature_pipeline.sources import Pull

LOG_COLUMNS = ["download_date", "source", "sha256", "is_new", "published", "latest_period", "resource_id", "url", "file"]


def load_pull_log(store: Store) -> pd.DataFrame:
    if store.exists(PULL_LOG):
        return pd.read_csv(io.BytesIO(store.read(PULL_LOG)), dtype=str)
    return pd.DataFrame(columns=LOG_COLUMNS, dtype=str)


def store_raw(store: Store, content: bytes, meta: dict, log: pd.DataFrame, run_date: str) -> dict:
    """Write the file if its content is new, and return its log entry."""
    sha = hashlib.sha256(content).hexdigest()
    seen = set(log.loc[log["source"] == meta["source"], "sha256"])
    key = f"raw/{meta['source']}/{run_date}.csv"
    if sha not in seen:
        store.write(key, content)
    else:
        # Same content as an earlier pull: point to the file that already holds it
        key = log.loc[(log["source"] == meta["source"]) & (log["sha256"] == sha), "file"].iloc[0]
    return {"download_date": run_date, "sha256": sha, "is_new": str(sha not in seen), "file": key} | meta


def record_pulls(store: Store, pulls: dict[str, Pull], run_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Store the raw files and update the log. Returns (full log, this run's entries)."""
    log = load_pull_log(store)
    earlier = log[log["download_date"] != run_date]  # a re-run on the same day compares with earlier days only
    this_run = pd.DataFrame([store_raw(store, content, meta, earlier, run_date) for content, meta in pulls.values()])
    this_run = this_run[LOG_COLUMNS]

    # Re-running on the same day replaces that day's entries instead of adding duplicates
    log = pd.concat([earlier, this_run], ignore_index=True)
    store.write(PULL_LOG, log.to_csv(index=False).encode())
    return log, this_run


def is_new_sake_release(this_run: pd.DataFrame) -> bool:
    return this_run.set_index("source").loc["sake", "is_new"] == "True"
