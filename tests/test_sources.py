import pandas as pd
import pytest

from src.feature_pipeline import config as cfg
from src.feature_pipeline.sources import (
    SourceError,
    parse_lik,
    parse_quarter,
    parse_sake,
    parse_wea,
    sake_release_dates,
    validate_sources,
)
from tests.conftest import QUARTERS, RUN_DATE


def test_parse_quarter_spellings():
    for text in ["2024-Q1", "2024Q1", "2024 T1", "2024-Q01"]:
        assert parse_quarter(text) == pd.Period("2024Q1", freq="Q")
    assert parse_quarter("2024-M01") is pd.NaT


def test_parse_sake_keeps_quarterly_scope(sake_csv):
    sake = parse_sake(sake_csv)
    assert set(sake["segment"]) == {"National total", "Frauen · Alle · Alle Alter"}
    assert sake["quarter"].min() == cfg.START_QUARTER  # 2009Q4 dropped
    assert cfg.EXCLUDED_AGE not in set(sake["age_group"])
    assert len(sake) == 2 * len(QUARTERS)  # no monthly rows, no duplicates
    assert sake["rate"].notna().all()


def test_parse_wea_uses_seco_wwa_and_lag(wea_csv):
    wea = parse_wea(wea_csv, RUN_DATE)
    assert wea["value"].notna().all()  # structural gap dropped
    assert (wea["value"] < 99).all()  # pre-COVID series ignored
    old = wea[wea["date"] < "2014-01-01"]
    assert (old["available_from"] == old["date"] + pd.Timedelta(days=cfg.WEA_LAG_DAYS)).all()


def test_parse_wea_caps_availability_at_run_date(wea_csv):
    """Everything in today's file was available today (refresh rows use the newest week)."""
    wea = parse_wea(wea_csv, RUN_DATE)
    assert wea["available_from"].max() == pd.Timestamp(RUN_DATE)
    assert wea.loc[wea["date"].idxmax(), "available_from"] == pd.Timestamp(RUN_DATE)


def test_parse_lik_reads_yoy_inflation(lik_csv):
    lik = parse_lik(lik_csv, RUN_DATE)
    assert lik["month"].is_unique
    assert lik["value"].abs().max() <= 1  # VVP only, not the index (~100)
    jan = lik[lik["month"] == pd.Period("2012-01", freq="M")].iloc[0]
    assert jan["available_from"] == pd.Timestamp("2012-01-31") + pd.Timedelta(days=cfg.LIK_LAG_DAYS)


def test_release_dates_prefer_issued_date_from_log(sake_csv):
    sake = parse_sake(sake_csv)
    log = pd.DataFrame({"source": ["sake"], "published": ["2014-02-20"], "latest_period": ["2013Q4"]})
    releases = sake_release_dates(sake["quarter"], log)
    assert releases[pd.Period("2013Q4", freq="Q")] == pd.Timestamp("2014-02-20")
    assert releases[pd.Period("2013Q3", freq="Q")] == pd.Timestamp("2013-09-30") + pd.Timedelta(days=cfg.SAKE_LAG_DAYS)


def test_validate_sources_passes(sources, two_segments):
    sake, wea, lik, _ = sources
    validate_sources(sake, wea, lik)


def test_validate_sources_stops_on_missing_quarter(sources, two_segments):
    sake, wea, lik, _ = sources
    broken = sake.drop(sake.index[5])
    with pytest.raises(SourceError, match="missing quarters"):
        validate_sources(broken, wea, lik)


def test_validate_sources_stops_on_wrong_segment_count(sources):
    sake, wea, lik, _ = sources  # cfg.N_SEGMENTS is 45, the synthetic data has 2
    with pytest.raises(SourceError, match="expected 45 segments"):
        validate_sources(sake, wea, lik)
