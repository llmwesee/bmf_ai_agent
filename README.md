# BFM AI Agent Demo

End-to-end demo application for Business Finance Management analysts in IT/ITeS organizations. The app monitors revenue realization, billing delays, unbilled revenue, collections risk, and generates AI-assisted follow-up drafts for account managers.

## Stack

- Python 3.11
- FastAPI
- LangChain
- LangGraph
- Langfuse
- OpenAI GPT-4.1
- Azure OpenAI GPT-4.1
- SQLite

## What the demo includes

- Seeded SQLite portfolio with account, project, revenue, billing, and invoice data
- Finance workbook generator at `data/bfm_demo_data.xlsx`
- Revenue KPI summary and project-level realization table
- Billing delay and collection risk alert queue
- LangGraph follow-up workflow with provider switch:
  - `mock` for offline deterministic demo runs
  - `openai` for GPT-4.1
  - `azure_openai` for Azure OpenAI GPT-4.1 deployments
- Optional Langfuse trace logging for agent runs
- Upload endpoint to replace the workbook with custom demo data

## Local setup

Python 3.11.14 is installed locally under `.python/`, and the virtual environment is created in `.venv/`.

Activate the environment:

```powershell
.venv\Scripts\activate
```

Install dependencies if needed:

```powershell
uv pip install --python .\.venv\Scripts\python.exe -e .[dev] --cache-dir .uv-cache
```

Create a local env file:

```powershell
Copy-Item .env.example .env
```

Optional credentials:

- `OPENAI_API_KEY` enables `openai`
- `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` enable `azure_openai`
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` enable Langfuse traces

## Run the app

```powershell
.venv\Scripts\python.exe -m uvicorn bfm_agent.app:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

On startup the app will:

1. Generate `data/bfm_demo_data.xlsx` if it does not exist.
2. Initialize SQLite at `data/bfm_demo.db`.
3. Import workbook data into the database.

## Useful endpoints

- `GET /api/summary`
- `GET /api/revenue-table`
- `GET /api/alerts`
- `GET /api/collections`
- `GET /api/report`
- `POST /api/agent/draft-followup`
- `POST /api/data/reseed`
- `POST /api/data/upload`
- `GET /api/data/workbook`

## Test

```powershell
.venv\Scripts\python.exe -m pytest
```
