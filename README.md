# Multifactor Quant Platform

An end-to-end platform for ranking U.S. large-cap stocks using financial factors, testing the ranking strategy historically, persisting results, and serving everything through an API and dashboard.

This project is built to behave like a small production research platform. It includes data ingestion, feature engineering, factor scoring, backtesting, persistence, command-line jobs, data-quality reporting, a FastAPI backend, and a React dashboard.

## Research validity status

The correctness, daily-accounting, and research-archive milestones are implemented; see [the research rebuild roadmap](docs/roadmap.md).
Historical yfinance multifactor backtests and model evaluation are now **blocked** because the
provider adapter supplies current fundamental snapshots, not point-in-time history. Snapshot
dates are preserved. Rankings can be produced only when those fundamentals were available on
the corresponding price date; otherwise the API explains that no eligible rankings exist.
Use `source=sample` for deterministic pipeline checks, not investment conclusions.

Walk-forward training now excludes unrealized labels, drawdown includes initial capital, and
portfolio costs account for drift and both buys and sells. Existing database results predate
these fixes and have not been regenerated. Risk metrics now use daily observations; CAGR uses actual elapsed calendar time.
The dashboard's CAGR spread is not risk-adjusted alpha; sector-balanced portfolios are not
benchmark-sector-neutral. The allocator's beta target is informational and is not enforced.

### Reproducible runs

```bash
python -m multifactor_platform.jobs.run_backtest --source sample --top-n 10
# Use the artifact.path returned by the first command:
python -m multifactor_platform.jobs.run_backtest --replay-run data/processed/research/runs/<run-id>
```

Each CLI run and API strategy comparison saves an immutable bundle containing input snapshots,
parameters, source files, numerical dependency versions, daily NAV/holdings/trades, and summary
results. Replay verifies checksums and requires matching code/dependencies; it compares every
regenerated output with the archive. This reproduces the supplied rankings/predictions, not ML
training. `--output-dir` changes the archive root for CLI runs.

The backtest detail API exposes `daily_ledger`, `daily_holdings`, `trades`, and `artifact` alongside
holding-period diagnostics. Strategy comparisons use an identical executable window and report
its boundaries in `settings`. The dashboard plots daily NAV.

Positions use adjusted total-return units rather than raw broker shares. Corporate actions remain
embedded in the adjusted price series. The simulator accrues cash using a configurable constant
annual rate, rejects missing daily marks, and marks holdings through the terminal date without
assuming liquidation. These mechanics do not replace point-in-time data or prove an investment edge.

### Point-in-time imports and free data direction

The project targets a **$0 SimFin + Tiingo stack**. The validated import source
`point_in_time` accepts historical financial states and universe events, computes
valuation using historical daily market cap, and normalizes only eligible stocks.
Publication/revision timestamps and immutable input identities are retained.

See [the import contract and free-tier limits](docs/data-contract.md) for CSV schemas,
a runnable fictitious example, provider limitations, and the remaining adapter work.
The SimFin/Tiingo boundary helpers operate on local records; live downloads and a
complete statement-to-TTM conversion are not yet connected.

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

- Live yfinance ingestion for prices and current fundamentals across a 100-stock large-cap universe
- Batched yfinance downloads with local Parquet caching when pandas has a parquet engine installed
- Deterministic sample data path for offline development
- Price validation and data-quality reporting
- Momentum, volatility, beta, value, quality, size, and liquidity features
- Cross-sectional normalization by date
- Weighted multifactor ranking model
- ML ranking models with walk-forward validation
- Monthly top-N and sector-balanced backtests with delayed rebalancing
- Explicit commission and slippage cost modeling
- Metrics including CAGR, Sharpe, volatility, max drawdown, win rate, turnover, alpha, tracking error, and information ratio
- Constrained portfolio optimizer with max position, sector exposure, turnover, and cash controls
- SQLite persistence for securities, prices, fundamentals, features, predictions, and backtest summaries
- FastAPI backend with interactive docs
- React dashboard with rankings, factor charts, model/strategy comparison, strategy-vs-SPY equity curves, turnover, costs, and sector exposure history
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

This is deliberately simple. A transparent baseline makes it easier to debug the data, understand rankings, and compare machine-learning models against something interpretable.

Implemented factor families:

- **Momentum**: 1-month, 3-month, 6-month, and 12-month excluding most recent month returns
- **Volatility**: 20-day volatility, 60-day volatility, beta to SPY
- **Value**: PE, PB, EV/EBITDA, free cash flow yield
- **Quality**: ROE, gross margin, debt/equity, earnings stability
- **Size/Liquidity**: market cap and dollar volume

## Machine Learning Models

The ML layer predicts each stock's next 21-trading-day return relative to the universe average. That target asks a practical ranking question: "Which stocks are likely to outperform the rest of the available universe over the next month?"

Implemented models:

