"""Sources, scope and publication lags of the feature pipeline (see docs/decisions.md, D2–D7)."""

import pandas as pd

from src.common.config import ROOT

# --- Sources ---
CKAN = "https://ckan.opendata.swiss/api/3/action"
SAKE_DATASET = "erwerbslosenquote-gemass-ilo-nach-geschlecht-nationalitat-und-altersgruppen-durchschnittliche-m"
WEA_URL = "https://scheduler.swissdatas.ch/scheduled/wwa.csv"
LIK_URL = "https://data.snb.ch/api/cube/plkopr/data/csv/en"

# --- Offline mode: dated snapshots from notebook 01 ---
SNAPSHOT_DIR = ROOT / "data/raw/exploration"
SNAPSHOT_DATE = "2026-10-15"

# --- Scope (notebook 01, section 3) ---
START_QUARTER = pd.Period("2010Q1", freq="Q")
EXCLUDED_AGE = "65+ Jahre"
N_SEGMENTS = 45

# --- Publication lags, used where the real publication date is unknown (notebook 02, section 2) ---
SAKE_LAG_DAYS = 49  # quarter end -> BFS release (Q2 2026: 30.06 -> 18.08)
WEA_LAG_DAYS = 24   # week start -> value in the file (observed 24 days on 15.10, 20 days on 25.10)
LIK_LAG_DAYS = 21   # month end -> SNB publication (August 2026 published 21.09)

# --- Storage keys ---
PULL_LOG = "raw/pull_log.csv"
