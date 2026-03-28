# LLM Data Analyst Agent

An AI-powered data analyst chatbot that lets users query databases and generate charts using natural language. Built with FastAPI, LangGraph, React, and DeepSeek LLM.

![Architecture](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square) ![LangGraph](https://img.shields.io/badge/Agent-LangGraph-FF6B35?style=flat-square) ![Frontend](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-61DAFB?style=flat-square) ![Database](https://img.shields.io/badge/Database-PostgreSQL-336791?style=flat-square) ![Docker](https://img.shields.io/badge/Deploy-Docker-2496ED?style=flat-square)

## Features

- **Natural language queries** — ask questions in plain text, get SQL results and charts
- **Real-time streaming** — watch the agent think, query, and respond step by step via Server-Sent Events
- **Chart generation** — agent writes and executes Python (matplotlib) to produce visualizations
- **CSV upload** — upload your own dataset; the agent works with it immediately, no restart needed
- **User isolation** — each user sees only their own data; CSV tables are per-user
- **Authentication** — JWT-based registration and login
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
│   ├── api/routes.py          # REST endpoints: auth, analyze, upload-csv
│   ├── auth/auth.py           # JWT authentication
│   ├── config.py              # Settings (reads from .env)
│   ├── core/
│   │   ├── graph.py           # LangGraph graph definition
│   │   ├── nodes.py           # Agent node (calls LLM, builds prompt dynamically)
│   │   ├── edges.py           # Routing logic (tool call vs. final answer)
│   │   ├── prompts.py         # System prompt builder
│   │   └── state.py           # LangGraph state schema
│   ├── database/
│   │   ├── database.py        # SQLAlchemy engine + session
│   │   └── seed.py            # Populates demo data (customers + orders)
│   ├── models/schemas.py      # Pydantic request/response models
│   └── tools/
│       ├── sql_tool.py        # Tool: execute SQL queries
│       ├── python_tool.py     # Tool: execute Python code (charts)
│       └── schemas.py         # Dynamic DB schema builder (per-user)
├── client/                    # React frontend (Vite)
│   └── src/
│       ├── api/index.js       # Axios client + SSE helper
│       └── pages/
│           ├── Dashboard.jsx  # Main chat interface
│           ├── LoginPage.jsx
│           └── RegisterPage.jsx
├── static/plots/              # Generated chart images (served by FastAPI)
├── Dockerfile.backend
├── Dockerfile.frontend        # Multi-stage: Node build → nginx serve
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
DATABASE_URL=postgresql+psycopg2://admin:password@localhost:5432/analyst_db
SECRET_KEY=your-random-secret-key-here
```

> **Note:** `DATABASE_URL` uses `localhost` for local dev. In Docker it is automatically overridden to use the `db` service hostname.

### 3. Build and start all containers

```bash
docker compose up --build -d
```

This starts three containers:
- `llm_agent_db` — PostgreSQL database
- `llm_agent_backend` — FastAPI backend
- `llm_agent_frontend` — nginx serving the React app

### 4. Seed the demo database

Run once after the first start to create demo tables (`customers`, `orders`) with sample data:

```bash
docker compose exec backend python -m app.database.seed
```

### 5. Open the app

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

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/signup` | No | Register a new user |
| `POST` | `/auth/login` | No | Log in, receive JWT token |
| `POST` | `/analyze` | Yes | Send a question, get a full response |
| `GET` | `/analyze/stream` | Yes | Send a question, receive SSE stream |
| `POST` | `/upload-csv` | Yes | Upload a CSV file as a personal table |
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
            Auth["Auth\nHttpOnly JWT Cookies"]
            subgraph LG["LangGraph Agent"]
                AgentNode["Agent Node\nDeepSeek LLM"]
                ToolNode["Tool Node"]
            end
            AgentNode -->|tool_calls| ToolNode
            ToolNode -->|messages| AgentNode
        end

        subgraph DB["db"]
            PG[("PostgreSQL 16\nusers · chats · messages\ncheckpoints · csv_u{id}")]
        end

        subgraph SB["sandbox"]
            Sandbox["Python Sandbox\npandas · matplotlib · numpy\nnetwork disabled · 512 MB RAM"]
        end
    end

    subgraph Ext["External"]
        LLM["DeepSeek API\nOpenAI-compatible"]
    end

    React -- "HTTP / SSE" --> nginx
    nginx -- "/api/ proxy" --> FastAPI
    FastAPI --> Auth
    FastAPI --> LG
    LG -- "LangGraph checkpoints\nSQLAlchemy ORM" --> PG
    ToolNode -- "execute_sql_query\nread-only role" --> PG
    ToolNode -- "execute_python_code\nDocker-out-of-Docker" --> Sandbox
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

    D -- "Yes: execute_sql_query" --> SQL["SQL Tool\nAST strip-comments\n+ SELECT-only allowlist\n+ read-only PG role"]
    D -- "Yes: execute_python_code" --> Py["Python Tool\nAST import validation\n→ Docker sandbox\n(network off, 512 MB, 30 s)"]

    SQL --> Back(["Back to Agent Node"])
    Py --> Back
    Back --> LLM

    D -- No --> Done["SSE event: done\nfinal answer saved to DB"]
    Done --> FE["React Frontend\nMarkdown · tables · inline charts\nChart lightbox"]

    style SQL fill:#FFF9C4,stroke:#F57F17
    style Py fill:#FFF9C4,stroke:#F57F17
    style LLM fill:#E3F2FD,stroke:#1565C0
    style FE fill:#E8F5E9,stroke:#2E7D32
```

### Security layers

| Layer | SQL tool | Python tool |
|---|---|---|
| **Layer 1** | Strip comments → SELECT-only allowlist + no semicolons + no `SELECT INTO` | AST parse → blocked imports (`os`, `sys`, `subprocess`, …) + blocked calls (`exec`, `eval`) |
| **Layer 2** | `analyst_readonly` PostgreSQL role — DDL/DML refused at DB level | Docker sandbox — network disabled, 512 MB RAM, 0.5 CPU, no env secrets |

## How It Works

### Request flow

```
User message
     │
     ▼
FastAPI /analyze/stream
     │
     ▼
LangGraph Agent Node
  ├─ Fetches live DB schema (filtered per user)
  ├─ Builds system prompt with schema
  └─ Calls DeepSeek LLM
     │
     ├─ Tool call? ──► Tool Node
     │                  ├─ execute_sql_query → PostgreSQL (read-only)
     │                  └─ execute_python_code → Docker sandbox (matplotlib)
     │                        │
     │                  Back to Agent Node (loop)
     │
     └─ Final answer? ──► SSE "done" event ──► React frontend
```

### Key design decisions

- **Dynamic schema per request** — `get_database_schema(user_id)` is called on every LLM invocation instead of once at startup, so the agent immediately sees uploaded CSV tables without a server restart.
- **Per-user CSV isolation** — CSV tables are named `csv_u{user_id}`. The schema builder hides other users' tables and hides demo tables when the user has their own CSV.
- **SSE through nginx** — `proxy_buffering off` and `proxy_cache off` are required; otherwise nginx buffers the stream and the frontend receives no events until the response completes.
- **Python execution in subprocess** — agent-generated Python code runs in a separate subprocess to isolate it from the server process. `PYTHONIOENCODING=utf-8` prevents encoding errors on Windows when output contains non-ASCII characters.
- **Conversation memory** — LangGraph `MemorySaver` checkpointer stores message history per `thread_id` (`user_{id}`), so each user has independent conversation history for the session lifetime.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | Yes | — | DeepSeek API key |
| `DATABASE_URL` | Yes | — | SQLAlchemy connection string |
| `SECRET_KEY` | Yes | — | JWT signing secret (any random string) |
| `ALGORITHM` | No | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `30` | JWT token lifetime |
| `LLM_MODEL_NAME` | No | `deepseek-chat` | LLM model identifier |
| `LLM_BASE_URL` | No | `https://api.deepseek.com/v1` | LLM API base URL |

## License

MIT
