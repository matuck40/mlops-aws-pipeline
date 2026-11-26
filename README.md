# mlops-aws-pipeline

**New study project, in progress.** I am building an end-to-end MLOps pipeline on AWS from scratch, writing the code myself to learn each piece.

## Plan

1. Daily ETL of a public dataset into S3
2. Training a classical model with versioned runs and metrics
3. Deploying the model as an API
4. Monitoring predictions against actuals, with retraining on drift
5. CI on GitHub with tests

Everything runs on the AWS free tier, with a cost alert from day one. Nothing here is production-grade yet; this README will track what is done.

## The problem

**Volt**, a fictional energy trader, decides every day how much energy to buy for each hour of tomorrow. Buying too much wastes money; buying too little means paying a premium at the last minute. This project forecasts the **next-day hourly load of Brazil's Southeast/Center-West subsystem**, using open data from [ONS](https://dados.ons.org.br/) (the national grid operator). Full spec: [`docs/SPEC.md`](docs/SPEC.md).

## Status

Built in vertical slices: first a thin end-to-end version, then each piece gets deeper.

- [x] **Slice 1 — local pipeline** ([plan](docs/plans/2026-11-25-fatia-1-local.md)): ETL of real ONS data, seasonal naive forecast, read-only API, CI with tests
- [ ] Slice 2 — the same pipeline on AWS (cost alert, S3, Lambda, EventBridge, API Gateway)
- [ ] Slice 3 — LightGBM vs. baselines, MAPE, MLflow
- [ ] Slice 4 — monitoring forecast vs. actual, drift alert, retraining

## How it works (slice 1)

```
ETL         downloads the ONS yearly CSV → keeps SE/CO → validates 24 hours → data/carga_horaria/data=YYYY-MM-DD/carga.parquet
Forecast    tomorrow's hour h = same hour 7 days earlier (seasonal naive) → data/previsoes/data_alvo=YYYY-MM-DD/previsao.parquet
API         only reads stored forecasts: GET /previsao?data=YYYY-MM-DD → 24 hourly values (404 if missing, 400 if invalid)
```

Each step has one job. The API never runs the model, so it stays fast and simple, and the daily batch forecast is what monitoring will compare against actuals.

## Run it

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                    # create the environment with locked versions
uv run python -m volt.etl 2026-11-18       # ETL for one day (repeat for the 7 days before the target)
uv run python -m volt.previsao 2026-11-25  # forecast a day (needs the load from 7 days earlier)
uv run uvicorn volt.api:app                # serve the API on http://localhost:8000
curl "localhost:8000/previsao?data=2026-11-25"
```

Tests: `uv run pytest`. They never touch the network: the download function is injected and replaced by a real ONS excerpt in `tests/fixtures/`.

## Workflow

Spec → plan → tasks. Each task starts with a failing test (TDD), lives on its own branch, and merges through a pull request only after CI passes (`main` is protected) and a code review.
