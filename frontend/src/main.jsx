import React, {
  useCallback,
  useDeferredValue,
  useEffect,
  useState,
} from "react";
import { createRoot } from "react-dom/client";

// ── Formatters ───────────────────────────────────────────────────────────────
const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const pctFmt = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function shortMoney(v) {
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return money.format(v);
}

function fmtDate(str) {
  if (!str) return "—";
  return new Date(str).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// ── Navigation ───────────────────────────────────────────────────────────────
const NAV = [
  { id: "overview", label: "Financial Health", desc: "Morning Scan" },
  { id: "revenue_realization", label: "Revenue", desc: "Realization Monitor" },
  { id: "billing_trigger", label: "Billing Triggers", desc: "Milestone Monitor" },
  { id: "unbilled_revenue", label: "Unbilled Revenue", desc: "Detection" },
  { id: "collection_monitoring", label: "Collections", desc: "AR Monitor" },
  { id: "revenue_forecasting", label: "Revenue Forecast", desc: "Projections" },
  { id: "agent_activity", label: "Agent Activity", desc: "Audit Log" },
  { id: "thresholds", label: "Admin Control", desc: "Thresholds & Controls" },
];

const NAV_ICONS = {
  overview: "◉",
  revenue_realization: "▣",
  billing_trigger: "◫",
  unbilled_revenue: "◷",
  collection_monitoring: "◎",
  revenue_forecasting: "◈",
  agent_activity: "◌",
  thresholds: "◧",
};

// ── Helpers ───────────────────────────────────────────────────────────────────
async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text();
    let msg = text;
    try {
      const json = JSON.parse(text);
      if (typeof json.detail === "string") msg = json.detail;
    } catch {}
    throw new Error(msg || `Request failed: ${url}`);
  }
  return res.json();
}

function riskCls(level) {
  if (level === "High") return "high";
  if (level === "Medium") return "medium";
  return "low";
}

function selKey(ref) {
  return ref ? `${ref.agent_key}:${ref.entity_type}:${ref.entity_id}` : "";
}

function sameSel(a, b) {
  return selKey(a) === selKey(b);
}

function makeRef(row, agentKey) {
  return {
    agent_key: agentKey,
    entity_type: row.entity_type,
    entity_id: row.entity_id,
  };
}

function findNudge(nudges, ref) {
  if (!ref || !nudges) return null;
  return (
    nudges.find(
      (n) => n.entity_id === ref.entity_id && n.entity_type === ref.entity_type
    ) || null
  );
}

function findRow(rows, ref) {
  if (!ref || !rows) return null;
  return rows.find((r) => r.entity_id === ref.entity_id) || null;
}

// ── Small UI Components ───────────────────────────────────────────────────────
function RiskBadge({ level }) {
  return (
    <span className={`risk-pill ${riskCls(level)}`}>{level || "—"}</span>
  );
}

// Composite risk for the Accounts overview table based on three KPIs:
// revenue gap %, unbilled revenue, and overdue AR
function compositeRisk(row) {
  const shortfall = row.revenue_plan > 0 ? Math.max(-row.revenue_gap, 0) / row.revenue_plan : 0;
  const unbilled = row.unbilled_amount || 0;
  const overdue = row.outstanding_collection || 0;
  if (shortfall >= 0.12 || unbilled >= 300_000 || overdue >= 200_000) return "High";
  if (shortfall >= 0.05 || unbilled >= 120_000 || overdue >= 100_000) return "Medium";
  return "Low";
}

function StatusBadge({ value }) {
  const cls = value ? value.toLowerCase().replace(/[\s/_]+/g, "-") : "";
  return (
    <span className={`status-pill ${cls}`}>{value || "—"}</span>
  );
}

