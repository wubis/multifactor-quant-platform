from datetime import date

from fastapi import FastAPI, HTTPException

from multifactor_platform.backtesting.engine import run_top_n_backtest
from multifactor_platform.config import get_settings
from multifactor_platform.utils.sample_app_data import load_sample_platform_data

settings = get_settings()
app = FastAPI(title=settings.app_name)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/rankings/latest")
def latest_rankings(limit: int = 50):
    _, _, rankings = load_sample_platform_data()
    latest_date = rankings["date"].max()
    rows = rankings.loc[rankings["date"] == latest_date].head(limit)
    return {
        "date": latest_date.date().isoformat(),
        "rankings": rows[
            ["ticker", "sector", "rank", "composite_score", "value_score", "quality_score", "momentum_score"]
        ].to_dict(orient="records"),
    }


@app.get("/rankings/{ranking_date}")
def rankings_by_date(ranking_date: date, limit: int = 50):
    _, _, rankings = load_sample_platform_data()
    requested = rankings.loc[rankings["date"] == str(ranking_date)].head(limit)
    if requested.empty:
        raise HTTPException(status_code=404, detail="No rankings found for date")
    return {"date": ranking_date.isoformat(), "rankings": requested.to_dict(orient="records")}


@app.get("/stocks/{ticker}/features")
def stock_features(ticker: str):
    _, features, _ = load_sample_platform_data()
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
    return {"ticker": ticker.upper(), "features": rows[columns].tail(120).to_dict(orient="records")}


@app.get("/backtests")
def list_backtests():
    prices, _, rankings = load_sample_platform_data()
    result = run_top_n_backtest(rankings, prices, n=10)
    return [{"id": "sample-top-10", "name": "Sample Top 10 Monthly", "metrics": result["metrics"]}]


@app.get("/backtests/{backtest_id}")
def get_backtest(backtest_id: str):
    if backtest_id != "sample-top-10":
        raise HTTPException(status_code=404, detail="Backtest not found")
    prices, _, rankings = load_sample_platform_data()
    result = run_top_n_backtest(rankings, prices, n=10)
    return {
        "id": backtest_id,
        "metrics": result["metrics"],
        "returns": [
            {"date": index.date().isoformat(), "return": value}
            for index, value in result["returns"].items()
        ],
    }


@app.get("/portfolio/latest")
def latest_portfolio(limit: int = 10):
    _, _, rankings = load_sample_platform_data()
    latest_date = rankings["date"].max()
    rows = rankings.loc[rankings["date"] == latest_date].head(limit).copy()
    rows["weight"] = 1 / len(rows)
    return {
        "date": latest_date.date().isoformat(),
        "positions": rows[["ticker", "sector", "rank", "weight"]].to_dict(orient="records"),
    }
