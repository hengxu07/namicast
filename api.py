import os
import uuid
import asyncio
import httpx
import anthropic
import json
import logging
import random
from collections import defaultdict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel
from typing import Optional


app = FastAPI(title="Namicast API", description="AI-powered surf forecast")
MOCK_MODE = os.environ.get("MOCK_MODE", "false").lower() == "true"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://namicast.vercel.app", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatMessage(BaseModel):
    role: str
    content: str | list

class ChatRequest(BaseModel):
    message: str
    board: str = "longboard"
    skill: str = "intermediate"
    session_id: str | None = None
    history: list[ChatMessage] = []  # legacy fallback

AGENT_TOOLS = [
    {
        "name": "geocode_location",
        "description": "Convert a surf spot name to latitude/longitude coordinates",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "Surf spot or beach name"}
            },
            "required": ["location"]
        }
    },
    {
        "name": "get_surf_conditions",
        "description": "Get surf forecast data for a location. Returns wave height, period, wind, swells, and session scores for today or a specific date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lng": {"type": "number"},
                "spot_name": {"type": "string"},
                "date": {"type": "string", "description": "ISO date string YYYY-MM-DD, or omit for today"}
            },
            "required": ["lat", "lng", "spot_name"]
        }
    },
    {
        "name": "get_spot_info",
        "description": "Get general knowledge about a surf spot: break type, difficulty, best swell/wind/tide, hazards.",
        "input_schema": {
            "type": "object",
            "properties": {
                "spot_name": {"type": "string"}
            },
            "required": ["spot_name"]
        }
    }
]

async def execute_agent_tool(tool_name: str, tool_input: dict, board: str, skill: str) -> dict:
    if tool_name == "geocode_location":
        async with httpx.AsyncClient() as client:
            res = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": tool_input["location"], "format": "json", "limit": 1},
                headers={"Accept-Language": "en", "User-Agent": "Namicast/1.0"}
            )
        data = res.json()
        if not data:
            return {"error": f"Location '{tool_input['location']}' not found"}
        place = data[0]
        return {
            "name": place["display_name"].split(",")[0],
            "lat": float(place["lat"]),
            "lng": float(place["lon"])
        }

    elif tool_name == "get_surf_conditions":
        lat, lng = tool_input["lat"], tool_input["lng"]
        spot_name = tool_input.get("spot_name", "Unknown")
        target_date = tool_input.get("date")

        hours_raw = await fetch_surf_data(lat, lng)  # warms the cache
        cache_key = get_cache_key(lat, lng)
        hours = get_cached(cache_key + "_hours") or []

        # Filter hours to target date if specified
        if target_date:
            from datetime import date as date_type
            target = date_type.fromisoformat(target_date)
            day_hours = [
                h for h in hours
                if datetime.fromisoformat(h["time"].replace("+00:00", "+00:00")).date() == target
            ]
        else:
            today = datetime.now(timezone.utc).date()
            day_hours = [
                h for h in hours
                if datetime.fromisoformat(h["time"].replace("+00:00", "+00:00")).date() == today
            ]

        def get_avg(hrs, key):
            vals = [h.get(key, {}).get("sg", 0) or 0 for h in hrs]
            return sum(vals) / len(vals) if vals else 0

        sessions_def = [
            {"name": "Dawn patrol", "time": "5am–8am",  "hours": [5, 6, 7]},
            {"name": "Morning",     "time": "8am–12pm", "hours": [8, 9, 10, 11]},
            {"name": "Afternoon",   "time": "12pm–5pm", "hours": [12, 13, 14, 15, 16]},
            {"name": "Evening",     "time": "5pm–8pm",  "hours": [17, 18, 19]},
        ]

        sessions_input = []
        for session in sessions_def:
            s_hours = [
                h for h in day_hours
                if datetime.fromisoformat(h["time"].replace("+00:00", "+00:00")).hour in session["hours"]
            ]
            if not s_hours:
                continue
            sessions_input.append({
                "name": session["name"],
                "time": session["time"],
                "waveHeight": meters_to_feet(get_avg(s_hours, "waveHeight")),
                "wavePeriod": round(get_avg(s_hours, "wavePeriod"), 1),
                "windSpeed": round(get_avg(s_hours, "windSpeed") * 2.237, 1),
                "windDirection": degrees_to_direction(get_avg(s_hours, "windDirection")),
                "tideHeight": round(get_avg(s_hours, "seaLevel"), 1),
            })

        scored = analyze_sessions_batch(sessions_input, board, skill) if sessions_input else []
        score_map = {s["name"]: s for s in scored}
        for s in sessions_input:
            s.update(score_map.get(s["name"], {"score": 5, "verdict": "Fair"}))

        # Get spot type for context
        spot_type = get_cached(cache_key + "_spot_type") or get_spot_type(spot_name)

        return {
            "spot_name": spot_name,
            "spot_type": spot_type,
            "date": target_date or datetime.now(timezone.utc).date().isoformat(),
            "overall": {
                "waveHeight": hours_raw["waveHeight"],
                "wavePeriod": hours_raw["wavePeriod"],
                "windSpeed": hours_raw["windSpeed"],
                "windDirection": hours_raw["windDirection"],
                "waterTemp": hours_raw["waterTemp"],
            },
            "sessions": sessions_input
        }

    elif tool_name == "get_spot_info":
        # Reuse the existing endpoint logic
        cache_key = f"spot_info_{tool_input['spot_name'].lower().replace(' ', '_')}"
        cached = get_cached(cache_key)
        if cached:
            return cached
        response = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": f"""Provide surf spot info for: {tool_input['spot_name']}
