const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const percentage = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 0,
});

const state = {
  provider: "mock",
};

document.addEventListener("DOMContentLoaded", async () => {
  await loadProviders();
  bindActions();
  await loadDashboard();
});

function bindActions() {
  document.getElementById("refreshButton").addEventListener("click", () => loadDashboard());
  document.getElementById("reseedButton").addEventListener("click", async () => {
    await fetch("/api/data/reseed?regenerate_workbook=true", { method: "POST" });
    await loadDashboard();
  });
}

async function loadProviders() {
  const response = await fetch("/api/providers");
  const providers = await response.json();
  const select = document.getElementById("providerSelect");
  const defaultProvider = select.dataset.defaultProvider || "mock";

  providers.forEach((provider) => {
    const option = document.createElement("option");
    option.value = provider.provider;
    option.textContent = `${provider.provider} · ${provider.model}${provider.available ? "" : " (not configured)"}`;
    select.appendChild(option);
  });
  select.value = providers.some((item) => item.provider === defaultProvider) ? defaultProvider : "mock";
  state.provider = select.value;
  select.addEventListener("change", (event) => {
    state.provider = event.target.value;
  });
}

async function loadDashboard() {
  const [summary, alerts, revenueRows, collections, report] = await Promise.all([
    fetchJson("/api/summary"),
    fetchJson("/api/alerts"),
    fetchJson("/api/revenue-table"),
    fetchJson("/api/collections"),
    fetchJson("/api/report"),
  ]);

  renderSummary(summary);
  renderAlerts(alerts);
  renderRevenueTable(revenueRows);
  renderCollections(collections);
  renderReport(report);
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`Request failed for ${url}`);
  }
  return response.json();
}

function renderSummary(summary) {
  const items = [
    { label: "Revenue Plan", value: money.format(summary.revenue_plan), note: "Current month target" },
    { label: "Recognized", value: money.format(summary.revenue_recognized), note: percentage.format(summary.revenue_completion_pct) + " completion" },
    { label: "Forecast Gap", value: money.format(summary.revenue_gap), note: "Forecast minus target" },
    { label: "Unbilled", value: money.format(summary.total_unbilled), note: "Pending billing release" },
    { label: "Overdue", value: money.format(summary.overdue_amount), note: "Outstanding collections" },
    { label: "High Risk Projects", value: String(summary.high_risk_projects), note: `${summary.medium_risk_projects} medium risk in queue` },
  ];

  const container = document.getElementById("summaryGrid");
  container.innerHTML = "";
  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "summary-card";
    card.innerHTML = `<p class="label">${item.label}</p><strong>${item.value}</strong><small>${item.note}</small>`;
    container.appendChild(card);
  });
}

function renderAlerts(alerts) {
  const container = document.getElementById("alertsList");
  container.innerHTML = "";
  alerts.forEach((alert) => {
    const card = document.createElement("article");
    card.className = "alert-card";
    card.innerHTML = `
      <div class="alert-card-header">
        <div>
          <h3>${alert.title}</h3>
          <p>${alert.message}</p>
          <small>${alert.account_name} · ${alert.project_code}</small>
        </div>
        <span class="severity-pill ${alert.severity.toLowerCase()}">${alert.severity}</span>
      </div>
      <p>${alert.suggested_action}</p>
      <button class="inline-action" data-account="${alert.account_name}" data-project="${alert.project_code}" data-focus="${alert.focus_area}">
        Draft follow-up
      </button>
    `;
    const button = card.querySelector("button");
    button.addEventListener("click", () =>
      draftFollowup({
        account_name: alert.account_name,
        project_code: alert.project_code,
        focus_area: alert.focus_area,
        provider: state.provider,
        question: `Prepare a ${alert.focus_area} follow-up for ${alert.account_name}.`,
      }),
    );
    container.appendChild(card);
  });
}

function renderRevenueTable(rows) {
  const body = document.getElementById("revenueTableBody");
  body.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.account_name}</td>
      <td><strong>${row.project_code}</strong><br/><small>${row.project_name}</small></td>
      <td>${row.account_manager}</td>
      <td>${money.format(row.revenue_plan)}</td>
      <td>${money.format(row.revenue_recognized)}</td>
      <td>${money.format(row.revenue_forecast)}</td>
      <td>${money.format(row.revenue_gap)}</td>
      <td>${money.format(row.unbilled_amount)}</td>
      <td>${row.overdue_days} days</td>
      <td><span class="risk-pill ${row.risk_level.toLowerCase()}">${row.risk_level}</span></td>
      <td><button class="inline-action">Analyze</button></td>
    `;
    tr.querySelector("button").addEventListener("click", () =>
      draftFollowup({
        account_name: row.account_name,
        project_code: row.project_code,
        focus_area: "revenue",
        provider: state.provider,
        question: `Summarize the revenue risk and draft a follow-up for ${row.project_code}.`,
      }),
    );
    body.appendChild(tr);
  });
}

function renderCollections(rows) {
  const body = document.getElementById("collectionsTableBody");
  body.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.account_name}</td>
      <td>${row.project_code}</td>
      <td>${row.invoice_number}</td>
      <td>${money.format(row.invoice_amount)}</td>
      <td>${money.format(row.outstanding_amount)}</td>
      <td>${row.due_date}</td>
      <td>${row.overdue_days}</td>
      <td>${row.status}</td>
    `;
    body.appendChild(tr);
  });
}

function renderReport(report) {
  document.getElementById("reportNarrative").textContent = report.narrative;
  renderStack(document.getElementById("topAccounts"), report.top_accounts, "account_name");
  renderStack(document.getElementById("deliveryUnits"), report.top_delivery_units, "delivery_unit");
}

function renderStack(container, items, labelKey) {
  container.innerHTML = "";
  items.forEach((item) => {
    const block = document.createElement("div");
    block.className = "stack-item";
    const secondaryValue = item.revenue_gap ?? item.revenue_forecast ?? 0;
    block.innerHTML = `<span>${item[labelKey]}</span><strong>${money.format(secondaryValue)}</strong>`;
    container.appendChild(block);
  });
}

async function draftFollowup(payload) {
  const data = await fetchJson("/api/agent/draft-followup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  document.getElementById("followupEmpty").classList.add("hidden");
  document.getElementById("followupContent").classList.remove("hidden");
  document.getElementById("followupSummary").textContent = data.summary;
  document.getElementById("followupNudge").textContent = data.nudge;
  document.getElementById("followupSubject").textContent = data.email_subject;
  document.getElementById("followupBody").textContent = data.email_body;
  document.getElementById("followupAction").textContent = data.recommended_action;
  const facts = document.getElementById("followupFacts");
  facts.innerHTML = "";
  data.supporting_facts.forEach((fact) => {
    const item = document.createElement("li");
    item.textContent = fact;
    facts.appendChild(item);
  });

  const traceLink = document.getElementById("traceLink");
  if (data.trace_url) {
    traceLink.href = data.trace_url;
    traceLink.classList.remove("hidden");
  } else {
    traceLink.classList.add("hidden");
    traceLink.removeAttribute("href");
  }
}
