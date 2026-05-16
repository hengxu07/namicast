import os
import uuid
import asyncio
import httpx
import anthropic
import json
import logging
import random
import psycopg2
import psycopg2.extras
from collections import defaultdict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler


app = FastAPI(title="Namicast API", description="AI-powered surf forecast")
MOCK_MODE = os.environ.get("MOCK_MODE", "false").lower() == "true"
DATABASE_URL = os.environ.get("DATABASE_URL")

DEFAULT_SPOTS = [
    {"name": "San Onofre",         "lat": 33.37, "lng": -117.57},
    {"name": "Doheny State Beach", "lat": 33.46, "lng": -117.68},
    {"name": "Huntington Beach",   "lat": 33.66, "lng": -118.00},
    {"name": "Malibu",             "lat": 34.04, "lng": -118.68},
    {"name": "Trestles",           "lat": 33.38, "lng": -117.59},
    {"name": "Rincon",             "lat": 34.37, "lng": -119.47},
]
DEFAULT_SPOT_NAMES = {s["name"].lower() for s in DEFAULT_SPOTS}

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

        cache_key = get_cache_key(lat, lng)

        # Check DB first for default spots
        db_row = await asyncio.to_thread(db_get_spot, spot_name) if spot_name.lower() in DEFAULT_SPOT_NAMES else None
        if db_row:
            hours_raw = db_row["conditions"]
            hours = db_row["hours_data"]
            set_cache(cache_key, hours_raw)
            set_cache(cache_key + "_hours", hours)
        else:
            hours_raw = await fetch_surf_data(lat, lng)
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

        for s in sessions_input:
            s.update(simple_score(s["waveHeight"], s["windSpeed"], s["wavePeriod"]))

        # Use cached spot type; default to beach break rather than blocking on a Claude call
        spot_type = get_cached(cache_key + "_spot_type") or "beach break"

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
        cache_key = f"spot_info_{tool_input['spot_name'].lower().replace(' ', '_')}"
        cached = get_cached(cache_key)
        if cached:
            return cached
        # Check DB for pre-computed spot info
        db_row = await asyncio.to_thread(db_get_spot, tool_input["spot_name"]) if tool_input["spot_name"].lower() in DEFAULT_SPOT_NAMES else None
        if db_row and db_row.get("spot_info"):
            set_cache(cache_key, db_row["spot_info"])
            return db_row["spot_info"]
        response = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": f"""Provide surf spot info for: {tool_input['spot_name']}
Return ONLY JSON: {{"type":"","difficulty":"","best_season":"","best_swell":"","best_wind":"","best_tide":"","hazards":"","description":""}}"""}]
        )
        raw = response.content[0].text
        result = parse_json_response(raw)
        set_cache(cache_key, result)
        return result

    return {"error": f"Unknown tool: {tool_name}"}


def parse_json_response(raw: str):
    """Extract JSON from Claude's response regardless of surrounding text or code fences."""
    # Try array first, then object
    for start_char, end_char in [('[', ']'), ('{', '}')]:
        start = raw.find(start_char)
        end = raw.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"No valid JSON found in response: {raw[:200]}")


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

Response rules — follow these strictly:
- NEVER narrate your reasoning or say "Let me think..." / "Let me start by..." — just act and respond
- NEVER use horizontal rules (---) or headers (##) in your responses
- Always geocode the location first, then fetch surf conditions — do not ask for permission, just do it
- If the user's location is vague (e.g. "Southern California"), pick the most relevant spot and state your assumption
- Give a direct, opinionated answer first, then supporting detail
- Use **bold** sparingly for spot names and session scores only
- Keep answers concise: 3-5 sentences for yes/no questions, short bullet points for comparisons
- Use the surfer's skill level and board to personalize — a {skill} on a {board} needs different advice than an expert on a shortboard
- No filler phrases like "Great choice!" or "Happy to help!" — be direct like a knowledgeable surf buddy"""


TOOL_LABELS = {
    "geocode_location": "Finding location...",
    "get_surf_conditions": "Checking surf data...",
    "get_spot_info": "Loading spot info...",
}


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    async def generate():
        session_id = request.session_id or str(uuid.uuid4())
        messages = list(_chat_sessions.get(session_id, {}).get("messages", []))
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
                _chat_sessions[session_id] = {"messages": messages[-40:], "last_active": datetime.now(timezone.utc)}
                _evict_old_sessions()
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

# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    if not DATABASE_URL:
        return None
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception as e:
        logger.error(f"DB connect failed: {e}")
        return None

def init_db():
    conn = get_db()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS spot_cache (
                    spot_name   TEXT PRIMARY KEY,
                    lat         FLOAT NOT NULL,
                    lng         FLOAT NOT NULL,
                    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    conditions  JSONB,
                    hours_data  JSONB,
                    spot_type   TEXT,
                    spot_info   JSONB,
                    daily       JSONB
                )
            """)
        conn.commit()
        logger.info("DB initialized")
    except Exception as e:
        logger.error(f"DB init failed: {e}")
    finally:
        conn.close()

