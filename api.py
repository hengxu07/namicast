import os
import httpx
import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone, timedelta
import hashlib

app = FastAPI(title="Namicast API", description="AI-powered surf forecast")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://namicast.vercel.app", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory cache
_cache = {}
CACHE_TTL_MINUTES = 60  # cache for 1 hour

def get_cache_key(lat: float, lng: float) -> str:
    """Generate cache key from coordinates."""
    return f"{round(lat, 2)}_{round(lng, 2)}"

def get_cached(key: str):
    """Get cached data if not expired."""
    if key in _cache:
        data, timestamp = _cache[key]
        if datetime.now(timezone.utc) - timestamp < timedelta(minutes=CACHE_TTL_MINUTES):
            return data
        else:
            del _cache[key]
    return None

def set_cache(key: str, data: dict):
    """Store data in cache with timestamp."""
    _cache[key] = (data, datetime.now(timezone.utc))

STORMGLASS_KEY = os.environ["STORMGLASS_KEY"]
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

def meters_to_feet(meters: float) -> float:
    """Convert meters to feet."""
    return round(meters * 3.28084, 1)

def degrees_to_direction(degrees: float) -> str:
    """Convert wind degrees to compass direction."""
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    index = round(degrees / 45) % 8
    return directions[index]

async def fetch_surf_data(lat: float, lng: float) -> dict:
    """Fetch surf conditions from Stormglass API."""
    cache_key = get_cache_key(lat, lng)
    cached = get_cached(cache_key)
    if cached:
        return cached

    params = "waveHeight,wavePeriod,windSpeed,windDirection,waterTemperature,swellHeight,swellPeriod,swellDirection,secondarySwellHeight,secondarySwellPeriod,secondarySwellDirection,windWaveHeight,windWavePeriod,windWaveDirection,tideHeight"
    url = "https://api.stormglass.io/v2/weather/point"

    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            params={"lat": lat, "lng": lng, "params": params},
            headers={"Authorization": STORMGLASS_KEY},
            timeout=10.0
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to fetch surf data")

    data = response.json()
    hours = data["hours"]

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
        "tideHeight": round(get_val("tideHeight"), 1),  # 加这行
        "swells": swells,
        "time": current["time"]
    }

    set_cache(cache_key, result)
    return result

def analyze_conditions(conditions: dict, board_type: str, skill_level: str) -> dict:
    """Use Claude to analyze surf conditions and give recommendations."""
    
    swell_text = ""
    for swell in conditions.get("swells", []):
        swell_text += f"\n- {swell['type']} swell: {swell['height']}ft @ {swell['period']}s {swell['direction']}"

    prompt = f"""You are an expert surf coach analyzing conditions for a surfer.

Current conditions:
- Total wave height: {conditions['waveHeight']} ft
- Wind: {conditions['windSpeed']} mph {conditions['windDirection']}
- Water temperature: {conditions['waterTemp']}°F

Swell breakdown:{swell_text if swell_text else ' No significant swells detected'}

Surfer profile:
- Board: {board_type}
- Skill level: {skill_level}

Provide a surf report in JSON format only, no other text:
{{
    "score": <1-10 integer>,
    "verdict": "<one of: Excellent, Good, Fair, Poor>",
    "summary": "<2-3 sentence summary of conditions>",
    "best_time": "<when today is best to surf>",
    "wetsuit": "<wetsuit recommendation>",
    "tips": ["<tip 1>", "<tip 2>", "<tip 3>"]
}}"""

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )
    
    import json
    raw = response.content[0].text
    clean = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(clean)

@app.get("/forecast")
async def get_forecast(
    lat: float,
    lng: float,
    board: str = "shortboard",
    skill: str = "intermediate"
):
    """Get surf forecast with AI analysis for a location."""
    conditions = await fetch_surf_data(lat, lng)
    analysis = analyze_conditions(conditions, board, skill)
    
    return {
        "conditions": conditions,
        "analysis": analysis,
        "location": {"lat": lat, "lng": lng}
    }