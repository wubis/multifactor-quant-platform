"""Select an identical executable window before running strategy comparisons."""
import pandas as pd

from multifactor_platform.backtesting.engine import _build_trade_schedule
from multifactor_platform.research import ResearchDataError, require_historical_research


def common_evaluation_window(rankings: list[pd.DataFrame], prices: pd.DataFrame, delay: int = 1):
    require_historical_research(prices)
    schedules = []
    for frame in rankings:
        require_historical_research(frame)
        schedules.append([event['trade_date'] for event in _build_trade_schedule(frame, prices, delay)])
    if not schedules or any(not schedule for schedule in schedules):
        raise ResearchDataError("No executable common evaluation window")
    common = sorted(set.intersection(*(set(schedule) for schedule in schedules)))
    if len(common) < 2:
        raise ResearchDataError("Comparison requires at least two common rebalance boundaries")
    start, end = common[0], common[-1]
    expected = [date for date in common if start <= date < end]
    if any([date for date in schedule if start <= date < end] != expected for schedule in schedules):
        raise ResearchDataError("Strategy predictions have gaps within the common evaluation window")
    return start, end
