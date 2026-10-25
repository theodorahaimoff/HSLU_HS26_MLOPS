"""Paths and environment shared by all pipelines."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Repo root: src/common/config.py -> src/common -> src -> repo
ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    """Read .env from the repo root, if there is one.

    Variables that are already set (e.g. GitHub Secrets in CI) are not overwritten. A relative
    GOOGLE_APPLICATION_CREDENTIALS path is read from the repo root, wherever the code runs.
    """
    load_dotenv(ROOT / ".env")
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if key_path and not Path(key_path).is_absolute():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(ROOT / key_path)