def db_get_spot(spot_name: str, max_age_hours: int = 12) -> dict | None:
    conn = get_db()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM spot_cache
                WHERE lower(spot_name) = lower(%s)
                  AND computed_at > NOW() - INTERVAL '%s hours'
            """, (spot_name, max_age_hours))
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"DB read failed: {e}")
        return None
    finally:
        conn.close()

def db_save_spot(spot_name: str, lat: float, lng: float, data: dict):
    conn = get_db()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO spot_cache (spot_name, lat, lng, computed_at, conditions, hours_data, spot_type, spot_info, daily)
                VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s, %s)
                ON CONFLICT (spot_name) DO UPDATE SET
                    computed_at = NOW(),
                    conditions  = EXCLUDED.conditions,
                    hours_data  = EXCLUDED.hours_data,
                    spot_type   = EXCLUDED.spot_type,
                    spot_info   = EXCLUDED.spot_info,
                    daily       = EXCLUDED.daily
            """, (
                spot_name, lat, lng,
                json.dumps(data["conditions"]),
                json.dumps(data["hours_data"]),
                data["spot_type"],
                json.dumps(data["spot_info"]),
                json.dumps(data["daily"]),
            ))
        conn.commit()
        logger.info(f"DB saved: {spot_name}")
    except Exception as e:
        logger.error(f"DB save failed for {spot_name}: {e}")
    finally:
        conn.close()

# ── In-memory cache (fallback when no DB) ─────────────────────────────────────

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

# Multi-turn chat sessions: session_id -> {messages, last_active}
SESSION_TTL_HOURS = 24
_chat_sessions: dict[str, dict] = {}

def _evict_old_sessions():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=SESSION_TTL_HOURS)
    stale = [sid for sid, s in _chat_sessions.items() if s["last_active"] < cutoff]
    for sid in stale:
        del _chat_sessions[sid]

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

async def analyze_forecast(
    conditions: dict,
    sessions_data: list,
    board_type: str,
    skill_level: str,
    spot_name: str = "Unknown",
    spot_type: str = "beach break",
) -> tuple[dict, list]:
    """Single Claude call returning both full analysis and per-session scores."""
    swell_text = "".join(
        f"\n- {s['type']}: {s['height']}ft @ {s['period']}s {s['direction']}"
        for s in conditions.get("swells", [])
    ) or " none"

    sessions_text = "".join(
        f"\n- {s['name']} ({s['time']}): {s['waveHeight']}ft, {s['wavePeriod']}s, {s['windSpeed']}mph {s['windDirection']}"
        for s in sessions_data
    ) or " no session data"

    prompt = f"""You are an expert surf coach analyzing {spot_name} ({spot_type}).

Conditions:
- Waves: {conditions['waveHeight']}ft @ {conditions['wavePeriod']}s
- Wind: {conditions['windSpeed']}mph {conditions['windDirection']}
- Water temp: {conditions['waterTemp']}°F
- Tide: {conditions.get('tideHeight', 0)}m
- Swells:{swell_text}

Today's sessions:{sessions_text}

Surfer: {skill_level} on a {board_type}

Address wind direction (offshore/onshore/cross-shore), how {spot_type} interacts with current swell, and personalize for the surfer's level.

Return ONLY JSON, no other text:
{{
  "analysis": {{
    "score": <1-10 integer>,
    "verdict": "<Excellent|Good|Fair|Poor>",
    "summary": "<2-3 sentences>",
    "wind_analysis": "<1 sentence>",
    "spot_analysis": "<1 sentence>",
    "best_time": "<best window today>",
    "wetsuit": "<recommendation>",
    "tips": ["<tip 1>", "<tip 2>", "<tip 3>"]
  }},
  "sessions": [
    {{"name": "<name>", "score": <1-10>, "verdict": "<Excellent|Good|Fair|Poor>"}}
  ]
}}
Include only the sessions provided."""

    response = await asyncio.to_thread(
        anthropic_client.messages.create,
        model="claude-sonnet-4-6",
        max_tokens=768,
        messages=[{"role": "user", "content": prompt}],
    )
    result = parse_json_response(response.content[0].text)
    return result["analysis"], result.get("sessions", [])

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
    result = parse_json_response(raw)
    set_cache(cache_key, result)
    return result

