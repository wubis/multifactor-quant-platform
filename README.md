# Multifactor Quant Platform

An end-to-end platform for ranking U.S. large-cap stocks using financial factors, testing the ranking strategy historically, persisting results, and serving everything through an API and dashboard.

This project is built to look and behave like a small production research platform, not just a notebook. It includes data ingestion, feature engineering, factor scoring, backtesting, persistence, command-line jobs, data-quality reporting, a FastAPI backend, and a React dashboard.

## What It Does

The platform answers a practical investment research question:

> Given the information available today, which stocks look most attractive relative to the rest of the universe?

The current workflow is:

```text
yfinance or sample data
  -> data validation
  -> factor engineering
  -> cross-sectional normalization
  -> weighted stock ranking
  -> monthly top-N backtest
  -> SQLite/Postgres-style persistence
  -> FastAPI endpoints
  -> React dashboard
```

The default live demo uses `yfinance`. The deterministic `sample` source is kept for offline tests and repeatable local demos.

## Core Concepts

**Universe**: the list of stocks the strategy is allowed to rank. This project starts with a compact U.S. large-cap universe plus SPY as a benchmark.

**Factor**: a measurable stock characteristic. Examples include momentum, valuation, volatility, quality, size, and liquidity.

**Feature**: the machine-learning term for an input variable. In this project, factor values are the features.

**Ranking model**: a model that orders stocks from most attractive to least attractive. The first model is intentionally interpretable: a weighted score across value, quality, momentum, low volatility, and liquidity.

**Backtest**: a historical simulation of a strategy. Here, the baseline strategy buys the top-ranked names, weights them equally, holds for one month, and rebalances monthly.

**ETL**: extract, transform, load. The platform extracts market data, transforms it into features and rankings, and loads it into a database.

## Current Capabilities

- Live yfinance ingestion for prices and current fundamentals
- Deterministic sample data path for offline development
- Price validation and data-quality reporting
- Momentum, volatility, beta, value, quality, size, and liquidity features
- Cross-sectional normalization by date
- Weighted multifactor ranking model
- Monthly top-N equal-weight backtester with delayed rebalancing
- Explicit commission and slippage cost modeling
- Metrics including CAGR, Sharpe, volatility, max drawdown, win rate, turnover, alpha, tracking error, and information ratio
- Constrained portfolio optimizer with max position, sector exposure, turnover, and cash controls
- SQLite persistence for securities, prices, fundamentals, features, predictions, and backtest summaries
- FastAPI backend with interactive docs
- React dashboard with rankings, factor charts, strategy-vs-SPY equity curves, turnover, costs, and sector exposure history
- Command-line jobs for repeatable pipeline execution
- GitHub Actions CI and scheduled sample ETL workflow
- Tests for factors, ranking, backtesting, API routes, jobs, and persistence

## Architecture

```text
Data Sources
  -> Ingestion Jobs
  -> Data Quality Checks
  -> Feature Engineering
  -> Feature Store Tables
  -> Ranking Model
  -> Backtester
  -> Portfolio Optimizer
  -> Persistence Layer
  -> FastAPI Backend
  -> React Dashboard
```

Important implementation choices:

- **FastAPI** serves rankings, backtests, portfolios, data-quality reports, and persistence status.
- **SQLAlchemy** defines the database models and supports local SQLite by default.
- **React + Recharts** powers the dashboard and visual analytics.
- **Command-line jobs** make the pipeline runnable outside the dashboard/API.
- **GitHub Actions** runs tests, dashboard builds, and a scheduled sample ETL workflow.

## Factor Model

The baseline model is a weighted score:

```text
composite_score =
  0.25 * value_score
+ 0.25 * quality_score
+ 0.25 * momentum_score
+ 0.15 * low_volatility_score
+ 0.10 * liquidity_score
```

This is deliberately simple. A transparent baseline makes it easier to debug the data, understand rankings, and compare future machine-learning models against something interpretable.

Implemented factor families:

- **Momentum**: 1-month, 3-month, 6-month, and 12-month excluding most recent month returns
- **Volatility**: 20-day volatility, 60-day volatility, beta to SPY
- **Value**: PE, PB, EV/EBITDA, free cash flow yield
- **Quality**: ROE, gross margin, debt/equity, earnings stability
- **Size/Liquidity**: market cap and dollar volume

## Backtesting

The baseline strategy:

1. Rank stocks monthly.
2. Select the top names.
3. Wait for the configured rebalance delay.
4. Trade on the next available market date.
5. Equal-weight the portfolio.
6. Hold until the next rebalance trade date.
7. Deduct commission and slippage costs based on turnover.

Tracked metrics:

- CAGR: annualized growth rate
- Benchmark CAGR: SPY annualized growth over the same holding windows
- Alpha: strategy CAGR minus SPY CAGR
- Sharpe ratio: return per unit of volatility
- Information ratio: excess return per unit of benchmark-relative volatility
- Tracking error: volatility of strategy returns minus benchmark returns
- Max drawdown: worst peak-to-trough loss
- Volatility: variability of returns
- Win rate: share of positive months
- Turnover: how much the portfolio changes each rebalance

The backtest detail API also returns date-level strategy returns, SPY returns, excess returns, turnover, cost breakdowns, sector exposure, and the rebalance log showing signal date, trade date, and next trade date.

## Data Quality And Research Caveats

The project includes `GET /data-quality/report?source=...` and a matching ingestion job. These checks report:

- empty price data
- duplicate ticker/date rows
- non-positive prices
- missing adjusted close values
- short ticker histories
- whether the source should be treated as demo-grade

Important caveat: `yfinance` is useful for a live end-to-end demo, but it is not a research-grade point-in-time dataset. Current yfinance fundamentals are applied as a snapshot, so historical backtest results should be treated as platform demonstrations, not investment claims.

To make this research-grade, the next data upgrades would be:

- point-in-time fundamentals
- historical universe membership
- delisted stock coverage
- corporate action auditing
- vendor/source metadata on every dataset

## Local Development

Install and test:

```bash
cd "/Users/justinwang/Desktop/Projects/multifactor-quant-platform"
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Run the backend:

```bash
uvicorn multifactor_platform.api.main:app --reload
```

API docs:

```text
http://127.0.0.1:8000/docs
```

Run the dashboard:

```bash
cd dashboard
npm install
npm run dev
```

Dashboard:

```text
http://localhost:5173
```

## Key API Endpoints

```text
GET  /health
GET  /rankings/latest?source=yfinance
GET  /portfolio/latest?source=yfinance
GET  /portfolio/optimized?source=yfinance
GET  /backtests?source=yfinance
GET  /backtests/yfinance-top-10?source=yfinance
GET  /stocks/AAPL/features?source=yfinance
GET  /data-quality/report?source=yfinance
GET  /persistence/status
POST /persistence/snapshot?source=yfinance
```

Use `source=sample` for deterministic offline runs.

## Command-Line Jobs

Jobs make the pipeline repeatable without relying on dashboard clicks.

```bash
python -m multifactor_platform.jobs.ingest_prices --source sample
python -m multifactor_platform.jobs.compute_features --source sample
python -m multifactor_platform.jobs.run_backtest --source sample --top-n 10
python -m multifactor_platform.jobs.persist_snapshot --source sample
python -m multifactor_platform.jobs.db_status
```

After `pip install -e ".[dev]"`, shorter aliases are available:

```bash
mfp-ingest-prices --source sample
mfp-compute-features --source sample
mfp-run-backtest --source sample --top-n 10
mfp-persist-snapshot --source sample
mfp-db-status
```

## Persistence

Local development uses SQLite by default:

```text
data/processed/multifactor.db
```

Persisted tables:

- `securities`
- `prices`
- `fundamentals`
- `features`
- `model_predictions`
- `backtest_results`

Docker can override the database URL to use PostgreSQL.

## CI And Scheduled Jobs

The repository includes GitHub Actions workflows:

- `.github/workflows/ci.yml`: installs Python and Node dependencies, runs the Python test suite, and builds the dashboard.
- `.github/workflows/nightly-etl.yml`: runs the sample ingestion, feature computation, backtest, persistence, and DB status jobs on a schedule or manual trigger.

The scheduled workflow intentionally uses `source=sample` so CI remains deterministic and does not fail because of transient yfinance/network issues.

## Testing

The test suite covers the highest-risk parts of the platform:

- factor calculations use past data
- rankings are generated correctly
- portfolio weights and turnover logic work
- API routes return expected shapes
- jobs run from the command line
- pipeline snapshots persist into SQLite

Run:

```bash
pytest
```

## Limitations

This is a portfolio project and platform scaffold, not an investment product.

Current limitations:

- yfinance is not point-in-time or institutionally auditable
- delisted stocks are not handled yet
- transaction cost and slippage models are explicit but still simplified
- ML models are placeholders for later phases
- portfolio optimization is deterministic and constraint-based, not yet a full risk-model optimizer

## Next Steps

- Add point-in-time fundamentals from a professional data vendor
- Store universe membership by date to reduce survivorship bias
- Implement Elastic Net and tree-based ranking models
- Add walk-forward validation and model comparison
- Add covariance/risk-model-aware portfolio optimization
- Add artifact uploads for scheduled ETL outputs
