# 🌊 Namicast

> AI-powered surf forecast app — ask any question about any spot, and the agent analyzes wind, tide, swell, and your skill level to give a personalized recommendation.

## Live Demo
**Frontend:** [namicast.vercel.app](https://namicast.vercel.app)  
**API:** [web-production-6c38f.up.railway.app/docs](https://web-production-6c38f.up.railway.app/docs)

## Features
- 💬 **Agent chat** — ask natural language questions like "Is San Ono good for dawn patrol tomorrow?" and the agent fetches real data to answer
- 🌊 **Streaming responses** — answers appear token-by-token with live tool status ("Checking surf data...")
- 🧠 **Multi-turn memory** — follow-up questions work in context ("What about Trestles instead?")
- 👤 **Surf profile** — save your board type and skill level, pre-loaded on every visit
- 🔍 **Global spot search** — search any surf location worldwide via geocoding
- 💨 **Wind & spot analysis** — offshore/onshore detection and spot-specific insights
- 🏄 **Spot info** — break type, best swell/wind/tide, hazards, and local knowledge
- 📊 **Swell breakdown** — primary, secondary, and wind swell components
- 📅 **5-day forecast** — daily scoring for trip planning
- ⏰ **Today's sessions** — Dawn patrol, Morning, Afternoon, Evening comparison
- ⚙️ **Unit preferences** — ft/m, °F/°C, mph/km/h

## How the agent works

The `/chat/stream` endpoint runs an agentic loop powered by Claude's tool_use feature. Claude decides which tools to call based on the question:

| Tool | What it does |
|---|---|
| `geocode_location` | Converts a spot name to lat/lng via Nominatim |
| `get_surf_conditions` | Fetches Stormglass data and scores each session window |
| `get_spot_info` | Returns break type, difficulty, hazards, and ideal conditions |

Claude orchestrates the calls, then synthesizes a direct answer personalized to your board and skill level. Responses stream via Server-Sent Events so text appears as it's generated.

## Tech Stack
| Layer | Tech |
|---|---|
| Backend | Python, FastAPI |
| AI | Claude claude-sonnet-4-6 (Anthropic) — tool_use + streaming |
| Weather Data | Stormglass Marine API |
| Geocoding | OpenStreetMap Nominatim |
| Frontend | React |
| Deployment | Railway (API) + Vercel (Frontend) |
| Caching | In-memory cache (1hr TTL) |

## Local Setup

### Backend
```bash
git clone https://github.com/hengxu07/namicast.git
cd namicast
pip install -r requirements.txt
export STORMGLASS_KEY="your-key"
export ANTHROPIC_API_KEY="your-key"
uvicorn api:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm start
```

### Mock Mode (no Stormglass calls — Claude still runs)
```bash
export MOCK_MODE=true
export ANTHROPIC_API_KEY="your-key"
uvicorn api:app --reload
```

## API Endpoints
| Method | Endpoint | Description |
|---|---|---|
| POST | `/chat/stream` | Agentic chat — streams SSE events, maintains session memory |
| GET | `/forecast` | Current conditions + AI analysis + today's sessions |
| GET | `/forecast/daily` | 5-day forecast |
| GET | `/spot-info` | Spot type, hazards, best conditions |