function KpiCard({ label, value, sub, variant, info }) {
  return (
    <div className={`kpi-card${variant ? ` kpi-${variant}` : ""}`}>
      {info && (
        <>
          <span className="kpi-info">
            <span className="kpi-info-icon">i</span>
          </span>
          {/* Tooltip is a sibling of kpi-info, positioned relative to the card */}
          <span className="kpi-tooltip">{info}</span>
        </>
      )}
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}

function KpiGrid({ cards }) {
  return (
    <div className="kpi-grid">
      {cards.map((c, i) => (
        <KpiCard key={i} {...c} />
      ))}
    </div>
  );
}

function SectionHeader({ title, sub, right }) {
  return (
    <div className="section-header">
      <div>
        <h2 className="section-title">{title}</h2>
        {sub && <p className="section-sub">{sub}</p>}
      </div>
      {right && <div className="section-header-right">{right}</div>}
    </div>
  );
}

// ── Data Table ────────────────────────────────────────────────────────────────
function DataTable({
  columns,
  rows,
  onRowClick,
  selectedRef,
  agentKey,
  emptyText,
}) {
  const deferred = useDeferredValue(rows);
  return (
    <div className="table-shell">
      <table>
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                style={col.width ? { width: col.width, minWidth: col.width } : {}}
              >
                <span className="th-inner">
                  {col.label}
                  {col.info && (
                    <span className="col-info-wrap">
                      <span className="col-info-icon">i</span>
                      <span className="col-info-tooltip">{col.info}</span>
                    </span>
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {deferred.map((row, i) => {
            const risk = row.risk_level || row.collection_risk;
            const ref = agentKey ? makeRef(row, agentKey) : null;
            const isSelected = ref && selectedRef && sameSel(selectedRef, ref);
            return (
              <tr
                key={row.entity_id != null ? row.entity_id : i}
                className={[
                  risk ? `risk-row-${risk.toLowerCase()}` : "",
                  isSelected ? "selected-row" : "",
                  onRowClick ? "clickable-row" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={() => onRowClick && onRowClick(row)}
              >
                {columns.map((col) => (
                  <td key={col.key}>
                    {col.render
                      ? col.render(row[col.key], row)
                      : row[col.key] ?? "—"}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
      {deferred.length === 0 && (
        <div className="empty-state slim">
          <span>{emptyText || "All clear — no items found."}</span>
        </div>
      )}
    </div>
  );
}

// ── Analysis Widget ───────────────────────────────────────────────────────────
function AnalysisWidget({ analysis }) {
  if (!analysis) return null;
  return (
    <div className="analysis-widget">
      <div className="aw-headline">{analysis.headline}</div>

      {analysis.why_triggered && (
        <div className="aw-block">
          <div className="aw-block-label">Why Triggered</div>
          <div className="aw-block-text">{analysis.why_triggered}</div>
        </div>
      )}

      {analysis.current_status && (
        <div className="aw-block">
          <div className="aw-block-label">Current Status</div>
          <div className="aw-block-text">{analysis.current_status}</div>
        </div>
      )}

      {analysis.recommended_action && (
        <div className="aw-action">
          <span className="aw-action-icon">→</span> {analysis.recommended_action}
        </div>
      )}

      {analysis.formula_inputs && analysis.formula_inputs.length > 0 && (
        <div className="aw-metrics">
          {analysis.formula_inputs.slice(0, 4).map((f, i) => (
            <div key={i} className="aw-metric">
              <div className="aw-metric-label">{f.label}</div>
              <div className="aw-metric-value">{f.display_value}</div>
            </div>
          ))}
        </div>
      )}

      {analysis.threshold_checks &&
        analysis.threshold_checks.some((t) => t.breached_level) && (
          <div className="aw-thresholds">
            {analysis.threshold_checks
              .filter((t) => t.breached_level)
              .map((t, i) => (
                <div
                  key={i}
                  className={`aw-threshold-row ${riskCls(t.breached_level)}`}
                >
                  <span>{t.label}</span>
                  <span>
                    {t.current_display} — <RiskBadge level={t.breached_level} />
                  </span>
                </div>
              ))}
          </div>
        )}

      {analysis.confidence_display && (
        <div className="aw-confidence">
          <span className="aw-confidence-label">Confidence</span>
          <span className="aw-confidence-value">{analysis.confidence_display}</span>
        </div>
      )}
    </div>
  );
}

// ── Draft Widget ──────────────────────────────────────────────────────────────
function DraftWidget({ draft, sending, channel, setChannel, onApprove }) {
  const [body, setBody] = useState(draft?.email_body || "");
  const [toEmail, setToEmail] = useState(draft?.recipient_email || "");
  const [ccEmails, setCcEmails] = useState("");

  useEffect(() => {
    setBody(draft?.email_body || "");
    setToEmail(draft?.recipient_email || "");
  }, [draft?.email_body, draft?.recipient_email]);

  if (!draft) return null;

  return (
    <div className="draft-widget">
      <div className="dw-header">
        <div className="dw-header-label">AI Draft</div>
        {draft.risk_level && <RiskBadge level={draft.risk_level} />}
      </div>

      {draft.nudge && <div className="dw-nudge">{draft.nudge}</div>}

      <div className="dw-field">
        <label className="dw-field-label">To</label>
        <input
          className="dw-email-input"
          type="email"
          value={toEmail}
          onChange={(e) => setToEmail(e.target.value)}
          placeholder="recipient@gmail.com"
        />
      </div>

      <div className="dw-field">
        <label className="dw-field-label">CC (optional)</label>
        <input
          className="dw-email-input"
          type="text"
          value={ccEmails}
          onChange={(e) => setCcEmails(e.target.value)}
          placeholder="cc1@gmail.com, cc2@gmail.com"
        />
      </div>

      <div className="dw-field">
        <label className="dw-field-label">Subject</label>
        <div className="dw-subject">{draft.email_subject || "—"}</div>
      </div>

      <div className="dw-field">
        <label className="dw-field-label">Message (editable)</label>
        <textarea
          className="dw-body"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={7}
        />
      </div>

      {draft.supporting_facts && draft.supporting_facts.length > 0 && (
        <div className="dw-facts">
          <div className="dw-field-label">Supporting Facts</div>
          <ul className="dw-facts-list">
            {draft.supporting_facts.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="dw-channel-row">
        <label className="dw-field-label">Send via</label>
        <select
          className="dw-select"
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
        >
          <option value="email">Email</option>
          <option value="gmail">Gmail</option>
        </select>
      </div>

      <button
        className="btn-primary dw-approve-btn"
        onClick={() => onApprove && onApprove(body, toEmail, ccEmails)}
        disabled={sending}
      >
        {sending ? "Sending…" : "✓ Approve & Send"}
      </button>
    </div>
  );
}

// ── Draft Modal ────────────────────────────────────────────────────────────────
function DraftModal({ open, draft, draftLoading, sending, channel, setChannel, onApprove, onClose }) {
  if (!open) return null;
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">AI Draft — Review &amp; Send</span>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        {draftLoading ? (
          <div className="ai-generating modal-loading">
            <div className="ai-spinner" />
            <span>AI is analyzing…</span>
          </div>
        ) : (
          <DraftWidget
            draft={draft}
            sending={sending}
            channel={channel}
            setChannel={setChannel}
            onApprove={onApprove}
          />
        )}
      </div>
    </div>
  );
}

// ── Project Detail Modal ───────────────────────────────────────────────────────
function ProjectDetailModal({ row, crossData, onClose, onAnalyze, draftLoading }) {
  if (!row) return null;
  const project = row.project_code;
  const billingRows = (crossData?.billing || []).filter((r) => r.project_code === project);
  const unbilledRow = (crossData?.unbilled || []).find((r) => r.project_code === project);
  const collectionRows = (crossData?.collections || []).filter((r) => r.project_code === project);
  const forecastRow = (crossData?.forecast || []).find((r) => r.project_code === project);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box modal-box--wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="pdm-title-block">
            <span className="modal-title">{row.account_name}</span>
            <span className="pdm-sub">{project} · {row.delivery_unit || ""}</span>
          </div>
          <div className="pdm-header-right">
            <RiskBadge level={row.risk_level} />
            <button className="modal-close" onClick={onClose}>✕</button>
          </div>
        </div>

        <div className="pdm-body">
          {/* Revenue Realization */}
          <div className="pdm-domain">
            <div className="pdm-domain-title">Revenue Realization</div>
            <div className="pdm-metrics">
              {[
                { label: "Revenue Plan", val: shortMoney(row.revenue_plan || 0) },
                { label: "Recognized", val: shortMoney(row.revenue_recognized || 0) },
                { label: "Revenue Gap", val: shortMoney(row.revenue_gap || 0), color: (row.revenue_gap || 0) < 0 ? "var(--danger)" : "var(--success)" },
                { label: "Completion", val: pctFmt.format(row.revenue_completion_pct || 0) },
                { label: "Forecast", val: shortMoney(row.revenue_forecast || 0) },
                { label: "Burn Rate", val: shortMoney(row.revenue_burn_rate || 0) + "/wk" },
              ].map(({ label, val, color }) => (
                <div className="pdm-metric" key={label}>
                  <span className="pdm-mlabel">{label}</span>
                  <span className="pdm-mval" style={color ? { color } : {}}>{val}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Unbilled Revenue */}
          <div className="pdm-domain">
            <div className="pdm-domain-title">Unbilled Revenue</div>
            {unbilledRow ? (
              <div className="pdm-metrics">
                {[
                  { label: "Unbilled Amount", val: shortMoney(unbilledRow.unbilled_revenue || 0), color: (unbilledRow.unbilled_revenue || 0) > 0 ? "var(--warning)" : undefined },
                  { label: "Revenue Recognized", val: shortMoney(unbilledRow.revenue_recognized || 0) },
                  { label: "Revenue Billed", val: shortMoney(unbilledRow.revenue_billed || 0) },
                  { label: "Days Unbilled", val: `${unbilledRow.days_unbilled ?? 0} days` },
                ].map(({ label, val, color }) => (
                  <div className="pdm-metric" key={label}>
                    <span className="pdm-mlabel">{label}</span>
                    <span className="pdm-mval" style={color ? { color } : {}}>{val}</span>
                  </div>
                ))}
              </div>
            ) : row.unbilled_amount > 0 ? (
              <div className="pdm-metrics">
                <div className="pdm-metric">
                  <span className="pdm-mlabel">Unbilled Amount</span>
                  <span className="pdm-mval" style={{ color: "var(--warning)" }}>{shortMoney(row.unbilled_amount)}</span>
                </div>
              </div>
            ) : (
              <div className="pdm-none">✓ No unbilled exposure</div>
            )}
          </div>

          {/* Billing Triggers */}
          <div className="pdm-domain">
            <div className="pdm-domain-title">Billing Triggers</div>
            {billingRows.length > 0 ? (
              <div className="pdm-billing-list">
                {billingRows.map((b, i) => (
                  <div className="pdm-billing-row" key={i}>
                    <div className="pdm-metrics">
                      {[
                        { label: "Milestone", val: b.billing_milestone || "—" },
                        { label: "Billable Amount", val: shortMoney(b.billable_amount || 0) },
                        { label: "Unbilled", val: shortMoney(b.unbilled_amount || 0), color: (b.unbilled_amount || 0) > 0 ? "var(--warning)" : undefined },
                        { label: "Status", val: b.billing_status || "—" },
                        { label: "Delay", val: b.billing_delay_days ? `${b.billing_delay_days} days` : "—" },
                      ].map(({ label, val, color }) => (
                        <div className="pdm-metric" key={label}>
                          <span className="pdm-mlabel">{label}</span>
                          <span className="pdm-mval" style={color ? { color } : {}}>{val}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="pdm-none">✓ No pending billing milestones</div>
            )}
          </div>

          {/* Collections / AR */}
          <div className="pdm-domain">
            <div className="pdm-domain-title">Collections / AR</div>
            {collectionRows.length > 0 ? (
              <div className="pdm-billing-list">
                {collectionRows.map((c, i) => (
                  <div className="pdm-billing-row" key={i}>
                    <div className="pdm-metrics">
                      {[
                        { label: "Invoice", val: c.invoice_number || "—" },
                        { label: "Invoice Amount", val: shortMoney(c.invoice_amount || 0) },
                        { label: "Outstanding", val: shortMoney(c.outstanding_balance || 0), color: (c.outstanding_balance || 0) > 0 ? "var(--danger)" : undefined },
                        { label: "Days Outstanding", val: `${c.days_outstanding ?? 0} days` },
                        { label: "Due Date", val: fmtDate(c.payment_due_date) },
                      ].map(({ label, val, color }) => (
                        <div className="pdm-metric" key={label}>
                          <span className="pdm-mlabel">{label}</span>
                          <span className="pdm-mval" style={color ? { color } : {}}>{val}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : row.outstanding_collection > 0 ? (
              <div className="pdm-metrics">
                <div className="pdm-metric">
                  <span className="pdm-mlabel">Outstanding AR</span>
                  <span className="pdm-mval" style={{ color: "var(--danger)" }}>{shortMoney(row.outstanding_collection)}</span>
                </div>
              </div>
            ) : (
              <div className="pdm-none">✓ No overdue AR</div>
            )}
          </div>

          {/* Revenue Forecast */}
          <div className="pdm-domain">
            <div className="pdm-domain-title">Revenue Forecast</div>
            {forecastRow ? (
              <div className="pdm-metrics">
                {[
                  { label: "Forecast", val: shortMoney(forecastRow.revenue_forecast || 0) },
                  { label: "Revenue Gap", val: shortMoney(forecastRow.revenue_gap || 0), color: (forecastRow.revenue_gap || 0) < 0 ? "var(--danger)" : "var(--success)" },
                  { label: "Confidence", val: forecastRow.forecast_confidence != null ? pctFmt.format(forecastRow.forecast_confidence) : "—" },
                ].map(({ label, val, color }) => (
                  <div className="pdm-metric" key={label}>
                    <span className="pdm-mlabel">{label}</span>
                    <span className="pdm-mval" style={color ? { color } : {}}>{val}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="pdm-none">No forecast data available</div>
            )}
          </div>
        </div>

        <div className="pdm-footer">
          <button className="btn-secondary" onClick={onClose}>Close</button>
          <button
            className="btn-primary"
            onClick={onAnalyze}
            disabled={draftLoading}
          >
            {draftLoading ? "Generating…" : "Analyze & Draft Action"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── AI Panel ──────────────────────────────────────────────────────────────────
function AiPanel({
  panelItems,
  selectedRef,
  onNudgeSelect,
  sectionRows,
  draft,
  draftLoading,
  onGenerate,
  showNudgeQueue,
  panelTitle,
  panelDesc,
}) {
  const [alertsOpen, setAlertsOpen] = useState(true);
  const selectedRow =
    sectionRows && selectedRef ? findRow(sectionRows, selectedRef) : null;
  const nudge =
    panelItems && selectedRef ? findNudge(panelItems, selectedRef) : null;
  const hasDraft =
    draft && selectedRef && sameSel(draft, selectedRef);

  // ── Overview: Nudge Queue mode ──────────────────────────────────────────────
  if (showNudgeQueue) {
    return (
      <aside className="ai-panel">
        <button
          className="accordion-toggle"
          onClick={() => setAlertsOpen((v) => !v)}
        >
          <div className="accordion-toggle-left">
            <span className="ai-panel-title">Agent Alerts</span>
            {panelItems && panelItems.length > 0 && (
              <span className="ai-panel-count">{panelItems.length}</span>
            )}
          </div>
          <span className="accordion-chevron">{alertsOpen ? "▲" : "▼"}</span>
        </button>

        {alertsOpen && (
          <>
            {(!panelItems || panelItems.length === 0) && (
              <div className="ai-empty">
                <div className="ai-empty-icon">✓</div>
                <div className="ai-empty-text">
                  All accounts on track. No action required today.
                </div>
              </div>
            )}
            <div className="nudge-list">
              {(panelItems || []).map((n) => {
                const ref = {
                  agent_key: n.agent_key,
                  entity_type: n.entity_type,
                  entity_id: n.entity_id,
                };
                const isActive = selectedRef && sameSel(selectedRef, ref);
                return (
                  <div
                    key={n.id}
                    className={`nudge-card severity-${riskCls(n.severity)}${isActive ? " active" : ""}`}
                  >
                    <div className="nc-top">
                      <div className="nc-account">{n.account_name}</div>
                      <RiskBadge level={n.severity} />
                    </div>
                    <div className="nc-title">{n.title}</div>
                    <div className="nc-message">{n.message}</div>
                    {n.suggested_action && (
                      <div className="nc-action">→ {n.suggested_action}</div>
                    )}
                    <div className="nc-buttons">
                      <button
                        className="btn-sm btn-primary"
                        onClick={() => onNudgeSelect(ref)}
                        disabled={draftLoading}
                      >
                        {isActive && hasDraft ? "Regenerate" : "Analyze & Draft"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
            {draftLoading && (
              <div className="ai-generating">
                <div className="ai-spinner" />
                <span>AI is analyzing…</span>
              </div>
            )}
          </>
        )}
      </aside>
    );
  }

  // ── Module: Detail / Entity mode ────────────────────────────────────────────
  return (
    <aside className="ai-panel">
      {panelTitle && (
        <div className="ai-panel-header ai-panel-header--module">
          <span className="ai-panel-title">{panelTitle}</span>
          {panelDesc && <span className="ai-panel-desc">{panelDesc}</span>}
        </div>
      )}
      {!selectedRow ? (
        <div className="ai-empty">
          <div className="ai-empty-icon">◉</div>
          <div className="ai-empty-text">
            Select a row from the table to review details and generate an AI action draft.
          </div>
          {panelItems && panelItems.length > 0 && (
            <div className="ai-section-nudges">
              <div className="ai-nudges-label">
                Open Alerts ({panelItems.length})
              </div>
              {panelItems.slice(0, 4).map((n) => (
                <div
                  key={n.id}
                  className={`mini-nudge severity-${riskCls(n.severity)}`}
                >
                  <RiskBadge level={n.severity} />
                  <span>
                    {n.account_name} — {n.title}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="detail-panel">
          <div className="dp-header">
            <div>
              <div className="dp-account">{selectedRow.account_name}</div>
              <div className="dp-project">
                {selectedRow.project_code || selectedRow.invoice_number || ""}
              </div>
            </div>
            <RiskBadge
              level={selectedRow.risk_level || selectedRow.collection_risk}
            />
          </div>

          {nudge && (
            <div className="dp-nudge-block">
              <div className="dp-nudge-title">{nudge.title}</div>
              <div className="dp-nudge-msg">{nudge.message}</div>
              {nudge.suggested_action && (
                <div className="dp-nudge-action">→ {nudge.suggested_action}</div>
              )}
            </div>
          )}

          {selectedRow.analysis && (
            <AnalysisWidget analysis={selectedRow.analysis} />
          )}

          <button
            className="btn-primary dp-generate-btn"
            onClick={() => onGenerate()}
            disabled={draftLoading}
          >
            {draftLoading ? "Generating Draft…" : hasDraft ? "↻ Regenerate Draft" : "Generate AI Draft"}
          </button>

          {draftLoading && (
            <div className="ai-generating">
              <div className="ai-spinner" />
              <span>AI is drafting…</span>
            </div>
          )}
        </div>
      )}
    </aside>
  );
}

// ── Overview Page ─────────────────────────────────────────────────────────────
function OverviewPage({
  dashboard,
  selectedRef,
  onNudgeSelect,
  onRowClick,
  draft,
  draftLoading,
  sending,
  channel,
  setChannel,
  onGenerate,
  onApprove,
}) {
  const [detailRow, setDetailRow] = useState(null);
  const crossData = {
    billing: dashboard.billing_trigger?.rows,
    unbilled: dashboard.unbilled_revenue?.rows,
    collections: dashboard.collection_monitoring?.rows,
    forecast: dashboard.revenue_forecasting?.rows,
  };

  function handleRowSelect(row) {
    setDetailRow(row);
    onRowClick && onRowClick(row);
  }

  const ov = dashboard.overview;
  const narrative = dashboard.narrative;
  const queue = dashboard.queue || [];
  const completionPct =
    ov.revenue_plan > 0 ? ov.revenue_recognized / ov.revenue_plan : 0;
  const gap = ov.revenue_forecast - ov.revenue_plan;

  const kpis = [
    {
      label: "Revenue Recognized",
      value: shortMoney(ov.revenue_recognized),
      sub: `of ${shortMoney(ov.revenue_plan)} plan · ${pctFmt.format(completionPct)}`,
      variant: completionPct < 0.8 ? "danger" : completionPct < 0.95 ? "warning" : "success",
      info: "Total revenue earned and booked across all projects this month. Completion % = Recognized ÷ Plan.",
    },
    {
      label: "Revenue Forecast",
      value: shortMoney(ov.revenue_forecast),
      sub: `Gap: ${gap >= 0 ? "+" : ""}${shortMoney(gap)}`,
      variant: gap < 0 ? "danger" : "success",
      info: "= Σ (Recognized + trend + milestone + pipeline) across all projects.\n• Trend = 7-day burn × remaining weeks\n• Milestone = 10% of pending billable\n• Pipeline = 20% of near-term pipeline",
    },
    {
      label: "Invoices Generated",
      value: ov.invoices_generated.toLocaleString(),
      sub: "This period",
      variant: "neutral",
      info: "Total count of invoices created across all projects in the current period.",
    },
    {
      label: "Unbilled Revenue",
      value: shortMoney(ov.unbilled_revenue),
      sub: "Recognized, not billed",
      variant: ov.unbilled_revenue > 200_000 ? "warning" : "neutral",
      info: "= Σ max(Revenue Recognized − Revenue Billed, 0) per project. Revenue that is earned and booked but no invoice has been raised yet.",
    },
    {
      label: "Outstanding AR",
      value: shortMoney(ov.outstanding_receivables),
      sub: "Pending collection",
      variant: ov.outstanding_receivables > 500_000 ? "warning" : "neutral",
      info: "= Σ max(Invoice Amount − Amount Received, 0) across all open invoices. Total unpaid balance pending collection.",
    },
    {
      label: "Revenue at Risk",
      value: shortMoney(ov.revenue_at_risk),
      sub: "High-risk exposure",
      variant: ov.revenue_at_risk > 300_000 ? "danger" : "warning",
      info: "= Σ max(Revenue Plan − Revenue Forecast, 0) per project. Measures the total shortfall for all projects where forecast is below plan.",
    },
  ];

  // All revenue rows with composite risk (revenue gap %, unbilled, overdue AR) sorted High→Low
  const allAccountRows = (dashboard.revenue_realization?.rows || [])
    .slice()
    .map((row) => ({ ...row, risk_level: compositeRisk(row) }))
    .sort((a, b) => {
      const order = { High: 0, Medium: 1, Low: 2 };
      const riskDiff = (order[a.risk_level] ?? 3) - (order[b.risk_level] ?? 3);
      if (riskDiff !== 0) return riskDiff;
      // Within same risk tier: sort by worst signal first
      return Math.min(b.revenue_gap, 0) - Math.min(a.revenue_gap, 0);
    });

  const atRiskCols = [
    { key: "account_name", label: "Account", info: "Client / company name for this project." },
    { key: "project_code", label: "Project", info: "Unique project identifier assigned internally." },
    {
      key: "revenue_gap",
      label: "Revenue Gap",
      info: "Forecast − Plan. Negative means the project is projected to miss its monthly revenue target.",
      render: (v) => (
        <span style={{ color: v < 0 ? "var(--danger)" : "inherit" }}>
          {shortMoney(v)}
        </span>
      ),
    },
    {
      key: "unbilled_amount",
      label: "Unbilled",
      info: "Revenue recognized (earned) but not yet invoiced to the client.",
      render: (v) => shortMoney(v || 0),
    },
    {
      key: "outstanding_collection",
      label: "Overdue AR",
      info: "Invoice amount that is past its due date and still unpaid by the client.",
      render: (v) => shortMoney(v || 0),
    },
    {
      key: "risk_level",
      label: "Risk",
      info: "Composite health across 3 signals. High: revenue gap >12% of plan, Unbilled >$300K, or Overdue AR >$200K. Medium: gap >5%, Unbilled >$120K, or Overdue AR >$100K. Low: all within limits.",
      render: (v) => <RiskBadge level={v} />,
    },
    {
      key: "_analyze",
      label: "",
      render: (_, row) => (
        <button
          className="btn-sm btn-primary row-analyze-btn"
          onClick={(e) => {
            e.stopPropagation();
            onRowClick && onRowClick(row);
            const ref = { agent_key: "revenue_realization", entity_type: row.entity_type, entity_id: row.entity_id };
            onGenerate && onGenerate(ref);
          }}
          disabled={draftLoading}
        >
          Analyze & Draft
        </button>
      ),
    },
  ];

  return (
    <div className="overview-layout">
      <KpiGrid cards={kpis} />

      <div className="overview-body">
        <div className="overview-main">
          {/* Morning narrative */}
          <div className="panel narrative-panel">
            <div className="panel-kicker">Morning Report</div>
            <div className="narrative-headline">{narrative.headline}</div>
            <p className="narrative-copy">{narrative.narrative}</p>

            {narrative.top_accounts && narrative.top_accounts.length > 0 && (
              <div className="narrative-accounts">
                <div className="narrative-accounts-title">
                  Top Accounts Needing Attention
                </div>
                {narrative.top_accounts.slice(0, 5).map((acc, i) => (
                  <div key={i} className="na-row">
                    <span className="na-name">{acc.account_name}</span>
                    <div className="na-metrics">
                      <span className="na-metric">
                        Revenue Gap:{" "}
                        <strong
                          style={{
                            color:
                              Number(acc.forecast_gap) < 0
                                ? "var(--danger)"
                                : "var(--success)",
                          }}
                        >
                          {shortMoney(Number(acc.forecast_gap))}
                        </strong>
                      </span>
                      {Number(acc.unbilled_revenue) > 0 && (
                        <span className="na-metric">
                          Unbilled:{" "}
                          <strong>
                            {shortMoney(Number(acc.unbilled_revenue))}
                          </strong>
                        </span>
                      )}
                      {Number(acc.overdue_amount) > 0 && (
                        <span className="na-metric">
                          Overdue:{" "}
                          <strong>
                            {shortMoney(Number(acc.overdue_amount))}
                          </strong>
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Accounts table */}
          <div className="panel">
            <SectionHeader
              title="Accounts"
              sub={`${allAccountRows.length} projects · click a row to review full project details`}
            />
            <DataTable
              columns={atRiskCols}
              rows={allAccountRows}
              onRowClick={handleRowSelect}
              selectedRef={selectedRef}
              agentKey="revenue_realization"
              emptyText="No project data available."
            />
          </div>
        </div>

        <AiPanel
          panelItems={queue}
          selectedRef={selectedRef}
          onNudgeSelect={onNudgeSelect}
          draft={draft}
          draftLoading={draftLoading}
          sending={sending}
          channel={channel}
          setChannel={setChannel}
          onGenerate={onGenerate}
          onApprove={onApprove}
          showNudgeQueue={true}
        />
      </div>

      {detailRow && (
        <ProjectDetailModal
          row={detailRow}
          crossData={crossData}
          draftLoading={draftLoading}
          onClose={() => setDetailRow(null)}
          onAnalyze={() => {
            const ref = { agent_key: "revenue_realization", entity_type: detailRow.entity_type, entity_id: detailRow.entity_id };
            onGenerate(ref);
            setDetailRow(null);
          }}
        />
      )}
    </div>
  );
}

// ── Revenue Page ──────────────────────────────────────────────────────────────
function RevenuePage({
  section,
  selectedRef,
  onRowClick,
  draft,
  draftLoading,
  sending,
  channel,
  setChannel,
  onGenerate,
  onApprove,
}) {
  const s = section.summary;
  const kpis = [
    { label: "Revenue Plan", value: shortMoney(s.revenue_plan), variant: "neutral", info: "Monthly revenue target set for this project in the contract. Used as the baseline for gap and completion calculations." },
    {
      label: "Revenue Recognized",
      value: shortMoney(s.revenue_recognized),
      sub: pctFmt.format(s.revenue_completion_pct) + " complete",
      variant: s.revenue_completion_pct < 0.8 ? "danger" : "success",
      info: "Revenue earned and booked this month. Completion % = Recognized ÷ Plan. Flags danger below 80%.",
    },
    {
      label: "Revenue Remaining",
      value: shortMoney(s.revenue_remaining),
      variant: "neutral",
      info: "= max(Revenue Plan − Revenue Recognized, 0). Amount still needed to hit the monthly plan.",
    },
    {
      label: "Forecast",
      value: shortMoney(s.revenue_forecast),
      variant: s.revenue_gap < 0 ? "warning" : "success",
      info: "= Recognized + trend (7-day burn × remaining weeks) + milestone (10% of pending billable) + pipeline (20% of near-term pipeline). Capped at contract value.",
    },
    {
      label: "Forecast Gap",
      value: shortMoney(s.revenue_gap),
      variant: s.revenue_gap < 0 ? "danger" : "success",
      info: "= Revenue Forecast − Revenue Plan. Negative value means the project is projected to miss its monthly target.",
    },
  ];

  const columns = [
    { key: "account_name", label: "Account" },
    { key: "project_code", label: "Project" },
    { key: "delivery_unit", label: "Delivery Unit" },
    { key: "account_manager", label: "Manager" },
    { key: "revenue_plan", label: "Plan", render: (v) => shortMoney(v) },
    { key: "revenue_recognized", label: "Recognized", render: (v) => shortMoney(v) },
    {
      key: "revenue_gap",
      label: "Revenue Gap",
      render: (v) => (
        <span style={{ color: v < 0 ? "var(--danger)" : "var(--success)" }}>
          {shortMoney(v)}
        </span>
      ),
    },
    {
      key: "revenue_completion_pct",
      label: "% Done",
      render: (v) => pctFmt.format(v),
    },
    {
      key: "revenue_burn_rate",
      label: "Burn Rate",
      render: (v) => shortMoney(v) + "/wk",
    },
    { key: "risk_level", label: "Risk", render: (v) => <RiskBadge level={v} /> },
  ];

  return (
    <div className="module-layout">
      <div className="module-main">
        <KpiGrid cards={kpis} />
        <div className="panel table-panel">
          <SectionHeader
            title="Revenue Realization"
            sub="Project-level revenue monitoring"
            right={
              <span className="table-count">{section.rows.length} projects</span>
            }
          />
          <DataTable
            columns={columns}
            rows={section.rows}
            onRowClick={onRowClick}
            selectedRef={selectedRef}
            agentKey="revenue_realization"
          />
        </div>
      </div>
      <div className="module-sidebar">
        <AiPanel
          panelItems={section.nudges}
          selectedRef={selectedRef}
          sectionRows={section.rows}
          draft={draft}
          draftLoading={draftLoading}
          sending={sending}
          channel={channel}
          setChannel={setChannel}
          onGenerate={onGenerate}
          onApprove={onApprove}
          showNudgeQueue={false}
          panelTitle="AI Action Panel"
          panelDesc="Select a project to review revenue gaps and draft account manager follow-ups."
        />
      </div>
    </div>
  );
}

// ── Billing Page ──────────────────────────────────────────────────────────────
function BillingPage({
  section,
  selectedRef,
  onRowClick,
  draft,
  draftLoading,
  sending,
  channel,
  setChannel,
  onGenerate,
  onApprove,
}) {
  const s = section.summary;
  const kpis = [
    { label: "Billable Amount", value: shortMoney(s.billable_amount), variant: "neutral", info: "Total value of completed milestones eligible for invoicing. = Σ billable_amount across approved milestones." },
    {
      label: "Invoices Generated",
      value: s.invoices_generated.toLocaleString(),
      variant: "neutral",
      info: "Count of invoices successfully created for completed milestones in this period.",
    },
    {
      label: "Invoices Pending",
      value: s.invoices_pending.toLocaleString(),
      variant: s.invoices_pending > 5 ? "warning" : "neutral",
      info: "Count of completed milestones where an invoice has not yet been created. Each pending milestone delays cash flow.",
    },
    {
      label: "Unbilled Revenue",
      value: shortMoney(s.unbilled_revenue),
      variant: s.unbilled_revenue > 100_000 ? "danger" : "warning",
      info: "= Σ max(Billable Amount − Billed Amount, 0) per milestone. Work is done and billable, but the invoice hasn't been raised.",
    },
    {
      label: "Avg Billing Delay",
      value: `${s.average_billing_delay.toFixed(0)}d`,
      sub: "Average days delayed",
      variant: s.average_billing_delay > 7 ? "warning" : "neutral",
      info: "= Average (Invoice Date − Milestone Completion Date) in days, across invoiced milestones. High delay signals slow billing turnaround.",
    },
    {
      label: "Billing Risk",
      value: shortMoney(s.billing_risk_amount),
      variant: "danger",
      info: "Total unbilled amount on milestones flagged as High risk — completed but not invoiced beyond the threshold.",
    },
  ];

  const columns = [
    { key: "account_name", label: "Account" },
    { key: "project_code", label: "Project" },
    { key: "billing_milestone", label: "Milestone" },
    { key: "billing_type", label: "Type" },
    {
      key: "milestone_completion_date",
      label: "Completed",
      render: (v) => fmtDate(v),
    },
    {
      key: "billable_amount",
      label: "Billable",
      render: (v) => shortMoney(v),
    },
    {
      key: "invoice_generated",
      label: "Invoiced",
      render: (v) =>
        v ? (
          <StatusBadge value="Yes" />
        ) : (
          <StatusBadge value="No" />
        ),
    },
    {
      key: "billing_delay_days",
      label: "Delay",
      render: (v) => (
        <span
          style={{
            color:
              v > 15
                ? "var(--danger)"
                : v > 7
                ? "var(--warning)"
                : "inherit",
          }}
        >
          {v}d
        </span>
      ),
    },
    {
      key: "billing_status",
      label: "Status",
      render: (v) => <StatusBadge value={v} />,
    },
    {
      key: "risk_level",
      label: "Risk",
      render: (v) => <RiskBadge level={v} />,
    },
  ];

  return (
    <div className="module-layout">
      <div className="module-main">
        <KpiGrid cards={kpis} />
        <div className="panel table-panel">
          <SectionHeader
            title="Billing Trigger Monitor"
            sub="Milestone-level billing tracking"
            right={
              <span className="table-count">{section.rows.length} milestones</span>
            }
          />
          <DataTable
            columns={columns}
            rows={section.rows}
            onRowClick={onRowClick}
            selectedRef={selectedRef}
            agentKey="billing_trigger"
          />
        </div>
      </div>
      <div className="module-sidebar">
        <AiPanel
          panelItems={section.nudges}
          selectedRef={selectedRef}
          sectionRows={section.rows}
          draft={draft}
          draftLoading={draftLoading}
          sending={sending}
          channel={channel}
          setChannel={setChannel}
          onGenerate={onGenerate}
          onApprove={onApprove}
          showNudgeQueue={false}
          panelTitle="AI Action Panel"
          panelDesc="Select a milestone to review billing readiness and draft invoicing notifications."
        />
      </div>
    </div>
  );
}

// ── Unbilled Page ─────────────────────────────────────────────────────────────
function UnbilledPage({
  section,
  selectedRef,
  onRowClick,
  draft,
  draftLoading,
  sending,
  channel,
  setChannel,
  onGenerate,
  onApprove,
}) {
  const s = section.summary;
  const kpis = [
    {
      label: "Total Recognized",
      value: shortMoney(s.total_revenue_recognized),
      variant: "neutral",
      info: "Total revenue earned and booked across all projects. This is the starting point — anything recognized but not invoiced appears as Unbilled.",
    },
    {
      label: "Total Billed",
      value: shortMoney(s.total_revenue_billed),
      variant: "neutral",
      info: "Sum of all invoice amounts raised against recognized revenue. Compare to Total Recognized to see the billing gap.",
    },
    {
      label: "Total Unbilled",
      value: shortMoney(s.total_unbilled_revenue),
      variant: s.total_unbilled_revenue > 200_000 ? "danger" : "warning",
      info: "= Σ max(Revenue Recognized − Revenue Billed, 0) per project. Revenue booked in P&L but not yet converted to an invoice.",
    },
    {
      label: "Avg Days Unbilled",
      value: `${s.average_days_unbilled.toFixed(0)}d`,
      variant: s.average_days_unbilled > 10 ? "warning" : "neutral",
      info: "Average age of the oldest pending billable milestone per project (today − milestone completion date). High values increase cash-flow risk.",
    },
    {
      label: "High Risk Unbilled",
      value: shortMoney(s.high_risk_unbilled_revenue),
      variant: "danger",
      info: "Unbilled revenue on projects whose aging exceeds the High-risk threshold. These need immediate billing action.",
    },
  ];

  const columns = [
    { key: "account_name", label: "Account" },
    { key: "project_code", label: "Project" },
    { key: "delivery_unit", label: "Delivery Unit" },
    { key: "account_manager", label: "Manager" },
    {
      key: "revenue_recognized",
      label: "Recognized",
      render: (v) => shortMoney(v),
    },
    {
      key: "revenue_billed",
      label: "Billed",
      render: (v) => shortMoney(v),
    },
    {
      key: "unbilled_revenue",
      label: "Unbilled",
      render: (v) => (
        <strong
          style={{ color: v > 50_000 ? "var(--danger)" : "inherit" }}
        >
          {shortMoney(v)}
        </strong>
      ),
    },
    {
      key: "days_unbilled",
      label: "Days Unbilled",
      render: (v) => (
        <span
          style={{ color: v > 10 ? "var(--warning)" : "inherit" }}
        >
          {v}d
        </span>
      ),
    },
    { key: "billing_owner", label: "Billing Owner" },
    {
      key: "risk_level",
      label: "Risk",
      render: (v) => <RiskBadge level={v} />,
    },
  ];

  return (
    <div className="module-layout">
      <div className="module-main">
        <KpiGrid cards={kpis} />
        <div className="panel table-panel">
          <SectionHeader
            title="Unbilled Revenue Detection"
            sub="Revenue recognized but not yet invoiced"
            right={
              <span className="table-count">{section.rows.length} projects</span>
            }
          />
          <DataTable
            columns={columns}
            rows={section.rows}
            onRowClick={onRowClick}
            selectedRef={selectedRef}
            agentKey="unbilled_revenue"
          />
        </div>
      </div>
      <div className="module-sidebar">
        <AiPanel
          panelItems={section.nudges}
          selectedRef={selectedRef}
          sectionRows={section.rows}
          draft={draft}
          draftLoading={draftLoading}
          sending={sending}
          channel={channel}
          setChannel={setChannel}
          onGenerate={onGenerate}
          onApprove={onApprove}
          showNudgeQueue={false}
          panelTitle="AI Action Panel"
          panelDesc="Select a project to review unbilled work and draft billing trigger requests."
        />
      </div>
    </div>
  );
}

// ── Collections Page ──────────────────────────────────────────────────────────
function CollectionsPage({
  section,
  selectedRef,
  onRowClick,
  draft,
  draftLoading,
  sending,
  channel,
  setChannel,
  onGenerate,
  onApprove,
}) {
  const s = section.summary;
  const kpis = [
    { label: "Total Invoiced", value: shortMoney(s.total_invoiced), variant: "neutral", info: "Total value of invoices sent to clients in this period. This is the gross billing base used for DSO and collection rate calculations." },
    {
      label: "Total Collected",
      value: shortMoney(s.total_collected),
      variant: "success",
      info: "Sum of all payments received against invoices in this period. Collection rate = Collected ÷ Invoiced.",
    },
    {
      label: "Outstanding AR",
      value: shortMoney(s.outstanding_receivables),
      variant: s.outstanding_receivables > 400_000 ? "warning" : "neutral",
      info: "= Σ max(Invoice Amount − Amount Received, 0) across all open invoices. Total unpaid balance still pending collection.",
    },
    {
      label: "DSO",
      value: `${s.dso.toFixed(0)}d`,
      sub: "Days Sales Outstanding",
      variant: s.dso > 45 ? "danger" : s.dso > 30 ? "warning" : "success",
      info: "= (Outstanding AR ÷ Total Invoiced) × Days in period. Measures how quickly invoices are collected. Lower is better. >30d = warning, >45d = high risk.",
    },
    {
      label: "Overdue Amount",
      value: shortMoney(s.overdue_amount),
      variant: s.overdue_amount > 100_000 ? "danger" : "warning",
      info: "= Σ max(Invoice Amount − Amount Received, 0) for invoices past their payment due date. Signals collection follow-up needed.",
    },
    {
      label: "High Risk Receivables",
      value: `${s.high_risk_receivables.toFixed(0)}`,
      sub: "accounts",
      variant: "danger",
      info: "Count of invoices overdue beyond the High-risk threshold. Each represents an escalation-level collection risk.",
    },
  ];

  const columns = [
    { key: "account_name", label: "Account" },
    { key: "invoice_number", label: "Invoice #" },
    { key: "project_code", label: "Project" },
    {
      key: "invoice_amount",
      label: "Invoice Amt",
      render: (v) => shortMoney(v),
    },
    {
      key: "invoice_date",
      label: "Invoice Date",
      render: (v) => fmtDate(v),
    },
    {
      key: "payment_due_date",
      label: "Due Date",
      render: (v) => fmtDate(v),
    },
    {
      key: "amount_received",
      label: "Collected",
      render: (v) => shortMoney(v),
    },
    {
      key: "outstanding_balance",
      label: "Outstanding",
      render: (v) => (
        <strong style={{ color: v > 0 ? "var(--warning)" : "inherit" }}>
          {shortMoney(v)}
        </strong>
      ),
    },
    {
      key: "overdue_days",
      label: "Overdue",
      render: (v) =>
        v > 0 ? (
          <span
            style={{
              color: v > 30 ? "var(--danger)" : "var(--warning)",
            }}
          >
            {v}d
          </span>
        ) : (
          "—"
        ),
    },
    {
      key: "collection_risk",
      label: "Risk",
      render: (v) => <RiskBadge level={v} />,
    },
    {
      key: "collection_status",
      label: "Status",
      render: (v) => <StatusBadge value={v} />,
    },
  ];

  return (
    <div className="module-layout">
      <div className="module-main">
        <KpiGrid cards={kpis} />
        <div className="panel table-panel">
          <SectionHeader
            title="Collection Monitoring"
            sub="Invoice-level AR tracking and collection status"
            right={
              <span className="table-count">{section.rows.length} invoices</span>
            }
          />
          <DataTable
            columns={columns}
            rows={section.rows}
            onRowClick={onRowClick}
            selectedRef={selectedRef}
            agentKey="collection_monitoring"
          />
        </div>
      </div>
      <div className="module-sidebar">
        <AiPanel
          panelItems={section.nudges}
          selectedRef={selectedRef}
          sectionRows={section.rows}
          draft={draft}
          draftLoading={draftLoading}
          sending={sending}
          channel={channel}
          setChannel={setChannel}
          onGenerate={onGenerate}
          onApprove={onApprove}
          showNudgeQueue={false}
          panelTitle="AI Action Panel"
          panelDesc="Select an invoice to review overdue AR and draft payment follow-up communications."
        />
      </div>
    </div>
  );
}

// ── Forecast Page ─────────────────────────────────────────────────────────────
function ForecastPage({
  section,
  selectedRef,
  onRowClick,
  draft,
  draftLoading,
  sending,
  channel,
  setChannel,
  onGenerate,
  onApprove,
}) {
  const s = section.summary;
  const kpis = [
    { label: "Revenue Plan", value: shortMoney(s.revenue_plan), variant: "neutral", info: "Aggregate monthly revenue target across all projects. Set from contract values and used as the benchmark for gap and confidence calculations." },
    {
      label: "Revenue Recognized",
      value: shortMoney(s.revenue_recognized),
      variant: "neutral",
      info: "Total revenue earned and booked across all projects this month. This is the confirmed baseline — the forecast builds on top of this.",
    },
    {
      label: "Forecast",
      value: shortMoney(s.revenue_forecast),
      variant: s.revenue_gap < 0 ? "warning" : "success",
      info: "= Recognized + trend + milestone + pipeline, capped at contract value.\n• Trend = 7-day burn rate × remaining weeks × forecast bias\n• Milestone = 10% of pending billable amount\n• Pipeline = 20% of near-term pipeline",
    },
    {
      label: "Forecast Gap",
      value: shortMoney(s.revenue_gap),
      variant: s.revenue_gap < 0 ? "danger" : "success",
      info: "= Revenue Forecast − Revenue Plan. Negative means the portfolio is projected to fall short of its monthly target.",
    },
    {
      label: "Confidence",
      value: pctFmt.format(s.forecast_confidence_score),
      variant: s.forecast_confidence_score < 0.6 ? "warning" : "success",
      info: "Base 92%.\n− up to 25% for stale revenue updates\n− up to 18% for high unbilled exposure\n− up to 22% for large forecast gap\n+ up to 12% for strong recognition pace\nClamped to 55%–96%.",
    },
  ];

  // Bar chart for top 8 projects
  const chartRows = section.rows.slice(0, 8);
  const maxVal = Math.max(
    ...chartRows.flatMap((r) => [r.revenue_plan, r.revenue_forecast]),
    1
  );

  const columns = [
    { key: "account_name", label: "Account" },
    { key: "project_code", label: "Project" },
    { key: "delivery_unit", label: "Delivery Unit" },
    { key: "revenue_plan", label: "Plan", render: (v) => shortMoney(v) },
    {
      key: "revenue_recognized",
      label: "Recognized",
      render: (v) => shortMoney(v),
    },
    {
      key: "revenue_forecast",
      label: "Forecast",
      render: (v) => shortMoney(v),
    },
    {
      key: "revenue_gap",
      label: "Revenue Gap",
      render: (v) => (
        <span style={{ color: v < 0 ? "var(--danger)" : "var(--success)" }}>
          {shortMoney(v)}
        </span>
      ),
    },
    {
      key: "forecast_confidence",
      label: "Confidence",
      render: (v) => pctFmt.format(v),
    },
    {
      key: "risk_level",
      label: "Risk",
      render: (v) => <RiskBadge level={v} />,
    },
  ];

  return (
    <div className="module-layout">
      <div className="module-main">
        <KpiGrid cards={kpis} />

        {/* Visual bar chart */}
        {chartRows.length > 0 && (
          <div className="panel forecast-chart-panel">
            <div className="panel-kicker">Revenue Forecast vs Plan (Top Projects)</div>
            <div className="forecast-chart">
              {chartRows.map((r) => {
                const planW = (r.revenue_plan / maxVal) * 100;
                const recW = (r.revenue_recognized / maxVal) * 100;
                const fcW = (r.revenue_forecast / maxVal) * 100;
                return (
                  <div key={r.entity_id} className="fc-row">
                    <div className="fc-label">
                      <span className="fc-code">{r.project_code}</span>
                      <span className="fc-account-name">{r.account_name}</span>
                    </div>
                    <div className="fc-bars">
                      <div className="fc-bar-group">
                        <div
                          className="fc-bar fc-plan"
                          style={{ width: `${planW}%` }}
                          title={`Plan: ${shortMoney(r.revenue_plan)}`}
                        />
                      </div>
                      <div className="fc-bar-group">
                        <div
                          className="fc-bar fc-recognized"
                          style={{ width: `${recW}%` }}
                          title={`Recognized: ${shortMoney(r.revenue_recognized)}`}
                        />
                      </div>
                      <div className="fc-bar-group">
                        <div
                          className="fc-bar fc-forecast"
                          style={{ width: `${fcW}%` }}
                          title={`Forecast: ${shortMoney(r.revenue_forecast)}`}
                        />
                      </div>
                    </div>
                    <div className="fc-value">{shortMoney(r.revenue_forecast)}</div>
                  </div>
                );
              })}
              <div className="fc-legend">
                <span className="fcl-item">
                  <span className="fcl-dot fcl-plan" />Plan
                </span>
                <span className="fcl-item">
                  <span className="fcl-dot fcl-recognized" />Recognized
                </span>
                <span className="fcl-item">
                  <span className="fcl-dot fcl-forecast" />Forecast
                </span>
              </div>
            </div>
          </div>
        )}

        <div className="panel table-panel">
          <SectionHeader
            title="Project Forecast Detail"
            sub="Revenue projections with confidence scoring"
            right={
              <span className="table-count">{section.rows.length} projects</span>
            }
          />
          <DataTable
            columns={columns}
            rows={section.rows}
            onRowClick={onRowClick}
            selectedRef={selectedRef}
            agentKey="revenue_forecasting"
          />
        </div>
      </div>
      <div className="module-sidebar">
        <AiPanel
          panelItems={section.nudges}
          selectedRef={selectedRef}
          sectionRows={section.rows}
          draft={draft}
          draftLoading={draftLoading}
          sending={sending}
          channel={channel}
          setChannel={setChannel}
          onGenerate={onGenerate}
          onApprove={onApprove}
          showNudgeQueue={false}
          panelTitle="AI Action Panel"
          panelDesc="Select a project to review forecast risk and draft proactive outreach to close gaps."
        />
      </div>
    </div>
  );
}

// ── Pending Approval Card ──────────────────────────────────────────────────────
const AREA_LABEL = {
  revenue_realization: "Revenue",
  billing_trigger: "Billing",
  unbilled_revenue: "Unbilled",
  collection_monitoring: "Collections",
  revenue_forecasting: "Forecast",
};

function PendingApprovalCard({ notification, onResolve }) {
  const [signal, setSignal] = useState("complete");
  const [resolving, setResolving] = useState(false);

  async function handleResolve() {
    setResolving(true);
    await onResolve(notification.id, signal);
    setResolving(false);
  }

  return (
    <div className="pending-card">
      <div className="pc-top">
        <span className="area-tag">{AREA_LABEL[notification.agent_key] || notification.agent_key}</span>
        <span className="type-tag">{notification.entity_type}</span>
        <span className="dir-tag dir-outbound">Awaiting Reply</span>
      </div>
      <div className="pc-subject">{notification.subject}</div>
      <div className="pc-meta">
        To: {notification.recipient_email} · {notification.channel} · {fmtDate(notification.sent_at || notification.created_at)}
      </div>
      <div className="pc-actions">
        <select
          className="pc-signal-select"
          value={signal}
          onChange={(e) => setSignal(e.target.value)}
        >
          <option value="complete">Approved / Completed</option>
          <option value="progress">In Progress</option>
          <option value="none">No Response</option>
        </select>
        <button
          className="btn-primary pc-resolve-btn"
          onClick={handleResolve}
          disabled={resolving}
        >
          {resolving ? "Resolving…" : "Resolve"}
        </button>
      </div>
    </div>
  );
}

// ── Activity Page ─────────────────────────────────────────────────────────────
function ActivityPage({ notifications, onResolve }) {
  const all = notifications || [];
  const pending = all.filter(
    (n) => n.direction === "outbound" && (n.status === "Mock Sent" || n.status === "Sent" || n.status === "mock_sent")
  );
  const rows = [...all].sort(
    (a, b) => new Date(b.created_at) - new Date(a.created_at)
  );

  const columns = [
    { key: "created_at", label: "Date", render: (v) => fmtDate(v) },
    {
      key: "agent_key",
      label: "Area",
      render: (v) => (
        <span className="area-tag">{AREA_LABEL[v] || v}</span>
      ),
    },
    {
      key: "entity_type",
      label: "Type",
      render: (v) => <span className="type-tag">{v}</span>,
    },
    { key: "subject", label: "Subject" },
    {
      key: "direction",
      label: "Direction",
      render: (v) => (
        <span className={`dir-tag dir-${v}`}>{v}</span>
      ),
    },
    { key: "channel", label: "Channel" },
    {
      key: "status",
      label: "Status",
      render: (v) => <StatusBadge value={v} />,
    },
    { key: "recipient_email", label: "Recipient" },
  ];

  return (
    <div className="activity-layout">
      {/* Pending Approvals */}
      <div className="panel">
        <SectionHeader
          title="Pending Approvals"
          sub="Actions sent by the agent — select reply signal and resolve to close"
          right={
            <span className="table-count">{pending.length} pending</span>
          }
        />
        {pending.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">✓</div>
            <p>No pending approvals. All sent actions have been resolved.</p>
          </div>
        ) : (
          <div className="pending-list">
            {pending.map((n) => (
              <PendingApprovalCard key={n.id} notification={n} onResolve={onResolve} />
            ))}
          </div>
        )}
      </div>

      {/* Activity Log */}
      <div className="panel">
        <SectionHeader
          title="Agent Activity Log"
          sub="Complete history of AI-generated actions and notifications"
          right={
            <span className="table-count">{rows.length} events</span>
          }
        />
        {rows.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">◌</div>
            <p>No agent activity recorded yet.</p>
            <p>Approve an AI action on any module to see it logged here.</p>
          </div>
        ) : (
          <DataTable columns={columns} rows={rows} />
        )}
      </div>
    </div>
  );
}

// ── Thresholds / Settings Page ────────────────────────────────────────────────
function ThresholdsPage({
  thresholds,
  drafts,
  onChange,
  onSave,
  savingId,
  onReseed,
  onUpload,
  uploading,
  uploadFile,
  setUploadFile,
  integrations,
  onSyncGmail,
}) {
  const grouped = {};
  for (const t of thresholds || []) {
    if (!grouped[t.agent_key]) grouped[t.agent_key] = [];
    grouped[t.agent_key].push(t);
  }

  const areaLabel = {
    revenue_realization: "Revenue Realization",
    billing_trigger: "Billing Triggers",
    unbilled_revenue: "Unbilled Revenue",
    collection_monitoring: "Collections",
    revenue_forecasting: "Revenue Forecast",
  };

  return (
    <div className="settings-layout">
      {/* Threshold sections per agent */}
      {Object.entries(grouped).map(([key, items]) => (
        <div key={key} className="panel settings-section">
          <div className="panel-kicker">{areaLabel[key] || key}</div>
          <div className="threshold-grid">
            {items.map((t) => {
              const d = drafts[t.id] ?? t;
              const saving = savingId === t.id;
              return (
                <div key={t.id} className="threshold-card">
                  <div className="tc-label">{t.label}</div>
                  <div className="tc-desc">{t.description}</div>
                  <div className="tc-fields">
                    <label className="tc-field">
                      <span>Medium ({t.unit})</span>
                      <input
                        type="number"
                        value={d.medium_value}
                        onChange={(e) =>
                          onChange(t.id, "medium_value", parseFloat(e.target.value))
                        }
                        className="tc-input"
                      />
                    </label>
                    <label className="tc-field">
                      <span>High ({t.unit})</span>
                      <input
                        type="number"
                        value={d.high_value}
                        onChange={(e) =>
                          onChange(t.id, "high_value", parseFloat(e.target.value))
                        }
                        className="tc-input"
                      />
                    </label>
                  </div>
                  <button
                    className="btn-primary tc-save"
                    onClick={() => onSave(t.id)}
                    disabled={saving}
                  >
                    {saving ? "Saving…" : "Save Threshold"}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* Data Management */}
      <div className="panel settings-section">
        <div className="panel-kicker">Data Management</div>
        <div className="data-mgmt-grid">
          <div className="data-mgmt-card">
            <div className="dmc-title">Upload Workbook</div>
            <div className="dmc-desc">
              Import data from an .xlsx workbook file. This replaces the current
              dataset.
            </div>
            <input
              type="file"
              accept=".xlsx"
              onChange={(e) =>
                setUploadFile(e.target.files?.[0] || null)
              }
              className="dmc-file-input"
            />
            {uploadFile && (
              <button
                className="btn-primary dmc-btn"
                onClick={onUpload}
                disabled={uploading}
              >
                {uploading
                  ? "Uploading…"
                  : `Upload "${uploadFile.name}"`}
              </button>
            )}
          </div>
          <div className="data-mgmt-card">
            <div className="dmc-title">Reseed Demo Data</div>
            <div className="dmc-desc">
              Regenerate and reload the default demo dataset from the seed
              workbook.
            </div>
            <button className="btn-secondary dmc-btn" onClick={onReseed}>
              Reseed Data
            </button>
          </div>
        </div>
      </div>

      {/* Integrations */}
      {integrations && integrations.length > 0 && (
        <div className="panel settings-section">
          <div className="panel-kicker">Integrations</div>
          <div className="integrations-grid">
            {integrations.map((intg) => (
              <div key={intg.channel} className="integration-card">
                <div className="intg-top">
                  <div className="intg-name">
                    {intg.channel === "gmail" ? "Gmail" : intg.channel}
                  </div>
                  <StatusBadge
                    value={intg.configured ? "configured" : "not-configured"}
                  />
                </div>
                <div className="intg-detail">{intg.detail}</div>
                {intg.last_sync_at && (
                  <div className="intg-sync">
                    Last sync: {fmtDate(intg.last_sync_at)}
                  </div>
                )}
                {intg.channel === "gmail" && intg.configured && (
                  <button
                    className="btn-secondary intg-btn"
                    onClick={onSyncGmail}
                  >
                    Sync Gmail Now
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────
function Sidebar({ active, onChange, queueCount }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-mark">BFM</div>
        <div className="sidebar-logo-text">
          <div className="sidebar-app-name">BFM Agent</div>
          <div className="sidebar-app-sub">AI Finance Operations</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        {NAV.map((item) => (
          <button
            key={item.id}
            className={`sidebar-nav-item${active === item.id ? " active" : ""}`}
            onClick={() => onChange(item.id)}
          >
            <span className="sni-icon">{NAV_ICONS[item.id]}</span>
            <span className="sni-text">
              <span className="sni-label">{item.label}</span>
              <span className="sni-desc">{item.desc}</span>
            </span>
            {item.id === "overview" && queueCount > 0 && (
              <span className="sni-badge">{queueCount}</span>
            )}
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-footer-text">BFM Agentic Platform</div>
      </div>
    </aside>
  );
}

// ── Top Bar ───────────────────────────────────────────────────────────────────
function TopBar({
  activeTab,
  provider,
  providers,
  onProviderChange,
  onRefresh,
  refreshing,
  lastUpdated,
}) {
  const navItem = NAV.find((n) => n.id === activeTab);
  const timeStr = lastUpdated
    ? new Date(lastUpdated).toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";

  return (
    <header className="top-bar">
      <div className="topbar-title">
        <div className="topbar-page-name">{navItem?.label || "Dashboard"}</div>
        <div className="topbar-page-sub">{navItem?.desc || ""}</div>
      </div>

      <div className="topbar-right">
        {timeStr && (
          <div className="topbar-updated">Updated at {timeStr}</div>
        )}

        <div className="topbar-provider">
          <label className="topbar-provider-label">AI</label>
          <select
            className="topbar-select"
            value={provider}
            onChange={(e) => onProviderChange(e.target.value)}
          >
            {(providers || []).map((p) => (
              <option
                key={p.provider}
                value={p.provider}
                disabled={!p.available}
              >
                {p.provider}
                {!p.available ? " (unavailable)" : ""}
              </option>
            ))}
          </select>
        </div>

        <button
          className={`topbar-refresh${refreshing ? " spinning" : ""}`}
          onClick={onRefresh}
          title="Refresh data"
          disabled={refreshing}
        >
          ↻
        </button>
      </div>
    </header>
  );
}

// ── App Root ──────────────────────────────────────────────────────────────────
function App({ defaultProvider }) {
  const [providers, setProviders] = useState([]);
  const [provider, setProvider] = useState(defaultProvider || "mock");
  const [dashboard, setDashboard] = useState(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [selectedRef, setSelectedRef] = useState(null);
  const [draft, setDraft] = useState(null);
  const [channel, setChannel] = useState("email");
  const [thresholdDrafts, setThresholdDrafts] = useState({});
  const [loading, setLoading] = useState(true);
  const [draftLoading, setDraftLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [savingThresholdId, setSavingThresholdId] = useState(null);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [statusMsg, setStatusMsg] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [draftModalOpen, setDraftModalOpen] = useState(false);
  const [dismissedRefs, setDismissedRefs] = useState(new Set());

  const showStatus = useCallback((msg, isError = false) => {
    if (isError) setError(msg);
    else setStatusMsg(msg);
    setTimeout(() => {
      setError("");
      setStatusMsg("");
    }, 5000);
  }, []);

  async function loadDashboard() {
    setLoading(true);
    setError("");
    try {
      const [providerList, data] = await Promise.all([
        fetchJson("/api/providers"),
        fetchJson("/api/dashboard"),
      ]);
      setProviders(providerList);
      setDashboard(data);
      setLastUpdated(new Date().toISOString());

      // Auto-select best available provider
      const currentOk = providerList.find(
        (p) => p.provider === provider && p.available
      );
      if (!currentOk) {
        const defaultOk = providerList.find(
          (p) => p.provider === defaultProvider && p.available
        );
        const firstOk = providerList.find((p) => p.available);
        setProvider((defaultOk || firstOk)?.provider || "mock");
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDashboard();
  }, []);

  function switchTab(tabId) {
    setActiveTab(tabId);
    setSelectedRef(null);
    setDraft(null);
  }

  function agentKeyForTab(tabId) {
    const keys = {
      overview: "revenue_realization",
      revenue_realization: "revenue_realization",
      billing_trigger: "billing_trigger",
      unbilled_revenue: "unbilled_revenue",
      collection_monitoring: "collection_monitoring",
      revenue_forecasting: "revenue_forecasting",
    };
    return keys[tabId] || tabId;
  }

  function handleRowClick(row) {
    const agentKey = agentKeyForTab(activeTab);
    const ref = makeRef(row, agentKey);
    if (selectedRef && sameSel(selectedRef, ref)) {
      setSelectedRef(null);
      setDraft(null);
    } else {
      setSelectedRef(ref);
      setDraft(null);
    }
  }

  function handleNudgeSelect(ref) {
    const alreadySelected = selectedRef && sameSel(selectedRef, ref);
    setSelectedRef(ref);
    if (!alreadySelected) {
      setDraft(null);
    }
    generateDraft(ref);
  }

  async function generateDraft(targetRef = null) {
    const ref = targetRef || selectedRef;
    if (!ref) return;

    setDraftModalOpen(true);
    setDraftLoading(true);
    setDraft(null);
    try {
      const resp = await fetchJson("/api/agent/draft-followup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_key: ref.agent_key,
          entity_type: ref.entity_type,
          entity_id: ref.entity_id,
          provider,
        }),
      });
      setDraft({
        ...resp,
        agent_key: ref.agent_key,
        entity_type: ref.entity_type,
        entity_id: ref.entity_id,
      });
    } catch (e) {
      showStatus(e.message, true);
    } finally {
      setDraftLoading(false);
    }
  }

  async function approveDraft() {
    if (!selectedRef) return;
    setSending(true);
    try {
      const resp = await fetchJson("/api/actions/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_key: selectedRef.agent_key,
          entity_type: selectedRef.entity_type,
          entity_id: selectedRef.entity_id,
          provider,
          channel,
        }),
      });
      showStatus(
        `✓ Sent — Status: ${resp.status} · Channel: ${resp.channel} · To: ${resp.recipient_email}`
      );
      // Hide this nudge from the queue until it is resolved
      const key = `${selectedRef.agent_key}:${selectedRef.entity_id}`;
      setDismissedRefs((prev) => new Set([...prev, key]));
      setDraftModalOpen(false);
      setDraft(null);
      setSelectedRef(null);
      loadDashboard();
    } catch (e) {
      showStatus(e.message, true);
    } finally {
      setSending(false);
    }
  }

  async function resolveNotification(notificationId, signal) {
    try {
      await fetchJson(`/api/actions/${notificationId}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ signal }),
      });
      showStatus("Marked as resolved. Agent alerts will update.");
      loadDashboard();
    } catch (e) {
      showStatus(e.message, true);
    }
  }

  async function saveThreshold(id) {
    const d = thresholdDrafts[id];
    if (!d) return;
    setSavingThresholdId(id);
    try {
      await fetchJson(`/api/thresholds/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          medium_value: d.medium_value,
          high_value: d.high_value,
        }),
      });
      showStatus("Threshold saved.");
      loadDashboard();
    } catch (e) {
      showStatus(e.message, true);
    } finally {
      setSavingThresholdId(null);
    }
  }

  async function reseedData() {
    try {
      const resp = await fetchJson("/api/data/reseed", { method: "POST" });
      showStatus(`Reseeded: ${resp.records_loaded} records loaded.`);
      loadDashboard();
    } catch (e) {
      showStatus(e.message, true);
    }
  }

  async function uploadWorkbook() {
    if (!uploadFile) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", uploadFile);
      const resp = await fetchJson("/api/data/upload", {
        method: "POST",
        body: formData,
      });
      showStatus(`Uploaded: ${resp.records_loaded} records loaded.`);
      setUploadFile(null);
      loadDashboard();
    } catch (e) {
      showStatus(e.message, true);
    } finally {
      setUploading(false);
    }
  }

  async function syncGmail() {
    try {
      const resp = await fetchJson("/api/integrations/gmail/sync", {
        method: "POST",
      });
      showStatus(
        `Gmail synced: ${resp.synced_threads} threads, ${resp.updated_actions} updated.`
      );
      loadDashboard();
    } catch (e) {
      showStatus(e.message, true);
    }
  }

  function handleThresholdChange(id, key, value) {
    setThresholdDrafts((prev) => {
      const existing =
        prev[id] ??
        dashboard?.thresholds?.find((t) => t.id === id) ??
        {};
      return { ...prev, [id]: { ...existing, [key]: value } };
    });
  }

  const visibleQueue = (dashboard?.queue || []).filter(
    (n) => !dismissedRefs.has(`${n.agent_key}:${n.entity_id}`)
  );
  const queueCount = visibleQueue.length;

  const moduleProps = {
    selectedRef,
    onRowClick: handleRowClick,
    draft,
    draftLoading,
    sending,
    channel,
    setChannel,
    onGenerate: generateDraft,
    onApprove: approveDraft,
  };

  return (
    <div className="app-shell">
      <DraftModal
        open={draftModalOpen}
        draft={draft}
        draftLoading={draftLoading}
        sending={sending}
        channel={channel}
        setChannel={setChannel}
        onApprove={approveDraft}
        onClose={() => setDraftModalOpen(false)}
      />
      <Sidebar active={activeTab} onChange={switchTab} queueCount={queueCount} />

      <div className="main-wrapper">
        <TopBar
          activeTab={activeTab}
          provider={provider}
          providers={providers}
          onProviderChange={setProvider}
          onRefresh={loadDashboard}
          refreshing={loading}
          lastUpdated={lastUpdated}
        />

        {(error || statusMsg) && (
          <div className={`status-banner${error ? " error" : ""}`}>
            {error || statusMsg}
          </div>
        )}

        <main className="page-content">
          {loading && !dashboard && (
            <div className="loading-state">
              <div className="loading-spinner" />
              <div className="loading-text">Loading dashboard data…</div>
            </div>
          )}

          {dashboard && (
            <>
              {activeTab === "overview" && (
                <OverviewPage
                  dashboard={{ ...dashboard, queue: visibleQueue }}
                  selectedRef={selectedRef}
                  onNudgeSelect={handleNudgeSelect}
                  onRowClick={handleRowClick}
                  draft={draft}
                  draftLoading={draftLoading}
                  sending={sending}
                  channel={channel}
                  setChannel={setChannel}
                  onGenerate={generateDraft}
                  onApprove={approveDraft}
                />
              )}

              {activeTab === "revenue_realization" && (
                <RevenuePage
                  section={dashboard.revenue_realization}
                  {...moduleProps}
                />
              )}

              {activeTab === "billing_trigger" && (
                <BillingPage
                  section={dashboard.billing_trigger}
                  {...moduleProps}
                />
              )}

              {activeTab === "unbilled_revenue" && (
                <UnbilledPage
                  section={dashboard.unbilled_revenue}
                  {...moduleProps}
                />
              )}

              {activeTab === "collection_monitoring" && (
                <CollectionsPage
                  section={dashboard.collection_monitoring}
                  {...moduleProps}
                />
              )}

              {activeTab === "revenue_forecasting" && (
                <ForecastPage
                  section={dashboard.revenue_forecasting}
                  {...moduleProps}
                />
              )}

              {activeTab === "agent_activity" && (
                <ActivityPage
                  notifications={dashboard.notifications}
                  onResolve={resolveNotification}
                />
              )}

              {activeTab === "thresholds" && (
                <ThresholdsPage
                  thresholds={dashboard.thresholds}
                  drafts={thresholdDrafts}
                  onChange={handleThresholdChange}
                  onSave={saveThreshold}
                  savingId={savingThresholdId}
                  onReseed={reseedData}
                  onUpload={uploadWorkbook}
                  uploading={uploading}
                  uploadFile={uploadFile}
                  setUploadFile={setUploadFile}
                  integrations={dashboard.integrations}
                  onSyncGmail={syncGmail}
                />
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}

// ── Mount ─────────────────────────────────────────────────────────────────────
const rootEl = document.getElementById("root");
const appName = rootEl?.dataset?.appName || "BFM AI Agent";
const defaultProvider = rootEl?.dataset?.defaultProvider || "mock";
createRoot(rootEl).render(<App appName={appName} defaultProvider={defaultProvider} />);
