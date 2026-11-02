# Decision log

Design decisions for the Swiss Segmented Unemployment Rate Predictor (P04, MLOps HS26).
Each entry names the review label it answers, so `docs/ms2_summary.pdf` can refer to it.

| ID | Date | Decision | Answers |
|----|------|----------|---------|
| D1 | 2026-10-15 | Nowcast with weekly and monthly indicators; SAKE stays the quarterly target | E1 |
| D2 | 2026-10-15 | Add SECO Weekly Economic Activity (WEA) as the main live source | E1 |
| D3 | 2026-10-15 | Switch the CPI covariate from quarterly to monthly LIK | E1 |
| D4 | 2026-10-15 | Retrain on a new SAKE release, not on a weekly schedule | E2 |
| D5 | 2026-10-15 | Store the download date with every pull of every source | A1, D2 |
| D6 | 2026-10-15 | Predict the year-on-year change; forecast = same quarter last year + change | B2 |
| D7 | 2026-10-15 | Features computed as of the release date of the latest SAKE quarter | E1, leakage |
| D8 | 2026-11-02 | Exact dependency versions in `uv.lock`, installed with `uv sync --locked` everywhere | B3 |
| D9 | 2026-11-02 | Keep the BFS `STATUS` code as a column; set the success target on the reliable segments | A2, B1 |
| D10 | 2026-11-02 | Seasonal naive is the stronger baseline; target restated against it | B2 |
| D11 | 2026-11-02 | Data versioning with dated raw files, hashes and manifests in the bucket, not DVC | reproducibility |
| D12 | 2026-11-02 | Feature pipeline scheduled daily instead of weekly | E1 |
| D13 | 2026-11-02 | Batch inference with a Streamlit UI; no FastAPI service | E3 |

---

## D1 · Nowcast design

**Context.** SAKE (BFS Labour Force Survey) is released quarterly and adds one value per series per quarter, about 3,000 rows in total. Before MS4 the pipeline would see at most one new release, so the ingest → retrain → monitor loop could barely be shown (editorial point E1).

**Decision.** The target stays the quarter-ahead ILO unemployment rate for the national total and 44 segments. Weekly and monthly indicators are added as features, so new data reaches the feature store every week and the forecast is refreshed between SAKE releases.

**Two cadences.**

| Cadence | Trigger | What runs |
|---------|---------|-----------|
| Weekly / monthly | New WEA or LIK value | Feature pipeline, inference refresh, input drift check. The UI shows "forecast as of <date>" |
| Quarterly | New SAKE release | Feature pipeline, retraining, evaluation, registry update |

**Consequence.** True unemployment values still arrive once a quarter, so model accuracy can only be measured quarterly. Drift monitoring runs on the weekly inputs instead.

**Alternatives considered.**

| Option | Why not |
|--------|---------|
| Monthly target from SECO registered unemployment | amstat.ch has no public API, monthly figures are only published as PDF reports, and the BFS table on opendata.swiss has annual averages only. Would require scraping |
| Job-ad data from Job-Room (SECO) | No official data access, only third-party scrapers |
| Second model forecasting next week's WEA | Gives a weekly label and a full weekly loop, but doubles the modelling work. Kept as future work |

## D2 · SECO Weekly Economic Activity (WEA)

**What.** SECO's weekly index of economic activity, built from daily and weekly indicators and closely tied to GDP growth. A value of 1.0 means activity was 1 % above the same week a year earlier.

**Source.** Machine-readable CSV published by SECO, no API key: `https://scheduler.swissdatas.ch/scheduled/wwa.csv`.

**Why.** Weekly updates (about 12 before MS4), official statistic, history back to 2005-01-03, which covers the backtest from 2010.

**Handling.**
- The file holds two series. Use `structure == "seco_wwa"` only and ignore `seco_wwa_pre_covid`.
- SECO labels WEA experimental and past values can be revised. Every pull is stored with its download date (see D5), and features are built from the vintage available at each forecast date.
- Observed: between the pulls of 15.10 and 25.10.2026 the 2026Q1 mean of WEA changed from −0.41 to −0.49. Revisions happen in practice, not only in theory.

**Alternatives considered.**

| Option | Why not |
|--------|---------|
| KOF Economic Barometer (monthly) | Measures the same general economic activity as WEA, and would need a second API client and schedule for little new signal |
| Monitoring Consumption Switzerland (weekly card spending) | Possible later addition, not needed for E1 |
| SNB exchange rates (daily) | Possible later addition, indirect link to unemployment |

## D3 · Monthly inflation instead of quarterly CPI

