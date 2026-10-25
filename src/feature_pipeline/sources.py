"""Pull, parse and validate the three sources: SAKE (target), WEA and LIK (live features).

Every parsed table gets an ``available_from`` date: the first day a value could have been known.
Features may only use values with ``available_from <= as_of`` (D7).
"""

import io
import json
import re
import time

import pandas as pd
import requests

from src.feature_pipeline import config as cfg

Pull = tuple[bytes, dict]  # raw file content and its metadata record


# --- Download helpers -------------------------------------------------------------------------------


def http_get(url: str, retries: int = 4, **params) -> requests.Response:
    """GET with retries on server errors (5xx) and timeouts, waiting 2, 4, 8 s. Client errors (4xx) fail at once."""
    reason = "no attempt"
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=60)
            if r.status_code < 500:
                r.raise_for_status()
                return r
            reason = f"HTTP {r.status_code}"
        except (requests.ConnectionError, requests.Timeout) as e:
            reason = type(e).__name__
        if attempt < retries - 1:
            wait = 2 ** (attempt + 1)
            print(f"{url}: {reason}, retrying in {wait} s")
            time.sleep(wait)
    raise RuntimeError(f"{url} failed after {retries} attempts ({reason})")


def ckan(action: str, **params) -> dict:
    body = http_get(f"{cfg.CKAN}/{action}", **params).json()
    if not body.get("success"):
        raise RuntimeError(body.get("error"))
    return body["result"]


def read_snapshot(name: str, ext: str = ".csv") -> bytes:
    return (cfg.SNAPSHOT_DIR / f"{name}_{cfg.SNAPSHOT_DATE}{ext}").read_bytes()


def parse_quarter(value):
    """Turn '2024-Q1' (and similar spellings) into a quarterly Period."""
    m = re.search(r"(\d{4})\s*[-/ ]?\s*[QqTtKk]\s*0?([1-4])\b", str(value))
    return pd.Period(year=int(m[1]), quarter=int(m[2]), freq="Q") if m else pd.NaT


# --- Pull -------------------------------------------------------------------------------------------


def pull_sake(offline: bool = False) -> Pull:
    """Look up the CSV resource in the CKAN dataset on every run instead of using a fixed URL (A1)."""
    pkg = json.loads(read_snapshot("sake_ckan", ".json")) if offline else ckan("package_show", id=cfg.SAKE_DATASET)
    csvs = [r for r in pkg["resources"] if "CSV" in (r.get("format") or "").upper()]
    if not csvs:
        raise RuntimeError("SAKE dataset has no CSV resource")
    if len(csvs) > 1:
        print(f"SAKE: {len(csvs)} CSV resources, taking the one with the latest 'issued' date")
    res = max(csvs, key=lambda r: r.get("issued") or "")
    url = res.get("download_url") or res.get("url")
    content = read_snapshot("sake") if offline else http_get(url).content

    periods = re.findall(rb'"(\d{4}-Q\d)"', content)
    return content, {
        "source": "sake",
        "url": url,
        "resource_id": res["id"],
        "published": (res.get("issued") or "")[:10] or None,
        "latest_period": str(max(parse_quarter(p.decode()) for p in periods)),
    }


def pull_wea(offline: bool = False) -> Pull:
    content = read_snapshot("wea") if offline else http_get(cfg.WEA_URL).content
    dates = pd.read_csv(io.BytesIO(content), usecols=["structure", "date"])
    latest = dates.loc[dates["structure"] == "seco_wwa", "date"].max()
    return content, {"source": "wea", "url": cfg.WEA_URL, "resource_id": None, "published": None, "latest_period": latest}


def pull_lik(offline: bool = False) -> Pull:
    content = read_snapshot("lik_snb") if offline else http_get(cfg.LIK_URL).content
    lines = content.decode("utf-8-sig").splitlines()
    published = lines[1].split(";")[1].strip('"')[:10]  # "PublishingDate";"YYYY-MM-DD HH:MM"
    latest = max(line.split(";")[0].strip('"') for line in lines[4:] if line)
    return content, {"source": "lik", "url": cfg.LIK_URL, "resource_id": None, "published": published, "latest_period": latest}


def pull_all(offline: bool = False) -> dict[str, Pull]:
    return {"sake": pull_sake(offline), "wea": pull_wea(offline), "lik": pull_lik(offline)}


# --- Parse ------------------------------------------------------------------------------------------

GENDER, NAT, AGE = "GENDER_DE", "NAT_DE", "DETAILS_DE"
NAT_SHORT = {"Schweizer und Schweizerinnen": "Schweizer", "Ausländer and Ausländerinnen": "Ausländer", "Total": "Alle"}


