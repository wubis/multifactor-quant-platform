import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, BarChart3, BriefcaseBusiness, Database, LineChart, RefreshCw } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart as RechartsLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import "./styles.css";

type View = "overview" | "backtests" | "models" | "risk";
type DataSource = "yfinance" | "sample";

type Ranking = {
  ticker: string;
  sector: string;
  rank: number;
  composite_score: number;
  value_score: number;
  quality_score: number;
  momentum_score: number;
};

type Metrics = {
  cagr: number;
  sharpe: number;
  volatility: number;
  max_drawdown: number;
  win_rate: number;
  average_turnover: number;
  average_rebalance_turnover: number;
  benchmark_cagr: number;
  alpha: number;
  tracking_error: number;
  information_ratio: number;
};

type Backtest = {
  id: string;
  name: string;
  metrics: Metrics;
  periods: number;
  warnings: string[];
};

type BacktestDetail = Backtest & {
  settings: {
    top_n: number;
    construction: string;
    commission_bps: number;
    slippage_bps: number;
    rebalance_delay_days: number;
    benchmark_ticker: string;
  };
  returns: { date: string; return: number }[];
  benchmark_returns: { date: string; return: number }[];
  excess_returns: { date: string; return: number }[];
  turnover: { date: string; turnover: number }[];
  costs: {
    date: string;
    turnover: number;
    commission_cost: number;
    slippage_cost: number;
    total_cost: number;
  }[];
  sector_exposure: { date: string; sector: string; weight: number }[];
  factor_exposure: { date: string; factor: string; exposure: number }[];
  holdings: { date: string; ticker: string; sector: string; rank: number; weight: number }[];
  rebalance_log: {
    date: string;
    signal_date: string;
    trade_date: string;
    next_trade_date: string;
    holdings: number;
    available_universe: number;
    turnover: number;
    changed_positions: number;
  }[];
};

type Portfolio = {
  date: string;
  positions: { ticker: string; sector: string; rank: number; weight: number; composite_score: number }[];
  sector_exposure: { sector: string; weight: number }[];
};

type ModelRow = {
  name: string;
  engine: string;
  rank_ic: number | null;
  rank_ic_std: number | null;
  hit_rate: number | null;
  rmse: number | null;
  r2: number | null;
  train_rank_ic: number | null;
  placebo_rank_ic: number | null;
  diagnostic_warnings: string[];
  fold_count: number;
  feature_count: number;
  status: string;
};

type PersistenceStatus = {
  database_url: string;
  securities: number;
  prices: number;
  fundamentals: number;
  features: number;
  model_predictions: number;
  backtest_results: number;
};

const API_BASE = "http://127.0.0.1:8000";

const navItems = [
  { id: "overview" as const, label: "Overview", icon: Activity },
  { id: "backtests" as const, label: "Backtests", icon: LineChart },
  { id: "models" as const, label: "Models", icon: BarChart3 },
  { id: "risk" as const, label: "Risk", icon: BriefcaseBusiness },
];

function formatPercent(value: number | undefined, digits = 1) {
  if (value === undefined || Number.isNaN(value)) return "n/a";
  return `${(value * 100).toFixed(digits)}%`;
}

function formatNumber(value: number | undefined, digits = 2) {
  if (value === undefined || Number.isNaN(value)) return "n/a";
  return value.toFixed(digits);
}

function metricTone(label: string, value?: number) {
  if (value === undefined || Number.isNaN(value)) return "neutral";
  if (["Alpha", "CAGR", "Sharpe", "Info Ratio"].includes(label)) {
    return value > 0 ? "positive" : value < 0 ? "negative" : "neutral";
  }
  if (label === "Max Drawdown") return value < -0.15 ? "negative" : value < -0.08 ? "caution" : "positive";
  if (label === "Rebalance Turnover") return value > 0.5 ? "negative" : value > 0.25 ? "caution" : "positive";
  if (label === "Tracking Error") return value > 0.1 ? "caution" : "neutral";
  return "neutral";
}

