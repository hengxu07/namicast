# 🌊 Namicast

> AI-powered surf forecast app — personalized session recommendations for any spot worldwide.

## Live Demo
**Frontend:** [namicast.vercel.app](https://namicast.vercel.app)  
**API:** [web-production-6c38f.up.railway.app/docs](https://web-production-6c38f.up.railway.app/docs)

## Features
- 🔍 **Global spot search** — search any surf location worldwide via geocoding
- 🤖 **AI session analysis** — Claude AI analyzes conditions based on board type and skill level
- 💨 **Wind & spot analysis** — offshore/onshore detection and spot-specific insights
- 🏄 **Spot info** — break type, best swell/wind/tide, hazards, and local knowledge
- 📊 **Swell breakdown** — primary, secondary, and wind swell components
- 📅 **5-day forecast** — rule-based daily scoring for trip planning
- ⏰ **Today's sessions** — Dawn patrol, Morning, Afternoon, Evening comparison
- ⚙️ **Unit preferences** — ft/m, °F/°C, mph/km/h

## Tech Stack
| Layer | Tech |
|---|---|
| Backend | Python, FastAPI |
| AI | Claude AI (Anthropic) |
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

### Mock Mode (no API calls)
```bash
export MOCK_MODE=true
export ANTHROPIC_API_KEY="your-key"
uvicorn api:app --reload
```

## API Endpoints
| Method | Endpoint | Description |
|---|---|---|
| GET | `/forecast` | Current conditions + AI analysis + today's sessions |
| GET | `/forecast/daily` | 5-day forecast |
| GET | `/spot-info` | Spot type, hazards, best conditions |