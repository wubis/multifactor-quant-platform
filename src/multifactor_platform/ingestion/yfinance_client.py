import hashlib
import json
from pathlib import Path

import pandas as pd

from multifactor_platform.ingestion.universe import SecurityDefinition, load_large_cap_universe


YFINANCE_TICKER_ALIASES = {
    "BRK.B": "BRK-B",
}

DEFAULT_CACHE_DIR = Path("data/external/yfinance")
DEFAULT_YFINANCE_PERIOD = "10y"
DEFAULT_YFINANCE_UNIVERSE_LIMIT = 100


def to_yfinance_ticker(ticker: str) -> str:
    return YFINANCE_TICKER_ALIASES.get(ticker, ticker)


def from_yfinance_ticker(ticker: str) -> str:
    reverse_aliases = {value: key for key, value in YFINANCE_TICKER_ALIASES.items()}
    return reverse_aliases.get(ticker, ticker)


def _cache_key(tickers: list[str], period: str, suffix: str) -> str:
    digest = hashlib.sha1(",".join(sorted(tickers)).encode("utf-8")).hexdigest()[:12]
    return f"{suffix}_{period}_{len(tickers)}_{digest}"


def _read_parquet_cache(path: Path, metadata_path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        frame = pd.read_parquet(path)
    except (ImportError, OSError, ValueError):
        return None
    if metadata_path.exists():
        try:
            frame.attrs.update(json.loads(metadata_path.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    frame.attrs["cache_hit"] = True
    return frame


def _write_parquet_cache(frame: pd.DataFrame, path: Path, metadata_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        key: value
        for key, value in frame.attrs.items()
        if isinstance(value, (str, int, float, bool, list, dict, type(None)))
    }
    try:
        frame.to_parquet(path, index=False)
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True))
    except (ImportError, OSError, ValueError):
        return


def _ticker_frame(downloaded: pd.DataFrame, yf_ticker: str) -> pd.DataFrame:
    if isinstance(downloaded.columns, pd.MultiIndex):
        if yf_ticker not in downloaded.columns.get_level_values(0):
            return pd.DataFrame()
        return downloaded[yf_ticker].copy()
    return downloaded.copy()


def fetch_yfinance_prices(
    universe: list[SecurityDefinition] | None = None,
    period: str = DEFAULT_YFINANCE_PERIOD,
    batch_size: int = 25,
    retries: int = 2,
    cache_dir: str | Path | None = DEFAULT_CACHE_DIR,
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "yfinance is not installed. Run `pip install -e \".[dev]\"` from the project root."
        ) from exc

    universe = universe or load_large_cap_universe(limit=DEFAULT_YFINANCE_UNIVERSE_LIMIT)
    yf_to_security = {to_yfinance_ticker(security.ticker): security for security in universe}
    tickers = list(yf_to_security)
    if cache_dir is not None:
        cache_root = Path(cache_dir)
        key = _cache_key(tickers, period, "prices")
        cached = _read_parquet_cache(cache_root / f"{key}.parquet", cache_root / f"{key}.json")
        if cached is not None:
            return cached

    rows = []
    failed_tickers = set()
    batch_failures = []
    for start in range(0, len(tickers), batch_size):
        batch = tickers[start : start + batch_size]
        downloaded = pd.DataFrame()
        last_error = None
        for _ in range(retries + 1):
            try:
                downloaded = yf.download(
                    tickers=batch,
                    period=period,
                    interval="1d",
                    auto_adjust=False,
                    progress=False,
                    group_by="ticker",
                    threads=True,
                )
            except Exception as exc:  # yfinance raises heterogeneous transport errors.
                last_error = str(exc)
                downloaded = pd.DataFrame()
            if not downloaded.empty:
                break

        if downloaded.empty:
            failed_tickers.update(from_yfinance_ticker(ticker) for ticker in batch)
            batch_failures.append({"tickers": batch, "error": last_error or "empty response"})
            continue

        for yf_ticker in batch:
            security = yf_to_security[yf_ticker]
            frame = _ticker_frame(downloaded, yf_ticker)
            if "Close" not in frame.columns:
                failed_tickers.add(security.ticker)
                continue
            frame = frame.dropna(subset=["Close"])
            if frame.empty:
                failed_tickers.add(security.ticker)
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

    output = pd.concat(rows, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)
    expected_tickers = [security.ticker for security in universe]
    output.attrs.update(
        {
            "cache_hit": False,
            "expected_tickers": expected_tickers,
            "expected_ticker_count": len(expected_tickers),
            "failed_tickers": sorted(failed_tickers),
            "batch_failures": batch_failures,
            "batch_size": batch_size,
            "period": period,
            "universe_limit": len([security for security in universe if security.ticker != "SPY"]),
        }
    )
    if cache_dir is not None:
        cache_root = Path(cache_dir)
        key = _cache_key(tickers, period, "prices")
        _write_parquet_cache(output, cache_root / f"{key}.parquet", cache_root / f"{key}.json")
    return output


def fetch_yfinance_fundamentals(
    universe: list[SecurityDefinition] | None = None,
    cache_dir: str | Path | None = DEFAULT_CACHE_DIR,
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "yfinance is not installed. Run `pip install -e \".[dev]\"` from the project root."
        ) from exc

    universe = universe or load_large_cap_universe(limit=DEFAULT_YFINANCE_UNIVERSE_LIMIT)
    tickers = [security.ticker for security in universe if security.ticker != "SPY"]
    if cache_dir is not None:
        cache_root = Path(cache_dir)
        key = _cache_key(tickers, "snapshot", "fundamentals")
        cached = _read_parquet_cache(cache_root / f"{key}.parquet", cache_root / f"{key}.json")
        if cached is not None:
            return cached

    rows = []
    failed_tickers = []
    as_of_date = pd.Timestamp.today().normalize()

    for security in universe:
        if security.ticker == "SPY":
            continue

        try:
            ticker = yf.Ticker(to_yfinance_ticker(security.ticker))
            info = ticker.info or {}
        except Exception:
            failed_tickers.append(security.ticker)
            info = {}
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

    output = pd.DataFrame(rows)
    output.attrs.update(
        {
            "cache_hit": False,
            "expected_tickers": tickers,
            "expected_ticker_count": len(tickers),
            "failed_tickers": sorted(failed_tickers),
            "universe_limit": len(tickers),
        }
    )
    if cache_dir is not None:
        cache_root = Path(cache_dir)
        key = _cache_key(tickers, "snapshot", "fundamentals")
        _write_parquet_cache(output, cache_root / f"{key}.parquet", cache_root / f"{key}.json")
    return output