def short_label(gender: str, nat: str, age: str) -> str:
    """Same segment labels as notebook 01."""
    gender = "Alle" if gender == "Total" else gender
    nat = NAT_SHORT.get(nat, nat)
    age = "Alle Alter" if age == "Total" else age.replace(" Jahre", "")
    if gender == nat == "Alle" and age == "Alle Alter":
        return "National total"
    return f"{gender} · {nat} · {age}"


def parse_sake(content: bytes) -> pd.DataFrame:
    raw = pd.read_csv(io.BytesIO(content), dtype=str, encoding="utf-8-sig")
    q = raw[raw["FREQ"] == "Q"].copy()
    q["quarter"] = q["PERIOD"].map(parse_quarter)
    q = q[(q["quarter"] >= cfg.START_QUARTER) & (q[AGE] != cfg.EXCLUDED_AGE)]
    q["segment"] = [short_label(g, n, a) for g, n, a in zip(q[GENDER], q[NAT], q[AGE])]
    q = q.drop_duplicates(["segment", "quarter"])  # the BFS hierarchy repeats some combinations
    return (
        q.rename(columns={GENDER: "gender", NAT: "nationality", AGE: "age_group", "STATUS": "status"})
        .assign(rate=pd.to_numeric(q["VALUE"], errors="coerce"))
        [["segment", "gender", "nationality", "age_group", "quarter", "rate", "status"]]
        .sort_values(["segment", "quarter"])
        .reset_index(drop=True)
    )


def parse_wea(content: bytes, run_date: str) -> pd.DataFrame:
    """Weekly WEA, seco_wwa only (D2). Available from week start + lag, at most the run date."""
    wea = pd.read_csv(io.BytesIO(content), parse_dates=["date"])
    wea = wea[wea["structure"] == "seco_wwa"].dropna(subset=["value"])  # 3 structural gaps in week 53 (notebook 01)
    wea = wea[["date", "value"]].sort_values("date").reset_index(drop=True)
    wea["available_from"] = (wea["date"] + pd.Timedelta(days=cfg.WEA_LAG_DAYS)).clip(upper=pd.Timestamp(run_date))
    return wea


def parse_lik(content: bytes, run_date: str) -> pd.DataFrame:
    """Monthly inflation VVP (D3). Available from month end + lag, at most the run date."""
    lik = pd.read_csv(io.BytesIO(content), sep=";", skiprows=2, encoding="utf-8-sig")
    lik = lik[lik["D0"] == "VVP"].dropna(subset=["Value"])
    lik = pd.DataFrame({"month": pd.PeriodIndex(lik["Date"], freq="M"), "value": lik["Value"].astype(float).values})
    available = lik["month"].dt.end_time.dt.normalize() + pd.Timedelta(days=cfg.LIK_LAG_DAYS)
    lik["available_from"] = available.clip(upper=pd.Timestamp(run_date))
    return lik.sort_values("month").reset_index(drop=True)


def sake_release_dates(quarters, log: pd.DataFrame) -> pd.Series:
    """Release date per quarter: real 'issued' date where the pull log has it, quarter end + lag otherwise."""
    releases = pd.Series(
        {q: q.end_time.normalize() + pd.Timedelta(days=cfg.SAKE_LAG_DAYS) for q in sorted(set(quarters))},
        name="released",
    )
    known = log[(log["source"] == "sake") & log["published"].notna()]
    for latest, published in zip(known["latest_period"], known["published"]):
        q = pd.Period(latest, freq="Q")
        if q in releases.index:
            releases[q] = pd.Timestamp(published)
    return releases


# --- Validate ---------------------------------------------------------------------------------------


class SourceError(ValueError):
    """A source changed shape. The run stops instead of writing a silently wrong feature table."""


def validate_sources(sake: pd.DataFrame, wea: pd.DataFrame, lik: pd.DataFrame) -> None:
    n_quarters = len(pd.period_range(cfg.START_QUARTER, sake["quarter"].max(), freq="Q"))
    per_segment = sake.groupby("segment")["quarter"].nunique()
    months = lik.loc[lik["month"] >= cfg.START_QUARTER.asfreq("M", "start"), "month"]

    checks = {
        f"expected {cfg.N_SEGMENTS} segments, got {sake['segment'].nunique()}": sake["segment"].nunique() == cfg.N_SEGMENTS,
        f"segments with missing quarters: {per_segment[per_segment < n_quarters].to_dict()}": (per_segment == n_quarters).all(),
        "SAKE has empty values in scope": sake["rate"].notna().all(),
        f"unexpected STATUS codes: {set(sake['status'])}": set(sake["status"]) <= {"A", "P", "U"},
        "WEA dates are not unique Mondays": wea["date"].is_unique and (wea["date"].dt.dayofweek == 0).all(),
        "LIK has duplicate months": lik["month"].is_unique,
        "LIK has missing months since 2010": len(months) == len(pd.period_range(months.min(), months.max(), freq="M")),
    }
    failed = [message for message, ok in checks.items() if not ok]
    if failed:
        raise SourceError("; ".join(failed))
