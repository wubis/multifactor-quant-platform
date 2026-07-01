from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd

from multifactor_platform.backtesting.engine import run_top_n_backtest
from multifactor_platform.config import get_settings
from multifactor_platform.data_quality import report_to_dict, validate_price_history
from multifactor_platform.db.persistence import database_status, persist_pipeline_snapshot
from multifactor_platform.optimization.constraints import PortfolioConstraints
from multifactor_platform.optimization.optimizer import optimize_ranked_portfolio
from multifactor_platform.utils.platform_data import DataSource, load_platform_data

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_data_or_503(source: DataSource):
    try:
        return load_platform_data(source)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _json_records(frame: pd.DataFrame, columns: list[str] | None = None) -> list[dict]:
    output = frame.copy()
    if columns is not None:
        output = output[columns]
    output = output.replace({pd.NA: None})
    output = output.where(pd.notna(output), None)
    records = output.to_dict(orient="records")
    for record in records:
        for key, value in record.items():
            if isinstance(value, pd.Timestamp):
                record[key] = value.date().isoformat()
    return records


@app.get("/")
def root() -> dict:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": "/health",
        "endpoints": [
            "/rankings/latest?source=yfinance",
            "/portfolio/latest?source=yfinance",
            "/portfolio/optimized?source=yfinance",
            "/backtests?source=yfinance",
            "/stocks/{ticker}/features?source=yfinance",
            "/data-quality/report?source=yfinance",
            "/persistence/status",
            "/persistence/snapshot?source=yfinance",
        ],
        "data_sources": ["yfinance", "sample"],
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/data-quality/report")
def data_quality_report(source: DataSource = "sample"):
    prices, _, _ = _load_data_or_503(source)
    return report_to_dict(validate_price_history(prices, source))


@app.get("/rankings/latest")
def latest_rankings(limit: int = 50, source: DataSource = "sample"):
    _, _, rankings = _load_data_or_503(source)
    latest_date = rankings["date"].max()
    rows = rankings.loc[rankings["date"] == latest_date].head(limit)
    return {
        "source": source,
        "date": latest_date.date().isoformat(),
        "rankings": _json_records(
            rows,
            [
                "ticker",
                "sector",
                "rank",
                "composite_score",
                "value_score",
                "quality_score",
                "momentum_score",
                "low_vol_score",
                "liquidity_score",
            ],
        ),
    }


@app.get("/rankings/{ranking_date}")
def rankings_by_date(ranking_date: date, limit: int = 50, source: DataSource = "sample"):
    _, _, rankings = _load_data_or_503(source)
    requested = rankings.loc[rankings["date"] == str(ranking_date)].head(limit)
    if requested.empty:
        raise HTTPException(status_code=404, detail="No rankings found for date")
    return {
        "source": source,
        "date": ranking_date.isoformat(),
        "rankings": _json_records(requested),
    }


@app.get("/stocks/{ticker}/features")
def stock_features(ticker: str, source: DataSource = "sample"):
    _, features, _ = _load_data_or_503(source)
    rows = features.loc[features["ticker"] == ticker.upper()].sort_values("date")
    if rows.empty:
        raise HTTPException(status_code=404, detail="Ticker not found")
    columns = [
        "date",
        "ticker",
        "momentum_1m",
        "momentum_3m",
        "volatility_20d",
        "pe_ratio",
        "roe",
        "market_cap",
        "dollar_volume",
    ]
    return {
        "source": source,
        "ticker": ticker.upper(),
        "features": _json_records(rows.tail(120), columns),
    }


@app.get("/backtests")
def list_backtests(source: DataSource = "sample"):
    prices, _, rankings = _load_data_or_503(source)
    result = run_top_n_backtest(rankings, prices, n=10, rebalance_delay_days=1)
    return [
        {
            "id": f"{source}-top-10",
            "name": f"{source.title()} Top 10 Monthly",
            "source": source,
            "metrics": result["metrics"],
            "settings": result["settings"],
        }
    ]


