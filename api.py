import os
import httpx
import anthropic
import json
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone, timedelta

app = FastAPI(title="Namicast API", description="AI-powered surf forecast")
MOCK_MODE = os.environ.get("MOCK_MODE", "false").lower() == "true"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://namicast.vercel.app", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)

# Simple in-memory cache
_cache = {}
CACHE_TTL_MINUTES = 60

def get_cache_key(lat: float, lng: float) -> str:
    return f"{round(lat, 2)}_{round(lng, 2)}"

def get_cached(key: str):
    if key in _cache:
        data, timestamp = _cache[key]
        if datetime.now(timezone.utc) - timestamp < timedelta(minutes=CACHE_TTL_MINUTES):
            return data
        else:
            del _cache[key]
    return None

def set_cache(key: str, data):
    _cache[key] = (data, datetime.now(timezone.utc))

STORMGLASS_KEY = os.environ["STORMGLASS_KEY"]
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

def meters_to_feet(meters: float) -> float:
    return round(meters * 3.28084, 1)

def degrees_to_direction(degrees: float) -> str:
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    index = round(degrees / 45) % 8
    return directions[index]

async def fetch_surf_data(lat: float, lng: float) -> dict:
    """Fetch surf conditions from Stormglass API."""

    if MOCK_MODE:
        mock_hours = [
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "waveHeight": {"sg": 1.2},
                "wavePeriod": {"sg": 12.0},
                "windSpeed": {"sg": 3.5},
                "windDirection": {"sg": 270},
                "waterTemperature": {"sg": 18.0},
                "swellHeight": {"sg": 1.0},
                "swellPeriod": {"sg": 12.0},
                "swellDirection": {"sg": 225},
                "secondarySwellHeight": {"sg": 0.4},
                "secondarySwellPeriod": {"sg": 8.0},
                "secondarySwellDirection": {"sg": 270},
                "windWaveHeight": {"sg": 0.3},
                "windWavePeriod": {"sg": 4.0},
                "windWaveDirection": {"sg": 260},
                "seaLevel": {"sg": 0.5},
            }
        ]
        cache_key = get_cache_key(lat, lng)
        set_cache(cache_key + "_hours", mock_hours)
        # fall through to process mock hours
        hours = mock_hours
        current = hours[0]

        def get_val(key):
            return current.get(key, {}).get("sg", 0) or 0

        swells = []
        if get_val("swellHeight") > 0.1:
            swells.append({
                "type": "Primary",
                "height": meters_to_feet(get_val("swellHeight")),
                "period": round(get_val("swellPeriod"), 1),
                "direction": degrees_to_direction(get_val("swellDirection"))
            })
        if get_val("secondarySwellHeight") > 0.1:
            swells.append({
                "type": "Secondary",
                "height": meters_to_feet(get_val("secondarySwellHeight")),
                "period": round(get_val("secondarySwellPeriod"), 1),
                "direction": degrees_to_direction(get_val("secondarySwellDirection"))
            })

        return {
            "waveHeight": meters_to_feet(get_val("waveHeight")),
            "wavePeriod": round(get_val("wavePeriod"), 1),
            "windSpeed": round(get_val("windSpeed") * 2.237, 1),
            "windDirection": degrees_to_direction(get_val("windDirection")),
            "waterTemp": round(get_val("waterTemperature") * 9/5 + 32, 1),
            "tideHeight": round(get_val("seaLevel"), 1),
            "swells": swells,
            "time": current["time"]
        }
    
    cache_key = get_cache_key(lat, lng)

    cached = get_cached(cache_key)
    if cached:
        return cached

    hours = get_cached(cache_key + "_hours")

    if not hours:
        params = "waveHeight,wavePeriod,windSpeed,windDirection,waterTemperature,swellHeight,swellPeriod,swellDirection,secondarySwellHeight,secondarySwellPeriod,secondarySwellDirection,windWaveHeight,windWavePeriod,windWaveDirection,seaLevel"
        url = "https://api.stormglass.io/v2/weather/point"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={"lat": lat, "lng": lng, "params": params},
                headers={"Authorization": STORMGLASS_KEY},
                timeout=10.0
            )


        if response.status_code != 200:
            logger.error(f"Stormglass error: {response.status_code} - {response.text}")
            raise HTTPException(status_code=502, detail="Failed to fetch surf data")

        hours = response.json()["hours"]
        set_cache(cache_key + "_hours", hours)

    now = datetime.now(timezone.utc)
    current = None
    for hour in hours:
        hour_time = datetime.fromisoformat(hour["time"].replace("+00:00", "+00:00"))
        if hour_time >= now:
            current = hour
            break

    if not current:
        current = hours[0]

    def get_val(key):
        return current.get(key, {}).get("sg", 0) or 0

    swells = []
    if get_val("swellHeight") > 0.1:
        swells.append({
            "type": "Primary",
            "height": meters_to_feet(get_val("swellHeight")),
            "period": round(get_val("swellPeriod"), 1),
            "direction": degrees_to_direction(get_val("swellDirection"))
        })
    if get_val("secondarySwellHeight") > 0.1:
        swells.append({
            "type": "Secondary",
            "height": meters_to_feet(get_val("secondarySwellHeight")),
            "period": round(get_val("secondarySwellPeriod"), 1),
            "direction": degrees_to_direction(get_val("secondarySwellDirection"))
        })
    if get_val("windWaveHeight") > 0.1:
        swells.append({
            "type": "Wind swell",
            "height": meters_to_feet(get_val("windWaveHeight")),
            "period": round(get_val("windWavePeriod"), 1),
            "direction": degrees_to_direction(get_val("windWaveDirection"))
        })

    result = {
        "waveHeight": meters_to_feet(get_val("waveHeight")),
        "wavePeriod": round(get_val("wavePeriod"), 1),
        "windSpeed": round(get_val("windSpeed") * 2.237, 1),
        "windDirection": degrees_to_direction(get_val("windDirection")),
        "waterTemp": round(get_val("waterTemperature") * 9/5 + 32, 1),
        "tideHeight": round(get_val("seaLevel"), 1),
        "swells": swells,
        "time": current["time"]
    }

    set_cache(cache_key, result)
    return result

