import pandas as pd


def prepare_fundamentals(fundamentals: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "ticker"}
    missing = required.difference(fundamentals.columns)
    if missing:
        raise ValueError(f"Missing fundamental columns: {sorted(missing)}")

    output = fundamentals.copy()
    output["date"] = pd.to_datetime(output["date"])
    return output.sort_values(["ticker", "date"]).reset_index(drop=True)
