# Setu — GenAI Stadium Companion

Setu is a multi-agent GenAI assistant that provides a single, conversational interface for every stadium stakeholder (fans, volunteers, organizers) during the FIFA World Cup 2026. 

## Features

- **Fan Dashboard**: Pathfinding (wheelchair-accessible), sustainable transport options, real-time crowd updates, and AI-powered lost-and-found matching.
- **Organizer Dashboard**: Live crowd density matrix, predictive surge forecasting, smart volunteer dispatch, PA announcement drafting (5 languages), and volunteer wellbeing monitoring.

## Architecture

* **Backend**: FastAPI, Python 3.14+, Gemini AI Client, In-Memory Graph + Respository (Firestore-ready).
* **Frontend**: React 18, Vite, TailwindCSS (v3), TypeScript.
* **AI Routing**: A strict semantic intent router ensures the LLM never invents graph paths, but instead delegates to deterministic systems (like Dijkstra's algorithm).

## Getting Started

### 1. Prerequisites
- Python 3.14+
- Node.js 18+
- Gemini API Key

### 2. Backend Setup
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Set your API Key
set GEMINI_API_KEY=your_key_here

# Run the server (runs on http://localhost:8000)
uvicorn app.main:app --reload
```

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173` to view the dashboards!

## Testing
Run the comprehensive 120+ unit test suite:
```bash
cd backend
python -m pytest tests/ -v
```

## Security & Rate Limiting
- Configurable per-session token-bucket rate limiter.
- Prompt injection guards (`app/services/input_sanitizer.py`).
- Strict intent boundaries.