function warningLabel(warning: string) {
  if (warning.includes("36 months") || warning.includes("monthly observations")) return "Short history";
  if (warning.includes("turnover")) return "High turnover";
  if (warning.includes("Train Rank IC")) return "Train/OOS gap";
  if (warning.includes("placebo")) return "Placebo check";
  if (warning.includes("Rank IC")) return "Weak signal";
  return warning.length > 28 ? `${warning.slice(0, 25)}...` : warning;
}

function modelSlug(id?: string) {
  if (!id) return "Weighted";
  if (id.includes("linear-regression")) return "Linear";
  if (id.includes("elastic-net")) return "Elastic Net";
  if (id.includes("random-forest")) return "Random Forest";
  if (id.includes("gradient-boosting")) return "Gradient Boosting";
  return "Weighted";
}

function topFactorExposure(detail?: BacktestDetail) {
  const exposures = latestFactorExposure(detail);
  if (!exposures.length) return undefined;
  return exposures.reduce((best, row) => (
    Math.abs(row.exposure) > Math.abs(best.exposure) ? row : best
  ));
}

function buildEquityCurve(returns: BacktestDetail["returns"] = []) {
  let equity = 1;
  return returns.map((row) => {
    equity *= 1 + row.return;
    return {
      date: row.date,
      equity: Number(equity.toFixed(4)),
      monthlyReturn: Number((row.return * 100).toFixed(2)),
    };
  });
}

function buildBacktestRows(detail?: BacktestDetail) {
  let strategyEquity = 1;
  let benchmarkEquity = 1;
  const benchmarkByDate = new Map((detail?.benchmark_returns || []).map((row) => [row.date, row.return]));
  const excessByDate = new Map((detail?.excess_returns || []).map((row) => [row.date, row.return]));

  return (detail?.returns || []).map((row) => {
    const benchmarkReturn = benchmarkByDate.get(row.date) || 0;
    strategyEquity *= 1 + row.return;
    benchmarkEquity *= 1 + benchmarkReturn;
    return {
      date: row.date,
      strategyEquity: Number(strategyEquity.toFixed(4)),
      benchmarkEquity: Number(benchmarkEquity.toFixed(4)),
      monthlyReturn: Number((row.return * 100).toFixed(2)),
      benchmarkReturn: Number((benchmarkReturn * 100).toFixed(2)),
      excessReturn: Number(((excessByDate.get(row.date) || 0) * 100).toFixed(2)),
    };
  });
}

function buildSectorHistory(detail?: BacktestDetail) {
  const recentDates = Array.from(new Set((detail?.sector_exposure || []).map((row) => row.date))).slice(-6);
  const sectors = Array.from(new Set((detail?.sector_exposure || []).map((row) => row.sector))).slice(0, 8);
  const rows = recentDates.map((date) => {
    const output: Record<string, string | number> = { date };
    sectors.forEach((sector) => {
      const match = detail?.sector_exposure.find((row) => row.date === date && row.sector === sector);
      output[sector] = Number(((match?.weight || 0) * 100).toFixed(1));
    });
    return output;
  });
  return { rows, sectors };
}

function latestHoldings(detail?: BacktestDetail) {
  const latestDate = detail?.holdings?.length ? detail.holdings[detail.holdings.length - 1].date : undefined;
  return (detail?.holdings || []).filter((row) => row.date === latestDate);
}

function latestSectorExposure(detail?: BacktestDetail) {
  const latestDate = detail?.sector_exposure?.length
    ? detail.sector_exposure[detail.sector_exposure.length - 1].date
    : undefined;
  return (detail?.sector_exposure || []).filter((row) => row.date === latestDate);
}