def analyze_conditions(conditions: dict, board_type: str, skill_level: str, spot_name: str = "Unknown", spot_type: str = "beach break") -> dict:
    """Use Claude to analyze surf conditions and give recommendations."""
    swell_text = ""
    for swell in conditions.get("swells", []):
        swell_text += f"\n- {swell['type']} swell: {swell['height']}ft @ {swell['period']}s {swell['direction']}"

    prompt = f"""You are an expert surf coach analyzing conditions at a specific surf spot.

Surf spot: {spot_name}
Spot type: {spot_type}

Current conditions:
- Total wave height: {conditions['waveHeight']} ft
- Wind: {conditions['windSpeed']} mph {conditions['windDirection']}
- Water temperature: {conditions['waterTemp']}°F
- Tide: {conditions.get('tideHeight', 0)} m


Swell breakdown:{swell_text if swell_text else ' No significant swells detected'}

Surfer profile:
- Board: {board_type}
- Skill level: {skill_level}

In your analysis, specifically address:
1. Whether the wind is offshore, onshore, or cross-shore for this spot, and how it affects wave quality
2. How the spot type ({spot_type}) interacts with current swell direction and period
3. Which swell direction is ideal for this spot and whether current swells are optimal

Provide a surf report in JSON format only, no other text:
{{
    "score": <1-10 integer>,
    "verdict": "<one of: Excellent, Good, Fair, Poor>",
    "summary": "<2-3 sentence summary including wind effect and spot characteristics>",
    "wind_analysis": "<1 sentence: is wind offshore/onshore/cross-shore and how it affects this spot>",
    "spot_analysis": "<1 sentence: how spot type affects today's conditions>",
    "best_time": "<when today is best to surf>",
    "wetsuit": "<wetsuit recommendation>",
    "tips": ["<tip 1>", "<tip 2>", "<tip 3>"]
}}"""

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text
    clean = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(clean)

