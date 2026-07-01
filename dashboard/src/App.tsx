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
  benchmark_cagr: number;
  alpha: number;
  tracking_error: number;
  information_ratio: number;
};

type Backtest = {
  id: string;
  name: string;
  metrics: Metrics;
};

type BacktestDetail = Backtest & {
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
  rebalance_log: {
    date: string;
    signal_date: string;
    trade_date: string;
    next_trade_date: string;
    holdings: number;
  }[];
};

type Portfolio = {
  date: string;
  positions: { ticker: string; sector: string; rank: number; weight: number; composite_score: number }[];
  sector_exposure: { sector: string; weight: number }[];
};

type ModelRow = {
  name: string;
  rank_ic: number | null;
  sharpe: number | null;
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

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed with ${response.status}`);
  }
  return response.json();
}

function MetricGrid({ metrics }: { metrics?: Metrics }) {
  return (
    <section className="metrics">
      <div><span>CAGR</span><strong>{formatPercent(metrics?.cagr)}</strong></div>
      <div><span>SPY CAGR</span><strong>{formatPercent(metrics?.benchmark_cagr)}</strong></div>
      <div><span>Alpha</span><strong>{formatPercent(metrics?.alpha)}</strong></div>
      <div><span>Sharpe</span><strong>{formatNumber(metrics?.sharpe)}</strong></div>
      <div><span>Info Ratio</span><strong>{formatNumber(metrics?.information_ratio)}</strong></div>
      <div><span>Max Drawdown</span><strong>{formatPercent(metrics?.max_drawdown)}</strong></div>
      <div><span>Turnover</span><strong>{formatPercent(metrics?.average_turnover, 0)}</strong></div>
      <div><span>Tracking Error</span><strong>{formatPercent(metrics?.tracking_error)}</strong></div>
    </section>
  );
}

function RankingsTable({ rankings }: { rankings: Ranking[] }) {
  const factorRows = rankings.slice(0, 8).map((row) => ({
    ticker: row.ticker,
    value: Number(row.value_score.toFixed(2)),
    quality: Number(row.quality_score.toFixed(2)),
    momentum: Number(row.momentum_score.toFixed(2)),
  }));

  return (
    <div className="panel-grid">
      <section className="panel">
        <h2>Top Ranked Names</h2>
        <table>
          <thead>
            <tr><th>Rank</th><th>Ticker</th><th>Sector</th><th>Score</th></tr>
          </thead>
          <tbody>
            {rankings.map((row) => (
              <tr key={row.ticker}>
                <td>{row.rank}</td>
                <td>{row.ticker}</td>
                <td>{row.sector}</td>
                <td>{formatNumber(row.composite_score)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="panel">
        <h2>Factor Scores</h2>
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
      </section>
    </div>
  );
}

function BacktestsView({ detail }: { detail?: BacktestDetail }) {
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

  return (
    <div className="panel-grid">
      <section className="panel wide-panel">
        <h2>Strategy vs SPY</h2>
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
  return (
    <section className="panel">
      <h2>Model Comparison</h2>
      <table>
        <thead>
          <tr><th>Model</th><th>Rank IC</th><th>Sharpe</th><th>Status</th></tr>
        </thead>
        <tbody>
          {models.map((model) => (
            <tr key={model.name}>
              <td>{model.name}</td>
              <td>{model.rank_ic === null ? "n/a" : formatNumber(model.rank_ic, 3)}</td>
              <td>{model.sharpe === null ? "n/a" : formatNumber(model.sharpe)}</td>
              <td><span className="status-pill">{model.status}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function RiskView({ portfolio }: { portfolio?: Portfolio }) {
  const exposureRows = (portfolio?.sector_exposure || []).map((row) => ({
    sector: row.sector,
    exposure: Number((row.weight * 100).toFixed(1)),
  }));

  return (
    <div className="panel-grid">
      <section className="panel wide-panel">
        <h2>Sector Exposure</h2>
        <div className="chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={exposureRows} layout="vertical" margin={{ left: 120 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" />
              <YAxis dataKey="sector" type="category" width={120} />
              <Tooltip />
              <Bar dataKey="exposure" fill="#1f6f8b" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
      <section className="panel">
        <h2>Latest Positions</h2>
        <table>
          <thead>
            <tr><th>Ticker</th><th>Weight</th><th>Rank</th></tr>
          </thead>
          <tbody>
            {(portfolio?.positions || []).map((row) => (
              <tr key={row.ticker}>
                <td>{row.ticker}</td>
                <td>{formatPercent(row.weight, 0)}</td>
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
  const [backtest, setBacktest] = useState<Backtest | undefined>();
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
    try {
      const [
        rankingResponse,
        backtestResponse,
        portfolioResponse,
        modelResponse,
        persistenceResponse,
      ] = await Promise.all([
        fetchJson<{ rankings: Ranking[] }>(`/rankings/latest?source=${source}&limit=10`),
        fetchJson<Backtest[]>(`/backtests?source=${source}`),
        fetchJson<Portfolio>(`/portfolio/latest?source=${source}&limit=10`),
        fetchJson<{ models: ModelRow[] }>(`/models?source=${source}`),
        fetchJson<PersistenceStatus>("/persistence/status"),
      ]);

      setRankings(rankingResponse.rankings);
      setBacktest(backtestResponse[0]);
      setPortfolio(portfolioResponse);
      setModels(modelResponse.models);
      setPersistence(persistenceResponse);
      setBacktestDetail(undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load dashboard data");
    } finally {
      setIsLoading(false);
    }
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

  const metrics = useMemo(() => backtestDetail?.metrics || backtest?.metrics, [backtest, backtestDetail]);

  const runBacktest = async () => {
    setIsLoading(true);
    setError(undefined);
    try {
      const detail = await fetchJson<BacktestDetail>(`/backtests/${source}-top-10?source=${source}`);
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
        <MetricGrid metrics={metrics} />
        {view === "overview" && <RankingsTable rankings={rankings} />}
        {view === "backtests" && <BacktestsView detail={backtestDetail} />}
        {view === "models" && <ModelsView models={models} />}
        {view === "risk" && <RiskView portfolio={portfolio} />}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
