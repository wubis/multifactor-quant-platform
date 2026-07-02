from multifactor_platform.ingestion.universe import load_large_cap_universe


def test_large_cap_universe_contains_100_stocks_plus_benchmark():
    universe = load_large_cap_universe(limit=100)
    tickers = [security.ticker for security in universe]

    assert len([ticker for ticker in tickers if ticker != "SPY"]) == 100
    assert tickers[-1] == "SPY"
    assert len(tickers) == len(set(tickers))
