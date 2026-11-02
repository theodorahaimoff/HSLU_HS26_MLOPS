"""Review point B2: MAE of the two naive baselines, from a stored feature version.

    uv run python -m src.training_pipeline.baselines             # latest version in the feature store (GCS if GCS_BUCKET is set)
    uv run python -m src.training_pipeline.baselines --offline   # latest version under data/ (after `run --offline`)

For target quarter t+1:
    seasonal naive = rate in t-3 (same quarter one year earlier)  -> column rate_t3
    persistence    = rate in t   (latest released quarter)        -> column rate_t

Segments are grouped by how often their SAKE value is flagged U (low reliability) in the stored rows (A2 / B1).
"""

import argparse

import pandas as pd

from src.common.feature_store import load_features
from src.common.storage import get_store

BASELINES = {"seasonal naive": "rate_t3", "persistence": "rate_t"}


def reliability_groups(features: pd.DataFrame) -> pd.Series:
    u_share = features.groupby("segment")["status_t"].apply(lambda s: (s == "U").mean())
    return u_share.map(lambda share: "mostly U" if share > 0.5 else ("some U" if share > 0 else "all A"))


def baseline_table(rows: pd.DataFrame, groups: pd.Series) -> pd.DataFrame:
    rows = rows.assign(group=rows["segment"].map(groups))
    errors = {name: (rows["y_rate"] - rows[col]).abs() for name, col in BASELINES.items()}
    table = pd.DataFrame(errors).assign(group=rows["group"], segment=rows["segment"])
    out = table.groupby("group").agg(**{f"MAE {n}": (n, "mean") for n in BASELINES}, segments=("segment", "nunique"))
    out.loc["all segments"] = [*(table[n].mean() for n in BASELINES), table["segment"].nunique()]
    national = table[table["segment"] == "National total"]
    out.loc["National total"] = [*(national[n].mean() for n in BASELINES), 1]
    out["segments"] = out["segments"].astype(int)
    out["better"] = out[[f"MAE {n}" for n in BASELINES]].idxmin(axis=1).str.removeprefix("MAE ")
    return out.round(3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--quarters", type=int, default=12, help="evaluation window: last N target quarters (default 12)")
    args = parser.parse_args()

    features = load_features(get_store(args.offline))
    labelled = features[(features["kind"] == "release") & features["y_rate"].notna()]
    groups = reliability_groups(labelled)
    quarters = sorted(labelled["target_quarter"].unique())

    for title, rows in [
        (f"last {args.quarters} target quarters ({quarters[-args.quarters]}-{quarters[-1]})",
         labelled[labelled["target_quarter"].isin(quarters[-args.quarters:])]),
        (f"all target quarters ({quarters[0]}-{quarters[-1]})", labelled),
    ]:
        print(f"\n{title}: MAE in percentage points")
        print(baseline_table(rows, groups).to_string())


if __name__ == "__main__":
    main()