**Decision.** Keep inflation as a covariate, as in the proposal, but ingest monthly year-on-year inflation instead of a quarterly CPI value.

**Source.** SNB data portal, cube `plkopr`, CSV without API key: `https://data.snb.ch/api/cube/plkopr/data/csv/en`. It republishes the BFS consumer price index (LIK). The series `VVP` is the change vs. the same month a year earlier in %. The second line of the file holds the publication date, stored with every pull (D5).

**Why.** Monthly updates about 3 weeks after month end, history from 1921, no gaps since 2010. Keeps the proposal's covariate.

**Alternatives considered.**

| Option | Why not |
|--------|---------|
| `landesindex-der-konsumentenpreise` on opendata.swiss | Published by Kanton Zug, not the BFS |
| BFS LIK datasets per year on opendata.swiss | HTML and PDF only |
| BFS table "CPI (december 2015=100), detailed results since 1982" | Last updated February 2021, old basket, `.xls` |

**Note.** Inflation correlates with the unemployment level (−0.63 three quarters later), but hardly with its change, so part of the link is likely a shared trend. Its contribution is checked in the MS3 evaluation.

## D4 · Retraining cadence

**Decision.** Retraining is triggered by a new SAKE release (new resource or changed hash → retrain → compare with the registered model). New WEA or LIK values only refresh inference.

**Why.** Weekly retraining on unchanged quarterly labels produces identical models (editorial point E2).

## D5 · Download dates for every source

**Decision.** Each ingested file is stored with its download date, and for SAKE also its release date. New SAKE releases are found by listing the resources of the CKAN dataset, not by watching one fixed file URL.

**Why.** A new quarterly release may be published as a separate resource (review point A1), and WEA values can be revised (D2). Storing dates makes it clear which data version every forecast used, and lets features be built only from data available at each cutoff, so nothing from the future leaks into the backtest.

## D6 · Target: year-on-year change

**Context.** SAKE values are not seasonally adjusted: Q1 and Q3 lie about 0.3 pp above the yearly mean, Q2 and Q4 below (exploration, section 3). The quarter-to-quarter change mostly reflects the season.

**Decision.** The model predicts, per segment, the change of the rate in quarter t+1 against quarter t−3 (same quarter one year earlier). The forecast is the rate in t−3 plus the predicted change. MAE is measured on the rate.

**Why.** WEA and inflation correlate clearly with the year-on-year change (WEA −0.66 two quarters back, inflation −0.50 in the same quarter), but hardly with the quarter-to-quarter change. A prediction of zero equals the seasonal-naive baseline, so the model learns a correction to it. The latest year-on-year change is a feature, so the persistence information stays available.

## D7 · Features as of the release date

**Decision.** One feature row per segment and target quarter t+1, computed as of the release date of quarter t (historically quarter end + 49 days, from now on the CSV `issued` date). Each row stores this `as_of` date.

| Group | Features |
|-------|----------|
| Segment | Gender, nationality, age group (categorical), quarter of the target |
| Own history | Rate in t, t−1, t−3, year-on-year change in t, `STATUS` of the value in t |
| WEA | Mean of the last 13 weeks before `as_of`, quarterly means 1–4 quarters back |
| Inflation | Latest year-on-year value published before `as_of`, quarterly means 1–4 quarters back |

Between SAKE releases, the weekly and monthly refresh recomputes the WEA and inflation features as of the refresh date.

**Limitation.** Only the current version of each source is available, not past versions. If SECO, the SNB or the BFS revised older values, the backtest uses the corrected numbers. From now on every pull is stored with its date (D5).

## D8 · Pinned dependencies

**Decision.** `uv.lock` pins every package with its exact version and hash, and is committed. Every install uses `uv sync --locked`: the CI run, the scheduled pipeline and the Docker build. `--locked` fails when `uv.lock` no longer matches `pyproject.toml`, so a forgotten `uv lock` turns CI red instead of installing something else. The old `requirements.txt` with minimum versions only was removed.

**Split.** Development tools (Jupyter, Matplotlib, pytest, ruff) are in the `dev` group. The Docker image installs with `--no-dev`, so they are not in it.

## D9 · Reliability flags of small segments

**Context.** Reviewers asked how the BFS marks unreliable values in small segments (A2, B1).

**Finding.** Values carry no brackets or symbols. Reliability is a separate `STATUS` column with SDMX observation status codes: `A` normal, `U` low reliability, `O` missing (no value), `P` provisional (monthly values only). In scope (2010Q1 onwards, without 65+) there are no `O` values, but 17 of 45 segments have `U` quarters, 7 of them in more than half of all quarters (exploration notebook, section 2–3).

