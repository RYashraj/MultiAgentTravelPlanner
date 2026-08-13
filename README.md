# VoyagerAI — Autonomous Multi-Agent AI Travel Planner

> **An AI-powered travel planning system where a hierarchy of LangGraph agents collaborates to generate real, constraint-aware itineraries — not static templates.**

---

## 🚦 Current Status & Deliverables (Weeks 1–5)

| Deliverable / Feature Area | Status | Key Implementation Details |
|---|---|---|
| **Week 1–2: Core API & Authentication** | ✅ Done | FastAPI + SQLAlchemy CRUD endpoints for trips, messages, itineraries, and agent runs. Full Supabase JWT + local Dev/Mock auth bypass. |
| **Week 3: LangGraph Multi-Agent Engine** | ✅ Done | StateGraph orchestration with type-safe message passing, conversation persistence, and real-time Server-Sent Events (SSE) streaming. |
| **Week 4: RAG Memory & Tool Calling** | ✅ Done | ChromaDB vector storage for personalized user preferences; integrated OpenWeather API and Google Places API tool calling. |
| **Week 5: Specialized Domain Agents** | ✅ Done | 5 distinct domain agents (`Coordinator`, `FlightAgent`, `HotelAgent`, `AttractionAgent`, `BudgetAgent`) with parallel execution. |
| **Week 5: Instant Heuristic Fallback DBs** | ✅ Done | Zero-latency local databases and arithmetic fallbacks (<1 ms response time, 0 rate-limit bottlenecks). |
| **Week 5: Intelligent Target Budget Fitting** | ✅ Done | Automatically optimizes accommodation & daily spend to respect explicit numeric user budgets (e.g., ₹50,000) with feasibility analysis. |
| **Full Interactive Frontend Workspace** | ✅ Done | Next.js 14 App Router, TypeScript, Tailwind CSS, real-time chat, and interactive budget/itinerary cards. |
| **Automated Verification & CI Suite** | ✅ Done | 100% test pass rate (`35/35 passing tests` in `pytest`) covering auth, graphs, agents, and RAG. |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend Framework** | Python 3.12, FastAPI, SQLAlchemy ORM, Alembic |
| **AI / Agent Engine** | Google Gemini 3.5 Flash (`gemini-3.5-flash`), LangGraph (`StateGraph`), Pydantic SecretStr |
| **Vector Store / RAG** | ChromaDB (local embedded vector database) |
| **External API Tools** | OpenWeather API, Google Places API |
| **Database** | SQLite (local dev) / PostgreSQL (production via Supabase) |
| **Authentication** | Supabase Auth (JWT ES256/RS256/HS256 verification) + Mock Auth Bypass |
| **Caching** | Redis session cache with automatic database fallback |
| **Frontend Application** | Next.js 14 (App Router), TypeScript, Tailwind CSS |
| **Streaming Protocol** | Server-Sent Events (SSE) `/api/v1/trips/{id}/messages?stream=true` |
| **DevOps & CI/CD** | GitHub Actions CI, Docker, Docker Compose |

---

## 📦 Setup & Installation Instructions

### Prerequisites
- **Python 3.12+**
- **Node.js 18+** & **npm**
- **Git**
- *(Optional)* **Docker & Docker Compose** for containerized quick-start
- *(Optional)* **Redis** (if running locally without Docker; falls back to in-memory if unavailable)

### 1. Clone & Configure Environment Variables
```bash
git clone https://github.com/RYashraj/MultiAgentTravelPlanner.git
cd MultiAgentTravelPlanner

# Backend environment setup
cp backend/.env.example backend/.env

# Frontend environment setup
cp frontend/.env.local.example frontend/.env.local
```

#### Required Backend Environment Variables (`backend/.env`)
| Variable | Description | Example / Note |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini API Key | Required for AI Planner Agent |
| `OPENWEATHER_API_KEY` | OpenWeatherMap API Key | Required for weather forecasts |
| `GOOGLE_PLACES_API_KEY` | Google Places API Key | Required for place recommendations |
| `DATABASE_URL` | SQLAlchemy Database URL | Defaults to `sqlite:///./travel.db` |
| `SUPABASE_URL` | Supabase Project URL | Optional — leave empty for local Mock Auth |
| `SUPABASE_ANON_KEY` | Supabase Public Anon Key | Optional — leave empty for local Mock Auth |
| `SUPABASE_JWT_SECRET` | Supabase JWT Secret | Optional — leave empty for local Mock Auth |

---

## 🚀 How to Run Locally

### Option A: Quick Start with Docker Compose (Recommended)
```bash
docker-compose up --build
```
- **Backend API & Swagger Docs:** http://localhost:8000/docs  
- **Frontend Workspace:** http://localhost:3000  

---

### Option B: Manual Local Development

#### 1. Start Backend Dev Server
```bash
cd backend

# Create and activate Python virtual environment
python -m venv venv

# Windows (Command Prompt):
venv\Scripts\activate.bat
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# macOS / Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Launch FastAPI server with hot-reload
uvicorn app.main:app --reload --port 8000
```
- API server will be live at http://localhost:8000.

#### 2. Start Frontend Dev Server
```bash
cd frontend

# Install Node dependencies
npm install

# Launch Next.js development server
npm run dev
```
- Open http://localhost:3000 in your browser.

---

## 📁 Folder & Architecture Overview