# ── Background refresh job ────────────────────────────────────────────────────

async def refresh_spot(spot: dict):
    """Fetch and store all board/skill-agnostic data for one spot."""
    name, lat, lng = spot["name"], spot["lat"], spot["lng"]
    try:
        conditions = await fetch_surf_data(lat, lng)
        cache_key = get_cache_key(lat, lng)
        hours_data = get_cached(cache_key + "_hours") or []
        spot_type = get_spot_type(name)
        set_cache(cache_key + "_spot_type", spot_type)

        spot_info_key = f"spot_info_{name.lower().replace(' ', '_')}"
        spot_info = get_cached(spot_info_key)
        if not spot_info:
            response = anthropic_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                messages=[{"role": "user", "content": f"""Provide information about the surf spot: {name}
Return ONLY a JSON object, no other text:
{{"type":"","difficulty":"","best_season":"","best_swell":"","best_wind":"","best_tide":"","hazards":"","description":"","known_for":""}}
If unknown, estimate from location."""}]
            )
            spot_info = parse_json_response(response.content[0].text)
            set_cache(spot_info_key, spot_info)

        def get_avg(hrs, key):
            vals = [h.get(key, {}).get("sg", 0) or 0 for h in hrs]
            return sum(vals) / len(vals) if vals else 0

        days_map = defaultdict(list)
        for hour in hours_data:
            date = datetime.fromisoformat(hour["time"].replace("+00:00", "+00:00")).date()
            days_map[date].append(hour)

        daily = []
        for date in sorted(days_map.keys())[:5]:
            day_hours = days_map[date]
            avg_wave = meters_to_feet(get_avg(day_hours, "waveHeight"))
            avg_wind = round(get_avg(day_hours, "windSpeed") * 2.237, 1)
            avg_period = round(get_avg(day_hours, "wavePeriod"), 1)
            sc = simple_score(avg_wave, avg_wind, avg_period)
            daily.append({
                "date": date.isoformat(),
                "weekday": date.strftime("%a"),
                "score": sc["score"],
                "verdict": sc["verdict"],
                "waveHeight": avg_wave,
                "wavePeriod": avg_period,
                "windSpeed": avg_wind,
                "windDirection": degrees_to_direction(get_avg(day_hours, "windDirection")),
            })

        await asyncio.to_thread(db_save_spot, name, lat, lng, {
            "conditions": conditions,
            "hours_data": hours_data,
            "spot_type": spot_type,
            "spot_info": spot_info,
            "daily": daily,
        })
        logger.info(f"Refreshed: {name}")
    except Exception as e:
        logger.error(f"Refresh failed for {name}: {e}")


async def refresh_all_spots():
    logger.info("Starting spot refresh for all default spots...")
    await asyncio.gather(*[refresh_spot(s) for s in DEFAULT_SPOTS])
    logger.info("Spot refresh complete.")


scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup():
    init_db()
    if DATABASE_URL:
        # Refresh at 5am and 5pm UTC daily
        scheduler.add_job(refresh_all_spots, "cron", hour="5,17", minute=0)
        scheduler.start()
        await refresh_all_spots()

@app.on_event("shutdown")
async def shutdown():
    if scheduler.running:
        scheduler.shutdown()

@app.post("/admin/refresh")
async def admin_refresh():
    """Manually trigger a refresh of all default spots."""
    asyncio.create_task(refresh_all_spots())
    return {"status": "refresh started"}


# ── Forecast endpoint ─────────────────────────────────────────────────────────

