# VoyagerAI — Autonomous Multi-Agent AI Travel Planner

> **An AI-powered travel planning system where a hierarchy of LangGraph agents collaborates to generate real, constraint-aware itineraries — not static templates.**

---

## 🚦 Current Status

| Area | Status |
|---|---|
| Backend API (FastAPI + SQLAlchemy) | ✅ Complete |
| Auth (Supabase JWT + mock bypass) | ✅ Complete |
| LangGraph Agent Graph (Coordinator + Supervisor) | ✅ Complete |
| Gemini LLM Planner Agent | ✅ Complete |
| Weather Tool (OpenWeather API) | ✅ Integrated |
| Places Tool (Google Places API) | ✅ Integrated |
| ChromaDB RAG Memory | ✅ Integrated |
| SSE Streaming Chat UI | ✅ Complete |
| Frontend (Next.js Trips Workspace) | ✅ Complete |
| CI (GitHub Actions) | ✅ Passing |
| Production deployment | 🔲 Not started |

---

## 🤖 Agent Architecture

```
User Request
     │
     ▼
┌──────────────────────────────────────────┐
│          Supervisor Agent                │
│  (LangGraph StateGraph orchestrator)     │
│  - Parses user message                   │
│  - Routes to Coordinator graph           │
│  - Streams response via SSE              │
└───────────────┬──────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────┐
│         Coordinator Agent                │
│  (LangGraph StateGraph)                  │
│  - Manages agent state                   │
│  - Delegates to Planner Agent            │
└───────────────┬──────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────┐
│          Planner Agent                   │
│  (Gemini 1.5 Pro LLM)                    │
│  - Calls Weather Tool → OpenWeather API  │
│  - Calls Places Tool → Google Places API │
│  - Reads ChromaDB for past trip context  │
│  - Generates structured itinerary        │
└──────────────────────────────────────────┘
                │
                ▼
         Parser Agent
     (Structured output extraction
      → JSON itinerary response)
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.12, FastAPI, SQLAlchemy, Alembic |
| **LLM / Agents** | Google Gemini 1.5 Pro, LangGraph (StateGraph) |
| **Memory / RAG** | ChromaDB (local vector store) |
| **External Tools** | OpenWeather API, Google Places API |
| **Database** | SQLite (local dev) / PostgreSQL via Supabase |
| **Auth** | Supabase Auth (JWKS ES256/RS256 + HS256) + mock bypass |
| **Cache** | Redis (session cache with DB fallback) |
| **Frontend** | Next.js 14 App Router, TypeScript, Tailwind CSS |
| **Streaming** | Server-Sent Events (SSE) |
| **CI** | GitHub Actions |
| **Containers** | Docker + docker-compose |

---

## 👥 Team

| Member | Role |
|---|---|
| **Yashraj** | Captain — Backend, Agents, Architecture |
| **Hetvi** | Backend, DB models |
| **Shreyas** | Backend, Auth, CI |
| **Meet** | Frontend, Streaming UI |

---

## 🚀 Local Setup & Installation

### Prerequisites
- Python 3.12+
- Node.js 18+
- Redis (running locally or via Docker)
- A Supabase project (or use SQLite + mock auth for local dev without Supabase)

### Option A — Quick start with Docker

```bash
docker-compose up --build
```

Backend → http://localhost:8000  
Frontend → http://localhost:3000

### Option B — Run manually

**1. Backend**

```bash
cd backend

# Create virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and fill in env vars
cp .env.example .env
# Edit .env: add GEMINI_API_KEY, OPENWEATHER_API_KEY, GOOGLE_PLACES_API_KEY
# For Supabase: add SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET
# For local-only dev without Supabase: leave Supabase vars empty (mock auth activates)

# Apply database migrations
alembic upgrade head

# Start dev server
uvicorn app.main:app --reload --port 8000
```

**2. Frontend**

```bash
cd frontend

npm install

