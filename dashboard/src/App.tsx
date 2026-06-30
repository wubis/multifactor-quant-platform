import React from "react";
import { createRoot } from "react-dom/client";
import { Activity, BarChart3, BriefcaseBusiness, LineChart } from "lucide-react";
import "./styles.css";

const sampleRankings = [
  { ticker: "MSFT", sector: "Information Technology", rank: 1, score: 1.42 },
  { ticker: "LLY", sector: "Health Care", rank: 2, score: 1.18 },
  { ticker: "JPM", sector: "Financials", rank: 3, score: 0.97 },
  { ticker: "COST", sector: "Consumer Staples", rank: 4, score: 0.86 },
];

function App() {
  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">Multifactor</div>
        <nav>
          <a className="active"><Activity size={18} /> Overview</a>
          <a><LineChart size={18} /> Backtests</a>
          <a><BarChart3 size={18} /> Models</a>
          <a><BriefcaseBusiness size={18} /> Risk</a>
        </nav>
      </aside>
      <section className="content">
        <header>
          <div>
            <p className="eyebrow">Monthly rebalance</p>
            <h1>Latest Stock Rankings</h1>
          </div>
          <button>Run Backtest</button>
        </header>
        <section className="metrics">
          <div><span>CAGR</span><strong>12.4%</strong></div>
          <div><span>Sharpe</span><strong>0.91</strong></div>
          <div><span>Max Drawdown</span><strong>-14.8%</strong></div>
          <div><span>Turnover</span><strong>28%</strong></div>
        </section>
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
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
