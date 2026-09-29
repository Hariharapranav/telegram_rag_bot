# 🏢 Enterprise AI Telegram Assistant

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Telegram](https://img.shields.io/badge/Telegram%20Bot%20API-v21+-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Supabase](https://img.shields.io/badge/Supabase-Storage%20%26%20DB-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com)
[![Redis](https://img.shields.io/badge/Redis-Semantic%20Cache-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![Gemini](https://img.shields.io/badge/Google-Gemini%202.0-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev)

A production-grade, multi-tenant enterprise **Retrieval-Augmented Generation (RAG)** assistant deployed directly on Telegram. Employees authenticate via frictionless one-tap company verification to query proprietary policies, manuals, and internal documentation. Administrators receive real-time AI observability, token usage tracking, remote Supabase document storage, and knowledge base controls.

---

## 📑 Table of Contents

- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Telegram Interface & User Workflows](#-telegram-interface--user-workflows)
- [Bot Commands](#-bot-commands)
- [Project Structure](#-project-structure)
- [Quick Start Guide](#-quick-start-guide)
  - [Prerequisites](#prerequisites)
  - [Local Development Setup](#local-development-setup)
  - [Docker Compose Setup](#docker-compose-setup)
- [Environment Configuration](#-environment-configuration)
- [REST API Endpoints](#-rest-api-endpoints)
- [Multi-Tenancy & Security Model](#-multi-tenancy--security-model)
- [Automated Testing](#-automated-testing)

---

## ✨ Key Features

| Feature | Description |
| :--- | :--- |
| **🏢 Strict Multi-Tenancy** | Every query, vector embedding, and cache entry is partitioned by `organization_id` using pgvector cosine distance (`<=>`). Zero cross-tenant data leakage. |
| **⚡ Semantic Caching** | High-performance Redis cosine similarity matching. Semantically identical questions receive instant answers at **$0.00 cost** and **<20ms latency**. |
| **🧭 Query Complexity Router** | Modular, explainable analyzer assessing query depth, length, and reasoning requirements to dynamically route queries between **Gemini Flash-Lite** and **Gemini Flash**. |
| **🎨 Safe HTML Rendering Engine** | Custom formatting layer (`app/telegram/formatting.py`) converts markdown into Telegram-compliant HTML, escaping entity-breaking characters to guarantee zero unparsed `**` or syntax crashes. |
| **📄 On-Demand Sources Modal** | Citations are discreetly attached as an interactive `[ 📄 View Sources ]` button that opens a native Telegram popup without cluttering the chat history. |
| **🔐 One-Tap Frictionless Authentication** | Passwordless login with case-insensitive Employee ID matching and clean confirmation cards explicitly showing assigned roles (`Administrator 🛡️` or `Employee 👤`). |
| **☁️ Supabase Cloud Storage** | Uploaded documents are saved remotely to Supabase Storage (`enterprise-documents`) scoped by tenant path `documents/{org_id}/{filename}` with automated synchronization upon deletion. |
| **📁 Native Document Ingestion** | Ingest `.pdf`, `.txt`, `.docx`, and `.md` files up to **10 MB** directly through Telegram chat drag-and-drop or the `/upload` command. |
| **📊 Real-Time Admin Telemetry** | Organization administrators can inspect token usage, query costs, average latency, and cache hit rates directly within Telegram via `/admin`. |

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    User([Telegram User]) -->|Natural Language Query| TG[Telegram Bot API]
    TG -->|Update| App[FastAPI Gateway / Polling Service]
    App --> Auth{Authenticated?}
    Auth -- No --> Menu[/start Greeting & Navigation Menu]
    Menu -->|/user| EmpAuth[Employee Sign In & Verification]
    Menu -->|/admin| AdminAuth[Admin Sign In & Confirmation]
    Auth -- Yes --> CacheCheck[Tenant-Isolated Semantic Cache]

    CacheCheck -->|Cache HIT| CachedReply[⚡ Instant Response <br/> 0 Tokens / $0.00]
    CachedReply --> CardFormat[HTML Executive Card Formatter]

    CacheCheck -->|Cache MISS| Router[Query Complexity Router]
    Router -->|Simple Query| FlashLite[Gemini Flash-Lite]
    Router -->|Complex Query| Flash[Gemini Flash]

    Router --> PG[(Supabase / PostgreSQL + pgvector)]
    PG -->|Top-K Chunks Scoped by Org ID| Grounding[Grounded Context Synthesis]
    
    FlashLite & Flash --> Grounding
    Grounding --> GenAnswer[Grounded Answer & Citations]
    GenAnswer --> StoreCache[Store in Redis Semantic Cache]
    StoreCache --> LogUsage[(Audit & Telemetry Logger)]
    LogUsage --> CardFormat

    CardFormat -->|Executive Card + Actions| Outbox[Telegram Chat Reply]
    Outbox --> User
```

---

## 📱 Telegram Interface & User Workflows

### 1. `/start` — Welcome Greeting & Navigation Menu
```text
User:   /start

Bot:    👋 Hello Alice! Welcome to Enterprise Assistant
        ━━━━━━━━━━━━━━━━━━━━━━
        I am your intelligent organization assistant powered by Gemini AI 
        and secure multi-tenant RAG.

        How would you like to proceed?

        • 👤 Employee / Member: Send /user to log in with your Employee ID
        • 🛡️ Organization Admin: Send /admin to manage documents & analytics
        • ℹ️ Need Help? Send /help for detailed command guidance

        [ 👤 Employee Sign In ]   [ 🛡️ Admin Portal ]
        [                   ℹ️ Help Guide                    ]
```

### 2. `/user` — Frictionless Employee Login
```text
User:   /user

Bot:    🏢 Welcome to Enterprise Assistant
        ━━━━━━━━━━━━━━━━━━━━━━
        To access your company's documents, please enter your 
        Organization ID or Organization Name:
        (e.g. acme_corp_001 or Acme Corporation)

User:   acme_corp_001

Bot:    🏢 Organization verified: Acme Corporation

        Please enter your Employee ID (e.g. EMP-001):

User:   EMP-001

Bot:    👤 Employee Profile Identified
        ━━━━━━━━━━━━━━━━━━━━━━━
        • Name: Alice Smith
        • Employee ID: EMP-001
        • Organization: Acme Corporation

        Tap Confirm & Sign In below to authenticate:
        [ ✅ Confirm & Sign In ]   [ ❌ Cancel ]

User:   [ Taps 'Confirm & Sign In' ]

Bot:    🏢 Enterprise Assistant Portal • Acme Corporation
        ━━━━━━━━━━━━━━━━━━━━━━━
        👋 Welcome back! Authenticated as Employee 👤.

        💬 Send any question about company policies, benefits, or documentation!
```

### 3. `/admin` — Administrator Control Panel & Uploads
```text
User:   /admin

Bot:    🛡️ Admin Control Panel
        ━━━━━━━━━━━━━━━━━━━━━━
        🏢 Organization: Acme Corporation (acme_corp_001)

        Use the menu buttons below to manage documents, users, and analytics:

        [ 📤 Upload Doc ]   [ 📁 Documents ]
        [ 📊 Stats      ]   [ 👥 Users     ]
        [ ➕ Add User   ]   [ 📈 Usage Feed ]
        [             🔒 Logout            ]
```

### 4. Direct Document Upload
Send `/upload` or drag & drop any `.pdf`, `.txt`, `.docx`, or `.md` file (up to 10 MB):
```text
Bot:    ⏳ Processing slidio_technology_policy_2026.pdf... extracting text and updating knowledge base.

Bot:    ✅ Document Uploaded & Ready!

        📄 File: slidio_technology_policy_2026.pdf
        🆔 Document ID: d6c4e091-a1b2-4c3d-8e4f-9a1b2c3d4e5f
        📦 Size: 5.3 KB
        🏢 Organization: slidio_org
        🟢 Status: Active & Searchable

        Employees can now query information from this document in Telegram.
        To delete this document later: /delete_doc d6c4e091-a1b2-4c3d-8e4f-9a1b2c3d4e5f

        [ 📤 Upload Document ]   [ 🔄 Refresh List ]
```

### 5. Natural Language Knowledge Base Query
```text
User:   How many days can we work from home?

Bot:    🏢 Acme Corporation Knowledge Base
        ━━━━━━━━━━━━━━━━━━━━━━
        Based on Acme Corporation's Flexible & Remote Work Guidelines:

        Full-time team members are permitted to work remotely for up to 
        3 days per week, with a minimum requirement of 2 days on-site at 
        their designated company office.

        Additionally, employees in good standing may request up to 30 
        business days per calendar year to work remotely from an approved 
        international location.
        ━━━━━━━━━━━━━━━━━━━━━━
        ✨ Verified from official company documents

        [ 👍 Helpful ]   [ 👎 Not Helpful ]
        [         📄 View Sources         ]
```

---

## 🤖 Bot Commands

Commands configured for BotFather (`/setcommands`):

```text
start - Welcome greeting and main navigation menu
user - Employee sign in and knowledge base portal
admin - Organization admin portal and document management
upload - Upload policy documents (.pdf, .txt, .docx, .md)
add_user - Add a new employee or admin to your organization
delete_doc - Delete a document from your organization's knowledge base
help - View guide and available commands
logout - Securely sign out of your current session
```

---

## 📂 Project Structure

```text
rag-assistant/
├── app/
│   ├── main.py                     # FastAPI application & lifecycle management
│   ├── config.py                   # Pydantic v2 Settings & environment mapping
│   ├── admin/                      # Admin analytics & command handlers
│   │   ├── analytics.py            # Tenant-scoped aggregate metrics, costs & query streams
│   │   └── handlers.py             # Admin panel, user management & in-chat document upload
│   ├── auth/                       # Authentication & session state management
│   │   ├── service.py              # Passwordless auth state machine & org lookup
│   │   ├── session.py              # UserSession data model & AuthState enum
│   │   └── otp.py                  # Core OTP generation & verification service
│   ├── cache/                      # Multi-tenant semantic cache
│   │   └── semantic_cache.py       # Redis vector matching with in-memory fallback
│   ├── db/                         # Database layer
│   │   ├── database.py             # Async SQLAlchemy engine & session factory
│   │   ├── models.py               # Declarative models (Organization, User, Document, QueryLog)
│   │   └── repositories.py         # Case-insensitive queries & pgvector cosine distance
│   ├── rag/                        # Retrieval-Augmented Generation core
│   │   ├── ingestion.py            # PDF/TXT/DOCX extraction, chunking & Supabase Storage upload
│   │   ├── chunking.py             # Recursive paragraph-aware text chunker
│   │   ├── embeddings.py           # Gemini embedding client with fallback
│   │   ├── retrieval.py            # Multi-tenant filtered pgvector retrieval
│   │   └── generation.py           # Grounded response synthesis with guardrails
│   ├── router/                     # Explainable Model Routing
│   │   └── model_router.py         # Heuristic complexity scorer (Flash vs Flash-Lite)
│   ├── services/                   # Background services
│   │   ├── usage_tracker.py        # Asynchronous token and cost telemetry logging
│   │   └── document_service.py     # Document lifecycle & synchronized Supabase Storage deletion
│   └── telegram/                   # Telegram Bot Interface
│       ├── bot.py                  # Application builder & update dispatcher
│       ├── handlers.py             # Message routing, greeting, queries & callbacks
│       ├── formatting.py           # Safe Telegram HTML rendering & markdown cleaner
│       └── keyboards.py            # Interactive inline keypads & navigation buttons
├── api/                            # Serverless entrypoints
│   └── index.py                    # Vercel Serverless ASGI wrapper
├── scripts/                        # Database migration, sync & seed scripts
│   ├── init_db.py                  # Table & pgvector extension initialization
│   ├── seed_data.py                # Seeds sample organizations, users & policies
│   ├── supabase_schema.sql         # Direct SQL schema for Supabase migrations
│   └── generate_sample_pdf.py      # Automated PDF generation utility for testing
├── tests/                          # Automated Pytest suite (26 tests)
│   ├── conftest.py                 # Async test fixtures and isolated database
│   ├── test_admin_analytics.py     # Token accounting, cost and latency tests
│   ├── test_admin_roles.py         # Administrator role elevation and validation tests
│   ├── test_auth_service.py        # One-tap login, case-insensitive ID & session tests
│   ├── test_config.py              # Environment configuration & defaults tests
│   ├── test_model_router.py        # Complexity scoring & dynamic model selection tests
│   ├── test_multi_tenancy.py       # Strict cross-tenant isolation tests
│   ├── test_rag_pipeline.py        # Grounded answering & anti-hallucination tests
│   ├── test_semantic_cache.py      # Cache hit, miss, and similarity threshold tests
│   └── test_telegram_formatting.py # HTML escaping, bold/code tags & fallback tests
├── Dockerfile                      # Production container image definition
├── docker-compose.yml              # Local pgvector & Redis service orchestration
├── requirements.txt                # Pinned production Python dependencies
├── vercel.json                     # Vercel deployment configuration
├── .gitignore                      # Git ignore rules (ignoring .env, .pdf, cache, etc.)
└── README.md                       # Comprehensive documentation
```

---

## ⚡ Quick Start Guide

### Prerequisites
* Python 3.11 or higher
* A Telegram Bot Token from [@BotFather](https://t.me/BotFather)
* A Google Gemini API Key from [Google AI Studio](https://aistudio.google.com/app/apikey)
* A Supabase Project (PostgreSQL with pgvector and Storage bucket `enterprise-documents`)

---

### Local Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Hariharapranav/telegram_rag_bot.git
   cd telegram_rag_bot
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and supply your credentials:
   ```dotenv
   TELEGRAM_BOT_TOKEN="your_bot_token_from_botfather"
   GEMINI_API_KEY="your_gemini_api_key"
   DATABASE_URL="postgresql+asyncpg://postgres:your_password@db.supabase.co:5432/postgres"
   SUPABASE_URL="https://your-project.supabase.co"
   SUPABASE_SERVICE_ROLE_KEY="your_service_role_key"
   SUPABASE_STORAGE_BUCKET="enterprise-documents"
   ```

5. **Initialize and Seed Database:**
   ```bash
   # Initialize tables & pgvector extension
   python scripts/init_db.py

   # Seed sample organizations, users, and policies
   python scripts/seed_data.py
   ```

6. **Start the application:**
   ```bash
   python -m uvicorn app.main:app --reload --port 8000
   ```
   The bot will begin polling Telegram immediately. Open your bot in Telegram and send `/start`.

---

### Docker Compose Setup

Run the local stack including PostgreSQL with `pgvector` and `redis:7-alpine`:

```bash
# 1. Copy and configure .env
cp .env.example .env

# 2. Build and launch services
docker compose up --build -d

# 3. Seed demo data inside container
docker compose exec app python scripts/seed_data.py

# 4. Verify service health
curl http://localhost:8000/health
```

---

## ⚙️ Environment Configuration

| Variable | Default | Description |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | *Required* | Bot Token issued by `@BotFather`. |
| `TELEGRAM_MODE` | `polling` | `polling` for local dev; `webhook` for production (e.g. Vercel). |
| `TELEGRAM_WEBHOOK_URL` | `null` | Public HTTPS endpoint when running in webhook mode. |
| `DATABASE_URL` | *SQLite fallback* | SQLAlchemy async database connection URI (PostgreSQL / Supabase). |
| `SUPABASE_URL` | `""` | Supabase project URL for remote document storage. |
| `SUPABASE_SERVICE_ROLE_KEY` | `""` | Supabase service role secret key. |
| `SUPABASE_STORAGE_BUCKET` | `enterprise-documents` | Supabase Storage bucket for policy files. |
| `REDIS_URL` | `redis://localhost:6379/0`| Redis connection URL for semantic cache. |
| `GEMINI_API_KEY` | *Required* | Google Gemini API key from AI Studio. |
| `GEMINI_MODEL_SIMPLE` | `gemini-2.0-flash-lite` | Model chosen for straightforward factual queries. |
| `GEMINI_MODEL_COMPLEX` | `gemini-2.0-flash` | Model chosen for multi-step reasoning queries. |
| `GEMINI_EMBEDDING_MODEL`| `models/text-embedding-004` | 768-dimensional text embedding model. |
| `SEMANTIC_CACHE_THRESHOLD` | `0.90` | Cosine similarity cutoff for returning cached answers. |
| `RAG_TOP_K` | `4` | Number of document chunks retrieved per query. |
| `RAG_SIMILARITY_THRESHOLD` | `0.45` | Minimum chunk cosine similarity threshold. |

---

## 🌐 REST API Endpoints

Interactive Swagger UI documentation is available at `http://localhost:8000/docs`.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Application, database, and cache readiness status. |
| `POST`| `/api/documents/upload` | Multipart file upload for enterprise document ingestion. |
| `GET` | `/api/documents/{org_id}` | Catalog of all indexed documents for a specific organization. |
| `GET` | `/api/admin/stats/{org_id}` | Aggregated metrics: queries, cache hit rate, cost & latency. |
| `GET` | `/api/admin/users/{org_id}` | User-level breakdown of query volume and token usage. |
| `GET` | `/api/admin/usage/{org_id}` | Live chronological audit log of processed queries. |
| `POST`| `/api/telegram/webhook` | Webhook receiver for production Telegram updates. |

---

## 🔒 Multi-Tenancy & Security Model

To satisfy enterprise compliance and prevent cross-tenant data leakage:
1. **Schema Partitioning**: All records (`documents`, `document_chunks`, `users`, and `query_logs`) include foreign keys to `organization_id`.
2. **Retrieval Scoping**: pgvector searches strictly enforce organization-level scoping:
   ```sql
   SELECT content, metadata, 1 - (embedding <=> :query_vec) AS similarity
   FROM document_chunks
   WHERE organization_id = :org_id
   ORDER BY embedding <=> :query_vec
   LIMIT :top_k;
   ```
3. **Storage Partitioning**: Files uploaded to Supabase Storage are saved under `documents/{org_id}/{filename}` and synchronized on deletion.
4. **Semantic Cache Partitioning**: Redis cache keys and sets are namespaced per organization:
   ```text
   semantic_cache:entry:{org_id}:{entry_id}
   semantic_cache:org:{org_id}:keys
   ```
5. **Anti-Hallucination Guardrails**: Prompts explicitly mandate: *"If the answer cannot be found in the provided context, respond: 'I couldn't find this information in your organization's documents.' Do not hallucinate."*

---

## 🧪 Automated Testing

The comprehensive test suite covers all components with 26 automated unit and integration tests:

```bash
python -m pytest -v
```

```text
tests/test_admin_analytics.py .                                          [  3%]
tests/test_admin_roles.py ....                                           [ 19%]
tests/test_auth_service.py ...                                           [ 30%]
tests/test_config.py ....                                                [ 46%]
tests/test_model_router.py ....                                          [ 61%]
tests/test_multi_tenancy.py .                                            [ 65%]
tests/test_rag_pipeline.py ...                                           [ 76%]
tests/test_semantic_cache.py ..                                          [ 84%]
tests/test_telegram_formatting.py ....                                   [100%]

======================== 26 passed, 1 warning in 9.20s ========================
```
