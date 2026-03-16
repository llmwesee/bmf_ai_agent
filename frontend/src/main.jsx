import React, { startTransition, useDeferredValue, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const percentage = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 0,
});

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed for ${url}`);
  }
  return response.json();
}

function SummaryCard({ label, value, note }) {
  return (
    <article className="summary-card">
      <p className="label">{label}</p>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}

function AlertCard({ alert, onDraft }) {
  return (
    <article className="alert-card">
      <div className="alert-card-header">
        <div>
          <h3>{alert.title}</h3>
          <p>{alert.message}</p>
          <small>
            {alert.account_name} · {alert.project_code}
          </small>
        </div>
        <span className={`severity-pill ${alert.severity.toLowerCase()}`}>{alert.severity}</span>
      </div>
      <p>{alert.suggested_action}</p>
      <button className="inline-action" onClick={() => onDraft(alert.account_name, alert.project_code, alert.focus_area)}>
        Draft follow-up
      </button>
    </article>
  );
}

function FollowUpPanel({ draft, loading }) {
  if (loading) {
    return (
      <aside className="panel followup-panel">
        <div className="panel-header">
          <div>
            <p className="panel-kicker">Agent Output</p>
            <h2>Follow-up draft</h2>
          </div>
        </div>
        <div className="empty-state">Generating draft...</div>
      </aside>
    );
  }

  if (!draft) {
    return (
      <aside className="panel followup-panel">
        <div className="panel-header">
          <div>
            <p className="panel-kicker">Agent Output</p>
            <h2>Follow-up draft</h2>
          </div>
        </div>
        <div className="empty-state">Select an alert or project to generate a follow-up draft.</div>
      </aside>
    );
  }

  return (
    <aside className="panel followup-panel">
      <div className="panel-header">
        <div>
          <p className="panel-kicker">Agent Output</p>
          <h2>Follow-up draft</h2>
        </div>
      </div>
      <div className="followup-content">
        <p className="followup-summary">{draft.summary}</p>
        <div className="followup-block">
          <span className="label">Nudge</span>
          <p>{draft.nudge}</p>
        </div>
        <div className="followup-block">
          <span className="label">Email Subject</span>
          <p>{draft.email_subject}</p>
        </div>
        <div className="followup-block">
          <span className="label">Email Body</span>
          <pre>{draft.email_body}</pre>
        </div>
        <div className="followup-block">
          <span className="label">Recommended Action</span>
          <p>{draft.recommended_action}</p>
        </div>
        <div className="followup-block">
          <span className="label">Supporting Facts</span>
          <ul>
            {draft.supporting_facts.map((fact) => (
              <li key={fact}>{fact}</li>
            ))}
          </ul>
        </div>
        {draft.trace_url ? (
          <a className="trace-link" target="_blank" rel="noreferrer" href={draft.trace_url}>
            Open Langfuse Trace
          </a>
        ) : null}
      </div>
    </aside>
  );
}

function RevenueTable({ rows, onDraft }) {
  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Account</th>
            <th>Project</th>
            <th>Manager</th>
            <th>Plan</th>
            <th>Recognized</th>
            <th>Forecast</th>
            <th>Gap</th>
            <th>Unbilled</th>
            <th>Overdue</th>
            <th>Risk</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.project_code}>
              <td>{row.account_name}</td>
              <td>
                <strong>{row.project_code}</strong>
                <br />
                <small>{row.project_name}</small>
              </td>
              <td>{row.account_manager}</td>
              <td>{money.format(row.revenue_plan)}</td>
              <td>{money.format(row.revenue_recognized)}</td>
              <td>{money.format(row.revenue_forecast)}</td>
              <td>{money.format(row.revenue_gap)}</td>
              <td>{money.format(row.unbilled_amount)}</td>
              <td>{row.overdue_days} days</td>
              <td>
                <span className={`risk-pill ${row.risk_level.toLowerCase()}`}>{row.risk_level}</span>
              </td>
              <td>
                <button className="inline-action" onClick={() => onDraft(row.account_name, row.project_code, "revenue")}>
                  Analyze
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CollectionsTable({ rows }) {
  return (
    <div className="table-wrapper compact-table">
      <table>
        <thead>
          <tr>
            <th>Account</th>
            <th>Project</th>
            <th>Invoice</th>
            <th>Amount</th>
            <th>Outstanding</th>
            <th>Due Date</th>
            <th>Overdue Days</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.invoice_number}>
              <td>{row.account_name}</td>
              <td>{row.project_code}</td>
              <td>{row.invoice_number}</td>
              <td>{money.format(row.invoice_amount)}</td>
              <td>{money.format(row.outstanding_amount)}</td>
              <td>{row.due_date}</td>
              <td>{row.overdue_days}</td>
              <td>{row.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StackList({ items, labelKey }) {
  return (
    <div className="stack-list">
      {items.map((item) => {
        const secondaryValue = item.revenue_gap ?? item.revenue_forecast ?? 0;
        return (
          <div className="stack-item" key={item[labelKey]}>
            <span>{item[labelKey]}</span>
            <strong>{money.format(secondaryValue)}</strong>
          </div>
        );
      })}
    </div>
  );
}

function App({ appName, defaultProvider }) {
  const [providers, setProviders] = useState([]);
  const [provider, setProvider] = useState(defaultProvider || "mock");
  const [dashboard, setDashboard] = useState({
    summary: null,
    alerts: [],
    revenueRows: [],
    collections: [],
    report: null,
  });
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(true);
  const [draftLoading, setDraftLoading] = useState(false);
  const [error, setError] = useState("");
  const deferredRevenueRows = useDeferredValue(dashboard.revenueRows);

  async function loadDashboard() {
    setLoading(true);
    setError("");
    try {
      const [summary, alerts, revenueRows, collections, report] = await Promise.all([
        fetchJson("/api/summary"),
        fetchJson("/api/alerts"),
        fetchJson("/api/revenue-table"),
        fetchJson("/api/collections"),
        fetchJson("/api/report"),
      ]);
      startTransition(() => {
        setDashboard({ summary, alerts, revenueRows, collections, report });
      });
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        const providerOptions = await fetchJson("/api/providers");
        setProviders(providerOptions);
        if (!providerOptions.some((item) => item.provider === defaultProvider)) {
          setProvider("mock");
        }
      } catch (providerError) {
        setError(providerError.message);
      }
      await loadDashboard();
    }

    bootstrap();
  }, []);

  async function handleReseed() {
    setError("");
    try {
      await fetchJson("/api/data/reseed?regenerate_workbook=true", { method: "POST" });
      await loadDashboard();
      setDraft(null);
    } catch (reseedError) {
      setError(reseedError.message);
    }
  }

  async function handleDraft(accountName, projectCode, focusArea) {
    setDraftLoading(true);
    setError("");
    try {
      const response = await fetchJson("/api/agent/draft-followup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_name: accountName,
          project_code: projectCode,
          focus_area: focusArea,
          provider,
          question: `Prepare a ${focusArea} follow-up for ${accountName}.`,
        }),
      });
      setDraft(response);
    } catch (draftError) {
      setError(draftError.message);
    } finally {
      setDraftLoading(false);
    }
  }

  const summary = dashboard.summary;
  const report = dashboard.report;
  const summaryItems = summary
    ? [
        { label: "Revenue Plan", value: money.format(summary.revenue_plan), note: "Current month target" },
        {
          label: "Recognized",
          value: money.format(summary.revenue_recognized),
          note: `${percentage.format(summary.revenue_completion_pct)} completion`,
        },
        { label: "Forecast Gap", value: money.format(summary.revenue_gap), note: "Forecast minus target" },
        { label: "Unbilled", value: money.format(summary.total_unbilled), note: "Pending billing release" },
        { label: "Overdue", value: money.format(summary.overdue_amount), note: "Outstanding collections" },
        {
          label: "High Risk Projects",
          value: String(summary.high_risk_projects),
          note: `${summary.medium_risk_projects} medium risk in queue`,
        },
      ]
    : [];

  return (
    <main className="page-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Operational Finance Demo</p>
          <h1>{appName}</h1>
          <p className="hero-copy">
            Revenue realization monitoring, billing delay tracking, overdue collection nudges, and AI-drafted account manager follow-ups for BFM leads.
          </p>
        </div>
        <div className="hero-actions">
          <label className="provider-picker">
            <span>LLM Provider</span>
            <select value={provider} onChange={(event) => setProvider(event.target.value)}>
              {providers.map((item) => (
                <option key={item.provider} value={item.provider}>
                  {item.provider} · {item.model}
                  {item.available ? "" : " (not configured)"}
                </option>
              ))}
            </select>
          </label>
          <button className="button secondary" onClick={loadDashboard}>
            Refresh Dashboard
          </button>
          <button className="button" onClick={handleReseed}>
            Reset Demo Data
          </button>
          <a className="button tertiary" href="/api/data/workbook">
            Download Workbook
          </a>
        </div>
      </header>

      {error ? <div className="status-banner error">{error}</div> : null}
      {loading ? <div className="status-banner">Loading dashboard...</div> : null}

      <section className="summary-grid">
        {summaryItems.map((item) => (
          <SummaryCard key={item.label} {...item} />
        ))}
      </section>

      <section className="layout-grid">
        <div className="panel panel-large">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">Focus Queue</p>
              <h2>High-priority nudges</h2>
            </div>
          </div>
          <div className="alert-list">
            {dashboard.alerts.map((alert) => (
              <AlertCard key={`${alert.project_code}-${alert.focus_area}`} alert={alert} onDraft={handleDraft} />
            ))}
          </div>
        </div>

        <FollowUpPanel draft={draft} loading={draftLoading} />
      </section>

      <section className="layout-grid bottom-grid">
        <div className="panel panel-large">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">Revenue Monitor</p>
              <h2>Revenue realization table</h2>
            </div>
          </div>
          <RevenueTable rows={deferredRevenueRows} onDraft={handleDraft} />
        </div>

        <div className="panel">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">Portfolio Brief</p>
              <h2>Report snapshot</h2>
            </div>
          </div>
          <p className="report-narrative">{report?.narrative ?? ""}</p>
          <div className="mini-section">
            <span className="label">Top gap accounts</span>
            <StackList items={report?.top_accounts ?? []} labelKey="account_name" />
          </div>
          <div className="mini-section">
            <span className="label">Delivery units</span>
            <StackList items={report?.top_delivery_units ?? []} labelKey="delivery_unit" />
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="panel-kicker">Collections Tracker</p>
            <h2>Open invoices</h2>
          </div>
        </div>
        <CollectionsTable rows={dashboard.collections} />
      </section>
    </main>
  );
}

const rootElement = document.getElementById("root");
createRoot(rootElement).render(
  <React.StrictMode>
    <App appName={rootElement.dataset.appName} defaultProvider={rootElement.dataset.defaultProvider} />
  </React.StrictMode>,
);
