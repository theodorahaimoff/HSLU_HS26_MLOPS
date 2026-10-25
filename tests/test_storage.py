"""Local store, feature versions and the pull log (D5). GCSStore has the same interface."""

import pandas as pd
import pytest

from src.common.feature_store import feature_versions, load_features, load_manifest, write_version
from src.common.storage import LocalStore
from src.feature_pipeline.pull_log import is_new_sake_release, load_pull_log, record_pulls


@pytest.fixture
def store(tmp_path):
    return LocalStore(tmp_path)


def pulls(sake: bytes = b"sake-v1", wea: bytes = b"wea-v1") -> dict:
    meta = {"url": "x", "resource_id": None, "published": None, "latest_period": "x"}
    return {"sake": (sake, {"source": "sake"} | meta), "wea": (wea, {"source": "wea"} | meta)}


def test_local_store_round_trip(store):
    store.write("raw/sake/2026-10-25.csv", b"abc")
    assert store.exists("raw/sake/2026-10-25.csv")
    assert store.read("raw/sake/2026-10-25.csv") == b"abc"
    assert store.list("raw") == ["raw/sake/2026-10-25.csv"]
    assert store.list("nothing") == []


def test_feature_versions_and_latest(store):
    for version, value in [("2026-10-25", 1.0), ("2026-11-02", 2.0)]:
        write_version(store, version, pd.DataFrame({"x": [value]}), {"version": version})
    assert feature_versions(store) == ["2026-10-25", "2026-11-02"]
    assert load_features(store)["x"].iloc[0] == 2.0
    assert load_features(store, "2026-10-25")["x"].iloc[0] == 1.0
    assert load_manifest(store)["version"] == "2026-11-02"


def test_load_features_without_versions_fails_clearly(store):
    with pytest.raises(FileNotFoundError):
        load_features(store)


def test_pull_log_stores_only_changed_files(store):
    _, first = record_pulls(store, pulls(), "2026-10-25")
    assert (first["is_new"] == "True").all() and is_new_sake_release(first)

    _, second = record_pulls(store, pulls(wea=b"wea-v2"), "2026-11-02")  # only WEA changed
    assert second.set_index("source")["is_new"].to_dict() == {"sake": "False", "wea": "True"}
    assert not is_new_sake_release(second)
    assert second.set_index("source").loc["sake", "file"] == "raw/sake/2026-10-25.csv"  # points to the old copy
    assert store.list("raw/sake") == ["raw/sake/2026-10-25.csv"]
    assert len(load_pull_log(store)) == 4


def test_rerun_on_the_same_day_replaces_that_days_entries(store):
    record_pulls(store, pulls(), "2026-10-25")
    _, rerun = record_pulls(store, pulls(), "2026-10-25")
    assert (rerun["is_new"] == "True").all()  # still new compared with earlier days
    assert len(load_pull_log(store)) == 2
