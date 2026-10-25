"""Feature pipeline: pull, store raw, parse, validate, build features, check, store a new version.

    uv run python -m src.feature_pipeline.run             # live, writes to GCS if GCS_BUCKET is set
    uv run python -m src.feature_pipeline.run --offline   # snapshots of notebook 01, writes to data/
"""

import argparse
from datetime import datetime, timezone

from src.common.feature_store import LABEL_COLUMNS, write_version
from src.common.storage import get_store
from src.feature_pipeline import config as cfg
from src.feature_pipeline.features import backfill, check_features, feature_columns
from src.feature_pipeline.pull_log import is_new_sake_release, record_pulls
from src.feature_pipeline.sources import parse_lik, parse_sake, parse_wea, pull_all, sake_release_dates, validate_sources


def run(offline: bool = False) -> str:
    run_date = cfg.SNAPSHOT_DATE if offline else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    store = get_store(offline)
    print(f"run date {run_date} | {'offline' if offline else 'live'} | storage {store.uri('')}")

    # 1 · Pull and store every pull with its download date (D5)
    pulls = pull_all(offline)
    log, this_run = record_pulls(store, pulls, run_date)
    new_sake = is_new_sake_release(this_run)
    for _, row in this_run.iterrows():
        print(f"  {row['source']:4}  latest {row['latest_period']:10}  new: {row['is_new']:5}  {row['file']}")

    # 2 · Parse and validate
    sake = parse_sake(pulls["sake"][0])
    wea = parse_wea(pulls["wea"][0], run_date)
    lik = parse_lik(pulls["lik"][0], run_date)
    releases = sake_release_dates(sake["quarter"], log)
    sake["available_from"] = sake["quarter"].map(releases)
    validate_sources(sake, wea, lik)

    # 3–4 · Features: backfill since 2011 plus refresh rows for the run date
    features = backfill(sake, wea, lik, releases, run_date)

    # 5 · Leakage and completeness checks
    check_features(features, sake, wea, lik, releases, run_date)

    # 6 · Store a new version
    manifest = {
        "version": run_date,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "offline": offline,
        "rows": len(features),
        "feature_columns": feature_columns(features),
        "label_columns": LABEL_COLUMNS,
        "new_sake_release": bool(new_sake),
        "lags_days": {"sake": cfg.SAKE_LAG_DAYS, "wea": cfg.WEA_LAG_DAYS, "lik": cfg.LIK_LAG_DAYS},
        "sources": this_run.set_index("source")[["sha256", "published", "latest_period", "download_date"]].to_dict("index"),
    }
    location = write_version(store, run_date, features, manifest)
    print(f"stored {location}: {len(features):,} rows, new SAKE release: {new_sake}")
    return location


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="use the snapshots of notebook 01 and write to data/")
    run(offline=parser.parse_args().offline)


if __name__ == "__main__":
    main()