### Project Directory Layout
```
MultiAgentTravelPlanner/
├── backend/
│   ├── app/
│   │   ├── agents/              # LangGraph Multi-Agent System
│   │   │   ├── coordinator.py   # StateGraph coordinating sub-agents
│   │   │   ├── supervisor.py    # Top-level orchestrator & SSE streaming
│   │   │   ├── planner.py       # Gemini 3.5 Flash planning engine
│   │   │   ├── parser.py        # Structured itinerary JSON extractor
│   │   │   └── state.py         # Shared AgentState TypedDict
│   │   ├── api/v1/              # FastAPI REST & SSE routes (/trips, /auth)
│   │   ├── core/                # JWT Auth middleware, security, cache
│   │   ├── db/                  # SQLAlchemy ORM models & session factory
│   │   ├── rag/                 # ChromaDB vector store for trip history
│   │   ├── repositories/        # Database access layer (CRUD)
│   │   ├── schemas/             # Pydantic validation schemas
│   │   ├── tools/               # Weather & Places API external wrappers
│   │   └── main.py              # Application lifecycle & middleware
│   ├── migrations/              # Alembic database migrations
│   ├── tests/                   # Complete pytest unit & integration suite
│   └── requirements.txt
├── frontend/
│   ├── app/                     # Next.js 14 App Router
│   │   ├── (auth)/              # Login and signup pages
│   │   ├── auth/callback/       # Supabase OAuth callback route
│   │   ├── trips/               # Trip listing dashboard
│   │   └── trips/[id]/          # Collaborative trip chat & itinerary view
│   ├── components/              # Reusable UI components & AuthGuard
│   ├── contexts/                # AuthContext provider (Supabase + dev bypass)
│   └── lib/                     # API client & Supabase utility wrapper
├── .github/workflows/ci.yml     # Automated CI pipeline
├── docker-compose.yml           # Container orchestration
└── README.md
```

### Multi-Agent Architecture
```
User Message / Query
        │
        ▼
┌────────────────────────────────────────────────────────┐
│                   Supervisor Agent                     │
│        (LangGraph Orchestrator & SSE Gateway)          │
│  • Validates & parses user input                       │
│  • Coordinates sub-agent execution flow                │
│  • Streamlines real-time SSE output back to client     │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│                  Coordinator Agent                     │
│     (StateGraph Routing & Task Delegation Layer)       │
│  • Manages shared AgentState across agent turns        │
│  • Delegates itinerary generation to Planner Agent     │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│                    Planner Agent                       │
│              (Google Gemini 3.5 Flash)                 │
│  • Calls OpenWeather API for real-time weather alerts  │
│  • Calls Google Places API for venue recommendations   │
│  • Retrieves ChromaDB RAG memory for user preferences  │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│                     Parser Agent                       │
│      (Structured JSON Itinerary Output Formatter)      │
└────────────────────────────────────────────────────────┘
```

---

## 🤖 Week 5: Multi-Agent Collaboration & Intelligent Budget Fitting

VoyagerAI has evolved from a single-prompt LLM wrapper into an **autonomous multi-agent collaboration suite**:

1. **Specialized Domain Agents (Parallel Orchestration)**:
   - **`FlightAgent`**: Evaluates routes, carriers, durations, and pricing with instant local route lookup and global heuristic fallback.
   - **`HotelAgent`**: Filters accommodations by budget tier (`budget`, `midrange`, `luxury`) and computes total nightly stays.
   - **`WeatherAgent`**: Fetches real-time weather forecasts via OpenWeather API and generates seasonal packing tips.
   - **`AttractionAgent`**: Recommends curated attractions, opening hours, and local activities via Google Places API and rich local databases.
   - **`BudgetAgent`**: Synthesizes all domain agent costs into an arithmetic budget breakdown.
2. **Zero-Latency Heuristic Fallbacks (Rate-Limit Safe)**:
   - To eliminate 30–60s LLM latency and avoid Google AI Studio free-tier rate limits (15 RPM), domain agents prioritize **instant local databases and heuristic algorithms (<1 ms execution time)**. Only the final `PlannerGraph` invokes Gemini to synthesize the narrative itinerary.
3. **Intelligent Target Budget Fitting**:
   - When a user enters an explicit numeric budget (e.g., `₹50,000` for 10 days), `BudgetAgent` automatically **scales accommodation and daily spend** to fit within the target ceiling, generating an explicit feasibility breakdown and actionable savings tips in the UI.

---

## 🔮 Roadmap — What's Next

- [ ] **Cloud Production Deployment** — Deploy backend to Railway/Render and frontend to Vercel with managed PostgreSQL.
- [ ] **Real-Time Collaborative Editing** — Add WebSockets for multi-user simultaneous trip planning.
- [ ] **Flight & Hotel Booking Integrations** — Integrate Amadeus or Skyscanner APIs for real-time ticket pricing.
- [ ] **Export to PDF & Calendar** — One-click downloadable itinerary PDFs and `.ics` calendar sync.
- [ ] **Managed Vector Database** — Transition ChromaDB to Pinecone / pgvector for cloud-scale RAG.
- [ ] **Budget & Route Optimizer** — Autonomous sub-agent to optimize travel paths and stay within specified cost ceilings.

---

## 👥 Contributors

| Member | Role |
|---|---|
| **Yashraj** | Captain |
| **Hetvi** | |
| **Shreyas** | |
| **Meet** | |

---

*Built with ❤️ by the VoyagerAI Team.*
