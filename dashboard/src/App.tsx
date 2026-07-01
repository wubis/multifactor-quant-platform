import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, BarChart3, BriefcaseBusiness, LineChart } from "lucide-react";
import "./styles.css";

type View = "overview" | "backtests" | "models" | "risk";

const navItems = [
  { id: "overview" as const, label: "Overview", icon: Activity },
  { id: "backtests" as const, label: "Backtests", icon: LineChart },
  { id: "models" as const, label: "Models", icon: BarChart3 },
  { id: "risk" as const, label: "Risk", icon: BriefcaseBusiness },
];

const sampleRankings = [
  { ticker: "MSFT", sector: "Information Technology", rank: 1, score: 1.42 },
  { ticker: "LLY", sector: "Health Care", rank: 2, score: 1.18 },
  { ticker: "JPM", sector: "Financials", rank: 3, score: 0.97 },
  { ticker: "COST", sector: "Consumer Staples", rank: 4, score: 0.86 },
];

const baseMetrics = {
  cagr: "12.4%",
  sharpe: "0.91",
  drawdown: "-14.8%",
  turnover: "28%",
};

const refreshedMetrics = {
  cagr: "13.1%",
  sharpe: "1.05",
  drawdown: "-12.9%",
  turnover: "30%",
};

function MetricGrid({ metrics }: { metrics: typeof baseMetrics }) {
  return (
    <section className="metrics">
      <div><span>CAGR</span><strong>{metrics.cagr}</strong></div>
      <div><span>Sharpe</span><strong>{metrics.sharpe}</strong></div>
      <div><span>Max Drawdown</span><strong>{metrics.drawdown}</strong></div>
      <div><span>Turnover</span><strong>{metrics.turnover}</strong></div>
    </section>
  );
}

function RankingsTable() {
  return (
    <section className="panel">
      <h2>Top Ranked Names</h2>
      <table>
        <thead>
          <tr><th>Rank</th><th>Ticker</th><th>Sector</th><th>Score</th></tr>
        </thead>
        <tbody>
          {sampleRankings.map((row) => (
            <tr key={row.ticker}>
              <td>{row.rank}</td>
              <td>{row.ticker}</td>
              <td>{row.sector}</td>
              <td>{row.score.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function BacktestsView() {
  const monthlyReturns = [
    { month: "Jan", value: "2.4%" },
    { month: "Feb", value: "-1.1%" },
    { month: "Mar", value: "3.2%" },
    { month: "Apr", value: "0.8%" },
    { month: "May", value: "1.7%" },
  ];

  return (
    <section className="panel">
      <h2>Backtest Results</h2>
      <table>
        <thead>
          <tr><th>Month</th><th>Portfolio Return</th><th>Benchmark Return</th></tr>
        </thead>
        <tbody>
          {monthlyReturns.map((row, index) => (
            <tr key={row.month}>
              <td>{row.month}</td>
              <td>{row.value}</td>
              <td>{["1.9%", "-0.4%", "2.1%", "0.5%", "1.2%"][index]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function ModelsView() {
  const models = [
    { name: "Weighted Score", ic: "0.041", sharpe: "1.05", status: "Active" },
    { name: "Elastic Net", ic: "0.035", sharpe: "0.88", status: "Research" },
    { name: "XGBoost", ic: "0.049", sharpe: "1.12", status: "Planned" },
  ];

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
              <td>{model.ic}</td>
              <td>{model.sharpe}</td>
              <td><span className="status-pill">{model.status}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function RiskView() {
  const exposures = [
    { sector: "Information Technology", exposure: "24%" },
    { sector: "Health Care", exposure: "18%" },
    { sector: "Financials", exposure: "17%" },
    { sector: "Consumer Staples", exposure: "11%" },
  ];

  return (
    <section className="panel">
      <h2>Risk Exposure</h2>
      <table>
        <thead>
          <tr><th>Sector</th><th>Exposure</th><th>Limit</th></tr>
        </thead>
        <tbody>
          {exposures.map((row) => (
            <tr key={row.sector}>
              <td>{row.sector}</td>
              <td>{row.exposure}</td>
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
  const [hasRunBacktest, setHasRunBacktest] = useState(false);
  const metrics = hasRunBacktest ? refreshedMetrics : baseMetrics;

  const titles = {
    overview: "Latest Stock Rankings",
    backtests: "Backtest Analytics",
    models: "Ranking Models",
    risk: "Portfolio Risk",
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
            <p className="eyebrow">Monthly rebalance</p>
            <h1>{titles[view]}</h1>
          </div>
          <button className="primary-action" onClick={() => setHasRunBacktest(true)} type="button">
            {hasRunBacktest ? "Backtest Updated" : "Run Backtest"}
          </button>
        </header>
        <MetricGrid metrics={metrics} />
        {view === "overview" && <RankingsTable />}
        {view === "backtests" && <BacktestsView />}
        {view === "models" && <ModelsView />}
        {view === "risk" && <RiskView />}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
