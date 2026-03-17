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

const number = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});

const tabs = [
  { id: "overview", label: "Morning Scan" },
  { id: "revenue_realization", label: "Revenue" },
  { id: "billing_trigger", label: "Billing" },
  { id: "unbilled_revenue", label: "Unbilled" },
  { id: "collection_monitoring", label: "Collections" },
  { id: "revenue_forecasting", label: "Forecast" },
  { id: "thresholds", label: "Controls" },
];

function selectionKey(item) {
  return item ? `${item.agent_key}:${item.entity_type}:${item.entity_id}` : "";
}

function sameSelection(left, right) {
  return selectionKey(left) === selectionKey(right);
}

function entityLabel(item) {
  if (!item) {
    return "No record selected";
  }
  if (item.invoice_number) {
    return item.invoice_number;
  }
  if (item.billing_milestone) {
    return item.billing_milestone;
  }
  if (item.project_code) {
    return item.project_code;
  }
  return `${item.entity_type} ${item.entity_id}`;
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const detail = await response.text();
    let message = detail;
    try {
      const payload = JSON.parse(detail);
      if (typeof payload.detail === "string") {
        message = payload.detail;
      }
    } catch {
      // Use raw text when the response is not JSON.
    }
    throw new Error(message || `Request failed for ${url}`);
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

function StatusBadge({ value, type = "risk" }) {
  return <span className={`${type}-pill ${(value || "low").toLowerCase().replace(/\s+/g, "-")}`}>{value}</span>;
}

function MetricGrid({ items }) {
  return (
    <div className="metric-grid">
      {items.map((item) => (
        <SummaryCard key={item.label} {...item} />
      ))}
    </div>
  );
}

function QueueCard({ item, active, onAnalyze, onDraft }) {
  return (
    <article className={`queue-card ${active ? "active" : ""}`}>
      <div className="queue-card-top">
        <div>
          <p className="queue-title">{item.title}</p>
          <p className="queue-copy">{item.message}</p>
          <small>
            {item.account_name}
            {item.project_code ? ` · ${item.project_code}` : ""}
          </small>
        </div>
        <StatusBadge value={item.severity} />
      </div>
      <p className="queue-action">{item.suggested_action}</p>
      <div className="queue-footer">
        <span className="queue-status">{item.current_status}</span>
        <div className="action-row">
          <button className="button-secondary" onClick={() => onAnalyze(item)}>
            Analyze
          </button>
          <button onClick={() => onDraft(item)}>Generate Draft</button>
        </div>
      </div>
    </article>
  );
}

function SimpleTable({ columns, rows, onInspect, selectedRef }) {
  const deferredRows = useDeferredValue(rows);
  return (
    <div className="table-shell">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.label}>{column.label}</th>
            ))}
            {onInspect ? <th></th> : null}
          </tr>
        </thead>
        <tbody>
          {deferredRows.map((row) => {
            const isSelected = sameSelection(selectedRef, row);
            return (
              <tr key={selectionKey(row)} className={isSelected ? "selected-row" : ""}>
                {columns.map((column) => (
                  <td key={column.label}>{column.render ? column.render(row) : row[column.key]}</td>
                ))}
                {onInspect ? (
                  <td>
                    <button className="table-button" onClick={() => onInspect(row)}>
                      Analyze
                    </button>
                  </td>
                ) : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function NotificationList({ items }) {
  if (!items.length) {
    return <div className="empty-state slim">No notifications sent yet.</div>;
  }

  return (
    <div className="notification-list">
      {items.map((item) => (
        <article key={item.id} className="notification-card">
          <div className="notification-meta">
            <StatusBadge value={item.status} type="status" />
            <span>{item.channel}</span>
            <span>{item.direction}</span>
          </div>
          <strong>{item.subject}</strong>
          <p>{item.message_excerpt}</p>
          <small>
            {item.recipient_email}
            {item.sender_email ? ` · ${item.sender_email}` : ""}
          </small>
        </article>
      ))}
    </div>
  );
}

function ThresholdEditor({ thresholds, drafts, onChange, onSave, savingId }) {
  return (
    <div className="threshold-grid">
      {thresholds.map((threshold) => {
        const draft = drafts[threshold.id] ?? threshold;
        return (
          <article className="threshold-card" key={threshold.id}>
            <div>
              <p className="label">{threshold.agent_key.replaceAll("_", " ")}</p>
              <h3>{threshold.label}</h3>
              <p>{threshold.description}</p>
            </div>
            <div className="threshold-fields">
              <label>
                <span>Medium</span>
                <input
                  type="number"
                  step="0.01"
                  value={draft.medium_value}
                  onChange={(event) => onChange(threshold.id, "medium_value", event.target.value)}
                />
              </label>
              <label>
                <span>High</span>
                <input
                  type="number"
                  step="0.01"
                  value={draft.high_value}
                  onChange={(event) => onChange(threshold.id, "high_value", event.target.value)}
                />
              </label>
              <button onClick={() => onSave(threshold.id)} disabled={savingId === threshold.id}>
                {savingId === threshold.id ? "Saving..." : "Save threshold"}
              </button>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function QueueStack({ items, selectedRef, onAnalyze, onDraft, className = "" }) {
  if (!items.length) {
    return <div className="empty-state slim">No nudges in this view right now.</div>;
  }

  return (
    <div className={`queue-list ${className}`.trim()}>
      {items.map((item) => (
        <QueueCard
          key={item.id}
          item={item}
          active={sameSelection(selectedRef, item)}
          onAnalyze={onAnalyze}
          onDraft={onDraft}
        />
      ))}
    </div>
  );
}

function AnalysisPanel({ item, nudge, generating, onGenerateDraft }) {
  if (!item) {
    return (
      <aside className="panel analysis-panel">
        <div className="panel-header">
          <div>
            <p className="panel-kicker">Analyze</p>
            <h2>Why this was triggered</h2>
          </div>
        </div>
        <div className="empty-state">Select a row or nudge to review the formula inputs, threshold breaches, and status logic.</div>
      </aside>
    );
  }

  return (
    <aside className="panel analysis-panel">
      <div className="panel-header">
        <div>
          <p className="panel-kicker">{item.agent_key.replaceAll("_", " ")}</p>
          <h2>
            {item.account_name} · {entityLabel(item)}
          </h2>
        </div>
        <div className="analysis-badges">
          <StatusBadge value={item.risk_level || item.collection_risk} />
          <StatusBadge value={item.analysis.current_status} type="status" />
        </div>
      </div>
      <div className="analysis-highlight">
        <span className="label">Why triggered</span>
        <p>{item.analysis.why_triggered}</p>
      </div>
      {nudge ? (
        <div className="analysis-highlight soft">
          <span className="label">Priority nudge</span>
          <p>{nudge.message}</p>
          <small>{nudge.suggested_action}</small>
        </div>
      ) : null}
      {item.analysis.confidence_display ? (
        <div className="analysis-confidence">
          <span className="label">Confidence</span>
          <strong>{item.analysis.confidence_display}</strong>
        </div>
      ) : null}
      <div className="analysis-section">
        <span className="label">Formula inputs</span>
        <div className="formula-grid">
          {item.analysis.formula_inputs.map((metric) => (
            <article className="formula-card" key={metric.key}>
              <small>{metric.label}</small>
              <strong>{metric.display_value}</strong>
              <p>{metric.description}</p>
            </article>
          ))}
        </div>
      </div>
      <div className="analysis-section">
        <span className="label">Threshold checks</span>
        <div className="threshold-check-list">
          {item.analysis.threshold_checks.map((check) => (
            <article className="threshold-check" key={check.metric_key}>
              <div className="panel-header">
                <strong>{check.label}</strong>
                <StatusBadge value={check.breached_level || "Low"} />
              </div>
              <p>
                Current: {check.current_display} · Medium: {check.medium_display} · High: {check.high_display}
              </p>
              <small>{check.description}</small>
            </article>
          ))}
        </div>
      </div>
      <div className="analysis-section">
        <span className="label">Calculation notes</span>
        <ul className="analysis-list">
          {item.analysis.calculation_notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </div>
      <button className="wide-button" onClick={onGenerateDraft} disabled={generating}>
        {generating ? "Generating draft..." : "Generate draft"}
      </button>
    </aside>
  );
}

function DraftPanel({ item, draft, sending, generating, channel, setChannel, onGenerateDraft, onApprove }) {
  if (!item) {
    return (
      <aside className="panel draft-panel">
        <div className="panel-header">
          <div>
            <p className="panel-kicker">Agent Workspace</p>
            <h2>Draft and approve actions</h2>
          </div>
        </div>
        <div className="empty-state">Select a queue item or table row to prepare a follow-up action.</div>
      </aside>
    );
  }

  const hasDraft = draft && sameSelection(draft, item);

  return (
    <aside className="panel draft-panel">
      <div className="panel-header">
        <div>
          <p className="panel-kicker">Agent Workspace</p>
          <h2>
            {item.account_name} · {entityLabel(item)}
          </h2>
        </div>
        <StatusBadge value={item.analysis.current_status} type="status" />
      </div>
      {!hasDraft ? (
        <>
          <div className="draft-section">
            <span className="label">Recommended action</span>
            <p>{item.analysis.recommended_action}</p>
          </div>
          <div className="draft-section">
            <span className="label">Current workspace state</span>
            <p>Generate a follow-up draft to review the message before approval and sending.</p>
          </div>
          <button className="wide-button" onClick={onGenerateDraft} disabled={generating}>
            {generating ? "Generating draft..." : "Generate draft"}
          </button>
        </>
      ) : (
        <>
          <div className="draft-section">
            <span className="label">Nudge</span>
            <p>{draft.nudge}</p>
          </div>
          <div className="draft-section">
            <span className="label">Subject</span>
            <p>{draft.email_subject}</p>
          </div>
          <div className="draft-section">
            <span className="label">Body</span>
            <pre>{draft.email_body}</pre>
          </div>
          <div className="draft-section">
            <span className="label">Supporting facts</span>
            <ul className="analysis-list">
              {draft.supporting_facts.map((fact) => (
                <li key={fact}>{fact}</li>
              ))}
            </ul>
          </div>
          <div className="draft-actions">
            <label>
              <span>Send via</span>
              <select value={channel} onChange={(event) => setChannel(event.target.value)}>
                <option value="mock_email">Mock email</option>
                <option value="gmail">Gmail</option>
              </select>
            </label>
            <button onClick={onApprove} disabled={sending}>
              {sending ? "Sending..." : "Approve and send"}
            </button>
          </div>
          {draft.trace_url ? (
            <a className="trace-link" href={draft.trace_url} rel="noreferrer" target="_blank">
              Open Langfuse trace
            </a>
          ) : null}
        </>
      )}
    </aside>
  );
}

function App({ appName, defaultProvider }) {
  const [providers, setProviders] = useState([]);
  const [provider, setProvider] = useState(defaultProvider || "mock");
  const [dashboard, setDashboard] = useState(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [selectedRef, setSelectedRef] = useState(null);
  const [draft, setDraft] = useState(null);
  const [channel, setChannel] = useState("mock_email");
  const [thresholdDrafts, setThresholdDrafts] = useState({});
  const [loading, setLoading] = useState(true);
  const [draftLoading, setDraftLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [savingThresholdId, setSavingThresholdId] = useState(null);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");

  async function loadDashboard() {
    setLoading(true);
    setError("");
    try {
      const [providerOptions, dashboardPayload] = await Promise.all([fetchJson("/api/providers"), fetchJson("/api/dashboard")]);
      setProviders(providerOptions);
      startTransition(() => {
        setDashboard(dashboardPayload);
      });
      setProvider((current) => {
        const currentOption = providerOptions.find((item) => item.provider === current && item.available);
        if (currentOption) {
          return current;
        }
        const configuredDefault = providerOptions.find((item) => item.provider === defaultProvider && item.available);
        const firstAvailable = providerOptions.find((item) => item.available);
        return configuredDefault?.provider ?? firstAvailable?.provider ?? "mock";
      });
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadDashboard();
  }, []);

  const sections = dashboard
    ? {
        revenue_realization: {
          summary: dashboard.revenue_realization.summary,
          nudges: dashboard.revenue_realization.nudges,
          rows: dashboard.revenue_realization.rows.map((row) => ({ ...row, agent_key: "revenue_realization" })),
          columns: [
            { label: "Account", key: "account_name" },
            { label: "Project", key: "project_code", render: (row) => <strong>{row.project_code}</strong> },
            { label: "Plan", key: "revenue_plan", render: (row) => money.format(row.revenue_plan) },
            { label: "Recognized", key: "revenue_recognized", render: (row) => money.format(row.revenue_recognized) },
            { label: "Remaining", key: "revenue_remaining", render: (row) => money.format(row.revenue_remaining) },
            { label: "Forecast", key: "revenue_forecast", render: (row) => money.format(row.revenue_forecast) },
            { label: "Gap", key: "revenue_gap", render: (row) => money.format(row.revenue_gap) },
            { label: "Completion", key: "revenue_completion_pct", render: (row) => percentage.format(row.revenue_completion_pct) },
            { label: "Risk", key: "risk_level", render: (row) => <StatusBadge value={row.risk_level} /> },
          ],
          metrics: [
            { label: "Revenue Plan", value: money.format(dashboard.revenue_realization.summary.revenue_plan), note: "Target revenue" },
            { label: "Recognized", value: money.format(dashboard.revenue_realization.summary.revenue_recognized), note: "Booked revenue" },
            { label: "Remaining", value: money.format(dashboard.revenue_realization.summary.revenue_remaining), note: "Yet to realize" },
            { label: "Gap", value: money.format(dashboard.revenue_realization.summary.revenue_gap), note: "Forecast minus plan" },
          ],
        },
        billing_trigger: {
          summary: dashboard.billing_trigger.summary,
          nudges: dashboard.billing_trigger.nudges,
          rows: dashboard.billing_trigger.rows.map((row) => ({ ...row, agent_key: "billing_trigger" })),
          columns: [
            { label: "Account", key: "account_name" },
            { label: "Project", key: "project_code" },
            { label: "Milestone", key: "billing_milestone" },
            { label: "Billable", key: "billable_amount", render: (row) => money.format(row.billable_amount) },
            { label: "Billed", key: "billed_amount", render: (row) => money.format(row.billed_amount) },
            { label: "Unbilled", key: "unbilled_amount", render: (row) => money.format(row.unbilled_amount) },
            { label: "Delay", key: "billing_delay_days", render: (row) => `${row.billing_delay_days} days` },
            { label: "Status", key: "billing_status", render: (row) => <StatusBadge value={row.billing_status} type="status" /> },
            { label: "Risk", key: "risk_level", render: (row) => <StatusBadge value={row.risk_level} /> },
          ],
          metrics: [
            { label: "Billable Amount", value: money.format(dashboard.billing_trigger.summary.billable_amount), note: "Eligible this period" },
            { label: "Invoices Pending", value: number.format(dashboard.billing_trigger.summary.invoices_pending), note: "Milestones waiting" },
            { label: "Unbilled Revenue", value: money.format(dashboard.billing_trigger.summary.unbilled_revenue), note: "Pending invoice trigger" },
            { label: "Avg Delay", value: `${number.format(dashboard.billing_trigger.summary.average_billing_delay)} days`, note: "Completion to billing" },
          ],
        },
        unbilled_revenue: {
          summary: dashboard.unbilled_revenue.summary,
          nudges: dashboard.unbilled_revenue.nudges,
          rows: dashboard.unbilled_revenue.rows.map((row) => ({ ...row, agent_key: "unbilled_revenue" })),
          columns: [
            { label: "Account", key: "account_name" },
            { label: "Project", key: "project_code" },
            { label: "Recognized", key: "revenue_recognized", render: (row) => money.format(row.revenue_recognized) },
            { label: "Billed", key: "revenue_billed", render: (row) => money.format(row.revenue_billed) },
            { label: "Unbilled", key: "unbilled_revenue", render: (row) => money.format(row.unbilled_revenue) },
            { label: "Aging", key: "days_unbilled", render: (row) => `${row.days_unbilled} days` },
            { label: "Owner", key: "billing_owner" },
            { label: "Risk", key: "risk_level", render: (row) => <StatusBadge value={row.risk_level} /> },
          ],
          metrics: [
            { label: "Recognized", value: money.format(dashboard.unbilled_revenue.summary.total_revenue_recognized), note: "Current period" },
            { label: "Billed", value: money.format(dashboard.unbilled_revenue.summary.total_revenue_billed), note: "Invoices raised" },
            { label: "Unbilled", value: money.format(dashboard.unbilled_revenue.summary.total_unbilled_revenue), note: "Revenue leakage risk" },
            { label: "Avg Aging", value: `${number.format(dashboard.unbilled_revenue.summary.average_days_unbilled)} days`, note: "Average days unbilled" },
          ],
        },
        collection_monitoring: {
          summary: dashboard.collection_monitoring.summary,
          nudges: dashboard.collection_monitoring.nudges,
          rows: dashboard.collection_monitoring.rows.map((row) => ({ ...row, agent_key: "collection_monitoring" })),
          columns: [
            { label: "Account", key: "account_name" },
            { label: "Invoice", key: "invoice_number" },
            { label: "Project", key: "project_code" },
            { label: "Amount", key: "invoice_amount", render: (row) => money.format(row.invoice_amount) },
            { label: "Received", key: "amount_received", render: (row) => money.format(row.amount_received) },
            { label: "Outstanding", key: "outstanding_balance", render: (row) => money.format(row.outstanding_balance) },
            { label: "Overdue", key: "overdue_days", render: (row) => `${row.overdue_days} days` },
            { label: "Status", key: "collection_status", render: (row) => <StatusBadge value={row.collection_status} type="status" /> },
            { label: "Risk", key: "collection_risk", render: (row) => <StatusBadge value={row.collection_risk} /> },
          ],
          metrics: [
            { label: "Total Invoiced", value: money.format(dashboard.collection_monitoring.summary.total_invoiced), note: "Invoices issued" },
            { label: "Collected", value: money.format(dashboard.collection_monitoring.summary.total_collected), note: "Cash received" },
            { label: "Receivables", value: money.format(dashboard.collection_monitoring.summary.outstanding_receivables), note: "Pending collections" },
            { label: "DSO", value: `${number.format(dashboard.collection_monitoring.summary.dso)} days`, note: "Average collection cycle" },
          ],
        },
        revenue_forecasting: {
          summary: dashboard.revenue_forecasting.summary,
          nudges: dashboard.revenue_forecasting.nudges,
          rows: dashboard.revenue_forecasting.rows.map((row) => ({ ...row, agent_key: "revenue_forecasting" })),
          columns: [
            { label: "Account", key: "account_name" },
            { label: "Project", key: "project_code" },
            { label: "Plan", key: "revenue_plan", render: (row) => money.format(row.revenue_plan) },
            { label: "Recognized", key: "revenue_recognized", render: (row) => money.format(row.revenue_recognized) },
            { label: "Forecast", key: "revenue_forecast", render: (row) => money.format(row.revenue_forecast) },
            { label: "Gap", key: "revenue_gap", render: (row) => money.format(row.revenue_gap) },
            { label: "Confidence", key: "forecast_confidence", render: (row) => percentage.format(row.forecast_confidence) },
            { label: "Risk", key: "risk_level", render: (row) => <StatusBadge value={row.risk_level} /> },
          ],
          metrics: [
            { label: "Revenue Plan", value: money.format(dashboard.revenue_forecasting.summary.revenue_plan), note: "Target revenue" },
            { label: "Recognized", value: money.format(dashboard.revenue_forecasting.summary.revenue_recognized), note: "Current actuals" },
            { label: "Forecast", value: money.format(dashboard.revenue_forecasting.summary.revenue_forecast), note: "Predicted month close" },
            { label: "Confidence", value: percentage.format(dashboard.revenue_forecasting.summary.forecast_confidence_score), note: "Average forecast confidence" },
          ],
        },
      }
    : {};

  function getSection(agentKey) {
    return sections[agentKey] ?? null;
  }

  function resolveEntity(ref) {
    if (!dashboard || !ref) {
      return null;
    }
    const section = getSection(ref.agent_key);
    return section?.rows.find((row) => sameSelection(row, ref)) ?? null;
  }

  function resolveNudge(ref) {
    if (!dashboard || !ref) {
      return null;
    }
    const section = getSection(ref.agent_key);
    return section?.nudges.find((item) => sameSelection(item, ref)) ?? dashboard.queue.find((item) => sameSelection(item, ref)) ?? null;
  }

  function defaultSelectionForTab(tabId) {
    if (!dashboard || tabId === "thresholds") {
      return null;
    }
    if (tabId === "overview") {
      return dashboard.queue[0] ?? null;
    }
    const section = getSection(tabId);
    return section?.nudges[0] ?? section?.rows[0] ?? null;
  }

  function selectItem(item) {
    const nextRef = {
      agent_key: item.agent_key,
      entity_type: item.entity_type,
      entity_id: item.entity_id,
    };
    setSelectedRef(nextRef);
    if (!sameSelection(draft, nextRef)) {
      setDraft(null);
    }
  }

  useEffect(() => {
    if (!dashboard || activeTab === "thresholds") {
      return;
    }
    const selectedItem = resolveEntity(selectedRef);
    if (selectedItem && (activeTab === "overview" || selectedItem.agent_key === activeTab)) {
      return;
    }
    const fallback = defaultSelectionForTab(activeTab);
    if (!fallback) {
      return;
    }
    const fallbackRef = {
      agent_key: fallback.agent_key,
      entity_type: fallback.entity_type,
      entity_id: fallback.entity_id,
    };
    if (!sameSelection(selectedRef, fallbackRef)) {
      setSelectedRef(fallbackRef);
      if (!sameSelection(draft, fallbackRef)) {
        setDraft(null);
      }
    }
  }, [dashboard, activeTab, selectedRef, draft]);

  async function generateDraft(target = null) {
    const item = target ?? resolveEntity(selectedRef);
    if (!item) {
      return;
    }
    setDraftLoading(true);
    setError("");
    try {
      const response = await fetchJson("/api/agent/draft-followup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_key: item.agent_key,
          entity_type: item.entity_type,
          entity_id: item.entity_id,
          provider,
          question: `Prepare a ${item.agent_key.replaceAll("_", " ")} follow-up for ${item.account_name}.`,
        }),
      });
      setDraft(response);
      setSelectedRef({
        agent_key: response.agent_key,
        entity_type: response.entity_type,
        entity_id: response.entity_id,
      });
    } catch (draftError) {
      setError(draftError.message);
    } finally {
      setDraftLoading(false);
    }
  }

  async function approveDraft() {
    if (!draft) {
      return;
    }
    setSending(true);
    setError("");
    setStatusMessage("");
    try {
      const response = await fetchJson("/api/actions/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_key: draft.agent_key,
          entity_type: draft.entity_type,
          entity_id: draft.entity_id,
          provider,
          channel,
          question: `Prepare a ${draft.agent_key.replaceAll("_", " ")} follow-up for ${draft.account_name}.`,
        }),
      });
      setStatusMessage(`Action ${response.action_id} sent to ${response.recipient_email} via ${response.channel}.`);
      await loadDashboard();
    } catch (approveError) {
      setError(approveError.message);
    } finally {
      setSending(false);
    }
  }

  async function saveThreshold(thresholdId) {
    const draftValues = thresholdDrafts[thresholdId];
    if (!draftValues) {
      return;
    }
    setSavingThresholdId(thresholdId);
    setError("");
    try {
      await fetchJson(`/api/thresholds/${thresholdId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          medium_value: Number(draftValues.medium_value),
          high_value: Number(draftValues.high_value),
        }),
      });
      setStatusMessage("Threshold updated.");
      await loadDashboard();
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSavingThresholdId(null);
    }
  }

  async function syncGmail() {
    setError("");
    try {
      const response = await fetchJson("/api/integrations/gmail/sync", { method: "POST" });
      setStatusMessage(response.detail);
      await loadDashboard();
    } catch (syncError) {
      setError(syncError.message);
    }
  }

  async function reseedData() {
    setError("");
    try {
      await fetchJson("/api/data/reseed?regenerate_workbook=true", { method: "POST" });
      setDraft(null);
      await loadDashboard();
    } catch (reseedError) {
      setError(reseedError.message);
    }
  }

  async function uploadWorkbook() {
    if (!uploadFile) {
      setError("Select an .xlsx workbook to upload.");
      return;
    }
    setUploading(true);
    setError("");
    setStatusMessage("");
    try {
      const formData = new FormData();
      formData.append("file", uploadFile);
      const response = await fetchJson("/api/data/upload", {
        method: "POST",
        body: formData,
      });
      setStatusMessage(`Workbook uploaded. ${response.records_loaded} records loaded from ${response.workbook_path}.`);
      setUploadFile(null);
      await loadDashboard();
    } catch (uploadError) {
      setError(uploadError.message);
    } finally {
      setUploading(false);
    }
  }

  function handleThresholdChange(id, key, value) {
    setThresholdDrafts((current) => ({
      ...current,
      [id]: {
        ...(current[id] ?? dashboard.thresholds.find((item) => item.id === id)),
        [key]: value,
      },
    }));
  }

  if (!dashboard) {
    return <main className="page-shell">{loading ? <div className="status-banner">Loading dashboard...</div> : null}</main>;
  }

  const selectedItem = resolveEntity(selectedRef);
  const selectedNudge = resolveNudge(selectedRef);
  const overviewCards = [
    { label: "Revenue Plan", value: money.format(dashboard.overview.revenue_plan), note: "Current period target" },
    { label: "Recognized", value: money.format(dashboard.overview.revenue_recognized), note: "Revenue already recognized" },
    { label: "Forecast", value: money.format(dashboard.overview.revenue_forecast), note: "AI-assisted month close" },
    { label: "Unbilled", value: money.format(dashboard.overview.unbilled_revenue), note: "Recognized but not invoiced" },
    { label: "Receivables", value: money.format(dashboard.overview.outstanding_receivables), note: "Open cash collections" },
    { label: "Revenue at Risk", value: money.format(dashboard.overview.revenue_at_risk), note: "Forecast below plan" },
  ];
  const topQueue = dashboard.queue.slice(0, 5);
  const backlogQueue = dashboard.queue.slice(5);

  return (
    <main className="page-shell">
      <header className="hero">
        <div className="hero-copy-block">
          <p className="eyebrow">BFM Lead Workspace</p>
          <h1>{appName}</h1>
          <p className="hero-copy">
            Morning financial health scan, five operational finance sub-agents, configurable risk thresholds, and approval-driven follow-ups tied to milestone and collection status.
          </p>
        </div>
        <div className="hero-actions">
          <label>
            <span>LLM Provider</span>
            <select value={provider} onChange={(event) => setProvider(event.target.value)}>
              {providers.map((item) => (
                <option key={item.provider} value={item.provider} disabled={!item.available}>
                  {item.provider} · {item.model}
                  {item.available ? "" : " (not configured)"}
                </option>
              ))}
            </select>
          </label>
          <button onClick={() => loadDashboard()}>Refresh dashboard</button>
          <button onClick={reseedData}>Reset demo data</button>
          <button onClick={syncGmail}>Sync Gmail replies</button>
          <a href="/api/data/workbook">Download workbook</a>
        </div>
      </header>

      {error ? <div className="status-banner error">{error}</div> : null}
      {statusMessage ? <div className="status-banner">{statusMessage}</div> : null}
      {loading ? <div className="status-banner">Refreshing dashboard...</div> : null}

      <MetricGrid items={overviewCards} />

      <nav className="tab-strip">
        {tabs.map((tab) => (
          <button key={tab.id} className={tab.id === activeTab ? "active" : ""} onClick={() => setActiveTab(tab.id)}>
            {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === "overview" ? (
        <section className="workspace-grid">
          <div className="workspace-main">
            <div className="panel">
              <div className="panel-header">
                <div>
                  <p className="panel-kicker">Morning Scan</p>
                  <h2>Top 5 priority nudges</h2>
                </div>
                <span className="queue-count">{topQueue.length} prioritized</span>
              </div>
              <QueueStack
                items={topQueue}
                selectedRef={selectedRef}
                onAnalyze={(item) => selectItem(item)}
                onDraft={async (item) => {
                  selectItem(item);
                  await generateDraft(item);
                }}
                className="featured-queue"
              />
            </div>
            <div className="panel">
              <div className="panel-header">
                <div>
                  <p className="panel-kicker">Backlog</p>
                  <h2>Remaining nudges</h2>
                </div>
                <span className="queue-count">{backlogQueue.length} more items</span>
              </div>
              <div className="scroll-shell">
                <QueueStack
                  items={backlogQueue}
                  selectedRef={selectedRef}
                  onAnalyze={(item) => selectItem(item)}
                  onDraft={async (item) => {
                    selectItem(item);
                    await generateDraft(item);
                  }}
                />
              </div>
            </div>
            <div className="panel">
              <div className="panel-header">
                <div>
                  <p className="panel-kicker">Narrative</p>
                  <h2>{dashboard.narrative.headline}</h2>
                </div>
              </div>
              <p className="report-copy">{dashboard.narrative.narrative}</p>
              <div className="split-stack">
                <div>
                  <span className="label">Accounts with biggest gap</span>
                  {dashboard.narrative.top_accounts.map((item) => (
                    <div className="stack-row" key={item.account_name}>
                      <span>{item.account_name}</span>
                      <strong>{money.format(item.forecast_gap || 0)}</strong>
                    </div>
                  ))}
                </div>
                <div>
                  <span className="label">Delivery units</span>
                  {dashboard.narrative.top_delivery_units.map((item) => (
                    <div className="stack-row" key={item.delivery_unit}>
                      <span>{item.delivery_unit}</span>
                      <strong>{money.format(item.forecast_gap || 0)}</strong>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="panel">
              <div className="panel-header">
                <div>
                  <p className="panel-kicker">Integration</p>
                  <h2>Notification channels</h2>
                </div>
              </div>
              {dashboard.integrations.map((item) => (
                <article className="integration-card" key={item.channel}>
                  <div className="integration-head">
                    <strong>{item.channel}</strong>
                    <StatusBadge value={item.configured ? "Configured" : "Not Configured"} type="status" />
                  </div>
                  <p>{item.detail}</p>
                  <small>Last sync: {item.last_sync_at ?? "Not synced yet"}</small>
                </article>
              ))}
            </div>
            <div className="panel">
              <div className="panel-header">
                <div>
                  <p className="panel-kicker">History</p>
                  <h2>Notification timeline</h2>
                </div>
              </div>
              <NotificationList items={dashboard.notifications} />
            </div>
          </div>
          <div className="workspace-sidebar">
            <AnalysisPanel item={selectedItem} nudge={selectedNudge} generating={draftLoading} onGenerateDraft={() => generateDraft()} />
            <DraftPanel
              item={selectedItem}
              draft={draft}
              sending={sending}
              generating={draftLoading}
              channel={channel}
              setChannel={setChannel}
              onGenerateDraft={() => generateDraft()}
              onApprove={approveDraft}
            />
          </div>
        </section>
      ) : null}

      {tabs
        .filter((tab) => !["overview", "thresholds"].includes(tab.id))
        .map((tab) =>
          activeTab === tab.id ? (
            <section className="workspace-grid" key={tab.id}>
              <div className="workspace-main">
                <div className="panel">
                  <div className="panel-header">
                    <div>
                      <p className="panel-kicker">{tab.label}</p>
                      <h2>{tab.label} agent</h2>
                    </div>
                    <span className="queue-count">{sections[tab.id].nudges.length} active nudges</span>
                  </div>
                  <MetricGrid items={sections[tab.id].metrics} />
                </div>
                <div className="panel">
                  <div className="panel-header">
                    <div>
                      <p className="panel-kicker">{tab.label}</p>
                      <h2>Priority nudges</h2>
                    </div>
                  </div>
                  <div className="scroll-shell medium">
                    <QueueStack
                      items={sections[tab.id].nudges}
                      selectedRef={selectedRef}
                      onAnalyze={(item) => selectItem(item)}
                      onDraft={async (item) => {
                        selectItem(item);
                        await generateDraft(item);
                      }}
                    />
                  </div>
                </div>
                <div className="panel">
                  <div className="panel-header">
                    <div>
                      <p className="panel-kicker">{tab.label}</p>
                      <h2>Agent data</h2>
                    </div>
                  </div>
                  <SimpleTable
                    columns={sections[tab.id].columns}
                    rows={sections[tab.id].rows}
                    selectedRef={selectedRef}
                    onInspect={(row) => selectItem(row)}
                  />
                </div>
              </div>
              <div className="workspace-sidebar">
                <AnalysisPanel item={selectedItem} nudge={selectedNudge} generating={draftLoading} onGenerateDraft={() => generateDraft()} />
                <DraftPanel
                  item={selectedItem}
                  draft={draft}
                  sending={sending}
                  generating={draftLoading}
                  channel={channel}
                  setChannel={setChannel}
                  onGenerateDraft={() => generateDraft()}
                  onApprove={approveDraft}
                />
              </div>
            </section>
          ) : null,
        )}

      {activeTab === "thresholds" ? (
        <section className="workspace-grid">
          <div className="workspace-main">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <p className="panel-kicker">Controls</p>
                  <h2>Risk thresholds and reply automation</h2>
                </div>
              </div>
              <div className="upload-panel">
                <div>
                  <span className="label">Workbook upload</span>
                  <p>Upload an .xlsx workbook (for example `sample_data.xlsx`) to recalculate all agent KPIs and nudges.</p>
                </div>
                <div className="upload-actions">
                  <input
                    type="file"
                    accept=".xlsx"
                    onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                  />
                  <button onClick={uploadWorkbook} disabled={uploading}>
                    {uploading ? "Uploading..." : "Upload workbook"}
                  </button>
                </div>
              </div>
              <ThresholdEditor
                thresholds={dashboard.thresholds}
                drafts={thresholdDrafts}
                onChange={handleThresholdChange}
                onSave={saveThreshold}
                savingId={savingThresholdId}
              />
            </section>
          </div>
          <div className="workspace-sidebar">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <p className="panel-kicker">Integrations</p>
                  <h2>Notification channels</h2>
                </div>
              </div>
              {dashboard.integrations.map((item) => (
                <article className="integration-card" key={item.channel}>
                  <div className="integration-head">
                    <strong>{item.channel}</strong>
                    <StatusBadge value={item.configured ? "Configured" : "Not Configured"} type="status" />
                  </div>
                  <p>{item.detail}</p>
                  <small>Last sync: {item.last_sync_at ?? "Not synced yet"}</small>
                </article>
              ))}
            </section>
            <section className="panel">
              <div className="panel-header">
                <div>
                  <p className="panel-kicker">History</p>
                  <h2>Recent notifications</h2>
                </div>
              </div>
              <NotificationList items={dashboard.notifications} />
            </section>
          </div>
        </section>
      ) : null}
    </main>
  );
}

const rootElement = document.getElementById("root");
createRoot(rootElement).render(<App appName={rootElement.dataset.appName} defaultProvider={rootElement.dataset.defaultProvider} />);