Return ONLY JSON: {{"type":"","difficulty":"","best_season":"","best_swell":"","best_wind":"","best_tide":"","hazards":"","description":""}}"""}]
        )
        raw = response.content[0].text
        result = json.loads(raw.replace("```json","").replace("```","").strip())
        set_cache(cache_key, result)
        return result

    return {"error": f"Unknown tool: {tool_name}"}


def serialize_content(content) -> list:
    """Convert Anthropic SDK content blocks to plain JSON-serializable dicts."""
    result = []
    for block in content:
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
    return result


@app.post("/chat")
async def chat(request: ChatRequest):
    today = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    system = f"""You are Namicast, an expert AI surf coach with access to real-time surf data.
Today is {today}. Tomorrow's date is {tomorrow}.
User profile: {request.skill} surfer riding a {request.board}.

When answering questions about surf conditions:
- Always geocode the location first if you don't have lat/lng
- Fetch surf conditions for the relevant date
- Give a direct, opinionated answer (yes/no with reasoning)
- Be specific: mention wave size, wind quality (offshore/onshore), session score
- Keep answers concise — 2-4 sentences for a yes/no question, more for planning questions
- Use the surfer's skill level and board to personalize the recommendation"""

    messages = [{"role": m.role, "content": m.content} for m in request.history]
    messages.append({"role": "user", "content": request.message})

    # Agentic loop
    for _ in range(5):  # max 5 tool-call rounds
        for attempt in range(3):
            try:
                response = anthropic_client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1024,
                    system=system,
                    tools=AGENT_TOOLS,
                    messages=messages
                )
                break
            except anthropic.APIStatusError as e:
                if e.status_code == 529 and attempt < 2:
                    import time; time.sleep(2 ** attempt)
                else:
                    raise HTTPException(status_code=503, detail="AI service temporarily overloaded. Please try again in a moment.")

        serialized = serialize_content(response.content)

        if response.stop_reason == "end_turn":
            text = next((b["text"] for b in serialized if b["type"] == "text"), "")
            return {
                "reply": text,
                "history": messages + [{"role": "assistant", "content": serialized}]
            }

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": serialized})
            tool_results = []
            for block in serialized:
                if block["type"] == "tool_use":
                    result = await execute_agent_tool(block["name"], block["input"], request.board, request.skill)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": json.dumps(result)
                    })
            messages.append({"role": "user", "content": tool_results})

    return {"reply": "Sorry, I couldn't complete that request.", "history": messages}


def _make_system_prompt(skill: str, board: str) -> str:
    today = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    return f"""You are Namicast, an expert AI surf coach with access to real-time surf data.
Today is {today}. Tomorrow's date is {tomorrow}.
User profile: {skill} surfer riding a {board}.

When answering questions about surf conditions:
- Always geocode the location first if you don't have lat/lng
- Fetch surf conditions for the relevant date
- Give a direct, opinionated answer (yes/no with reasoning)
- Be specific: mention wave size, wind quality (offshore/onshore), session score
- Keep answers concise — 2-4 sentences for a yes/no question, more for planning questions
- Use the surfer's skill level and board to personalize the recommendation"""


