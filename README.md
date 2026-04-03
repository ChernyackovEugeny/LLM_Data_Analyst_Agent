# LLM Data Analyst Agent

An AI-powered data analyst chatbot that lets users query databases and generate charts using natural language. Built with FastAPI, LangGraph, React, and DeepSeek LLM.

![Architecture](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square) ![LangGraph](https://img.shields.io/badge/Agent-LangGraph-FF6B35?style=flat-square) ![Frontend](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-61DAFB?style=flat-square) ![Database](https://img.shields.io/badge/Database-PostgreSQL-336791?style=flat-square) ![Docker](https://img.shields.io/badge/Deploy-Docker-2496ED?style=flat-square)

## Features

- **Natural language queries** — ask questions in plain text, get SQL results and charts
- **Real-time streaming** — watch the agent think, query, and respond step by step via Server-Sent Events
- **Chart generation** — agent writes and executes Python (matplotlib) to produce visualizations
- **SQL results as files** — query results are saved to CSV files; the LLM receives only a path and a 10-row preview, keeping the context window lean
- **CSV upload** — upload your own dataset; the agent works with it immediately, no restart needed
- **User isolation** — each user sees only their own data; CSV tables are per-user
- **Authentication** — HttpOnly cookie-based auth with access + refresh token rotation
- **Persistent memory** — conversation history stored in PostgreSQL; survives server restarts
- **Conversation summarization** — long chats are automatically compressed to stay within the context window
- **Multiple chats** — each chat has independent history; create, switch, and delete chats freely
- **Markdown rendering** — agent responses render formatted text, tables, and inline charts
- **Chart lightbox** — click any chart to view it fullscreen

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | DeepSeek (`deepseek-chat`) via OpenAI-compatible API |
| Agent framework | LangGraph + LangChain |
| Backend | FastAPI + uvicorn |
| Database | PostgreSQL 16 |
| Frontend | React 19 + Vite 8 + Tailwind CSS 4 |
| Web server | nginx (reverse proxy + SPA routing) |
| Containerization | Docker + Docker Compose |

## Project Structure

```
LLM_Data_Analyst_Agent/
├── app/
│   ├── api/routes.py          # REST endpoints: auth, analyze, chats, upload-csv
│   ├── auth/auth.py           # Cookie-based auth, token creation/validation
│   ├── config.py              # Settings (reads from .env)
│   ├── core/
│   │   ├── graph.py           # LangGraph graph definition
│   │   ├── nodes.py           # Agent node + summarization node
│   │   ├── edges.py           # Routing logic (tools / summarize / end)
│   │   ├── prompts.py         # System prompt builder
│   │   └── state.py           # LangGraph state schema
│   ├── database/
│   │   ├── database.py        # SQLAlchemy engine + session
│   │   └── seed.py            # Populates demo data (customers + orders)
│   ├── models/schemas.py      # Pydantic request/response models
│   └── tools/
│       ├── sql_tool.py        # Tool: execute SQL, save result to CSV, return path + preview
│       ├── python_tool.py     # Tool: execute Python code in Docker sandbox
│       └── schemas.py         # Dynamic DB schema builder (per-user)
├── client/                    # React frontend (Vite)
│   └── src/
│       ├── api/index.js       # Axios client + SSE helper
│       └── pages/
│           ├── Dashboard.jsx  # Main chat interface
│           ├── LoginPage.jsx
│           └── RegisterPage.jsx
├── docker/
│   ├── init-readonly-user.sh  # Creates analyst_readonly PostgreSQL role on first start
│   └── 03-chats-schema.sql    # Creates chats + messages tables
├── static/plots/              # Generated chart images (served by FastAPI)
│   └── results/               # SQL query results saved as CSV files
├── Dockerfile.backend
├── Dockerfile.frontend        # Multi-stage: Node build → nginx serve
├── Dockerfile.sandbox         # Isolated Python sandbox image
├── docker-compose.yml
├── nginx.conf
├── main.py                    # Local dev entrypoint (uvicorn with --reload)
└── requirements.txt
```

## Quick Start (Docker)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- A [DeepSeek API key](https://platform.deepseek.com/)

### 1. Clone the repository

```bash
git clone <repo-url>
cd LLM_Data_Analyst_Agent
```

### 2. Create `.env` file

Create a `.env` file in the project root:

```env
DEEPSEEK_API_KEY=sk-...your-key-here...
SECRET_KEY=your-random-secret-key-here

# Database credentials — used by both docker-compose and local dev
POSTGRES_USER=admin
POSTGRES_PASSWORD=password
POSTGRES_DB=analyst_db

# Local dev: backend connects to localhost
# In Docker this is overridden by docker-compose.yml to use the "db" service hostname
DATABASE_URL=postgresql+psycopg2://admin:password@localhost:5432/analyst_db

# Read-only DB user for the SQL tool (SELECT only; DDL/DML refused at DB level)
# Generate a strong password: openssl rand -hex 32
READONLY_DB_PASSWORD=your-readonly-password-here
READONLY_DATABASE_URL=postgresql+psycopg2://analyst_readonly:your-readonly-password-here@localhost:5432/analyst_db

# Docker Compose project name — determines the volume name for plots
COMPOSE_PROJECT_NAME=llm_data_analyst_agent
```

### 3. Build the Python sandbox image

The sandbox is a separate Docker image used to run agent-generated Python code in isolation. Build it once before the first start:

```bash
docker compose build sandbox
```

### 4. Build and start all containers

```bash
docker compose up --build -d
```

This starts three containers:
- `llm_agent_db` — PostgreSQL database
- `llm_agent_backend` — FastAPI backend
- `llm_agent_frontend` — nginx serving the React app

### 5. Seed the demo database

Run once after the first start to create demo tables (`customers`, `orders`) with sample data:

```bash
docker compose exec backend python -m app.database.seed
```

### 6. Open the app

Go to [http://localhost](http://localhost)

Register an account and start chatting with your data.

## Usage

### Querying built-in data

After seeding, the agent has access to two demo tables:

- `customers` — 20 customers with name and city
- `orders` — 500 orders with amount, profit, and date

Example questions:
- *"Which 5 customers brought the most profit?"*
- *"Show monthly revenue for 2023 as a bar chart"*
- *"What is the average order amount by city?"*

### Uploading your own CSV

Click the **paperclip icon** in the chat input to upload a `.csv` file (max 10 MB). The agent will immediately switch to your data — no restart needed. Uploading a new file replaces the previous one.

Column names are automatically sanitized (spaces → underscores, lowercased) before being stored in PostgreSQL.

### Reading charts

Charts appear inline in the chat. Click any chart to open it fullscreen. Press `Esc` or click outside to close.

## Stopping the App

```bash
docker compose down
```

Data is preserved in Docker volumes (`postgres_data`, `plots_data`). To wipe everything including data:

```bash
docker compose down -v
```

## Rebuilding After Code Changes

| Changed files | Command |
|---|---|
| Backend Python code | `docker compose up --build -d backend` |
| Frontend React code | `docker compose up --build -d frontend` |
| Both | `docker compose up --build -d` |

## Local Development (without Docker)

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL running locally

### Backend

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
# or: source .venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
python main.py                # starts uvicorn on :8000 with hot-reload
```

In local dev, `USE_SANDBOX` defaults to `false` — Python code runs in a subprocess fallback instead of Docker.

### Frontend

```bash
cd client
npm install
npm run dev                   # starts Vite dev server on :5173
```

The Vite dev server proxies `/api/` and `/static/` to `http://localhost:8000`, so the frontend works with relative URLs in both local dev and Docker.

### Seed the database

```bash
python -m app.database.seed
```

## API Reference

Base URL: `http://localhost:8000/api/v1` (or `/api/v1` through nginx)

Interactive Swagger docs: [http://localhost:8000/docs](http://localhost:8000/docs)

Authentication uses **HttpOnly cookies** — no `Authorization` header is needed. The login endpoint sets `access_token` and `refresh_token` cookies automatically.

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/signup` | No | Register a new user |
| `POST` | `/auth/login` | No | Log in, sets HttpOnly cookie |
| `POST` | `/auth/logout` | No | Clear auth cookies |
| `POST` | `/auth/refresh` | Cookie | Refresh access token (token rotation) |
| `GET` | `/auth/me` | Yes | Get current user info |
| `GET` | `/analyze/stream` | Yes | Send a question, receive SSE stream |
| `POST` | `/upload-csv` | Yes | Upload a CSV file as a personal table |
| `POST` | `/chats` | Yes | Create a new chat |
| `GET` | `/chats` | Yes | List all chats for current user |
| `DELETE` | `/chats/{chat_id}` | Yes | Delete a chat and its history |
| `GET` | `/chats/{chat_id}/messages` | Yes | Get message history for a chat |
| `GET` | `/health` | No | Health check |

### SSE Event Types

The `/analyze/stream` endpoint emits the following events:

```jsonc
{"type": "thinking"}                                   // agent is processing
{"type": "tool_call", "tool": "execute_sql_query"}     // tool being called
{"type": "tool_result", "tool": "execute_sql_query"}   // tool returned
{"type": "done", "answer": "..."}                      // final answer
{"type": "error", "message": "..."}                    // error occurred
```

## Architecture

### System Overview

```mermaid
graph TB
    subgraph Browser["Browser"]
        React["React 19 + Vite\nSPA (Tailwind CSS)"]
    end

    subgraph Compose["Docker Compose"]
        subgraph FE["frontend"]
            nginx["nginx\nReverse Proxy + SPA routing"]
        end

        subgraph BE["backend"]
            FastAPI["FastAPI + Uvicorn"]
            Auth["Auth\nHttpOnly Cookies\n+ Token Rotation"]
            subgraph LG["LangGraph Agent"]
                AgentNode["Agent Node\nDeepSeek LLM"]
                ToolNode["Tool Node"]
                SummarizeNode["Summarize Node"]
            end
            AgentNode -->|tool_calls| ToolNode
            ToolNode -->|messages| AgentNode
            AgentNode -->|messages > threshold| SummarizeNode
        end

        subgraph DB["db"]
            PG[("PostgreSQL 16\nusers · chats · messages\ncheckpoints · csv_u{id}")]
        end

        subgraph SB["sandbox"]
            Sandbox["Python Sandbox\npandas · matplotlib · numpy\nnetwork disabled · 512 MB RAM"]
        end

        Volume[("plots_data volume\nstatic/plots/\n└── results/*.csv\n└── *.png")]
    end

    subgraph Ext["External"]
        LLM["DeepSeek API\nOpenAI-compatible"]
    end

    React -- "HTTP / SSE" --> nginx
    nginx -- "/api/ proxy" --> FastAPI
    FastAPI --> Auth
    FastAPI --> LG
    LG -- "AsyncPostgresSaver\ncheckpoints" --> PG
    ToolNode -- "execute_sql_query\nread-only role → saves CSV" --> PG
    ToolNode -- "CSV file" --> Volume
    ToolNode -- "execute_python_code\nDocker-out-of-Docker" --> Sandbox
    Sandbox -- "reads CSV · writes PNG" --> Volume
    AgentNode -- "chat completions" --> LLM
```

### Agent Pipeline

```mermaid
flowchart TD
    U(["User message\n(natural language)"])
    U --> API["FastAPI /analyze/stream\nSSE endpoint"]
    API --> Persist["Save user message\nto DB (chat history)"]
    Persist --> Schema["get_database_schema(user_id)\ndynamic schema — sees uploaded CSV"]
    Schema --> Prompt["build_agent_prompt(schema)\nsystem prompt + LangGraph memory"]
    Prompt --> LLM["DeepSeek LLM\nwith bound tools"]

    LLM --> D{tool_calls?}

    D -- "execute_sql_query" --> SQL["SQL Tool\n1. Strip comments\n2. SELECT-only allowlist\n3. read-only PG role\n→ saves full result to CSV\n→ returns path + 10-row preview"]
    D -- "execute_python_code" --> Py["Python Tool\n1. AST import validation\n2. Docker sandbox\n   network off · 512 MB · 30 s\n→ reads CSV via pd.read_csv(path)\n→ saves PNG to plots/"]

    SQL --> Back(["Back to Agent Node"])
    Py --> Back
    Back --> LLM

    D -- No --> Summarize{messages\n> threshold?}
    Summarize -- Yes --> Sum["Summarize Node\ncompress old messages\nincremental summary"]
    Summarize -- No --> Done["SSE event: done\nfinal answer saved to DB"]
    Done --> FE["React Frontend\nMarkdown · tables · inline charts\nChart lightbox"]

    style SQL fill:#FFF9C4,stroke:#F57F17
    style Py fill:#FFF9C4,stroke:#F57F17
    style LLM fill:#E3F2FD,stroke:#1565C0
    style FE fill:#E8F5E9,stroke:#2E7D32
    style Sum fill:#FCE4EC,stroke:#C62828
```

### Security Layers

| Layer | SQL tool | Python tool |
|---|---|---|
| **Layer 1** | Strip comments → SELECT-only allowlist + no semicolons + no `SELECT INTO` | AST parse → blocked imports (`os`, `sys`, `subprocess`, …) + blocked calls (`exec`, `eval`) |
| **Layer 2** | `analyst_readonly` PostgreSQL role — DDL/DML refused at DB level | Docker sandbox — network disabled, 512 MB RAM, 0.5 CPU, no env secrets |

## Key Design Decisions

- **SQL results as files, not context** — `execute_sql_query` saves the full result set to a CSV file under `static/plots/results/` and returns only the file path + a 10-row preview. The LLM never sees thousands of rows in its context; Python code loads data with `pd.read_csv(path)`.

- **Dynamic schema per request** — `get_database_schema(user_id)` is called on every LLM invocation instead of once at startup, so the agent immediately sees uploaded CSV tables without a server restart.

- **Per-user CSV isolation** — CSV tables are named `csv_u{user_id}`. The schema builder hides other users' tables and hides demo tables when the user has their own CSV.

- **Persistent conversation memory** — LangGraph uses `AsyncPostgresSaver` to store checkpoints in PostgreSQL. History survives backend restarts and is isolated per chat (`thread_id = chat_{id}`).

- **Conversation summarization** — when message count exceeds `SUMMARY_THRESHOLD`, the `summarize_node` compresses old messages into a running summary and removes them from state. The summary is injected as a `SystemMessage` on the next turn.

- **Docker-out-of-Docker sandbox** — the backend runs in Docker and cannot share host paths with sandboxes. A named Docker volume (`plots_data`) acts as a shared bus: the backend writes scripts and reads CSVs from it, the sandbox container mounts the same volume.

- **HttpOnly cookie auth** — tokens are stored in HttpOnly cookies, not `localStorage`, so they are not accessible to JavaScript (XSS protection). `SameSite=Lax` on cookies provides CSRF protection. Short-lived access tokens (30 min) are refreshed via a long-lived refresh token (30 days) with token rotation.

- **SSE through nginx** — `proxy_buffering off` and `proxy_cache off` are required; otherwise nginx buffers the stream and the frontend receives no events until the response completes.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | Yes | — | DeepSeek API key |
| `DATABASE_URL` | Yes | — | SQLAlchemy connection string (admin role) |
| `SECRET_KEY` | Yes | — | Cookie signing secret (use `openssl rand -hex 32`) |
| `READONLY_DATABASE_URL` | No | `""` | Connection string for read-only SQL tool role |
| `READONLY_DB_PASSWORD` | No | — | Password for `analyst_readonly` PG role |
| `ALGORITHM` | No | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `30` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `30` | Refresh token lifetime |
| `COOKIE_SECURE` | No | `false` | Set `true` in production (HTTPS only) |
| `LLM_MODEL_NAME` | No | `deepseek-chat` | LLM model identifier |
| `LLM_BASE_URL` | No | `https://api.deepseek.com/v1` | LLM API base URL |
| `USE_SANDBOX` | No | `false` | `true` = Docker sandbox for Python; `false` = subprocess fallback |
| `PLOTS_VOLUME_NAME` | No | `llm_data_analyst_agent_plots_data` | Docker volume name shared with sandbox |
| `SANDBOX_IMAGE_NAME` | No | `analyst-sandbox:latest` | Python sandbox Docker image |
| `SUMMARY_THRESHOLD` | No | `20` | Message count that triggers summarization |
| `SUMMARY_KEEP_LAST` | No | `8` | Messages kept verbatim after summarization |
| `PLOTS_MAX_AGE_HOURS` | No | `24` | Delete PNG and CSV files older than this on startup (`0` = disabled) |

## License

MIT