def get_spot_type(spot_name: str) -> str:
    """Use Claude to determine surf spot type."""
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": f"""What type of surf break is {spot_name}? 
Reply with ONLY one of: point break, beach break, reef break, river mouth.
If unknown, reply: beach break"""
        }]
    )
    return response.content[0].text.strip().lower()

@app.get("/spot-info")
async def get_spot_info(spot_name: str):
    """Get general information about a surf spot."""
    cache_key = f"spot_info_{spot_name.lower().replace(' ', '_')}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": f"""Provide information about the surf spot: {spot_name}

Return ONLY a JSON object, no other text:
{{
    "type": "<point break/beach break/reef break/river mouth>",
    "difficulty": "<beginner/intermediate/advanced/expert>",
    "best_season": "<best months or season>",
    "best_swell": "<ideal swell direction and size>",
    "best_wind": "<ideal wind direction>",
    "best_tide": "<ideal tide>",
    "hazards": "<main hazards>",
    "description": "<2 sentence description of the spot>",
    "known_for": "<what this spot is famous for>"
}}

If you don't know this specific spot, provide best estimates based on its location."""
        }]
    )

    raw = response.content[0].text
    clean = raw.replace("```json", "").replace("```", "").strip()
    result = json.loads(clean)
    set_cache(cache_key, result)
    return result

@app.get("/forecast")
async def get_forecast(
    lat: float,
    lng: float,
    board: str = "longboard",
    skill: str = "intermediate",
    spot_name: str = "Unknown"
):
    conditions = await fetch_surf_data(lat, lng)

    """Get surf forecast with AI analysis and daily session breakdown."""
    # Get spot type (cache it too)
    cache_key = get_cache_key(lat, lng)
    spot_type = get_cached(cache_key + "_spot_type")
    if not spot_type:
        spot_type = get_spot_type(spot_name)
        set_cache(cache_key + "_spot_type", spot_type)

    analysis = analyze_conditions(conditions, board, skill)

    cache_key = get_cache_key(lat, lng)
    hours = get_cached(cache_key + "_hours")

    sessions_def = [
        {"name": "Dawn patrol", "time": "5am–8am",  "hours": [5, 6, 7]},
        {"name": "Morning",     "time": "8am–12pm", "hours": [8, 9, 10, 11]},
        {"name": "Afternoon",   "time": "12pm–5pm", "hours": [12, 13, 14, 15, 16]},
        {"name": "Evening",     "time": "5pm–8pm",  "hours": [17, 18, 19]},
    ]

    def get_avg(hours_data, key):
        vals = [h.get(key, {}).get("sg", 0) or 0 for h in hours_data]
        return sum(vals) / len(vals) if vals else 0

    sessions = []
    now = datetime.now(timezone.utc)

    if hours:
        for session in sessions_def:
            session_hours = [
                h for h in hours
                if datetime.fromisoformat(h["time"].replace("+00:00", "+00:00")).date() == now.date()
                and datetime.fromisoformat(h["time"].replace("+00:00", "+00:00")).hour in session["hours"]
            ]

            if not session_hours:
                continue

            avg_wave = meters_to_feet(get_avg(session_hours, "waveHeight"))
            avg_period = round(get_avg(session_hours, "wavePeriod"), 1)
            avg_wind = round(get_avg(session_hours, "windSpeed") * 2.237, 1)
            avg_wind_dir = degrees_to_direction(get_avg(session_hours, "windDirection"))

            session_conditions = {
                "waveHeight": avg_wave,
                "wavePeriod": avg_period,
                "windSpeed": avg_wind,
                "windDirection": avg_wind_dir,
                "waterTemp": round(get_avg(session_hours, "waterTemperature") * 9/5 + 32, 1),
                "swells": [],
            }

            session_analysis = analyze_conditions(session_conditions, board, skill)

            sessions.append({
                "name": session["name"],
                "time": session["time"],
                "score": session_analysis["score"],
                "verdict": session_analysis["verdict"],
                "waveHeight": avg_wave,
                "wavePeriod": avg_period,
                "windSpeed": avg_wind,
                "windDirection": avg_wind_dir,
                "best": False
            })

        if sessions:
            best = max(sessions, key=lambda s: s["score"])
            best["best"] = True

    return {
        "conditions": conditions,
        "analysis": analysis,
        "location": {"lat": lat, "lng": lng},
        "forecast": sessions
    }