@app.get("/backtests/{backtest_id}")
def get_backtest(backtest_id: str, source: DataSource = "sample"):
    valid_ids = {"sample-top-10", "yfinance-top-10"}
    if backtest_id not in valid_ids:
        raise HTTPException(status_code=404, detail="Backtest not found")
    prices, _, rankings = _load_data_or_503(source)
    result = run_top_n_backtest(rankings, prices, n=10, rebalance_delay_days=1)
    return {
        "id": f"{source}-top-10",
        "source": source,
        "metrics": result["metrics"],
        "settings": result["settings"],
        "returns": [
            {"date": index.date().isoformat(), "return": value}
            for index, value in result["returns"].items()
        ],
        "benchmark_returns": [
            {"date": index.date().isoformat(), "return": value}
            for index, value in result["benchmark_returns"].items()
        ],
        "excess_returns": [
            {"date": index.date().isoformat(), "return": value}
            for index, value in result["excess_returns"].items()
        ],
        "turnover": [
            {"date": index.date().isoformat(), "turnover": value}
            for index, value in result["turnover"].items()
        ],
        "costs": [
            {
                "date": index.date().isoformat(),
                "turnover": row["turnover"],
                "commission_cost": row["commission_cost"],
                "slippage_cost": row["slippage_cost"],
                "total_cost": row["total_cost"],
            }
            for index, row in result["costs"].iterrows()
        ],
        "sector_exposure": [
            {
                "date": row["date"].date().isoformat(),
                "sector": row["sector"],
                "weight": row["weight"],
            }
            for _, row in result["sector_exposure"].iterrows()
        ],
        "rebalance_log": [
            {
                "date": row["date"].date().isoformat(),
                "signal_date": row["signal_date"].date().isoformat(),
                "trade_date": row["trade_date"].date().isoformat(),
                "next_trade_date": row["next_trade_date"].date().isoformat(),
                "holdings": row["holdings"],
            }
            for _, row in result["rebalance_log"].iterrows()
        ],
    }


@app.get("/portfolio/latest")
def latest_portfolio(limit: int = 10, source: DataSource = "sample"):
    _, _, rankings = _load_data_or_503(source)
    latest_date = rankings["date"].max()
    rows = rankings.loc[rankings["date"] == latest_date].head(limit).copy()
    rows["weight"] = 1 / len(rows)
    sector_exposure = (
        rows.groupby("sector")["weight"].sum().sort_values(ascending=False).reset_index()
    )
    return {
        "source": source,
        "date": latest_date.date().isoformat(),
        "positions": _json_records(rows, ["ticker", "sector", "rank", "weight", "composite_score"]),
        "sector_exposure": _json_records(sector_exposure),
    }


@app.get("/portfolio/optimized")
def optimized_portfolio(
    source: DataSource = "sample",
    candidate_limit: int = 50,
    max_position_size: float = 0.05,
    max_sector_exposure: float = 0.25,
    cash_minimum: float = 0.02,
):
    _, _, rankings = _load_data_or_503(source)
    latest_date = rankings["date"].max()
    latest = rankings.loc[rankings["date"] == latest_date].copy()
    result = optimize_ranked_portfolio(
        latest,
        constraints=PortfolioConstraints(
            max_position_size=max_position_size,
            max_sector_exposure=max_sector_exposure,
            cash_minimum=cash_minimum,
        ),
        candidate_limit=candidate_limit,
    )
    return {
        "source": source,
        "date": latest_date.date().isoformat(),
        "positions": _json_records(result["positions"]),
        "sector_exposure": _json_records(result["sector_exposure"]),
        "cash_weight": result["cash_weight"],
        "invested_weight": result["invested_weight"],
        "turnover": result["turnover"],
        "constraints": result["constraints"],
    }


@app.get("/models")
def models(source: DataSource = "sample"):
    return {
        "source": source,
        "models": [
            {"name": "Weighted Score", "rank_ic": None, "sharpe": None, "status": "Active"},
            {"name": "Elastic Net", "rank_ic": None, "sharpe": None, "status": "Planned"},
            {"name": "XGBoost", "rank_ic": None, "sharpe": None, "status": "Planned"},
        ],
    }


@app.get("/persistence/status")
def persistence_status():
    return database_status()


@app.post("/persistence/snapshot")
def persist_snapshot(source: DataSource = "sample"):
    return persist_pipeline_snapshot(source)
