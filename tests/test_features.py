"""Leakage and label tests for the feature rows (D6, D7)."""

import pandas as pd
import pytest

from src.feature_pipeline.features import LeakageError, backfill, build_features, check_features
from tests.conftest import RUN_DATE


@pytest.fixture
def features(sources):
    sake, wea, lik, releases = sources
    return backfill(sake, wea, lik, releases, RUN_DATE)


def test_backfill_has_release_and_refresh_rows(features, sources):
    _, _, _, releases = sources
    release_rows = features[features["kind"] == "release"]
    refresh_rows = features[features["kind"] == "refresh"]
    assert release_rows["as_of"].nunique() == len(releases) - 4  # from 2011Q1 on
    assert len(refresh_rows) == 2 and (refresh_rows["as_of"] == pd.Timestamp(RUN_DATE)).all()


def test_no_leakage_on_any_date(features, sources):
    """Truncation test on every as_of date: removing future data must not change any feature."""
    sake, wea, lik, releases = sources
    check_features(features, sake, wea, lik, releases, RUN_DATE, n_truncation_dates=features["as_of"].nunique())


def test_check_features_detects_a_leaked_label(features, sources):
    sake, wea, lik, releases = sources
    leaky = features.copy()
    first = leaky["as_of"] == leaky["as_of"].min()
    leaky.loc[first, "rate_t"] = leaky.loc[first, "y_rate"]  # future value used as a feature
    with pytest.raises(LeakageError):
        check_features(leaky, sake, wea, lik, releases, RUN_DATE, n_truncation_dates=features["as_of"].nunique())


def test_target_is_the_next_quarter_and_not_yet_released(features, sources):
    _, _, _, releases = sources
    quarter_t = pd.PeriodIndex(features["quarter_t"], freq="Q")
    target = pd.PeriodIndex(features["target_quarter"], freq="Q")
    assert (target == quarter_t + 1).all()
    for as_of, q in zip(features["as_of"], target):
        assert releases.get(q, pd.Timestamp.max) > as_of


def test_label_is_year_on_year_change(features, sources):
    sake = sources[0].set_index(["segment", "quarter"])["rate"]
    labelled = features.dropna(subset=["y_rate"])
    for _, row in labelled.sample(10, random_state=0).iterrows():
        target = pd.Period(row["target_quarter"], freq="Q")
        assert row["y_rate"] == pytest.approx(sake[(row["segment"], target)])
        assert row["y_yoy"] == pytest.approx(sake[(row["segment"], target)] - sake[(row["segment"], target - 4)])


def test_only_the_newest_target_has_no_label(features):
    unlabelled = features.loc[features["y_rate"].isna(), "target_quarter"].unique()
    assert list(unlabelled) == ["2014Q1"]


def test_refresh_uses_newest_week_and_month(features, sources):
    _, wea, lik, _ = sources
    refresh = features[features["kind"] == "refresh"].iloc[0]
    assert refresh["wea_last_week"] == wea["date"].max()
    assert refresh["lik_last_month"] == str(lik["month"].max())


def test_release_rows_respect_the_lags(sources):
    sake, wea, lik, releases = sources
    as_of = releases[pd.Period("2012Q2", freq="Q")]  # 2012-08-18
    row = build_features(as_of, sake, wea, lik).iloc[0]
    assert row["quarter_t"] == "2012Q2"
    assert row["wea_last_week"] + pd.Timedelta(days=24) <= as_of < row["wea_last_week"] + pd.Timedelta(days=31)
    assert row["lik_last_month"] == "2012-06"  # July is only published on 21.08
