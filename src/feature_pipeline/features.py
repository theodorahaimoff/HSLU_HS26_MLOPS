"""Feature rows as of a date (D6, D7), backfill, and the leakage checks.

``build_features(as_of)`` returns one row per segment. It finds t, the latest SAKE quarter released by
``as_of``; the target is quarter t+1. It uses only values with ``available_from <= as_of``.
"""

import numpy as np
import pandas as pd

from src.common.feature_store import LABEL_COLUMNS
from src.feature_pipeline import config as cfg

KEY_COLUMNS = ["as_of", "kind", "segment", "quarter_t", "target_quarter"]
AUDIT_COLUMNS = ["wea_last_week", "lik_last_month", "sake_released"]


def available(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    return df[df["available_from"] <= as_of]


def quarterly_means(values: pd.Series, quarter_of_value: pd.Series, quarters: list) -> list[float]:
    """Mean of the values in each of the given quarters (NaN if a quarter has no value)."""
    by_quarter = values.groupby(quarter_of_value).mean()
    return [by_quarter.get(q, np.nan) for q in quarters]


def build_features(as_of, sake: pd.DataFrame, wea: pd.DataFrame, lik: pd.DataFrame, kind: str = "release") -> pd.DataFrame:
    as_of = pd.Timestamp(as_of)
    known = available(sake, as_of)
    t = known["quarter"].max()
    target = t + 1
    back = [t, t - 1, t - 2, t - 3]  # 1 to 4 quarters before the target

    rates = known.pivot(index="segment", columns="quarter", values="rate")
    labels = sake[sake["quarter"] == target].set_index("segment")["rate"]  # future values, labels only
    seg = known[known["quarter"] == t].set_index("segment")

    wea_now, lik_now = available(wea, as_of), available(lik, as_of)
    wea_q = quarterly_means(wea_now["value"], wea_now["date"].dt.to_period("Q"), back)
    lik_q = quarterly_means(lik_now["value"], lik_now["month"].dt.asfreq("Q"), back)

    f = pd.DataFrame(
        {
            "as_of": as_of,
            "kind": kind,
            "quarter_t": str(t),
            "target_quarter": str(target),
            "gender": seg["gender"],
            "nationality": seg["nationality"],
            "age_group": seg["age_group"],
            "target_qoy": target.quarter,
            "rate_t": rates[t],
            "rate_t1": rates[t - 1],
            "rate_t3": rates[t - 3],
            "yoy_t": rates[t] - rates[t - 4],
            "status_t": seg["status"],
            "wea_13w": wea_now["value"].tail(13).mean(),
            **{f"wea_q{i}": v for i, v in enumerate(wea_q, start=1)},
            "lik_latest": lik_now["value"].iloc[-1],
            **{f"lik_q{i}": v for i, v in enumerate(lik_q, start=1)},
            "wea_last_week": wea_now["date"].max(),
            "lik_last_month": str(lik_now["month"].max()),
            "sake_released": seg["available_from"],
            "y_rate": labels.reindex(seg.index),
        }
    )
    f["y_yoy"] = f["y_rate"] - f["rate_t3"]
    return f.rename_axis("segment").reset_index()


def backfill(sake: pd.DataFrame, wea: pd.DataFrame, lik: pd.DataFrame, releases: pd.Series, run_date: str) -> pd.DataFrame:
    """Release rows for every SAKE release since 2011Q1, plus refresh rows as of the run date."""
    first_t = cfg.START_QUARTER + 4  # first quarter with a value 4 quarters earlier, needed for yoy_t
    dates = releases[(releases.index >= first_t) & (releases <= pd.Timestamp(run_date))]
    parts = [build_features(d, sake, wea, lik, kind="release") for d in dates]
    if pd.Timestamp(run_date) > dates.max():
        parts.append(build_features(run_date, sake, wea, lik, kind="refresh"))
    return pd.concat(parts, ignore_index=True)


def feature_columns(features: pd.DataFrame) -> list[str]:
    excluded = set(KEY_COLUMNS) | set(AUDIT_COLUMNS) | set(LABEL_COLUMNS)
    return [c for c in features.columns if c not in excluded]


# --- Checks -----------------------------------------------------------------------------------------


class LeakageError(ValueError):
    """A feature row uses a value that was not available on its as_of date."""


def check_features(
    features: pd.DataFrame,
    sake: pd.DataFrame,
    wea: pd.DataFrame,
    lik: pd.DataFrame,
    releases: pd.Series,
    run_date: str,
    n_truncation_dates: int = 5,
) -> None:
    """Leakage and completeness checks of notebook 02, section 5. Raises instead of writing a bad version."""
    run_day = pd.Timestamp(run_date)
    columns = feature_columns(features)

    # 1 · Audit columns: the newest input of every row was available on its as_of
    wea_avail = (features["wea_last_week"] + pd.Timedelta(days=cfg.WEA_LAG_DAYS)).clip(upper=run_day)
    lik_months = pd.PeriodIndex(features["lik_last_month"], freq="M")
    lik_avail = (lik_months.end_time.normalize() + pd.Timedelta(days=cfg.LIK_LAG_DAYS)).to_series().clip(upper=run_day)
    if not (features["sake_released"] <= features["as_of"]).all():
        raise LeakageError("a row uses a SAKE quarter released after its as_of")
    if not (wea_avail <= features["as_of"]).all():
        raise LeakageError("a row uses a WEA week not available on its as_of")
    if not (lik_avail.values <= features["as_of"].values).all():
        raise LeakageError("a row uses a LIK month not available on its as_of")

    # 2 · The target quarter was never released before as_of
    target_release = pd.PeriodIndex(features["target_quarter"], freq="Q").map(lambda q: releases.get(q, pd.Timestamp.max))
    if not (target_release > features["as_of"]).all():
        raise LeakageError("a row predicts a quarter that was already released")

    # 3 · Truncation: rebuilding from only the data available on as_of gives the same features
    rng = np.random.default_rng(0)
    as_ofs = features["as_of"].unique()
    for as_of in rng.choice(as_ofs, size=min(n_truncation_dates, len(as_ofs)), replace=False):
        as_of = pd.Timestamp(as_of)
        full = features[features["as_of"] == as_of].set_index("segment")[columns]
        cut = build_features(as_of, available(sake, as_of), available(wea, as_of), available(lik, as_of))
        cut = cut.set_index("segment")[columns]
        try:
            pd.testing.assert_frame_equal(full, cut.loc[full.index], check_dtype=False)
        except AssertionError as e:
            raise LeakageError(f"features as of {as_of.date()} change when future data is removed:\n{e}") from e

    # Completeness: no empty features
    missing = features[columns].isna().sum()
    if missing.sum():
        raise ValueError(f"empty features: {missing[missing > 0].to_dict()}")