@app.get("/forecast")
async def get_forecast(
    lat: float,
    lng: float,
    board: str = "longboard",
    skill: str = "intermediate",
    spot_name: str = "Unknown"
):
    """Get surf forecast with AI analysis and daily session breakdown."""
    cache_key = get_cache_key(lat, lng)

    # ── Fast path: load pre-computed data from DB ──────────────────────────────
    db_row = await asyncio.to_thread(db_get_spot, spot_name) if spot_name.lower() in DEFAULT_SPOT_NAMES else None

    if db_row:
        conditions = db_row["conditions"]
        hours      = db_row["hours_data"]
        spot_type  = db_row["spot_type"]
        # Warm the in-memory cache so the agent tools can use it too
        set_cache(cache_key, conditions)
        set_cache(cache_key + "_hours", hours)
        set_cache(cache_key + "_spot_type", spot_type)
    else:
        # ── Slow path: live fetch ──────────────────────────────────────────────
        conditions = await fetch_surf_data(lat, lng)
        hours      = get_cached(cache_key + "_hours")
        spot_type  = get_cached(cache_key + "_spot_type") or "beach break"
        # Save to DB so next request is fast
        if DATABASE_URL:
            asyncio.create_task(refresh_spot({"name": spot_name, "lat": lat, "lng": lng}))

    # Build sessions input from hours data
    sessions_def = [
        {"name": "Dawn patrol", "time": "5am–8am",  "hours": [5, 6, 7]},
        {"name": "Morning",     "time": "8am–12pm", "hours": [8, 9, 10, 11]},
        {"name": "Afternoon",   "time": "12pm–5pm", "hours": [12, 13, 14, 15, 16]},
        {"name": "Evening",     "time": "5pm–8pm",  "hours": [17, 18, 19]},
    ]

    def get_avg(hours_data, key):
        vals = [h.get(key, {}).get("sg", 0) or 0 for h in hours_data]
        return sum(vals) / len(vals) if vals else 0

    now = datetime.now(timezone.utc)
    sessions_input = []
    if hours:
        for session in sessions_def:
            session_hours = [
                h for h in hours
                if datetime.fromisoformat(h["time"].replace("+00:00", "+00:00")).date() == now.date()
                and datetime.fromisoformat(h["time"].replace("+00:00", "+00:00")).hour in session["hours"]
            ]
            if not session_hours:
                continue
            sessions_input.append({
                "name":          session["name"],
                "time":          session["time"],
                "waveHeight":    meters_to_feet(get_avg(session_hours, "waveHeight")),
                "wavePeriod":    round(get_avg(session_hours, "wavePeriod"), 1),
                "windSpeed":     round(get_avg(session_hours, "windSpeed") * 2.237, 1),
                "windDirection": degrees_to_direction(get_avg(session_hours, "windDirection")),
            })

    # Single Claude call for both analysis and session scores
    analysis_key = cache_key + f"_analysis_{board}_{skill}"
    cached_analysis = get_cached(analysis_key)
    if cached_analysis:
        analysis = cached_analysis
        scored = cached_analysis.get("_sessions", [])
    else:
        analysis, scored = await analyze_forecast(
            conditions, sessions_input, board, skill, spot_name, spot_type
        )
        analysis["_sessions"] = scored  # store together to avoid double-caching
        set_cache(analysis_key, analysis)

    score_map = {s["name"]: s for s in scored}
    sessions = [
        {**s, "score": score_map.get(s["name"], {}).get("score", 5),
              "verdict": score_map.get(s["name"], {}).get("verdict", "Fair"),
              "best": False}
        for s in sessions_input
    ]
    if sessions:
        max(sessions, key=lambda s: s["score"])["best"] = True

    return {
        "conditions": conditions,
        "analysis":   {k: v for k, v in analysis.items() if k != "_sessions"},
        "location":   {"lat": lat, "lng": lng},
        "forecast":   sessions
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
    days: int = 5,
    spot_name: str = ""
):
    """Get multi-day surf forecast."""
    cache_key = get_cache_key(lat, lng)
    hours = get_cached(cache_key + "_hours")

    # Fast path: check DB for pre-computed daily data
    if not hours and spot_name and spot_name.lower() in DEFAULT_SPOT_NAMES:
        db_row = await asyncio.to_thread(db_get_spot, spot_name)
        if db_row:
            if db_row.get("daily"):
                return {"daily": db_row["daily"][:days], "location": {"lat": lat, "lng": lng}}
            hours = db_row.get("hours_data")
            if hours:
                set_cache(cache_key + "_hours", hours)

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