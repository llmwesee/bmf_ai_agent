# BFM AI Agent

Production-style demo application for Business Finance Management leads in IT/ITeS organizations. The app models five operational finance sub-agents and a morning financial health scan across accounts, projects, milestones, billing, unbilled revenue, collections, and revenue forecasting.

## Stack

- Python 3.11
- FastAPI
- React
- LangChain
- LangGraph
- Langfuse
- OpenAI GPT-4.1
- Azure OpenAI GPT-4.1
- SQLite
- Gmail API integration

## Included capabilities

- Morning financial health scan for BFM leads
- Five dedicated sub-agents:
  - Revenue realization monitoring
  - Billing trigger monitoring
  - Unbilled revenue detection
  - Collection monitoring
  - Revenue forecasting
- Dynamic KPI calculations derived from raw project, milestone, and invoice inputs
- Editable risk thresholds from the UI
- LangGraph-driven follow-up drafting with `mock`, `openai`, and `azure_openai`
- Notification approval workflow with mock email or Gmail send
- Gmail reply sync that can update milestone and collection status after responses
- Seed workbook generation at [data/bfm_demo_data.xlsx](/C:/Users/heman/OneDrive/Desktop/bmf_ai_agent/bmf_ai_agent/data/bfm_demo_data.xlsx)

## Local setup

Activate the existing virtual environment:

```powershell
.venv\Scripts\activate
```

Install backend and frontend dependencies:

```powershell
.venv\Scripts\python -m pip install -e .[dev]
npm.cmd install
```

Rebuild the React bundle after frontend edits:

```powershell
npm.cmd run build
```

## Environment

The app reads `.env` automatically.

Optional LLM and tracing keys:

- `OPENAI_API_KEY`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_HOST`

Optional Gmail integration keys:

- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `GMAIL_REFRESH_TOKEN`
- `GMAIL_USER_EMAIL`

Without these keys the app still works in `mock` mode and keeps Gmail actions disabled.

## Run

```powershell
.venv\Scripts\python -m uvicorn bfm_agent.app:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

On startup the app will:

1. Regenerate the seed workbook if the older demo workbook format is detected.
2. Ensure the SQLite schema matches the five-agent data model.
3. Load demo accounts, projects, milestones, invoices, and thresholds into SQLite.

## Main API endpoints

- `GET /api/dashboard`
- `GET /api/providers`
- `GET /api/thresholds`
- `PUT /api/thresholds/{threshold_id}`
- `POST /api/agent/draft-followup`
- `POST /api/actions/approve`
- `POST /api/integrations/gmail/sync`
- `POST /api/data/reseed`
- `POST /api/data/upload`
- `GET /api/data/workbook`

## Test

```powershell
.venv\Scripts\pytest
```
