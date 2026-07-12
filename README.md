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

## 🛠️ Tech Stack & Infrastructure (Week 2 Skeleton Complete)
- **Backend:** FastAPI + SQLAlchemy + Alembic (Python 3.12)
- **Frontend:** Next.js 14 (App Router) + Tailwind CSS (TypeScript)
- **Database:** PostgreSQL (Supabase in production, local Docker for dev)
- **Cache:** Redis
- **CI:** GitHub Actions

## 👥 The Team
*   **Yashraj** (Captain)
*   **Hetvi**
*   **Shreyas**
*   **Meet**

---

## 🚀 Local Setup & Installation

### Option A — Docker (recommended)
```bash
git clone <your-repo-url>
cd voyagerai
cp backend/.env.example backend/.env
docker compose up --build
```
- Backend: http://localhost:8000/docs
- Frontend: http://localhost:3000

### Option B — Run manually

**Backend**
```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then fill in DATABASE_URL if not using Docker's Postgres
alembic upgrade head
uvicorn app.main:app --reload
```

**Frontend**
```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Visit http://localhost:3000 — it pings the backend `/health` endpoint live and shows API + DB connection status.

## 🗄️ Database migrations
```bash
cd backend
alembic revision --autogenerate -m "describe your change"
alembic upgrade head
```
Never edit the DB schema by hand — always go through a migration so everyone's local DB and production stay in sync.

## 🧪 Running tests
```bash
cd backend && pytest tests/ -v
cd frontend && npm run lint && npm run build
```
Both run automatically in CI on every push/PR via `.github/workflows/ci.yml`.

## 📁 Project structure
```
voyagerai/
├── backend/
│   ├── app/
│   │   ├── api/v1/       # route handlers
│   │   ├── core/          # config
│   │   ├── db/             # models, session, base
│   │   └── main.py
│   ├── migrations/         # Alembic
│   └── tests/
├── frontend/
│   └── app/                 # Next.js App Router pages
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## 🔄 Git workflow
```bash
git checkout -b feat/your-feature develop
# ...make changes...
git add .
git commit -m "feat: short description"
git push origin feat/your-feature
# open PR into develop, get 1 review, merge
# develop -> main only at end of each week, after Friday demo
```

## 📝 Week 2 Submission Checklist
- [x] Tech stack finalized and justified
- [x] ER diagram (see project roadmap doc)
- [x] Architecture diagram (see project roadmap doc)
- [x] Backend skeleton — FastAPI + DB connectivity, tested
- [x] Frontend skeleton — Next.js, pings backend live, tested
- [x] Database schema — Users + Trips tables, Alembic migration verified (upgrade + downgrade)
- [x] Docker + docker-compose for local dev
- [x] GitHub Actions CI (backend tests + frontend build/lint)
- [ ] Push to GitHub, confirm CI passes on the actual repo