- **Linear Regression**: a simple linear baseline that shows whether factors have stable directional relationships with forward returns
- **Elastic Net**: a regularized linear model that can shrink noisy factor weights and reduce overfitting
- **Random Forest**: a tree ensemble that can capture nonlinear relationships between factors
- **Gradient Boosting**: uses XGBoost if installed, LightGBM if installed, and otherwise falls back to scikit-learn histogram gradient boosting

Validation uses a walk-forward setup. The model trains on earlier dates, validates on a later window, then rolls forward and repeats. This better matches how a trading model would be used in production with training labels admitted only after their realization dates.

Model diagnostics include:

- Rank IC: Spearman correlation between predicted ranking and realized future relative return
- Hit rate: share of predictions with the correct positive/negative direction
- RMSE and MAE: prediction error magnitude
- R2: regression fit on the validation windows
- Fold count: number of walk-forward validation windows

## Backtesting

The baseline strategy:

1. Rank stocks monthly.
2. Select the top names.
3. Wait for the configured rebalance delay.
4. Trade on the next available market date.
5. Equal-weight the portfolio.
6. Hold until the next rebalance trade date.
7. Fund commission and slippage from actual buys and sells before earning holding-period returns.
8. Carry drifted weights into the next rebalance.

Tracked metrics:

- CAGR: annualized growth rate
- Benchmark CAGR: SPY annualized growth over the same holding windows
- CAGR spread: strategy CAGR minus SPY CAGR (legacy API key `alpha`)
- Sharpe ratio: annualized arithmetic excess return per unit of volatility; cash rate defaults to zero
- Information ratio: annualized arithmetic active return per unit of tracking error
- Tracking error: volatility of strategy returns minus benchmark returns
- Max drawdown: worst peak-to-trough loss
- Volatility: variability of returns
- Win rate: share of positive months
- Turnover: how much the portfolio changes each rebalance

The backtest detail API also returns date-level strategy returns, SPY returns, excess returns, turnover, cost breakdowns, sector exposure, and the rebalance log showing signal date, trade date, and next trade date.

Implemented strategy variants include the original weighted-score top-10 portfolio, a sector-balanced weighted-score portfolio, and out-of-sample Linear Regression, Elastic Net, Random Forest, and Gradient Boosting portfolios built from walk-forward model predictions.

The yfinance path uses 10 years of price history by default over a curated 100-stock U.S. large-cap universe, plus SPY as the benchmark. These defaults can be changed with `MFP_YFINANCE_PERIOD`, `MFP_YFINANCE_UNIVERSE_LIMIT`, and `MFP_YFINANCE_BATCH_SIZE`. Downloads are batched so partial vendor failures can be reported ticker-by-ticker. Price and fundamental snapshots are cached under `data/external/yfinance/` as Parquet files when the local pandas environment supports Parquet; if not, the pipeline still runs without cache persistence. Backtest responses include warnings when the validation period is short, when holdings do not change after the initial rebalance, or when a strategy selects most of the available universe. The detail response also includes rebalance-level holdings, the configured data period, and the observed ticker count so results can be inspected instead of treated as a black box.

## Data Quality And Research Caveats

The project includes `GET /data-quality/report?source=...` and a matching ingestion job. These checks report:

- empty price data
- duplicate ticker/date rows
- non-positive prices
- missing adjusted close values
- zero or missing volume rows
- daily adjusted-return outliers
- stale latest price dates
- expected-vs-observed ticker coverage
- failed yfinance price/fundamental tickers
- whether the response came from local cache
- short ticker histories
- whether the source should be treated as demo-grade

Important caveat: `yfinance` is useful for a live end-to-end demo, but it is not a research-grade point-in-time dataset. Current yfinance fundamentals remain snapshots with their original dates; historical multifactor backtests and model evaluation using this source are disabled.

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
GET  /backtests/yfinance-sector-neutral-top-12?source=yfinance
GET  /backtests/yfinance-random-forest-top-10?source=yfinance
GET  /backtests/yfinance-gradient-boosting-top-10?source=yfinance
GET  /models?source=yfinance
GET  /models/walk-forward?source=yfinance
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
python -m multifactor_platform.jobs.evaluate_models --source sample
python -m multifactor_platform.jobs.persist_snapshot --source sample
python -m multifactor_platform.jobs.db_status
```

After `pip install -e ".[dev]"`, shorter aliases are available:

```bash
mfp-ingest-prices --source sample
mfp-compute-features --source sample
mfp-run-backtest --source sample --top-n 10
mfp-evaluate-models --source sample
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
- ML models use compact factor features and require stronger research before investment use
- portfolio optimization is deterministic and constraint-based, not yet a full risk-model optimizer

## Next Steps

- Add point-in-time fundamentals from a professional data vendor
- Store universe membership by date to reduce survivorship bias
- Persist trained model artifacts and walk-forward prediction sets
- Add richer feature selection and hyperparameter search
- Add covariance/risk-model-aware portfolio optimization
- Add artifact uploads for scheduled ETL outputs

Free data integration: [SimFin conversion and cached Tiingo downloads](docs/data-contract.md#free-provider-conversion-and-download) now have CLI workflows and offline regression tests. Real historical membership and capitalization inputs are still required.
