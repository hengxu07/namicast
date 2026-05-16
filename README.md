# 🌊 Namicast

> AI-powered surf forecast app — ask any question about any spot, and the agent autonomously fetches real-time data to give a personalized recommendation based on your board and skill level.

## Live Demo
**Frontend:** [namicast.vercel.app](https://namicast.vercel.app)  
**API:** [web-production-6c38f.up.railway.app/docs](https://web-production-6c38f.up.railway.app/docs)

## Features
- 💬 **Agent chat** — ask natural language questions like "Is San Ono good for dawn patrol tomorrow?" and the agent autonomously fetches real data to answer
- 🌊 **Streaming responses** — answers appear token-by-token with live tool status indicators ("Checking surf data...")
- 🧠 **Multi-turn memory** — follow-up questions work in context ("What about Trestles instead?"), with 24h session TTL
- 👤 **Surf profile** — save your board type and skill level, pre-loaded into every AI response
- 🔍 **Global spot search** — search any surf location worldwide via geocoding, with quick-pick dropdown for popular spots
- 💨 **Wind & spot analysis** — offshore/onshore detection and spot-specific insights
- 🏄 **Spot info** — break type, best swell/wind/tide, hazards, and local knowledge
- 📊 **Swell breakdown** — primary, secondary, and wind swell components
- 📅 **5-day forecast** — daily scoring for trip planning
- ⏰ **Today's sessions** — Dawn patrol, Morning, Afternoon, Evening comparison
- ⚙️ **Unit preferences** — ft/m, °F/°C, mph/km/h

## How the agent works

The `/chat/stream` endpoint runs an agentic loop powered by Claude's tool_use feature. Claude autonomously decides which tools to call and in what order based on the question — no hardcoded routing:

| Tool | What it does |
|---|---|
| `geocode_location` | Converts a spot name to lat/lng via OpenStreetMap Nominatim |
| `get_surf_conditions` | Fetches Stormglass data, scores each session window, checks DB cache first |
| `get_spot_info` | Returns break type, difficulty, hazards, and ideal conditions |

Claude orchestrates up to 5 tool-call rounds, then synthesizes a direct answer personalized to the surfer's board and skill level. Responses stream via Server-Sent Events so text appears as it's generated.

### Performance architecture

Default spots (San Onofre, Doheny, Huntington Beach, Malibu, Trestles, Rincon) are pre-computed and cached in PostgreSQL every 12 hours via an APScheduler cron job. Requests for these spots hit the DB fast path instead of making live Stormglass API calls, cutting response time significantly. Non-default spots fall back to live fetch and trigger a background DB population task for future requests.

```
Request for default spot → DB fast path (< 50ms)
Request for unknown spot → Live Stormglass fetch → background DB save
```

## Tech Stack
| Layer | Tech |
|---|---|
| Backend | Python, FastAPI (async) |
| AI | Claude Sonnet 4.6 (Anthropic) — tool_use + SSE streaming |
| Weather Data | Stormglass Marine API |
| Geocoding | OpenStreetMap Nominatim |
| Database | PostgreSQL (Railway) — pre-computed spot cache, JSONB storage |
| Scheduler | APScheduler — cron refresh at 5am/5pm UTC |
| Frontend | React, Tailwind CSS |
| UI | Dark ocean theme, glassmorphism cards, Inter font |
| Deployment | Railway (API) + Vercel (Frontend) |
| Caching | PostgreSQL (12hr TTL) + in-memory fallback (1hr TTL) |

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

### Mock Mode (no Stormglass calls — Claude agent still runs)
```bash
export MOCK_MODE=true
export ANTHROPIC_API_KEY="your-key"
uvicorn api:app --reload
```

### With PostgreSQL caching (optional)
```bash
export DATABASE_URL="postgresql://user:pass@host/db"
uvicorn api:app --reload
# On startup: initializes schema, warms cache for all 6 default spots
```

## API Endpoints
| Method | Endpoint | Description |
|---|---|---|
| POST | `/chat/stream` | Agentic chat — streams SSE events, maintains session memory with TTL |
| GET | `/forecast` | Current conditions + AI analysis + today's sessions (DB fast path) |
| GET | `/forecast/daily` | 5-day forecast (DB fast path for default spots) |
| GET | `/spot-info` | Spot type, hazards, best conditions |
| POST | `/admin/refresh` | Manually trigger cache refresh for all default spots |
