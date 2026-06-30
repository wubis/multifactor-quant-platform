from dataclasses import dataclass


@dataclass(frozen=True)
class SecurityDefinition:
    ticker: str
    name: str
    sector: str


DEFAULT_UNIVERSE = [
    SecurityDefinition("AAPL", "Apple Inc.", "Information Technology"),
    SecurityDefinition("MSFT", "Microsoft Corp.", "Information Technology"),
    SecurityDefinition("NVDA", "NVIDIA Corp.", "Information Technology"),
    SecurityDefinition("AMZN", "Amazon.com Inc.", "Consumer Discretionary"),
    SecurityDefinition("META", "Meta Platforms Inc.", "Communication Services"),
    SecurityDefinition("GOOGL", "Alphabet Inc.", "Communication Services"),
    SecurityDefinition("BRK.B", "Berkshire Hathaway Inc.", "Financials"),
    SecurityDefinition("JPM", "JPMorgan Chase & Co.", "Financials"),
    SecurityDefinition("UNH", "UnitedHealth Group Inc.", "Health Care"),
    SecurityDefinition("LLY", "Eli Lilly and Co.", "Health Care"),
    SecurityDefinition("XOM", "Exxon Mobil Corp.", "Energy"),
    SecurityDefinition("PG", "Procter & Gamble Co.", "Consumer Staples"),
    SecurityDefinition("COST", "Costco Wholesale Corp.", "Consumer Staples"),
    SecurityDefinition("HD", "Home Depot Inc.", "Consumer Discretionary"),
    SecurityDefinition("AVGO", "Broadcom Inc.", "Information Technology"),
    SecurityDefinition("V", "Visa Inc.", "Financials"),
    SecurityDefinition("MA", "Mastercard Inc.", "Financials"),
    SecurityDefinition("JNJ", "Johnson & Johnson", "Health Care"),
    SecurityDefinition("WMT", "Walmart Inc.", "Consumer Staples"),
    SecurityDefinition("SPY", "SPDR S&P 500 ETF Trust", "Benchmark"),
]


def load_default_universe(limit: int | None = None) -> list[SecurityDefinition]:
    universe = DEFAULT_UNIVERSE if limit is None else DEFAULT_UNIVERSE[:limit]
    return list(universe)
