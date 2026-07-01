# Multifactor Stock Ranking Platform

This project is an educational, production-style system for ranking stocks.

The basic idea is:

1. Collect stock market data.
2. Turn that data into useful measurements called factors.
3. Combine those factors into a score for each stock.
4. Rank stocks from most attractive to least attractive.
5. Test whether buying the highly ranked stocks would have worked historically.
6. Serve the results through an API and dashboard.

In other words, it is an end-to-end data and machine learning platform for multifactor equity ranking, including ETL pipelines, feature engineering, model evaluation, backtesting, APIs, and dashboarding. It is a mini version of the type of system an investment firm might use to organize data, test ideas, and decide which stocks look interesting.

## What Problem Is This Solving?

There are thousands of publicly traded stocks. Looking at each one manually is slow and inconsistent.

A stock ranking platform tries to answer:

> Given the information we have today, which stocks look better or worse than the rest?

This project starts with large U.S. companies, such as S&P 500-style stocks, and ranks them once per month.

The first version does not try to predict the exact price of a stock. Instead, it asks a simpler question:

> Over the next month, which stocks are likely to do better than the average stock in the universe?

That is called predicting relative return. A stock can have a positive relative return even if the whole market falls, as long as it falls less than the average stock.

## Key Finance Concepts

### Stock Universe

The universe is the list of stocks the system is allowed to consider.

For example:

- S&P 500 companies
- the 500 most liquid U.S. stocks
- only technology stocks
- only profitable companies

This project starts with a simplified large-cap U.S. universe. Large-cap means large companies by market value.

### Rebalancing

Rebalancing means updating the portfolio on a schedule.

This project uses monthly rebalancing:

1. At the end of each month, rank all stocks.
2. Buy the top-ranked stocks.
3. Hold them for about one month.
4. Repeat the process next month.

### Factors

A factor is a measurable trait of a stock.

For example, one factor is momentum:

> Has this stock been going up recently?

Another factor is value:

> Is this stock cheap compared with the company's earnings or assets?

This project uses several factor families:

- Momentum: recent price strength
- Volatility: how much the stock price moves around
- Value: whether the stock looks cheap or expensive
- Quality: whether the company appears financially strong
- Size and liquidity: how large and easy to trade the stock is

### Portfolio

A portfolio is the collection of stocks we choose to hold.

The first strategy is intentionally simple:

> Buy the top 50 ranked stocks with equal weights.

Equal weight means each stock gets the same allocation. If we hold 50 stocks, each stock gets 2% of the portfolio.

## Key Machine Learning Concepts

### Features

In machine learning, a feature is an input variable.

For this project, features are the factor values for each stock on each date.

Example features:

- 1-month return
- 6-month return
- 20-day volatility
- PE ratio
- return on equity
- market cap

Each stock-date pair becomes one row of training or ranking data.

### Target

The target is what we want to predict.

This project's first target is:

> Next-month return minus the average next-month return of the universe.

That means the model is rewarded for identifying stocks that outperform their peers, not necessarily stocks that go up in absolute terms.

### Baseline Model

Before using advanced machine learning, this project starts with a simple weighted scoring model.

The first scoring formula is:

```text
composite_score =
  0.25 * value_score
+ 0.25 * quality_score
+ 0.25 * momentum_score
+ 0.15 * low_volatility_score
+ 0.10 * liquidity_score
```

This is useful because it is easy to understand. If the baseline does not work, a complex model probably will not magically fix the problem.

### Ranking Instead Of Classification

Some ML projects classify things:

> Is this stock good or bad?

This project ranks things:

> Is this stock better or worse than the other stocks available today?

Ranking is natural for investing because capital is limited. We usually do not need to know whether every stock is good. We need to know which stocks are most attractive compared with the alternatives.

### Walk-Forward Validation

Walk-forward validation is a realistic way to test models over time.

Instead of randomly mixing old and new data, we train on the past and test on the future.

Example:

```text
Train:    2015-2019
Validate: 2020
Test:     2021

Train:    2015-2020
Validate: 2021
Test:     2022
```

