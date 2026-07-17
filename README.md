# VoyagerAI — Autonomous Multi-Agent AI Travel Planner

## 📌 Project Overview
The **Multi-Agent Travel Planner** is an AI-driven system designed to automate and optimize the complex process of travel planning. Built as part of our Agentic AI Internship, this project leverages a multi-agent architecture where distinct AI personas collaborate to generate personalized, constraint-aware itineraries.

By breaking down the broad task of "planning a trip" into specialized sub-tasks, the system ensures high accuracy, real-time data integration, and a seamless user experience.

## 🤖 Agent Architecture (Proposed)
Our system utilizes a collaborative approach with the following specialized agents:
*   **🧑‍✈️ The Supervisor (Orchestrator):** Interacts with the user, extracts constraints (budget, dates, preferences), delegates tasks to sub-agents, and compiles the final itinerary.
*   **🚆 The Logistics Agent:** Responsible for fetching and optimizing transport routes (flights, trains, local transit).
*   **🏨 The Accommodation Agent:** Identifies optimal stays based on budget, safety, and proximity to planned activities.
*   **🎒 The Experience Agent:** Curates day-by-day schedules, including highly-rated food spots, hidden gems, and core attractions.

## 🛠️ Tech Stack & Infrastructure (Week 3 Completed)
- **Backend:** FastAPI + SQLAlchemy + Alembic (Python 3.12/3.14)
- **Frontend:** Next.js 14 (App Router) + Tailwind CSS (TypeScript)
- **Database:** SQLite (local dev), PostgreSQL / Supabase (production)
- **Authentication:** Supabase Auth (ES256/RS256 JWKS & HS256 verify) + Mock bypass for local dev
- **Orchestration:** LangGraph (StateGraph)
- **Cache:** Redis Session Cache (with DB lookup fallback)
- **CI:** GitHub Actions

## 👥 The Team
*   **Yashraj** (Captain)
*   **Hetvi**
*   **Shreyas**
*   **Meet**

---

## 🚀 Local Setup & Installation

### Option A — Run manually

**Backend**
1. Navigate to backend:
   ```bash
   cd backend
   ```
2. Create and activate virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy the environment variables:
   ```bash
   cp .env.example .env
   # Populate with your Supabase project keys (URL, Anon Key, JWT Secret)
   ```
5. Apply database migrations:
   ```bash
   alembic upgrade head
   ```
6. Run the local dev server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

**Frontend**
1. Navigate to frontend:
   ```bash
   cd frontend
   ```
2. Install Node dependencies:
   ```bash
   npm install
   ```
3. Copy environment variables:
   ```bash
   cp .env.local.example .env.local
   # Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY to sync real Supabase auth, or leave empty to default to Mock Auth bypass mode.
   ```
4. Start Next.js server:
   ```bash
   npm run dev
   ```

---

## 🧪 Running tests
```bash
# Backend unit tests
cd backend && venv\Scripts\python -m pytest
# Frontend production build compilation
cd frontend && npm run build
```

## 📁 Project structure
```
voyagerai/
├── backend/
│   ├── app/
│   │   ├── api/v1/       # auth, health, trips router endpoints
│   │   ├── core/         # auth middleware, Redis cache client, security token parser
│   │   ├── db/           # SQLAlchemy models and SQLite connection
│   │   ├── repositories/ # Users, Trips, Messages, Itineraries, AgentRuns repositories
│   │   ├── schemas/      # Pydantic request/response models
│   │   ├── agents/       # Supervisor Agent & Coordinator Agent StateGraph
│   │   └── main.py
│   ├── migrations/       # Alembic migrations
│   └── tests/            # Pytest test suite
├── frontend/
│   ├── app/              # Next.js App Router (dashboard, auth, chat workspace)
│   ├── components/       # AuthGuard, Navbar, Modal layout components
│   ├── contexts/         # AuthContext state provider
│   └── lib/              # api and supabase wrappers
```

## 📝 Week 3 Submission Checklist
- [x] Repository pattern database layer (Users, Trips, Messages, Itineraries, AgentRuns)
- [x] Redis caching configuration for decoded user sessions
- [x] JWT token verification using ES256/RS256 JWKS fetch and legacy HS256 fallbacks
- [x] Coordinator Agent LangGraph StateGraph skeleton compiled and wired
- [x] Next.js frontend split into structured landing, auth, dashboard, and chat layout pages
- [x] Real-time chat workspace with stream processing and logs console UI
- [x] 100% passing automated test suite (13/13 backend tests)
- [x] Next.js compilation (static check & type check) runs error-free