**Decision.**
- The code is kept: every feature row has `status_t`, the status of the latest released value, so the model and the UI can use it.
- All 45 segments stay in the model and the UI. The UI (MS4) shows a "low reliability" note next to segments whose latest value is `U`.
- The success target (D10) is measured on the 28 segments without any `U` value. The 17 segments with `U` values are reported separately.

## D10 · Baseline for the success target

**Context.** The proposal set a 15 % target against the seasonal-naive baseline only (B2).

**Comparison.** Both naive baselines on the stored features, forecasts as of each release date, MAE in percentage points (`uv run python -m src.training_pipeline.baselines`):

| Segments | Seasonal naive (rate in t−3) | Persistence (rate in t) |
|---|---|---|
| 28 segments without `U` | **0.630** | 0.672 |
| 10 segments with some `U` | **0.919** | 1.348 |
| 7 segments mostly `U` | **1.272** | 1.663 |
| All 45 segments | **0.794** | 0.976 |
| National total only | 0.347 | **0.333** |

Window: the last 12 target quarters, 2023Q3–2026Q2, the same window as the walk-forward backtest in the proposal. Over all quarters since 2011Q2 the seasonal naive is better in every group, the national total included (0.377 vs 0.448).

**Decision.** Seasonal naive is the stronger baseline. Because the series is not seasonally adjusted (D6), persistence carries last quarter's season into the next one. The target is restated: **the model's MAE over the last 12 quarters is at least 15 % lower than the seasonal-naive MAE on the 28 segments without `U` values, i.e. at most 0.535 pp (0.630 × 0.85).** The 17 segments with `U` values and the national total are reported against both baselines, without a target.

**Note.** A model that predicts a year-on-year change of zero (D6) reproduces the seasonal naive exactly, so the target measures what the WEA and inflation features add on top of it. The numbers are recomputed with every new SAKE release.

## D11 · Data versioning without DVC

**Context.** The course uses DVC for data versioning: data in a remote, a pointer file with a hash in Git.

**Decision.** The same guarantees are covered without DVC, in the bucket that also holds the feature store:

| DVC | Here |
|---|---|
| Content hash in a `.dvc` file in Git | SHA-256 of every pull in `raw/pull_log.csv` |
| Data in a remote (S3, GCS) | Every changed file as `raw/<source>/<download date>.csv` on GCS |
| `git checkout` + `dvc checkout` to get a past version | Every feature version has a `manifest.json` with the hashes of its source files and the git commit of the code that built it |

**Why.** The data is not edited by hand and not committed by people: it arrives from three live sources on a schedule. The pipeline therefore versions it itself, at the moment of download, with no extra tool or second remote. DVC would add value if raw data were changed manually or if expensive pipeline stages needed caching. Neither applies: a full run takes under a minute.

## D12 · Daily schedule

**Decision.** The feature pipeline runs daily (GitHub Actions, 05:17 UTC) instead of weekly.

**Why.** WEA is published weekly and LIK monthly, but not on fixed weekdays, so a weekly run can be up to six days late. Unchanged files are not stored again (D5), so a run without new data costs a few seconds and one small feature version. GitHub can start scheduled runs hours late; the daily schedule makes up for skipped or late runs.

## D13 · Serving: batch forecasts and one Streamlit app

**Context.** The proposal planned a FastAPI backend next to a Streamlit frontend. Reviewers asked why both are needed (E3).

**Decision.** No FastAPI service. A scheduled batch inference job loads the champion model, forecasts all 45 segments and writes the forecasts to GCS. A single Streamlit app on Cloud Run reads and shows them.

**Why.** The inputs of every forecast are known before anyone asks: the features of all 45 segments are already in the feature store, and choosing a segment in the UI adds no new input. An API would only return what the batch job has already computed, as a second service to deploy, secure and monitor. This is the batch shape of the inference pipeline (SW06: scheduled batch → table, UI reads the table).

**What replaces the API's guarantees.**

| With an API | Here |
|---|---|
| `/health` reports the model version | Every forecast row stores `model_version`, `feature_time` and `created_at`; the UI shows them next to the forecast |
| Health probe for the platform | Streamlit's built-in `/_stcore/health` for Cloud Run |
| Smoke test after a deploy | The deploy workflow checks that the UI answers and that the newest forecast file carries the champion's version |
| Prediction log | The forecast files themselves, one per run (SW06: in batch, the predictions file is the log) |

**Revisit if** the UI ever needs forecasts for inputs that are not precomputed, e.g. user-defined scenarios. Then a `/predict` endpoint would earn its place.