This matters because financial markets change over time. A model that only works because it accidentally saw the future is not useful.

## Key Infrastructure Concepts

### ETL Pipeline

ETL stands for Extract, Transform, Load.

In this project:

- Extract means downloading or receiving market and fundamentals data.
- Transform means cleaning it and calculating derived fields.
- Load means storing it in a database or files so other parts of the system can use it.

### Database

The database stores the important tables:

- securities: stock metadata, such as ticker and sector
- prices: daily open, high, low, close, adjusted close, and volume
- fundamentals: accounting metrics like PE, PB, ROE, and debt/equity
- features: calculated factor values
- model_predictions: model scores and ranks
- backtest_results: performance metrics from historical simulations

The scaffold includes SQLAlchemy models for these tables. SQLAlchemy is a Python library for defining and interacting with relational database tables.

For local development, the default database is SQLite:

```text
data/processed/multifactor.db
```

Docker can still override the database URL to use PostgreSQL.

### Feature Store

A feature store is a central place to keep reusable features.

Instead of recalculating momentum, volatility, value, and quality metrics separately for every model, the system computes them once and stores them.

This makes experiments more consistent and reduces accidental differences between models.

### API

An API is a way for programs to talk to each other.

This project uses FastAPI, a Python web framework.

The API exposes endpoints such as:

- `GET /rankings/latest`
- `GET /portfolio/latest`
- `GET /backtests`
- `GET /stocks/{ticker}/features`

For example, the dashboard can call `/rankings/latest` to display the newest stock ranking.

### Dashboard

The dashboard is the user interface.

It is built with React and is meant to show:

- latest rankings
- top and bottom stocks
- portfolio summary
- backtest results
- model comparison
- risk exposures

The dashboard calls the FastAPI backend directly. It includes clickable sections for Overview, Backtests, Models, and Risk, plus charts for factor scores, equity curve, monthly returns, and sector exposure.

## Architecture

```text
Data Sources
  -> ETL Pipeline
  -> Raw Database
  -> Feature Engineering Jobs
  -> Feature Store
  -> Ranking Models
  -> Backtester
  -> Portfolio Optimizer
  -> FastAPI Backend
  -> React Dashboard
```

Here is what each layer does:

- Data Sources: where the raw stock data comes from
- ETL Pipeline: downloads, cleans, and validates the data
- Raw Database: stores unmodified or lightly cleaned source data
- Feature Engineering Jobs: calculate factors like momentum and volatility
- Feature Store: stores reusable features by stock and date
- Ranking Models: turn features into scores and ranks
- Backtester: simulates how a strategy would have performed historically
- Portfolio Optimizer: converts scores into portfolio weights with constraints
- FastAPI Backend: serves rankings, features, and backtest results
- React Dashboard: lets a human explore the system visually

## Current MVP Scope

The first version focuses on:

- Universe: U.S. large-cap stocks
- Rebalance frequency: monthly
- Prediction target: next-month relative return
- Output: ranking from 1 to N
- First strategy: buy top 50 stocks equally weighted

The scaffold currently uses generated sample data so the system can run without a paid data vendor.

It also includes a live demo path using `yfinance`:

```text
yfinance price/fundamental download
  -> validation and cleaning
  -> feature engineering
  -> weighted ranking model
  -> top-N backtest
  -> FastAPI endpoints
  -> React dashboard
```

The dashboard defaults to `source=yfinance`, while the API still supports `source=sample` for offline tests and demos.

Important caveat: yfinance is useful for a local demo, but it is not a professional point-in-time research dataset. The yfinance demo uses current fundamentals as a snapshot, which is fine for showing the platform plumbing but not enough for trustworthy historical performance claims.

## Factors In The MVP

### Momentum

Momentum measures recent price strength.

Implemented or planned metrics:

- 1-month return
- 3-month return
- 6-month return
- 12-month return excluding the most recent month

The 12-month excluding 1-month version is common because the most recent month can sometimes reverse.

### Volatility

Volatility measures how much a stock's price moves around.