TOOL_LABELS = {
    "geocode_location": "Finding location...",
    "get_surf_conditions": "Checking surf data...",
    "get_spot_info": "Loading spot info...",
}


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    async def generate():
        session_id = request.session_id or str(uuid.uuid4())
        messages = list(_chat_sessions.get(session_id, []))
        messages.append({"role": "user", "content": request.message})

        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

        system = _make_system_prompt(request.skill, request.board)

        for _ in range(5):
            try:
                async with async_anthropic_client.messages.stream(
                    model="claude-sonnet-4-6",
                    max_tokens=1024,
                    system=system,
                    tools=AGENT_TOOLS,
                    messages=messages,
                ) as stream:
                    async for text in stream.text_stream:
                        yield f"data: {json.dumps({'type': 'text', 'delta': text})}\n\n"
                    final = await stream.get_final_message()
            except anthropic.APIStatusError as e:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Service temporarily busy. Please try again.'})}\n\n"
                return

            serialized = serialize_content(final.content)

            if final.stop_reason == "end_turn":
                messages.append({"role": "assistant", "content": serialized})
                _chat_sessions[session_id] = messages[-40:]
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            if final.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": serialized})
                tool_results = []
                for block in serialized:
                    if block["type"] == "tool_use":
                        label = TOOL_LABELS.get(block["name"], "Working...")
                        yield f"data: {json.dumps({'type': 'tool_start', 'label': label})}\n\n"
                        result = await execute_agent_tool(block["name"], block["input"], request.board, request.skill)
                        yield f"data: {json.dumps({'type': 'tool_done'})}\n\n"
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "content": json.dumps(result),
                        })
                messages.append({"role": "user", "content": tool_results})

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
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
async_anthropic_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_KEY)

# Multi-turn chat sessions: session_id -> list of messages (capped at 40)
_chat_sessions: dict[str, list] = {}

def meters_to_feet(meters: float) -> float:
    return round(meters * 3.28084, 1)

def degrees_to_direction(degrees: float) -> str:
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    index = round(degrees / 45) % 8
    return directions[index]

