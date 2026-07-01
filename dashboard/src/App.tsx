import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, BarChart3, BriefcaseBusiness, LineChart, RefreshCw } from "lucide-react";
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
};

type Backtest = {
  id: string;
  name: string;
  metrics: Metrics;
};

type BacktestDetail = Backtest & {
  returns: { date: string; return: number }[];
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

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
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
      <div><span>Sharpe</span><strong>{formatNumber(metrics?.sharpe)}</strong></div>
      <div><span>Max Drawdown</span><strong>{formatPercent(metrics?.max_drawdown)}</strong></div>
      <div><span>Turnover</span><strong>{formatPercent(metrics?.average_turnover, 0)}</strong></div>
    </section>
  );
}

function RankingsTable({ rankings }: { rankings: Ranking[] }) {
  return (
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
  );
}

function BacktestsView({ detail }: { detail?: BacktestDetail }) {
  return (
    <section className="panel">
      <h2>Backtest Returns</h2>
      <table>
        <thead>
          <tr><th>Date</th><th>Monthly Return</th></tr>
        </thead>
        <tbody>
          {(detail?.returns || []).slice(-12).map((row) => (
            <tr key={row.date}>
              <td>{row.date}</td>
              <td>{formatPercent(row.return)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
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
  return (
    <section className="panel">
      <h2>Sector Exposure</h2>
      <table>
        <thead>
          <tr><th>Sector</th><th>Exposure</th><th>Limit</th></tr>
        </thead>
        <tbody>
          {(portfolio?.sector_exposure || []).map((row) => (
            <tr key={row.sector}>
              <td>{row.sector}</td>
              <td>{formatPercent(row.weight, 0)}</td>
              <td>25%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
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
      const [rankingResponse, backtestResponse, portfolioResponse, modelResponse] = await Promise.all([
        fetchJson<{ rankings: Ranking[] }>(`/rankings/latest?source=${source}&limit=10`),
        fetchJson<Backtest[]>(`/backtests?source=${source}`),
        fetchJson<Portfolio>(`/portfolio/latest?source=${source}&limit=10`),
        fetchJson<{ models: ModelRow[] }>(`/models?source=${source}`),
      ]);

      setRankings(rankingResponse.rankings);
      setBacktest(backtestResponse[0]);
      setPortfolio(portfolioResponse);
      setModels(modelResponse.models);
      setBacktestDetail(undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load dashboard data");
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
            <button className="primary-action" onClick={runBacktest} type="button">
              {isLoading ? "Loading" : "Run Backtest"}
            </button>
          </div>
        </header>
        {error && <div className="error-banner">{error}</div>}
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
