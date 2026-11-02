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
WEA_LAG_DAYS = 24  # week start -> value in the file (observed 24 days on 15.10, 20 days on 25.10)
LIK_LAG_DAYS = 21  # month end -> SNB publication (August 2026 published 21.09)

# --- Plausible value ranges (data validation, D14) ---
# Wide margins around what was observed 2010-2026, so a real crisis passes but a unit or scale error does not.
RATE_RANGE = (0.0, 50.0)  # any segment, in %; observed 1.3 to 22.8
NATIONAL_RATE_RANGE = (1.0, 15.0)  # national total, in %; observed 3.7 to 5.8. Catches a value delivered as 0.043 or 430
WEA_RANGE = (-30.0, 30.0)  # % vs. the same week a year earlier; observed -10.4 (April 2020) to 13.7
INFLATION_RANGE = (-10.0, 15.0)  # % vs. the same month a year earlier, since 2010; observed -1.4 to 3.5

# --- Storage keys ---
PULL_LOG = "raw/pull_log.csv"