async def fetch_surf_data(lat: float, lng: float) -> dict:
    """Fetch surf conditions from Stormglass API."""
    cache_key = get_cache_key(lat, lng)

    cached = get_cached(cache_key)
    if cached:
        return cached

    hours = get_cached(cache_key + "_hours")

    if not hours:
        if MOCK_MODE:
            mock_hours = []
            base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            for d in range(5):
                for h in range(24):
                    mock_hours.append({
                        "time": (base + timedelta(days=d, hours=h)).isoformat(),
                        "waveHeight":            {"sg": random.uniform(0.5, 2.0)},
                        "wavePeriod":            {"sg": random.uniform(6, 14)},
                        "windSpeed":             {"sg": random.uniform(1, 8)},
                        "windDirection":         {"sg": random.uniform(0, 360)},
                        "waterTemperature":      {"sg": 18.0},
                        "seaLevel":              {"sg": random.uniform(-0.5, 1.0)},
                        "swellHeight":           {"sg": random.uniform(0.3, 1.5)},
                        "swellPeriod":           {"sg": random.uniform(8, 14)},
                        "swellDirection":        {"sg": 225},
                        "secondarySwellHeight":  {"sg": random.uniform(0.1, 0.5)},
                        "secondarySwellPeriod":  {"sg": random.uniform(5, 8)},
                        "secondarySwellDirection": {"sg": 270},
                        "windWaveHeight":        {"sg": random.uniform(0.1, 0.4)},
                        "windWavePeriod":        {"sg": random.uniform(3, 5)},
                        "windWaveDirection":     {"sg": 260},
                    })
            hours = mock_hours
            set_cache(cache_key + "_hours", hours)
        else:
            params = "waveHeight,wavePeriod,windSpeed,windDirection,waterTemperature,swellHeight,swellPeriod,swellDirection,secondarySwellHeight,secondarySwellPeriod,secondarySwellDirection,windWaveHeight,windWavePeriod,windWaveDirection,seaLevel"
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.stormglass.io/v2/weather/point",
                    params={"lat": lat, "lng": lng, "params": params},
                    headers={"Authorization": STORMGLASS_KEY},
                    timeout=10.0
                )
            if response.status_code != 200:
                logger.error(f"Stormglass error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=502, detail="Failed to fetch surf data")
            hours = response.json()["hours"]
            set_cache(cache_key + "_hours", hours)

    # Find the current or next available hour
    now = datetime.now(timezone.utc)
    current = None
    for hour in hours:
        if datetime.fromisoformat(hour["time"].replace("+00:00", "+00:00")) >= now:
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
        "waveHeight":  meters_to_feet(get_val("waveHeight")),
        "wavePeriod":  round(get_val("wavePeriod"), 1),
        "windSpeed":   round(get_val("windSpeed") * 2.237, 1),
        "windDirection": degrees_to_direction(get_val("windDirection")),
        "waterTemp":   round(get_val("waterTemperature") * 9/5 + 32, 1),
        "tideHeight":  round(get_val("seaLevel"), 1),
        "swells":      swells,
        "time":        current["time"]
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
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text
    clean = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(clean)

def analyze_sessions_batch(sessions_data: list, board_type: str, skill_level: str) -> list:
    """Score all daily sessions in one Claude call instead of one per session."""
    sessions_text = ""
    for s in sessions_data:
        sessions_text += f"\n- {s['name']} ({s['time']}): {s['waveHeight']}ft waves, {s['wavePeriod']}s period, {s['windSpeed']}mph {s['windDirection']} wind"

    prompt = f"""You are a surf coach. Score each session for a {skill_level} on a {board_type}.

Sessions:{sessions_text}

Return ONLY a JSON array, no other text:
[
  {{"name": "Dawn patrol", "score": <1-10>, "verdict": "<Excellent|Good|Fair|Poor>"}},
  {{"name": "Morning",     "score": <1-10>, "verdict": "<Excellent|Good|Fair|Poor>"}},
  {{"name": "Afternoon",   "score": <1-10>, "verdict": "<Excellent|Good|Fair|Poor>"}},
  {{"name": "Evening",     "score": <1-10>, "verdict": "<Excellent|Good|Fair|Poor>"}}
]
Only include sessions that were provided."""

    response = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",  # Haiku: faster and cheaper for simple scoring
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text
    clean = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(clean)

def get_spot_type(spot_name: str) -> str:
    """Use Claude to determine surf spot type."""
    response = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",  # Simple classification, Haiku is sufficient
        max_tokens=20,
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
        model="claude-sonnet-4-6",
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

        # Cache analysis per location + board + skill combination
    analysis_key = cache_key + f"_analysis_{board}_{skill}"
    analysis = get_cached(analysis_key)
    if not analysis:
        analysis = analyze_conditions(conditions, board, skill, spot_name, spot_type)
        set_cache(analysis_key, analysis)

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
        # Build all session conditions first without any Claude calls
        sessions_input = []
        for session in sessions_def:
            session_hours = [
                h for h in hours
                if datetime.fromisoformat(h["time"].replace("+00:00", "+00:00")).date() == now.date()
                and datetime.fromisoformat(h["time"].replace("+00:00", "+00:00")).hour in session["hours"]
            ]
            if not session_hours:
                continue

            avg_wave     = meters_to_feet(get_avg(session_hours, "waveHeight"))
            avg_period   = round(get_avg(session_hours, "wavePeriod"), 1)
            avg_wind     = round(get_avg(session_hours, "windSpeed") * 2.237, 1)
            avg_wind_dir = degrees_to_direction(get_avg(session_hours, "windDirection"))

            sessions_input.append({
                "name":          session["name"],
                "time":          session["time"],
                "waveHeight":    avg_wave,
                "wavePeriod":    avg_period,
                "windSpeed":     avg_wind,
                "windDirection": avg_wind_dir,
            })

        # One Claude call for all sessions instead of four
        scored = analyze_sessions_batch(sessions_input, board, skill)
        score_map = {s["name"]: s for s in scored}

        sessions = []
        for s in sessions_input:
            result = score_map.get(s["name"], {})
            sessions.append({
                **s,
                "score":   result.get("score", 5),
                "verdict": result.get("verdict", "Fair"),
                "best":    False,
            })

        if sessions:
            max(sessions, key=lambda s: s["score"])["best"] = True

    return {
        "conditions": conditions,
        "analysis": analysis,
        "location": {"lat": lat, "lng": lng},
        "forecast": sessions
    }

def simple_score(wave_height: float, wind_speed: float, wave_period: float) -> dict:
    """Simple scoring without AI for daily forecast overview."""
    score = 5
    # Wave height (ideal 3-8ft)
    if wave_height < 1: score -= 2
    elif wave_height < 2: score -= 1
    elif wave_height > 10: score -= 2
    elif 3 <= wave_height <= 8: score += 1

    # Period (higher is better)
    if wave_period > 12: score += 2
    elif wave_period > 8: score += 1
    elif wave_period < 6: score -= 2

    # Wind (lower is better)
    if wind_speed < 5: score += 1
    elif wind_speed > 15: score -= 2
    elif wind_speed > 10: score -= 1

    score = max(1, min(10, score))
    if score >= 8: verdict = "Excellent"
    elif score >= 6: verdict = "Good"
    elif score >= 4: verdict = "Fair"
    else: verdict = "Poor"

    return {"score": score, "verdict": verdict}

@app.get("/forecast/daily")
async def get_daily_forecast(
    lat: float,
    lng: float,
    board: str = "longboard",
    skill: str = "intermediate",
    days: int = 5
):
    """Get multi-day surf forecast."""
    cache_key = get_cache_key(lat, lng)
    hours = get_cached(cache_key + "_hours")

    if not hours:
        if MOCK_MODE:
            # Generate mock hours for 5 days
            hours = []
            base = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
            for d in range(5):
                for h in range(24):

                    hours.append({
                        "time": (base + timedelta(days=d, hours=h)).isoformat(),
                        "waveHeight": {"sg": random.uniform(0.5, 2.0)},
                        "wavePeriod": {"sg": random.uniform(6, 14)},
                        "windSpeed": {"sg": random.uniform(1, 8)},
                        "windDirection": {"sg": random.uniform(0, 360)},
                        "waterTemperature": {"sg": 18.0},
                        "seaLevel": {"sg": random.uniform(-0.5, 1.0)},
                        "swellHeight": {"sg": random.uniform(0.3, 1.5)},
                        "swellPeriod": {"sg": random.uniform(8, 14)},
                        "swellDirection": {"sg": 225},
                        "secondarySwellHeight": {"sg": random.uniform(0.1, 0.5)},
                        "secondarySwellPeriod": {"sg": random.uniform(5, 8)},
                        "secondarySwellDirection": {"sg": 270},
                        "windWaveHeight": {"sg": random.uniform(0.1, 0.4)},
                        "windWavePeriod": {"sg": random.uniform(3, 5)},
                        "windWaveDirection": {"sg": 260},
                    })
            set_cache(cache_key + "_hours", hours)
        else:
            # Fetch from Stormglass
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
                raise HTTPException(status_code=502, detail="Failed to fetch surf data")
            hours = response.json()["hours"]
            set_cache(cache_key + "_hours", hours)

    def get_avg(hours_data, key):
        vals = [h.get(key, {}).get("sg", 0) or 0 for h in hours_data]
        return sum(vals) / len(vals) if vals else 0

    # Group hours by date
    days_map = defaultdict(list)
    for hour in hours:
        date = datetime.fromisoformat(hour["time"].replace("+00:00", "+00:00")).date()
        days_map[date].append(hour)

    daily = []
    for date in sorted(days_map.keys())[:days]:
        day_hours = days_map[date]
        avg_wave = meters_to_feet(get_avg(day_hours, "waveHeight"))
        avg_period = round(get_avg(day_hours, "wavePeriod"), 1)
        avg_wind = round(get_avg(day_hours, "windSpeed") * 2.237, 1)
        avg_wind_dir = degrees_to_direction(get_avg(day_hours, "windDirection"))

        conditions = {
            "waveHeight": avg_wave,
            "wavePeriod": avg_period,
            "windSpeed": avg_wind,
            "windDirection": avg_wind_dir,
            "waterTemp": round(get_avg(day_hours, "waterTemperature") * 9/5 + 32, 1),
            "swells": [],
        }
        # analysis = analyze_conditions(conditions, board, skill)
        analysis = simple_score(avg_wave, avg_wind, avg_period)

        daily.append({
            "date": date.isoformat(),
            "weekday": date.strftime("%a"),
            "score": analysis["score"],
            "verdict": analysis["verdict"],
            "waveHeight": avg_wave,
            "wavePeriod": avg_period,
            "windSpeed": avg_wind,
            "windDirection": avg_wind_dir,
            # "summary": analysis["summary"],
        })

    return {"daily": daily, "location": {"lat": lat, "lng": lng}}