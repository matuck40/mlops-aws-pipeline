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
uv run python -m volt.backfill 2023-11-26 2026-11-25  # load a date range, each year downloaded once; exits 1 if any day failed
uv run python -m volt.previsao 2026-11-25  # forecast a day (needs the load from 7 days earlier)
uv run uvicorn volt.api:app                # serve the API on http://localhost:8000
curl "localhost:8000/previsao?data=2026-11-25"
```

Data goes to the `data/` folder by default; set `VOLT_DADOS` to use another folder. The backfill also works with `VOLT_DADOS=s3://<bucket>` (to be run in the deploy phase).

Tests: `uv run pytest`. They never touch the network: the download function is injected and replaced by a real ONS excerpt in `tests/fixtures/`.

## Deploy to AWS

**Not run yet.** The commands below are the plan; slice 2 has only the S3 bucket in `template.yaml` so far. Region: `us-east-2`.

```bash
aws login                # authenticate first (no credentials are stored in the repo)
sam validate --lint      # local check of template.yaml
sam build                # output goes to .aws-sam/ (ignored by Git)
sam deploy               # settings come from samconfig.toml; confirms the change set before applying
aws s3 ls                # the bucket volt-dados-<account-id> should appear
```

## Tear down

**Not run yet.** Order matters: CloudFormation cannot delete a bucket that still has objects.

```bash
# 1. empty the data bucket
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
aws s3 rm "s3://volt-dados-$ACCOUNT" --recursive

# 2. delete the project stack (asks for confirmation; add --no-prompts to skip)
sam delete --stack-name volt --region us-east-2

# 3. find the bucket SAM created for deploy packages
B=$(aws cloudformation describe-stacks --stack-name aws-sam-cli-managed-default --region us-east-2 \
  --query "Stacks[0].Outputs[?OutputKey=='SourceBucket'].OutputValue" --output text)

# 4. empty it. This bucket is versioned, so `aws s3 rm` is not enough:
#    delete every object version, then every delete marker.
aws s3api delete-objects --bucket "$B" --region us-east-2 --delete "$(aws s3api list-object-versions \
  --bucket "$B" --region us-east-2 --output json --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}')"
aws s3api delete-objects --bucket "$B" --region us-east-2 --delete "$(aws s3api list-object-versions \
  --bucket "$B" --region us-east-2 --output json --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}')"

# 5. delete the SAM-managed stack
aws cloudformation delete-stack --stack-name aws-sam-cli-managed-default --region us-east-2
```

Each `delete-objects` call handles up to 1000 entries (repeat if there are more; this project stores only a handful of packages). The second call errors harmlessly if there are no delete markers. The simplest alternative for step 4 is the **Empty** button on the bucket in the S3 console.

## Workflow

Spec → plan → tasks. Each task starts with a failing test (TDD), lives on its own branch, and merges through a pull request only after CI passes (`main` is protected) and a code review.
