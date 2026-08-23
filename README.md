# VoyagerAI — Autonomous Multi-Agent AI Travel Planner

> **An AI-powered travel planning system where a hierarchy of LangGraph agents collaborates to generate real, constraint-aware itineraries — not static templates.**

---

## 🌟 What VoyagerAI Can Do

VoyagerAI takes the stress out of travel planning by offering a fully autonomous, intelligent system that builds personalized itineraries tailored to your specific constraints, preferences, and budget.

Key capabilities include:
- **Constraint-Aware Planning**: Builds itineraries that strictly adhere to your set budgets and preferences, automatically scaling accommodations and daily spend.
- **Dynamic Multi-Agent Collaboration**: Leverages specialized AI agents working together in real-time to plan flights, hotels, attractions, and budgets simultaneously.
- **Context-Aware Recommendations**: Generates packing lists and daily plans that respect real weather forecasts at your destination.
- **Personalized RAG Memory**: Remembers your preferences and past interactions to provide highly tailored recommendations.
- **Trip Management**: Save favorite trips, view trip history, and easily manage your upcoming travel plans.

---

## ⚙️ How It Works

VoyagerAI is powered by a robust **LangGraph Multi-Agent Engine** that orchestrates a team of specialized AI agents:

1. **`FlightAgent`**: Evaluates routes, carriers, and pricing to find the best travel options.
2. **`HotelAgent`**: Filters accommodations by budget tier and location.
3. **`WeatherAgent`**: Fetches real-time weather forecasts to inform packing and activity planning.
4. **`AttractionAgent`**: Recommends curated attractions based on your preferences.
5. **`BudgetAgent`**: Synthesizes all costs into a clear, arithmetic breakdown to ensure you stay within your limit.

These agents communicate seamlessly through a `StateGraph` orchestration system, with real-time Server-Sent Events (SSE) streaming updates directly to the frontend. A local ChromaDB vector store powers the RAG memory for personalized interactions, while external tools (OpenWeather API, Google Places API) provide real-time data.

---

## 🛠️ Tech Stack

- **Backend framework**: Python 3.12, FastAPI, SQLAlchemy ORM
- **AI / Agent Engine**: Google Gemini 3.5 Flash, LangGraph (`StateGraph`)
- **Vector Store / RAG**: ChromaDB 
- **External API Tools**: OpenWeather API, Google Places API
- **Database**: SQLite / PostgreSQL
- **Frontend Application**: Next.js 14, TypeScript, Tailwind CSS

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

## 👥 Contributors

| Member | Role |
|---|---|
| **Yashraj** | Captain |
| **Hetvi** | |
| **Shreyas** | |
| **Meet** | |

*Built with ❤️ by the VoyagerAI Team.*
