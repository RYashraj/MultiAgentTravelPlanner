# VoyagerAI — Autonomous Multi-Agent AI Travel Planner

> **An AI-powered travel planning system where a hierarchy of LangGraph agents collaborates to generate real, constraint-aware itineraries — not static templates.**

---

## 🚦 Current Status & Deliverables (Weeks 1–8)

| Deliverable / Feature Area | Status | Key Implementation Details |
|---|---|---|
| **Week 1–2: Core API & Authentication** | ✅ Done | FastAPI + SQLAlchemy CRUD endpoints for trips, messages, itineraries, and agent runs. Full Supabase JWT + local Dev/Mock auth bypass. |
| **Week 3: LangGraph Multi-Agent Engine** | ✅ Done | StateGraph orchestration with type-safe message passing, conversation persistence, and real-time Server-Sent Events (SSE) streaming. |
| **Week 4: RAG Memory & Tool Calling** | ✅ Done | ChromaDB vector storage for personalized user preferences; integrated OpenWeather API and Google Places API tool calling. |
| **Week 5: Specialized Domain Agents** | ✅ Done | 5 distinct domain agents (`Coordinator`, `FlightAgent`, `HotelAgent`, `AttractionAgent`, `BudgetAgent`) with parallel execution. |
| **Week 6: Saved Trips & Packing Lists** | ✅ Done | Save/unsave favorite trips, view trip history, and generate context-aware packing lists that respect real weather. |
| **Week 7: API Hardening & Rate Limiting** | ✅ Done | Global exception handling, structured logging with Sentry PII scrubbing, and global sliding-window rate limiting. |
| **Week 8: Production Readiness** | ✅ Done | Hardened Dockerfile, full CI pipeline (pytest, linting, security scans), cleaned up unused dependencies, and unified `main` branch. |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend Framework** | Python 3.12, FastAPI, SQLAlchemy ORM, Alembic |
| **AI / Agent Engine** | Google Gemini 3.5 Flash, LangGraph (`StateGraph`) |
| **Vector Store / RAG** | ChromaDB (local embedded vector database) |
| **External API Tools** | OpenWeather API, Google Places API |
| **Database** | SQLite (local dev) / PostgreSQL (production via Supabase) |
| **Authentication** | Supabase Auth (JWT verification) + Mock Auth Bypass |
| **Frontend Application** | Next.js 14 (App Router), TypeScript, Tailwind CSS |
| **DevOps & CI/CD** | GitHub Actions CI, Docker, Docker Compose |

---

## 📦 Setup & Installation Instructions

### Prerequisites
- **Python 3.12+**
- **Node.js 18+** & **npm**
- **Git**
- *(Optional)* **Docker & Docker Compose**

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
| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API Key |
| `OPENWEATHER_API_KEY` | OpenWeatherMap API Key |
| `GOOGLE_PLACES_API_KEY` | Google Places API Key |
| `DATABASE_URL` | SQLAlchemy Database URL (defaults to sqlite) |

#### Required Frontend Environment Variables (`frontend/.env.local`)
| Variable | Description |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | http://localhost:8000/api/v1 |

*(No Google Maps integration required.)*

---

## 🚀 How to Run Locally

### Option A: Quick Start with Docker Compose
```bash
docker-compose up --build
```
- **Backend API & Docs:** http://localhost:8000/docs  
- **Frontend Workspace:** http://localhost:3000  

### Option B: Manual Local Development

#### 1. Start Backend Dev Server
```bash
cd backend
python -m venv venv
# Activate venv (Windows: .\venv\Scripts\Activate.ps1 | macOS: source venv/bin/activate)
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

#### 2. Start Frontend Dev Server
```bash
cd frontend
npm install
npm run dev
```

---

## 🤖 Multi-Agent Collaboration

VoyagerAI uses an autonomous multi-agent collaboration suite:

1. **Specialized Domain Agents**:
   - **`FlightAgent`**: Evaluates routes, carriers, and pricing.
   - **`HotelAgent`**: Filters accommodations by budget tier.
   - **`WeatherAgent`**: Fetches real-time weather forecasts.
   - **`AttractionAgent`**: Recommends curated attractions.
   - **`BudgetAgent`**: Synthesizes all costs into an arithmetic breakdown.
2. **Intelligent Target Budget Fitting**:
   - Automatically scales accommodation and daily spend to fit within the user's explicit numeric budget.

---

## 👥 Contributors

| Member | Role |
|---|---|
| **Yashraj** | Captain |
| **Hetvi** | |
| **Shreyas** | |
| **Meet** | |

*Built with ❤️ by the VoyagerAI Team.*