# Copy and fill in env vars
cp .env.local.example .env.local
# Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY
# Leave empty to use Mock Auth bypass mode (no Supabase needed)

npm run dev
```

Frontend → http://localhost:3000

---

## 🧪 Running Tests

```bash
# Backend unit + integration tests
cd backend
venv\Scripts\python -m pytest -v

# Frontend production build check
cd frontend
npm run build
```

---

## 📁 Project Structure

```
MultiAgentTravelPlanner/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── coordinator.py   # LangGraph StateGraph — top-level agent graph
│   │   │   ├── supervisor.py    # Orchestrator: parses input, invokes graph, streams SSE
│   │   │   ├── planner.py       # Gemini LLM planner — calls weather + places tools
│   │   │   ├── parser.py        # Structured itinerary extraction from LLM output
│   │   │   └── state.py         # AgentState TypedDict shared across all agents
│   │   ├── api/v1/
│   │   │   ├── trips.py         # Trip CRUD + /stream SSE endpoint
│   │   │   ├── auth.py          # Auth routes
│   │   │   └── health.py        # Health check
│   │   ├── core/
│   │   │   ├── security.py      # Supabase JWT verification
│   │   │   ├── cache.py         # Redis session cache
│   │   │   └── auth_middleware.py
│   │   ├── db/
│   │   │   ├── models.py        # SQLAlchemy ORM models
│   │   │   └── session.py       # DB engine + session factory
│   │   ├── repositories/        # Users, Trips, Messages, Itineraries, AgentRuns
│   │   ├── schemas/             # Pydantic request/response models
│   │   ├── tools/
│   │   │   ├── weather_tool.py  # OpenWeather API wrapper
│   │   │   └── places_tool.py   # Google Places API wrapper
│   │   ├── rag/
│   │   │   └── chroma_store.py  # ChromaDB vector store (trip memory/RAG)
│   │   └── main.py              # FastAPI app factory + lifespan
│   ├── migrations/              # Alembic migrations
│   ├── tests/                   # Pytest test suite
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── (auth)/              # Login + Signup pages
│   │   ├── trips/               # Trip listing page
│   │   └── trips/[id]/          # Trip workspace (chat + itinerary viewer)
│   ├── components/              # AuthGuard, Navbar
│   ├── contexts/                # AuthContext (Supabase + mock)
│   └── lib/
│       ├── api.ts               # Backend API client
│       └── supabase.ts          # Supabase client wrapper
├── .github/workflows/ci.yml     # GitHub Actions CI
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## 🔮 Roadmap — What's Next

- [ ] **Production deployment** — Deploy backend to Railway/Render, frontend to Vercel
- [ ] **Real-time collaboration** — Multi-user trip editing via WebSockets
- [ ] **Flight & Hotel search** — Integrate Amadeus or Skyscanner API
- [ ] **PDF export** — Generate downloadable itinerary PDFs
- [ ] **Persistent RAG** — Move ChromaDB to a hosted vector DB (e.g. Pinecone)
- [ ] **Budget optimizer** — Agent that automatically optimizes within a given budget
- [ ] **Mobile app** — React Native wrapper for iOS/Android

---

## ⚠️ Environment Variables

Create `backend/.env` from `backend/.env.example`:

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | ✅ Yes | Google Gemini API key |
| `OPENWEATHER_API_KEY` | ✅ Yes | OpenWeather API key |
| `GOOGLE_PLACES_API_KEY` | ✅ Yes | Google Places API key |
| `SUPABASE_URL` | Optional | Supabase project URL (leave empty for SQLite + mock auth) |
| `SUPABASE_ANON_KEY` | Optional | Supabase public anon key |
| `SUPABASE_JWT_SECRET` | Optional | Supabase JWT signing secret |
| `REDIS_URL` | Optional | Redis connection URL (defaults to `redis://localhost:6379`) |
| `DATABASE_URL` | Optional | DB URL (defaults to SQLite `travel.db`) |

> **Never commit `.env` files.** They are gitignored. Rotate any keys that were exposed.
