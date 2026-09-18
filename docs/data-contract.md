# Free data stack and point-in-time import contract

## Project constraint: $0 data spend

The selected direction is **SimFin free fundamentals + Tiingo Starter EOD prices**.
There is no paid-provider dependency, automatic upgrade, or paid fallback. Provider
credentials have not been supplied. A cached Tiingo downloader and local SimFin
statement converter are implemented and tested offline; live data remains unverified.

Verified September 15, 2026 from primary documentation:

- [SimFin free plan](https://www.simfin.com/en/prices/): five years of fundamentals,
  API/bulk download. This is shorter than the historical coverage advertised for
  paid plans. Warmup, training, and held-out evaluation further reduce usable history.
- [Tiingo Starter](https://www.tiingo.com/about/pricing): 500 unique symbols/month,
  50 requests/hour, 1,000 requests/day, and 1 GB/month. A download scheduler must
  account for usage outside this project too; cache full histories and refresh only
  when necessary. These limits include the benchmark and historical/delisted symbols,
  not just current holdings. Do not select today's survivors to fit a symbol quota.
- [SimFin's field definitions](https://raw.githubusercontent.com/SimFin/simfin/master/simfin/names.py):
  bulk financial values represent the latest restatement; `Restated Date` is the
  latest revision date. `Publish Date` is the original publication date. Using
  current values from the original publication date can leak later revisions.
- [Tiingo EOD documentation](https://www.tiingo.com/documentation/end-of-day): keep
  raw prices/volume separate from `adjClose`, which is used for total returns.

The adapter `annotate_simfin_availability` conservatively admits a supplied value
after the later publication/restatement day (New York time). This is reconstructed
public availability, **not historical free-feed delivery time**, and cannot recover
missing prior versions. SimFin's free download cadence is also slower than its
paid/live offering. Preserve every downloaded vintage going forward.

The free stack does not automatically provide a complete historical universe or
an audited security crosswalk. Neither an intersection of today's vendor catalogs
nor current sector metadata establishes historical eligibility. Membership events
remain a separate required input. Delisting payouts and raw corporate-action
accounting remain unfinished in the simulator.

Tiingo EOD does not supply the daily market cap needed by this contract. Obtain
historically dated share/market-cap data and reconcile split bases before producing
that field. SimFin's weighted-average, split-adjusted shares are not interchangeable
with contemporaneous raw shares. `normalize_tiingo_eod` deliberately requires daily
market cap and session cutoffs as separate metadata.

## What the importer accepts

A folder with `manifest.json`, `prices.csv`, `fundamentals.csv`, `membership.csv`.
These are **normalized contract files**, not untouched SimFin/Tiingo exports. There
is not yet a complete automatic SimFin statement-to-TTM adapter. A sample export
must establish the available columns, periods, units, and revision treatment first.

All accounting amounts are USD **units**, not millions. Identity is `security_id`.
The current ticker-based engine requires one stable canonical symbol per security
and rejects symbol reuse/changes; resolve aliases with an explicit crosswalk first.

Common row fields: `security_id`, `source`, `retrieved_at`.
All timestamps require an explicit UTC offset; session/period dates use YYYY-MM-DD.

### Prices

Additional fields:

` ticker, date, decision_at, open, high, low, close, adj_close, volume, market_cap `

- One observation per security/session, plus one SPY benchmark series.
- `decision_at` is the documented signal-information cutoff, shared across the
  session's securities and belonging to that New York session date. Include early
  closes correctly; the importer does not supply an exchange calendar.
- OHLC and volume use a consistent raw basis. Adjusted close is total return.
- Market cap is historical and contemporaneous, not today's capitalization copied
  backward. SPY does not need market cap.
- Keep prices for exiting securities so existing holdings can still be valued.

### Fundamentals

Additional fields:

` fiscal_period_end, published_at, available_at, revision_id, net_income_ttm,
free_cash_flow_ttm, book_equity, average_book_equity, gross_profit_ttm,
revenue_ttm, total_debt, earnings_stability `

- Every row is a complete reported financial state for the indicated latest fiscal
  period: TTM flow fields, current balance sheet, and average equity over the ROE
  measurement period. Annual and quarterly flows must not be accidentally mixed.
- `available_at >= published_at >= fiscal_period_end`.
- Preserve revisions as new rows. Ambiguous same-period/same-availability records
  are rejected. An old-period amendment cannot replace an already-known newer
  fiscal state. A correction affecting a newer TTM state must explicitly supply
  that corrected newer state and its own availability timestamp.
- `earnings_stability` must be calculated from then-available observations and its
  formula documented in the manifest. Do not insert the demo's constant placeholder.
- Missing values remain missing. Complete-case filtering currently excludes them.
  Negative earnings/equity make the corresponding valuation ratio unavailable.
- Financial states older than 550 calendar days from their fiscal endpoint expire.
  This is a conservative initial research policy, not a universal filing rule.

### Membership

Additional fields:

` effective_date, available_at, eligible, sector `

- `eligible` is `true` or `false`. Rows describe entry, exit, and sector-state changes.
- Apply an event only when BOTH its effective date and availability timestamp have
  arrived. No known state means no eligibility. Future announcements do not apply early.
- Each event is a complete membership/sector state. Prior-effective-date corrections
  do not supersede a newer effective state.
- Every nonbenchmark ID in prices must have fundamental and membership records;
  coverage mismatches are rejected instead of silently losing securities.
- Normalization occurs only after historical eligibility and complete-feature checks.
  Retained price histories compute return lookbacks and exact-calendar 21-session
  target endpoints before this filter, including returns after universe exit.

### Manifest

```json
{
  "schema_version": 1,
  "currency": "USD",
  "provider": "SimFin free + Tiingo Starter (normalized exports)",
  "availability_policy": "Describe publication, restatement, timestamp precision and delivery assumptions",
  "universe_policy": "Describe historical selection rules and evidence for membership events",
  "corporate_action_policy": "Describe price adjustment, shares alignment and delisting coverage",
  "earnings_stability_definition": "Describe the historical calculation and required observations"
}
```

Passing validation proves schema and temporal consistency, not vendor correctness,
survivorship-free coverage, or investability. Coverage exclusions are stored in
feature-frame metadata. The generic data-quality report retains an explicit warning.

## Run a fictitious end-to-end example

Use a new directory; the example command refuses to overwrite an existing one:

```bash
python -m multifactor_platform.jobs.import_point_in_time data/external/pit-example --example
# Set the exact immutable path returned above:
export MFP_POINT_IN_TIME_DATASET="/absolute/path/to/data/processed/research/datasets/<dataset-id>"
python -m multifactor_platform.jobs.run_backtest --source point_in_time --top-n 2
```

For actual normalized exports, omit `--example`. Restart the API after changing the
dataset setting; its comparison cache is process-local. Select **Point-in-time import**
in the dashboard. The configured dataset is content-addressed and verified on load.

The legacy SQLite snapshot endpoint is deliberately unavailable for this source:
its schema would discard publication/revision histories. Research runs and normalized
input packets use immutable archives instead. Frozen-prediction replay remains supported.

## Free-provider conversion and download

Convert **discrete quarterly**, semicolon-separated SimFin income, balance and
cashflow exports. Annual, TTM and YTD flows must not be substituted. Supply a comma-separated
crosswalk with `SimFinId,security_id,ticker,tiingo_symbol`; each identifier must be unique.
Select one primary security per company explicitly. No ticker aliases are inferred.

```bash
python -m multifactor_platform.jobs.convert_simfin \
  --income /path/us-income-quarterly.csv \
  --balance /path/us-balance-quarterly.csv \
  --cashflow /path/us-cashflow-quarterly.csv \
  --crosswalk /path/crosswalk.csv \
  --retrieved-at 2026-09-15T18:00:00Z \
  --output data/external/simfin-vintage-20260915
```

Use the actual retrieval timestamp. The output includes normalized `fundamentals.csv`,
contributing-row provenance, a coverage/formula report, and copies plus hashes of raw inputs.
Existing output directories are rejected. Eight consecutive income quarters are required;
TTM flows use four quarters, ROE equity averages endpoints one year apart, and earnings
stability is negative population standard deviation of eight quarterly net margins.
Free cash flow adds operating cash flow to the **signed** change in fixed assets and
intangibles. Missing observations produce coverage exclusions, never zero-filled values.
Late amendments trigger recomputation of the latest complete state at their availability date.
Bulk exports may omit original vintages: conservative reconstruction cannot recover them.

Set `TIINGO_API_KEY` in your local process environment (do not commit or paste the token).

```bash
python -m multifactor_platform.jobs.download_tiingo \
  --symbols SPY AAPL MSFT --start-date 2022-01-01 --end-date 2025-12-31 \
  --cache-dir data/external/tiingo
```

Each completed symbol prints a JSON receipt. Raw responses and retrieval receipts are
retained by hash. Exact repeat requests use the cache; `--refresh` obtains and preserves
a new vintage. Requests stop on errors or budget exhaustion without automatic retries.
The SQLite ledger enforces conservative free-tier request, symbol and bandwidth budgets;
it reserves a bounded response allowance before sending a request. Rate-limit responses
pause requests for an hour. Use the same `--usage-db` for every client sharing an account.
**The ledger cannot see usage from other tools**, so leave account headroom. No paid fallback
is implemented. Re-run after the budget resets to resume using completed cached responses.

Before importing a real packet, provide historical membership/sector events and independent
session metadata (`date,decision_at,market_cap`) to `normalize_tiingo_eod`. SimFin weighted-average,
split-adjusted shares are not a substitute for historical outstanding shares aligned with raw
Tiingo close. Copy the converted fundamentals into the normalized packet described above.
The adapters are tested offline; actual vendor exports, account access and an end-to-end
real-data run still need validation. Surviving-symbol downloads alone do not establish
survivorship-free universe or delisting coverage.
