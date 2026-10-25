"""Small synthetic files in the exact formats of the three sources.

The real snapshots are gitignored, so the tests build their own data and run anywhere, including CI.
Two segments, quarters 2010Q1–2013Q4, run date 2014-03-31.
"""

import numpy as np
import pandas as pd
import pytest

from src.feature_pipeline import config as cfg
from src.feature_pipeline.sources import parse_lik, parse_sake, parse_wea, sake_release_dates

RUN_DATE = "2014-03-31"
QUARTERS = pd.period_range("2010Q1", "2013Q4", freq="Q")

SAKE_HEADER = (
    '"INDICATORS_HRCHY","INDICATORS_FR","INDICATORS_DE","GENDER_FR","GENDER_DE","NAT_FR","NAT_DE",'
    '"DETAILS_FR","DETAILS_DE","PERIOD","FREQ","MEASURE_FR","MEASURE_DE","VALUE","STATUS"'
)


def sake_row(gender: str, age: str, period: str, freq: str, value, status: str) -> str:
    value = "" if value is None else f"{value}"
    return f'"P","X","X","x","{gender}","x","Total","x","{age}","{period}","{freq}","x","x",{value},"{status}"'


def sake_rate(segment_no: int, q: pd.Period) -> float:
    """Deterministic rate with a seasonal pattern, different per segment."""
    return round(4 + segment_no + 0.3 * (q.quarter in (1, 3)) + 0.05 * (q.year - 2010), 4)


@pytest.fixture
def sake_csv() -> bytes:
    rows = [SAKE_HEADER]
    for no, (gender, age) in enumerate([("Total", "Total"), ("Frauen", "Total")]):
        for q in QUARTERS:
            rows.append(sake_row(gender, age, f"{q.year}-Q{q.quarter}", "Q", sake_rate(no, q), "A"))
    rows.append(sake_row("Total", "Total", "2009-Q4", "Q", 9.9, "A"))  # before the scope, dropped
    rows.append(sake_row("Total", "65+ Jahre", "2012-Q1", "Q", 2.0, "U"))  # excluded age group
    rows.append(sake_row("Total", "Total", "2012-M01", "M", 4.1, "A"))  # monthly value, dropped
    rows.append(sake_row("Total", "Total", "2012-Q1", "Q", sake_rate(0, pd.Period("2012Q1")), "A"))  # duplicate
    return ("﻿" + "\n".join(rows) + "\n").encode("utf-8")


@pytest.fixture
def wea_csv() -> bytes:
    rows = ["structure,type,seas_adj,date,value"]
    for i, d in enumerate(pd.date_range("2009-01-05", "2014-03-24", freq="W-MON")):
        value = "" if d == pd.Timestamp("2009-12-28") else f"{np.sin(i / 8):.4f}"  # one structural gap
        rows.append(f"seco_wwa,index,csa,{d.date()},{value}")
    rows.append("seco_wwa_pre_covid,index,csa,2012-01-02,99.0")  # other series, ignored
    return ("\n".join(rows) + "\n").encode()


@pytest.fixture
def lik_csv() -> bytes:
    rows = ['﻿"CubeId";"plkopr"', '"PublishingDate";"2014-03-20 09:00"', "", '"Date";"D0";"Value"']
    for i, m in enumerate(pd.period_range("2009-01", "2014-02", freq="M")):
        rows.append(f'"{m}";"LD2010100";"{100 + i / 10:.2f}"')
        rows.append(f'"{m}";"VVP";"{np.cos(i / 6):.4f}"')
    return ("\n".join(rows) + "\n").encode("utf-8")


@pytest.fixture
def empty_log() -> pd.DataFrame:
    return pd.DataFrame(columns=["source", "published", "latest_period"], dtype=str)


@pytest.fixture
def sources(sake_csv, wea_csv, lik_csv, empty_log):
    """Parsed tables as the pipeline uses them: (sake, wea, lik, releases)."""
    sake = parse_sake(sake_csv)
    wea = parse_wea(wea_csv, RUN_DATE)
    lik = parse_lik(lik_csv, RUN_DATE)
    releases = sake_release_dates(sake["quarter"], empty_log)
    sake["available_from"] = sake["quarter"].map(releases)
    return sake, wea, lik, releases


@pytest.fixture
def two_segments(monkeypatch):
    monkeypatch.setattr(cfg, "N_SEGMENTS", 2)
