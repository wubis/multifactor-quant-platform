from dataclasses import dataclass


@dataclass(frozen=True)
class PortfolioConstraints:
    max_position_size: float = 0.05
    min_position_size: float = 0.0
    max_sector_exposure: float = 0.25
    max_turnover: float = 0.30
    beta_target: float = 1.0
    cash_minimum: float = 0.02
