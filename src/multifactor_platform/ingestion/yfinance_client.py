import pandas as pd

from multifactor_platform.ingestion.universe import SecurityDefinition, load_default_universe


YFINANCE_TICKER_ALIASES = {
    "BRK.B": "BRK-B",
}


def to_yfinance_ticker(ticker: str) -> str:
    return YFINANCE_TICKER_ALIASES.get(ticker, ticker)


def from_yfinance_ticker(ticker: str) -> str:
    reverse_aliases = {value: key for key, value in YFINANCE_TICKER_ALIASES.items()}
    return reverse_aliases.get(ticker, ticker)


def fetch_yfinance_prices(
    universe: list[SecurityDefinition] | None = None,
    period: str = "5y",
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "yfinance is not installed. Run `pip install -e \".[dev]\"` from the project root."
        ) from exc

    universe = universe or load_default_universe()
    yf_to_security = {to_yfinance_ticker(security.ticker): security for security in universe}
    tickers = list(yf_to_security)
    downloaded = yf.download(
        tickers=tickers,
        period=period,
        interval="1d",
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    if downloaded.empty:
        raise RuntimeError("yfinance returned no price data")

    rows = []
    for yf_ticker, security in yf_to_security.items():
        if isinstance(downloaded.columns, pd.MultiIndex):
            if yf_ticker not in downloaded.columns.get_level_values(0):
                continue
            frame = downloaded[yf_ticker].copy()
        else:
            frame = downloaded.copy()

        frame = frame.dropna(subset=["Close"])
        if frame.empty:
            continue

        adj_close = frame["Adj Close"] if "Adj Close" in frame.columns else frame["Close"]
        rows.append(
            pd.DataFrame(
                {
                    "date": pd.to_datetime(frame.index).tz_localize(None),
                    "ticker": security.ticker,
                    "sector": security.sector,
                    "open": frame["Open"].astype(float).to_numpy(),
                    "high": frame["High"].astype(float).to_numpy(),
                    "low": frame["Low"].astype(float).to_numpy(),
                    "close": frame["Close"].astype(float).to_numpy(),
                    "adj_close": adj_close.astype(float).to_numpy(),
                    "volume": frame["Volume"].fillna(0).astype(float).to_numpy(),
                }
            )
        )

    if not rows:
        raise RuntimeError("No usable ticker price history was returned by yfinance")

    return pd.concat(rows, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)


def fetch_yfinance_fundamentals(
    universe: list[SecurityDefinition] | None = None,
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "yfinance is not installed. Run `pip install -e \".[dev]\"` from the project root."
        ) from exc

    universe = universe or load_default_universe()
    rows = []
    as_of_date = pd.Timestamp.today().normalize()

    for security in universe:
        if security.ticker == "SPY":
            continue

        ticker = yf.Ticker(to_yfinance_ticker(security.ticker))
        info = ticker.info or {}
        market_cap = info.get("marketCap")
        free_cashflow = info.get("freeCashflow")
        total_debt = info.get("totalDebt")
        total_equity = info.get("totalStockholderEquity")
        debt_to_equity = info.get("debtToEquity")
        if debt_to_equity is None and total_debt is not None and total_equity:
            debt_to_equity = total_debt / total_equity
        elif debt_to_equity is not None and debt_to_equity > 10:
            debt_to_equity = debt_to_equity / 100

        rows.append(
            {
                "date": as_of_date,
                "ticker": security.ticker,
                "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
                "pb_ratio": info.get("priceToBook"),
                "ev_to_ebitda": info.get("enterpriseToEbitda"),
                "fcf_yield": free_cashflow / market_cap if free_cashflow and market_cap else None,
                "roe": info.get("returnOnEquity"),
                "gross_margin": info.get("grossMargins"),
                "debt_to_equity": debt_to_equity,
                "earnings_stability": 0.5,
                "market_cap": market_cap,
            }
        )

    return pd.DataFrame(rows)