Implemented or planned metrics:

- 20-day realized volatility
- 60-day realized volatility
- beta to SPY

Beta measures how sensitive a stock is to the overall market. A beta near 1 means the stock tends to move similarly to the market.

### Value

Value factors ask whether a stock looks cheap relative to the company's business.

Implemented or planned metrics:

- PE ratio: price divided by earnings
- PB ratio: price divided by book value
- EV/EBITDA: enterprise value divided by EBITDA
- free cash flow yield: free cash flow divided by market value

Lower PE, lower PB, lower EV/EBITDA, and higher free cash flow yield often indicate cheaper stocks.

### Quality

Quality factors ask whether a company looks financially strong.

Implemented or planned metrics:

- ROE: return on equity
- gross margin
- debt/equity
- earnings stability

Higher ROE, higher gross margin, lower debt, and more stable earnings are generally better.

### Size And Liquidity

Size and liquidity measure how large and tradable a stock is.

Implemented or planned metrics:

- market cap
- average daily dollar volume

Dollar volume is price multiplied by share volume. A stock with high dollar volume is usually easier to trade without moving the price too much.

## Backtesting Explained

A backtest is a historical simulation.

It asks:

> If we had used this strategy in the past, what would have happened?

The first backtest strategy is:

1. At each monthly rebalance date, rank all stocks.
2. Select the top 50.
3. Give each selected stock the same weight.
4. Hold for one month.
5. Repeat.

The backtester tracks:

- CAGR: annualized growth rate
- Sharpe ratio: return per unit of risk
- max drawdown: worst peak-to-trough loss
- volatility: how much returns fluctuate
- turnover: how much the portfolio changes each rebalance
- win rate: percentage of positive months
- transaction costs: estimated trading costs

Backtests are useful, but they are easy to fool. A good backtest must avoid using future information.

## Common Failure Modes

### Survivorship Bias

Survivorship bias happens when we test only on companies that exist today.

Example:

If we use today's S&P 500 list to test a strategy from 2010, we accidentally exclude companies that were in the index back then but later failed, merged, or were removed.

Control:

- Store universe membership by date.
- Use the stock list that was available at each point in history.

### Lookahead Leakage

Lookahead leakage happens when the model uses information that would not have been known at the time.

Example:

Using a company's full-year earnings report before it was actually published.

Control:

- Use as-of dates and publish dates.
- Separate the signal date from the trade execution date.

### Corporate Actions

Corporate actions include stock splits, dividends, mergers, and ticker changes.

If prices are not adjusted correctly, returns can be wrong.

Control:

- Use adjusted prices for return calculations.
- Keep raw prices for auditing.

### Overfitting

Overfitting means the model learned noise from historical data instead of a repeatable pattern.

Control:

- Use simple baselines first.
- Use walk-forward validation.
- Compare models on data they did not train on.

### Ignoring Trading Costs

A strategy can look great before costs and terrible after costs.

Trading costs include:

- commissions
- bid/ask spread
- slippage
- market impact

Control:

- Include transaction costs from the first backtest.
- Track turnover.

### Liquidity Problems

Some stocks are hard to trade in large size.

Control:

- Filter by average daily dollar volume.
- Cap position sizes.

### Sector Concentration

A strategy might accidentally buy mostly one sector, such as technology.

That can make performance depend more on sector exposure than stock selection skill.

Control:

- Report sector exposure.
- Add sector exposure limits in the optimizer.

## Local Development

### Backend Setup

From the project root:

```bash
cd "/Users/justinwang/Desktop/Projects/multifactor-quant-platform"
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn multifactor_platform.api.main:app --reload
```

The API will be available at:

```text
http://127.0.0.1:8000
```

The interactive API docs will be available at:

```text
http://127.0.0.1:8000/docs
```

Useful API endpoints:

```text
GET /health
GET /rankings/latest?source=yfinance
GET /portfolio/latest?source=yfinance
GET /backtests?source=yfinance
GET /backtests/yfinance-top-10?source=yfinance
GET /stocks/AAPL/features?source=yfinance
GET /persistence/status
POST /persistence/snapshot?source=yfinance
```

