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

## 📝 Week 3 Completed Checklist
- [x] **Auth & Database:** Real user accounts working end-to-end via Supabase Auth + FastAPI JWT middleware.
- [x] **Repository Pattern:** Users, Trips, Messages, Itineraries, AgentRuns mapped and tested.
- [x] **Dockerized Stack:** Backend, Frontend, Postgres, and Redis running seamlessly.
- [x] **LangGraph Skeleton:** Coordinator Agent running as a real LangGraph StateGraph.
- [x] **Streaming Chat UI:** Next.js UI talks to the backend, handles SSE streaming, and persists messages to DB.
- [x] **100% Tests Passing:** Automated test suite fully functional.

## 🔮 Week 4: Real Multi-Agent Intelligence (Next Up)
- **Real Tool Calling:** Implement `weather_tool.py` (OpenWeather) and `places_tool.py` (Google Places).
- **LangGraph Orchestration:** Build out the `Planner Agent` to dynamically call Weather + Attraction agents based on constraints.
- **Memory/RAG:** Integrate ChromaDB so past trip messages are embedded and retrieved for context.
- **Goal:** Replace our current "static/stub" responses with a real, dynamic, and constraint-aware itinerary generated live.
