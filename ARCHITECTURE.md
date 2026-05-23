# Namicast — Architecture

## Stack

| Layer | Technology | Notes |
|---|---|---|
| Frontend | React + Tailwind CSS | Hosted on Vercel |
| Backend | FastAPI (Python) | Single `api.py`, hosted on Railway |
| AI | Claude API (claude-sonnet-4-6) | Agentic loop + SSE streaming + forecast analysis |
| AI (classification) | Claude Haiku (claude-haiku-4-5) | Spot type classification — cheaper, fast |
| Surf data | Stormglass Marine API | Wave height, period, wind, swell, tide |
| Geocoding | OpenStreetMap Nominatim | Spot name → lat/lng (free) |
| Database | PostgreSQL (JSONB) | Pre-computed spot cache, 12hr TTL |
| In-memory cache | Python dict | 1hr TTL fallback when no DB |
| Scheduler | APScheduler | Cron refresh at 5am/5pm UTC |

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         Browser                              │
│                                                              │
│   React + Tailwind  — Vercel                                 │
│   ┌───────────────────────────────────────────────────────┐  │
│   │  Search bar (geocoding) + default spot quick-picks    │  │
│   │  ChatInterface — SSE streaming chat                   │  │
│   │  DailyForecast / WeeklyForecast cards                 │  │
│   │  ProfileModal  — board type + skill level             │  │
│   └───────────────────────┬───────────────────────────────┘  │
└───────────────────────────┼──────────────────────────────────┘
                            │ HTTPS / SSE
┌───────────────────────────▼──────────────────────────────────┐
│                   FastAPI Backend  — Railway                  │
│                                                              │
│  POST /chat/stream    — streaming agentic chat               │
│  POST /chat           — non-streaming chat (legacy)          │
│  GET  /forecast       — conditions + AI analysis + sessions  │
│  GET  /forecast/daily — 5-day daily forecast                 │
│  GET  /spot-info      — break type, hazards, ideal conds     │
│  POST /admin/refresh  — manually trigger cache refresh       │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Claude Agent (claude-sonnet-4-6)                       │ │
│  │  Agentic loop — up to 5 tool-call rounds                │ │
│  │                                                         │ │
│  │  Tools:                                                 │ │
│  │    geocode_location(location)  → Nominatim lat/lng      │ │
│  │    get_surf_conditions(lat, lng, spot_name, date)       │ │
│  │    get_spot_info(spot_name)    → break type, hazards    │ │
│  │                                                         │ │
│  │  Streams via SSE: text delta, tool_start, tool_done     │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌──────────────────────────────────┐                        │
│  │  APScheduler (cron)              │                        │
│  │  5am + 5pm UTC — refresh_all()  │                        │
│  │  Fetches Stormglass for all 6   │                        │
│  │  default spots, saves to DB      │                        │
│  └──────────────────────────────────┘                        │
└────────────┬───────────────────────────┬─────────────────────┘
             │                           │
┌────────────▼──────────┐   ┌────────────▼────────────────────┐
│      PostgreSQL        │   │    External APIs                │
│                        │   │                                 │
│  spot_cache            │   │  Stormglass Marine API          │
│    spot_name (PK)      │   │    wave, wind, swell, tide      │
│    conditions  (JSONB) │   │    5-day hourly data            │
│    hours_data  (JSONB) │   │                                 │
│    spot_info   (JSONB) │   │  OpenStreetMap Nominatim        │
│    daily       (JSONB) │   │    spot name → lat/lng          │
│    computed_at         │   │                                 │
└───────────────────────┘   └─────────────────────────────────┘
```

---

## Data Flow

### Chat request (`/chat/stream`)
1. Frontend sends `{message, session_id, board, skill}` to `POST /chat/stream`
2. Backend loads session history from `_chat_sessions[session_id]` (in-memory)
3. Claude agent receives system prompt + history + message
4. Claude decides which tools to call; SSE events stream back:
   - `tool_start` → UI shows "Checking surf data..."
   - `tool_done` → UI hides the indicator
   - `text` delta → appended to chat bubble token-by-token
   - `done` → stream closes
5. Session history saved back to `_chat_sessions` (trimmed to last 40 messages); sessions older than 24hr are evicted

### Tool execution: `get_surf_conditions`
```
1. Check in-memory cache (1hr TTL)
2. If default spot → check PostgreSQL (12hr TTL)  ← fast path
3. If cache miss → call Stormglass API            ← slow path
4. Compute session windows (dawn patrol / morning / afternoon / evening)
5. Score each session via simple_score()
6. Return conditions + sessions to agent
```

### Forecast page (`/forecast`)
```
1. GET /forecast, /spot-info, /forecast/daily fired in parallel from frontend
2. /forecast: same cache lookup as above + analyze_forecast() Claude call
3. /spot-info: in-memory cache → DB → Claude Haiku generation
4. /forecast/daily: DB pre-computed daily data or hourly aggregation
```

### Background refresh (APScheduler)
```
Every 12 hours (5am + 5pm UTC):
  For each of the 6 default SoCal spots:
    1. Fetch Stormglass hourly data (5-day)
    2. Classify spot type via Claude Haiku
    3. Generate spot info via Claude Sonnet
    4. Compute daily aggregates + session scores
    5. Upsert into spot_cache table
```

---

## Caching Strategy

| Tier | Storage | TTL | Scope |
|---|---|---|---|
| DB fast path | PostgreSQL | 12 hours | Default spots only |
| In-memory | Python dict | 1 hour | Any spot, any key |
| Analysis cache | In-memory | 1 hour | Per (lat, lng, board, skill) |
| Session memory | In-memory dict | 24 hours | Per session_id |

Non-default (searched) spots fall back to a live Stormglass call and trigger a background `refresh_spot()` task to populate the DB for future requests.

---

## Agent Tools

| Tool | Calls | Purpose |
|---|---|---|
| `geocode_location` | Nominatim | Converts any spot name to lat/lng |
| `get_surf_conditions` | Stormglass (via cache) | Returns wave, wind, swell, session scores |
| `get_spot_info` | Claude Haiku / DB | Break type, difficulty, hazards, best conditions |

Claude orchestrates up to 5 tool-call rounds, then synthesizes a direct, personalized recommendation.

---

## Session Management

Chat sessions are stored in `_chat_sessions` — a plain Python dict keyed by `session_id` (UUID). History is trimmed to the last 40 messages to avoid context overflow. Sessions older than 24 hours are evicted lazily on each new message.

**Note:** this dict is in-process memory. A Railway restart clears all active sessions.

---

## Mock Mode

Set `MOCK_MODE=true` to run without a Stormglass API key. The backend generates randomized hourly data for 5 days. Claude agent still runs normally — useful for frontend development and demos.

---

## Directory Structure

```
namicast/
├── api.py                  — entire backend: routes, agent, caching, DB, scheduler
├── requirements.txt
├── Procfile
└── frontend/
    ├── src/
    │   ├── App.js              — main layout, spot search, forecast fetch
    │   ├── components/
    │   │   ├── ChatInterface.js — SSE streaming chat UI
    │   │   ├── DailyForecast.js
    │   │   ├── WeeklyForecast.js
    │   │   └── ProfileModal.js  — board + skill, saved to localStorage
    │   └── utils/
    │       └── scoreColor.js
    ├── tailwind.config.js
    └── package.json
```
