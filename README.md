# Swiss Segmented Unemployment Rate Predictor

MLOPS HS26 semester project — Hochschule Luzern

Full proposal: [`docs/proposal.pdf`](docs/proposal.pdf)

## What this predicts

Switzerland's ILO unemployment rate for the **next quarter** — the national total,
and independently for each of 44 demographic segments (gender × nationality × age
bracket), 45 series in total. All 45 are forecast automatically on every run; the UI
only lets you *view* a segment's forecast, it doesn't trigger a new prediction.

## Architecture (FTI)

```mermaid
flowchart LR
    Live[("BFS SAKE + LIK CSV")] --> Feat["Feature pipeline<br/><sub>daily hash-check</sub>"]
    Feat -->|write| FS[("Feature Store")]
    FS -->|read| Train["Training pipeline<br/><sub>weekly + manual</sub>"]
    Train -->|register| Reg[("Model Registry")]
    Reg -->|load best| Inf["Inference pipeline<br/><sub>scheduled batch, all 45 segments</sub>"]
    Inf --> UI["UI<br/><sub>gender / nationality / age checkboxes</sub>"]
    FS -.->|features at inference time| Inf
```

| Stage | What it does | Trigger |
|---|---|---|
| **Feature pipeline** | Pulls SAKE unemployment + LIK inflation data from the `opendata.swiss` CKAN API, builds lag/seasonal/covariate features, writes to the feature store | Daily hash-check (sources update quarterly/monthly) |
| **Training pipeline** | Trains one pooled LightGBM model across all 45 segments, registers it | Weekly + manual dispatch |
| **Inference pipeline** | Loads the best registered model, produces all 45 forecasts in a batch, serves them | Scheduled, after each training run |

## Data

| Source | Role | Frequency | Access |
|--------|------|-----------|--------|
| BFS Labour Force Survey (SAKE), ILO unemployment rate by gender, nationality and age group | Target (label) | Quarterly | opendata.swiss CKAN API |
| SECO Weekly Economic Activity (WEA) | Nowcast feature | Weekly | CSV from SECO |
| BFS consumer price index (LIK) | Nowcast feature | Monthly | opendata.swiss |

**Scope.** SAKE data from 2010-Q1, the first quarter with the full gender × nationality × age breakdown. The 65+ age group is excluded. This gives the national total plus 44 segments.

**How the system stays live.** SAKE only changes once a quarter, so the forecast is a nowcast: new WEA values arrive weekly and new LIK values monthly, and each refreshes the features and the forecast. A new SAKE release triggers retraining.

**Data versions.** Every download is stored with its download date (and SAKE with its release date), because WEA values can be revised and SAKE releases can appear as new files.

**Change from the MS1 proposal.** The proposal used SAKE with a quarterly CPI covariate only. After the MS1 reviews (editorial point E1) WEA was added and CPI switched to monthly LIK. See [`docs/decisions.md`](docs/decisions.md) for the reasons and the alternatives considered.

## Tech stack

- **Model**: LightGBM (pooled, single model across all segments)
- **Feature store**: versioned Parquet on GCS
- **Experiment tracking + registry**: Weights & Biases (academic tier)
- **Orchestration**: GitHub Actions
- **Serving**: FastAPI backend + Streamlit frontend, containerized, deployed on Google Cloud Run

See [`docs/proposal.pdf`](docs/proposal.pdf) for the full data source, feature, and evaluation details.

## Repository layout

```
.
├── .github/workflows/      # scheduled feature/training pipeline jobs
├── data/
│   ├── raw/                # fetched source CSVs (gitignored)
│   └── processed/          # engineered feature tables (gitignored)
├── docs/
│   └── proposal.pdf        # MS1 proposal
├── notebooks/               # exploratory analysis, backfill checks
├── src/
│   ├── feature_pipeline/    # ingestion + feature engineering
│   ├── training_pipeline/   # LightGBM training + W&B logging/registry
│   ├── inference_pipeline/  # FastAPI + Streamlit serving
│   └── common/              # shared config, data schemas
├── tests/
├── .env.example
├── .gitignore
├── Dockerfile
├── requirements.txt
└── README.md
```

## Local setup

```bash
git clone https://github.com/theodorahaimoff/HSLU_HS26_MLOPS.git
cd HSLU_HS26_MLOPS
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env 
```

## Running the pipelines locally

```bash
python -m src.feature_pipeline.ingest      # fetch + build features
python -m src.training_pipeline.train      # train + register pooled model
uvicorn src.inference_pipeline.api:app     # start the FastAPI backend
streamlit run src/inference_pipeline/app.py  # start the UI
```