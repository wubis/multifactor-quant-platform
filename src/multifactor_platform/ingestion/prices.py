import pandas as pd


REQUIRED_PRICE_COLUMNS = {
    "date",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
}


def validate_prices(prices: pd.DataFrame) -> None:
    missing = REQUIRED_PRICE_COLUMNS.difference(prices.columns)
    if missing:
        raise ValueError(f"Missing price columns: {sorted(missing)}")
    if prices.duplicated(["ticker", "date"]).any():
        raise ValueError("Duplicate ticker/date rows found in prices")
    if (prices[["open", "high", "low", "close", "adj_close"]] <= 0).any().any():
        raise ValueError("Price columns must be positive")


def prepare_prices(prices: pd.DataFrame) -> pd.DataFrame:
    validate_prices(prices)
    output = prices.copy()
    output["date"] = pd.to_datetime(output["date"])
    return output.sort_values(["ticker", "date"]).reset_index(drop=True)