If yfinance is unavailable or you want the deterministic offline demo, use `source=sample` instead:

```text
GET /rankings/latest?source=sample
GET /portfolio/latest?source=sample
GET /backtests?source=sample
```

### Dashboard Setup

The dashboard lives in the `dashboard/` directory.

```bash
cd "/Users/justinwang/Desktop/Projects/multifactor-quant-platform/dashboard"
npm install
npm run dev
```

The dashboard usually runs at:

```text
http://localhost:5173
```

The backend and dashboard are separate processes. In normal development, keep both running:

- backend: `http://127.0.0.1:8000`
- dashboard: `http://localhost:5173`

The database button in the dashboard writes the currently selected source into the local database. For example, if the source selector says `sample`, it persists the sample pipeline. If it says `yfinance`, it persists the yfinance-backed pipeline.

## Current Scaffold

The current codebase includes:

- generated sample market and fundamentals data
- live yfinance price and fundamentals ingestion
- price and fundamentals validation helpers
- factor calculations for momentum, volatility, beta, and liquidity
- cross-sectional normalization
- weighted baseline ranking model
- monthly top-N backtesting engine
- FastAPI backend
- React dashboard with API-backed charts
- SQLAlchemy database models
- SQLite persistence for prices, fundamentals, features, predictions, and backtest summaries
- tests for factor timing, ranking, portfolio weights, and API routes

## Suggested Build Order

### 1. Make The Baseline Reliable

Before adding complex ML, make sure the simple ranking system works end to end:

- data loads
- features compute correctly
- rankings are stable
- backtests do not use future data
- API endpoints return expected data

### 2. Add Real Data

Replace generated sample data with real data from a provider such as:

- yfinance for demos
- Polygon
- Financial Modeling Prep
- Nasdaq Data Link
- Intrinio
- Sharadar-style point-in-time datasets

For serious research, point-in-time fundamentals are very important.

### 3. Persist Data

Move from in-memory sample data to PostgreSQL tables:

- prices
- fundamentals
- securities
- features
- model predictions
- backtest results

### 4. Improve The Dashboard

Connect the React dashboard to the FastAPI backend.

Add charts for:

- equity curve
- drawdown
- monthly returns
- factor scores over time
- sector exposure

### 5. Add ML Models

After the baseline is trusted, add:

- linear regression
- Ridge, Lasso, and Elastic Net
- Random Forest
- XGBoost or LightGBM
- LambdaMART ranking model

Compare each model against the weighted baseline.

### 6. Add Portfolio Optimization

Move from "buy top 50 equally weighted" to constrained allocation.

Possible constraints:

- max position size: 5%
- max sector exposure: 25%
- max turnover per rebalance: 30%
- beta target near 1.0
- minimum cash level: 2%

## Testing Philosophy

The most important tests are not just "does the code run?"

The most important tests are:

- Does momentum use only past prices?
- Does the backtest trade after the signal is known?
- Do portfolio weights sum to 1?
- Are transaction costs applied correctly?
- Are sector and position constraints respected?
- Does the API return the expected shape?

High-signal example tests:

```text
test_momentum_uses_only_past_prices
test_backtest_does_not_trade_on_same_day_signal
test_portfolio_respects_max_position_size
test_sector_exposure_constraint
```

## Limitations

This is currently a scaffold, not an investment product.

Important limitations:

- sample data is generated, not real
- fundamentals are simplified
- there is no true point-in-time vendor dataset yet
- delisted companies are not handled yet
- transaction costs are simplified
- dashboard model metadata is still placeholder-level
- ML models are placeholders for later phases

Those limitations are normal for an MVP. The purpose of the scaffold is to create a clean system shape before adding expensive data, complex models, and production deployment.

## Concepts Used

1. Finance: factors, portfolios, backtesting, risk, and trading constraints.
2. Machine learning: features, targets, ranking, validation, and model comparison.
3. Infrastructure: ETL, databases, APIs, Docker, tests, and dashboards.