function latestFactorExposure(detail?: BacktestDetail) {
  const latestDate = detail?.factor_exposure?.length
    ? detail.factor_exposure[detail.factor_exposure.length - 1].date
    : undefined;
  return (detail?.factor_exposure || []).filter((row) => row.date === latestDate);
}

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed with ${response.status}`);
  }
  return response.json();
}

function MetricGrid({ metrics }: { metrics?: Metrics }) {
  const items = [
    { label: "CAGR", value: metrics?.cagr, display: formatPercent(metrics?.cagr) },
    { label: "SPY CAGR", value: metrics?.benchmark_cagr, display: formatPercent(metrics?.benchmark_cagr) },
    { label: "Alpha", value: metrics?.alpha, display: formatPercent(metrics?.alpha) },
    { label: "Sharpe", value: metrics?.sharpe, display: formatNumber(metrics?.sharpe) },
    { label: "Info Ratio", value: metrics?.information_ratio, display: formatNumber(metrics?.information_ratio) },
    { label: "Max Drawdown", value: metrics?.max_drawdown, display: formatPercent(metrics?.max_drawdown) },
    {
      label: "Rebalance Turnover",
      value: metrics?.average_rebalance_turnover,
      display: formatPercent(metrics?.average_rebalance_turnover, 0),
    },
    { label: "Tracking Error", value: metrics?.tracking_error, display: formatPercent(metrics?.tracking_error) },
  ];
  return (
    <section className="metrics">
      {items.map((item) => (
        <div className={`metric-card ${metricTone(item.label, item.value)}`} key={item.label}>
          <span>{item.label}</span>
          <strong>{item.display}</strong>
        </div>
      ))}
    </section>
  );
}

function StrategySummary({
  selectedBacktest,
  detail,
}: {
  selectedBacktest?: Backtest;
  detail?: BacktestDetail;
}) {
  const holdings = latestHoldings(detail);
  const topExposure = topFactorExposure(detail);
  const warnings = detail?.warnings || selectedBacktest?.warnings || [];

  return (
    <section className="strategy-summary">
      <div>
        <span>Selected Strategy</span>
        <strong>{selectedBacktest?.name || "n/a"}</strong>
      </div>
      <div>
        <span>Engine</span>
        <strong>{modelSlug(selectedBacktest?.id)}</strong>
      </div>
      <div>
        <span>Months</span>
        <strong>{selectedBacktest?.periods || 0}</strong>
      </div>
      <div>
        <span>Holdings</span>
        <strong>{holdings.length || detail?.settings?.top_n || "n/a"}</strong>
      </div>
      <div>
        <span>Top Tilt</span>
        <strong>{topExposure ? `${topExposure.factor} ${formatNumber(topExposure.exposure, 2)}` : "n/a"}</strong>
      </div>
      <div className="summary-warnings">
        {warnings.length ? warnings.slice(0, 3).map((warning) => (
          <span className="warning-chip" key={warning} title={warning}>{warningLabel(warning)}</span>
        )) : <span className="ok-chip">No warnings</span>}
      </div>
    </section>
  );
}

function OverviewView({
  rankings,
  selectedBacktest,
  detail,
}: {
  rankings: Ranking[];
  selectedBacktest?: Backtest;
  detail?: BacktestDetail;
}) {
  const factorRows = rankings.slice(0, 8).map((row) => ({
    ticker: row.ticker,
    value: Number(row.value_score.toFixed(2)),
    quality: Number(row.quality_score.toFixed(2)),
    momentum: Number(row.momentum_score.toFixed(2)),
  }));
  const holdings = latestHoldings(detail);
  const topExposure = topFactorExposure(detail);
  const latestExposure = latestSectorExposure(detail);
  const sectorCount = new Set(latestExposure.map((row) => row.sector)).size;
  const isWeightedStrategy = selectedBacktest
    ? !["linear-regression", "elastic-net", "random-forest", "gradient-boosting"].some((slug) =>
        selectedBacktest.id.includes(slug),
      )
    : true;

  return (
    <div className="panel-grid">
      <section className="panel">
        <h2>{selectedBacktest ? `${selectedBacktest.name} Holdings` : "Latest Holdings"}</h2>
        <table>
          <thead>
            <tr><th>Rank</th><th>Ticker</th><th>Sector</th><th>Weight</th></tr>
          </thead>
          <tbody>
            {(holdings.length ? holdings : rankings.map((row) => ({ ...row, weight: 0.1 }))).map((row) => (
              <tr key={`${row.ticker}-${row.rank}`}>
                <td>{row.rank}</td>
                <td>{row.ticker}</td>
                <td>{row.sector}</td>
                <td>{formatPercent(row.weight, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="panel">
        <h2>{isWeightedStrategy ? "Weighted Factor Scores" : "Selected Strategy Context"}</h2>
        {isWeightedStrategy ? (
          <div className="chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={factorRows}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="ticker" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="value" fill="#1f6f8b" />
                <Bar dataKey="quality" fill="#5f8f3e" />
                <Bar dataKey="momentum" fill="#c06c3e" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <table>
            <tbody>
              <tr><th>Strategy</th><td>{selectedBacktest?.name || "n/a"}</td></tr>
              <tr><th>Backtest Months</th><td>{selectedBacktest?.periods || 0}</td></tr>
              <tr><th>Latest Holdings</th><td>{holdings.length}</td></tr>
              <tr><th>Sector Count</th><td>{sectorCount || "n/a"}</td></tr>
              <tr><th>Top Factor Tilt</th><td>{topExposure ? `${topExposure.factor} ${formatNumber(topExposure.exposure, 2)}` : "n/a"}</td></tr>
              <tr><th>Warnings</th><td>{detail?.warnings?.length || selectedBacktest?.warnings?.length || 0}</td></tr>
              <tr><th>Avg Rebalance Turnover</th><td>{formatPercent(selectedBacktest?.metrics.average_rebalance_turnover, 1)}</td></tr>
              <tr><th>Information Ratio</th><td>{formatNumber(selectedBacktest?.metrics.information_ratio)}</td></tr>
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function BacktestsView({ backtests, detail }: { backtests: Backtest[]; detail?: BacktestDetail }) {
  const chartRows = buildBacktestRows(detail);
  const turnoverRows = (detail?.turnover || []).map((row) => ({
    date: row.date,
    turnover: Number((row.turnover * 100).toFixed(1)),
  }));
  const costRows = (detail?.costs || []).map((row) => ({
    date: row.date,
    totalCost: Number((row.total_cost * 100).toFixed(3)),
    slippage: Number((row.slippage_cost * 100).toFixed(3)),
    commission: Number((row.commission_cost * 100).toFixed(3)),
  }));
  const sectorHistory = buildSectorHistory(detail);
  const latestHoldingDate = detail?.holdings?.length ? detail.holdings[detail.holdings.length - 1].date : undefined;
  const latestHoldings = (detail?.holdings || []).filter((row) => row.date === latestHoldingDate);
  const bestInfoRatio = Math.max(...backtests.map((row) => row.metrics.information_ratio || -Infinity));
  const bestCagr = Math.max(...backtests.map((row) => row.metrics.cagr || -Infinity));

  return (
    <div className="panel-grid">
      {!!detail?.warnings?.length && (
        <section className="panel wide-panel warning-panel">
          <h2>Backtest Warnings</h2>
          <div className="chip-row">
            {detail.warnings.map((warning) => (
              <span className="warning-chip" key={warning} title={warning}>{warningLabel(warning)}</span>
            ))}
          </div>
        </section>
      )}
      <section className="panel wide-panel">
        <h2>Strategy Comparison</h2>
        <table>
          <thead>
            <tr><th>Strategy</th><th>Months</th><th>CAGR</th><th>SPY CAGR</th><th>Alpha</th><th>Sharpe</th><th>Info Ratio</th></tr>
          </thead>
          <tbody>
            {backtests.map((row) => (
              <tr className={row.id === detail?.id ? "selected-row" : ""} key={row.id}>
                <td>{row.name}</td>
                <td>{row.periods}</td>
                <td className={row.metrics.cagr === bestCagr ? "best-cell" : ""}>{formatPercent(row.metrics.cagr)}</td>
                <td>{formatPercent(row.metrics.benchmark_cagr)}</td>
                <td className={metricTone("Alpha", row.metrics.alpha)}>{formatPercent(row.metrics.alpha)}</td>
                <td>{formatNumber(row.metrics.sharpe)}</td>
                <td className={row.metrics.information_ratio === bestInfoRatio ? "best-cell" : ""}>{formatNumber(row.metrics.information_ratio)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="panel wide-panel">
        <h2>{detail?.name || "Selected Strategy"} vs SPY</h2>
        <div className="chart">
          <ResponsiveContainer width="100%" height="100%">
            <RechartsLineChart data={chartRows}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" minTickGap={28} />
              <YAxis domain={["auto", "auto"]} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="strategyEquity" name="Strategy" stroke="#1f6f8b" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="benchmarkEquity" name="SPY" stroke="#c06c3e" strokeWidth={2} dot={false} />
            </RechartsLineChart>
          </ResponsiveContainer>
        </div>
      </section>
      <section className="panel">
        <h2>Recent Excess Returns</h2>
        <div className="chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartRows.slice(-12)}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" minTickGap={24} />
              <YAxis />
              <Tooltip />
              <Bar dataKey="excessReturn" fill="#5f8f3e" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
      <section className="panel">
        <h2>Turnover by Rebalance</h2>
        <div className="chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={turnoverRows.slice(-12)}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" minTickGap={24} />
              <YAxis />
              <Tooltip />
              <Bar dataKey="turnover" fill="#1f6f8b" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
      <section className="panel">
        <h2>Rebalance Diagnostics</h2>
        <table>
          <thead>
            <tr><th>Date</th><th>Holdings</th><th>Universe</th><th>Changed</th><th>Turnover</th></tr>
          </thead>
          <tbody>
            {(detail?.rebalance_log || []).slice(-8).map((row) => (
              <tr key={row.date}>
                <td>{row.date}</td>
                <td>{row.holdings}</td>
                <td>{row.available_universe}</td>
                <td>{row.changed_positions}</td>
                <td>{formatPercent(row.turnover, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="panel wide-panel">
        <h2>Sector Exposure Over Time</h2>
        <div className="chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={sectorHistory.rows}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" />
              <YAxis />
              <Tooltip />
              <Legend />
              {sectorHistory.sectors.map((sector, index) => (
                <Bar
                  dataKey={sector}
                  fill={["#1f6f8b", "#5f8f3e", "#c06c3e", "#7d5ba6", "#d4a017", "#2f7d6d", "#9b4d4d", "#617080"][index % 8]}
                  key={sector}
                  stackId="sector"
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
      <section className="panel wide-panel">
        <h2>Latest Strategy Holdings</h2>
        <table>
          <thead>
            <tr><th>Ticker</th><th>Sector</th><th>Rank</th><th>Weight</th></tr>
          </thead>
          <tbody>
            {latestHoldings.map((row) => (
              <tr key={`${row.date}-${row.ticker}`}>
                <td>{row.ticker}</td>
                <td>{row.sector}</td>
                <td>{row.rank}</td>
                <td>{formatPercent(row.weight, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="panel">
        <h2>Return Table</h2>
        <table>
          <thead>
            <tr><th>Date</th><th>Strategy</th><th>SPY</th><th>Excess</th></tr>
          </thead>
          <tbody>
            {chartRows.slice(-8).map((row) => (
              <tr key={row.date}>
                <td>{row.date}</td>
                <td>{formatPercent(row.monthlyReturn / 100)}</td>
                <td>{formatPercent(row.benchmarkReturn / 100)}</td>
                <td>{formatPercent(row.excessReturn / 100)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="panel">
        <h2>Cost Table</h2>
        <table>
          <thead>
            <tr><th>Date</th><th>Total Cost</th><th>Slippage</th><th>Commission</th></tr>
          </thead>
          <tbody>
            {costRows.slice(-8).map((row) => (
              <tr key={row.date}>
                <td>{row.date}</td>
                <td>{formatPercent(row.totalCost / 100, 3)}</td>
                <td>{formatPercent(row.slippage / 100, 3)}</td>
                <td>{formatPercent(row.commission / 100, 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function ModelsView({ models }: { models: ModelRow[] }) {
  const bestRankIc = Math.max(...models.map((model) => model.rank_ic ?? -Infinity));
  const diagnostics = models.filter((model) => model.diagnostic_warnings?.length);

  return (
    <div className="panel-grid">
      <section className="panel wide-panel">
        <h2>Model Comparison</h2>
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>Engine</th>
              <th>Rank IC</th>
              <th>Train IC</th>
              <th>Placebo IC</th>
              <th>Hit Rate</th>
              <th>RMSE</th>
              <th>Folds</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {models.map((model) => (
              <tr key={model.name}>
                <td>{model.name}</td>
                <td>{model.engine}</td>
                <td className={model.rank_ic === bestRankIc ? "best-cell" : ""}>{model.rank_ic === null ? "n/a" : formatNumber(model.rank_ic, 3)}</td>
                <td>{model.train_rank_ic === null ? "n/a" : formatNumber(model.train_rank_ic, 3)}</td>
                <td>{model.placebo_rank_ic === null ? "n/a" : formatNumber(model.placebo_rank_ic, 3)}</td>
                <td>{model.hit_rate === null ? "n/a" : formatPercent(model.hit_rate)}</td>
                <td>{model.rmse === null ? "n/a" : formatNumber(model.rmse, 4)}</td>
                <td>{model.fold_count}</td>
                <td><span className="status-pill">{model.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="panel wide-panel">
        <h2>Model Diagnostics</h2>
        <div className="diagnostic-list">
          {diagnostics.length ? diagnostics.map((model) => (
            <div className="diagnostic-row" key={model.name}>
              <strong>{model.name}</strong>
              <div className="chip-row">
                {model.diagnostic_warnings.map((warning) => (
                  <span className="warning-chip" key={warning} title={warning}>{warningLabel(warning)}</span>
                ))}
              </div>
            </div>
          )) : <span className="ok-chip">No model diagnostics triggered</span>}
        </div>
      </section>
    </div>
  );
}

function RiskView({
  portfolio,
  selectedBacktest,
  detail,
}: {
  portfolio?: Portfolio;
  selectedBacktest?: Backtest;
  detail?: BacktestDetail;
}) {
  const strategyExposure = latestSectorExposure(detail);
  const factorExposure = latestFactorExposure(detail);
  const strategyHoldings = latestHoldings(detail);
  const exposureSource = strategyExposure.length ? strategyExposure : (portfolio?.sector_exposure || []);
  const positionSource = strategyHoldings.length ? strategyHoldings : (portfolio?.positions || []);
  const exposureRows = exposureSource.map((row) => ({
    sector: row.sector,
    exposure: Number((row.weight * 100).toFixed(1)),
  })).sort((a, b) => b.exposure - a.exposure);
  const factorRows = factorExposure
    .map((row) => ({ factor: row.factor, exposure: Number(row.exposure.toFixed(2)) }))
    .sort((a, b) => Math.abs(b.exposure) - Math.abs(a.exposure));
  const maxSectorExposure = Math.max(...exposureRows.map((row) => row.exposure), 1);
  const maxFactorExposure = Math.max(...factorRows.map((row) => Math.abs(row.exposure)), 1);

  return (
    <div className="panel-grid">
      <section className="panel wide-panel">
        <h2>{selectedBacktest ? `${selectedBacktest.name} Sector Exposure` : "Sector Exposure"}</h2>
        <div className="bar-list">
          {exposureRows.map((row) => (
            <div className="bar-row" key={row.sector}>
              <span>{row.sector}</span>
              <div><i style={{ width: `${(row.exposure / maxSectorExposure) * 100}%` }} /></div>
              <strong>{row.exposure.toFixed(1)}%</strong>
            </div>
          ))}
        </div>
      </section>
      <section className="panel">
        <h2>{selectedBacktest ? "Latest Factor Exposures" : "Factor Exposures"}</h2>
        <div className="factor-bars">
          {factorRows.map((row) => {
            const offset = row.exposure < 0 ? 50 - (Math.abs(row.exposure) / maxFactorExposure) * 50 : 50;
            const width = (Math.abs(row.exposure) / maxFactorExposure) * 50;
            return (
              <div className="factor-row" key={row.factor}>
                <span>{row.factor}</span>
                <div><i className={row.exposure < 0 ? "negative-bar" : ""} style={{ left: `${offset}%`, width: `${width}%` }} /></div>
                <strong>{formatNumber(row.exposure, 2)}</strong>
              </div>
            );
          })}
        </div>
      </section>
      <section className="panel">
        <h2>{selectedBacktest ? "Selected Strategy Positions" : "Latest Positions"}</h2>
        <table>
          <thead>
            <tr><th>Ticker</th><th>Sector</th><th>Weight</th><th>Rank</th></tr>
          </thead>
          <tbody>
            {positionSource.map((row) => (
              <tr key={row.ticker}>
                <td>{row.ticker}</td>
                <td>{row.sector}</td>
                <td>{formatPercent(row.weight, 1)}</td>
                <td>{row.rank}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function App() {
  const [view, setView] = useState<View>("overview");
  const [source, setSource] = useState<DataSource>("yfinance");
  const [rankings, setRankings] = useState<Ranking[]>([]);
  const [backtests, setBacktests] = useState<Backtest[]>([]);
  const [selectedBacktestId, setSelectedBacktestId] = useState<string | undefined>();
  const [backtestDetail, setBacktestDetail] = useState<BacktestDetail | undefined>();
  const [portfolio, setPortfolio] = useState<Portfolio | undefined>();
  const [models, setModels] = useState<ModelRow[]>([]);
  const [persistence, setPersistence] = useState<PersistenceStatus | undefined>();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const titles = {
    overview: "Latest Stock Rankings",
    backtests: "Backtest Analytics",
    models: "Ranking Models",
    risk: "Portfolio Risk",
  };

  const loadDashboard = async () => {
    setIsLoading(true);
    setError(undefined);
    const requests = [
      {
        label: "rankings",
        load: () => fetchJson<{ rankings: Ranking[] }>(`/rankings/latest?source=${source}&limit=10`),
        apply: (response: { rankings: Ranking[] }) => setRankings(response.rankings),
      },
      {
        label: "backtests",
        load: () => fetchJson<Backtest[]>(`/backtests?source=${source}`),
        apply: (response: Backtest[]) => {
          setBacktests(response);
          setSelectedBacktestId((current) => (
            response.some((row) => row.id === current) ? current : response[0]?.id
          ));
          setBacktestDetail(undefined);
        },
      },
      {
        label: "portfolio",
        load: () => fetchJson<Portfolio>(`/portfolio/latest?source=${source}&limit=10`),
        apply: (response: Portfolio) => setPortfolio(response),
      },
      {
        label: "models",
        load: () => fetchJson<{ models: ModelRow[] }>(`/models?source=${source}`),
        apply: (response: { models: ModelRow[] }) => setModels(response.models),
      },
      {
        label: "persistence",
        load: () => fetchJson<PersistenceStatus>("/persistence/status"),
        apply: (response: PersistenceStatus) => setPersistence(response),
      },
    ] as const;

    const results = await Promise.allSettled(
      requests.map(async (request) => ({
        label: request.label,
        value: await request.load(),
      })),
    );

    const failures: string[] = [];
    results.forEach((result, index) => {
      if (result.status === "fulfilled") {
        requests[index].apply(result.value.value as never);
      } else {
        const reason = result.reason instanceof Error ? result.reason.message : "request failed";
        failures.push(`${requests[index].label}: ${reason}`);
      }
    });

    if (failures.length) {
      setError(`Some dashboard data could not load. ${failures.join(" | ")}`);
    }
    setIsLoading(false);
  };

  const persistSnapshot = async () => {
    setIsLoading(true);
    setError(undefined);
    try {
      await fetchJson(`/persistence/snapshot?source=${source}`, { method: "POST" });
      const status = await fetchJson<PersistenceStatus>("/persistence/status");
      setPersistence(status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to persist snapshot");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadDashboard();
  }, [source]);

  useEffect(() => {
    if (!selectedBacktestId) return;

    let cancelled = false;
    const loadSelectedBacktest = async () => {
      setError(undefined);
      try {
        const detail = await fetchJson<BacktestDetail>(`/backtests/${selectedBacktestId}?source=${source}`);
        if (!cancelled) {
          setBacktestDetail(detail);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unable to load selected strategy");
        }
      }
    };

    loadSelectedBacktest();
    return () => {
      cancelled = true;
    };
  }, [source, selectedBacktestId]);

  const selectedBacktest = useMemo(
    () => backtests.find((row) => row.id === selectedBacktestId) || backtests[0],
    [backtests, selectedBacktestId],
  );
  const metrics = useMemo(
    () => backtestDetail?.metrics || selectedBacktest?.metrics,
    [selectedBacktest, backtestDetail],
  );

  const runBacktest = async () => {
    setIsLoading(true);
    setError(undefined);
    try {
      const id = selectedBacktestId || selectedBacktest?.id || `${source}-top-10`;
      const detail = await fetchJson<BacktestDetail>(`/backtests/${id}?source=${source}`);
      setBacktestDetail(detail);
      setView("backtests");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to run backtest");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">Multifactor</div>
        <nav>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={view === item.id ? "active" : ""}
                key={item.id}
                onClick={() => setView(item.id)}
                type="button"
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>
      <section className="content">
        <header>
          <div>
            <p className="eyebrow">{source} data source</p>
            <h1>{titles[view]}</h1>
          </div>
          <div className="toolbar">
            <select value={source} onChange={(event) => setSource(event.target.value as DataSource)}>
              <option value="yfinance">yfinance</option>
              <option value="sample">sample</option>
            </select>
            <select
              value={selectedBacktestId || ""}
              onChange={(event) => {
                setSelectedBacktestId(event.target.value);
                setBacktestDetail(undefined);
              }}
            >
              {backtests.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
            <button className="icon-action" onClick={loadDashboard} type="button" aria-label="Refresh dashboard">
              <RefreshCw size={18} />
            </button>
            <button className="icon-action" onClick={persistSnapshot} type="button" aria-label="Persist snapshot">
              <Database size={18} />
            </button>
            <button className="primary-action" onClick={runBacktest} type="button">
              {isLoading ? "Loading" : "Run Backtest"}
            </button>
          </div>
        </header>
        {error && <div className="error-banner">{error}</div>}
        {persistence && (
          <div className="db-strip">
            <span>{persistence.prices.toLocaleString()} prices</span>
            <span>{persistence.features.toLocaleString()} features</span>
            <span>{persistence.model_predictions.toLocaleString()} predictions</span>
            <span>{persistence.backtest_results.toLocaleString()} backtests</span>
          </div>
        )}
        <StrategySummary selectedBacktest={selectedBacktest} detail={backtestDetail} />
        <MetricGrid metrics={metrics} />
        {view === "overview" && (
          <OverviewView rankings={rankings} selectedBacktest={selectedBacktest} detail={backtestDetail} />
        )}
        {view === "backtests" && <BacktestsView backtests={backtests} detail={backtestDetail} />}
        {view === "models" && <ModelsView models={models} />}
        {view === "risk" && (
          <RiskView portfolio={portfolio} selectedBacktest={selectedBacktest} detail={backtestDetail} />
        )}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
