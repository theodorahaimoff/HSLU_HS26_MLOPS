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

**Alternatives considered.**

| Option | Why not |
|--------|---------|
| KOF Economic Barometer (monthly) | Measures the same general economic activity as WEA, and would need a second API client and schedule for little new signal |
| Monitoring Consumption Switzerland (weekly card spending) | Possible later addition, not needed for E1 |
| SNB exchange rates (daily) | Possible later addition, indirect link to unemployment |

## D3 · Monthly LIK instead of quarterly CPI

**Decision.** Keep inflation as a covariate, as in the proposal, but ingest the monthly LIK (BFS consumer price index) instead of a quarterly value.

**Why.** Adds a second source that updates during the semester and keeps the proposal's covariate. Inflation is expected to be a weak predictor of unemployment in the short run; its importance is checked in the MS3 evaluation.

**To do.** Locate the monthly LIK resource on opendata.swiss and record its URL here.

## D4 · Retraining cadence

**Decision.** Retraining is triggered by a new SAKE release (new resource or changed hash → retrain → compare with the registered model). New WEA or LIK values only refresh inference.

**Why.** Weekly retraining on unchanged quarterly labels produces identical models (editorial point E2).

## D5 · Download dates for every source

**Decision.** Each ingested file is stored with its download date, and for SAKE also its release date. New SAKE releases are found by listing the resources of the CKAN dataset, not by watching one fixed file URL.

**Why.** A new quarterly release may be published as a separate resource (review point A1), and WEA values can be revised (D2). Storing dates makes it clear which data version every forecast used, and lets features be built only from data available at each cutoff, so nothing from the future leaks into the backtest.