"""Mental-health guidance API with live web search, Groq LLM, and nearby-psychologist finder."""

from __future__ import annotations

import math
import os
import re
import warnings
from pathlib import Path
from typing import Any

# Suppress renamed-package notice from the duckduckgo_search shim
warnings.filterwarnings("ignore", category=RuntimeWarning, module="duckduckgo_search")

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "qwen/qwen3.8-27b"

ASSETS = {
    "Student Mental Health Predictor.css",
    "Student Mental Health Predictor.js",
    "rag_chat.js",
}

# ---------------------------------------------------------------------------
# Crisis detection
# ---------------------------------------------------------------------------
CRISIS_TERMS = (
    "suicid", "kill myself", "end my life", "want to die", "wish i were dead",
    "wish i was dead", "self harm", "self-harm", "self-injury", "hurt myself",
    "harm myself", "cut myself", "not safe with myself", "can't go on",
    "cannot go on", "no reason to live",
)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class NearbyRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_m: int = Field(default=15000, ge=1000, le=30000)


# ---------------------------------------------------------------------------
# Web search via DuckDuckGo (no API key required)
# ---------------------------------------------------------------------------

def _web_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Return a list of {title, url, snippet} dicts from DuckDuckGo (no key needed)."""
    try:
        from duckduckgo_search import DDGS  # type: ignore[import-untyped]
        results: list[dict[str, str]] = []
        with DDGS() as ddgs:
            for item in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("href", ""),
                    "snippet": item.get("body", ""),
                })
        return results
    except Exception:
        return []


def _format_search_context(results: list[dict[str, str]]) -> str:
    if not results:
        return ""
    lines = ["Web search results:\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r['title']}\nURL: {r['url']}\n{r['snippet']}\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Groq LLM call
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a compassionate, knowledgeable mental-health support assistant embedded in a Student Mental Health Predictor tool.

Your goals:
1. Provide empathetic, accurate, evidence-based guidance on mental health topics including stress, anxiety, depression, sleep, study pressure, social media balance, and finding professional help.
2. When web search results are provided, use them to give up-to-date, specific answers with cited sources.
3. Always recommend professional help for serious or persistent concerns.
4. Keep responses concise (3–5 sentences for simple questions, up to a short paragraph for complex ones).
5. Never diagnose. Never replace professional care.
6. If the user is in crisis, always provide emergency resources first.

Format: Plain conversational text. At the end, if you used web sources, list them as "Sources:" with numbered bullet points (title and URL).

Tone: Warm, non-judgmental, clear. Avoid jargon."""


def _call_groq(user_message: str, search_context: str) -> str:
    """Call Groq LLM and return the assistant reply text."""
    groq_api_key = os.getenv("GROQ_API_KEY", "")
    if not groq_api_key:
        raise RuntimeError("GROQ_API_KEY not set. Add it to your .env file.")

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]
    if search_context:
        messages.append({
            "role": "system",
            "content": f"Use the following live web search results to enrich your answer:\n\n{search_context}",
        })
    messages.append({"role": "user", "content": user_message})

    resp = requests.post(
        GROQ_API_URL,
        headers={
            "Authorization": f"Bearer {groq_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": 0.4,
            "max_tokens": 600,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Source extraction from LLM response
# ---------------------------------------------------------------------------

_SOURCE_HEADER = re.compile(r"sources?\s*:", re.IGNORECASE)
_SOURCE_LINE = re.compile(r"^\s*[\d\-\*\•]+[\.\)]\s*(.+?)\s*\(?(https?://[^\s\)]+)\)?", re.IGNORECASE)


def _extract_sources(text: str) -> tuple[str, list[dict[str, str]]]:
    """Split LLM reply into (answer_text, sources_list)."""
    match = _SOURCE_HEADER.search(text)
    if not match:
        return text, []

    body = text[: match.start()].strip()
    sources_block = text[match.end():].strip()
    sources: list[dict[str, str]] = []
    for line in sources_block.splitlines():
        m = _SOURCE_LINE.match(line)
        if m:
            title, url = m.group(1).strip(), m.group(2).strip()
            sources.append({"title": title or url, "url": url})
        elif line.strip().startswith("http"):
            sources.append({"title": line.strip(), "url": line.strip()})
    return body, sources


# ---------------------------------------------------------------------------
# Main answer function
# ---------------------------------------------------------------------------

def answer_question(message: str) -> dict[str, Any]:
    normalized = message.lower()

    # Crisis check — always first
    if any(term in normalized for term in CRISIS_TERMS):
        return {
            "answer": (
                "I'm sorry you're facing this. If you may act on these thoughts "
                "or are in immediate danger, call your local emergency number or go "
                "to the nearest emergency department now. In the U.S. or Canada, "
                "call or text 988. Globally, find a local line at findahelpline.com. "
                "Please stay with someone you trust. This chat is not an emergency service."
            ),
            "sources": [
                {"title": "988 Suicide & Crisis Lifeline", "url": "https://988lifeline.org/"},
                {"title": "Find a helpline by country", "url": "https://findahelpline.com/"},
            ],
            "urgent": True,
        }

    # Compose a targeted search query
    search_query = f"mental health tips {message} site:nimh.nih.gov OR site:nhs.uk OR site:apa.org OR site:mind.org.uk"
    search_results = _web_search(search_query, max_results=5)
    search_context = _format_search_context(search_results)

    # Call the LLM
    try:
        raw_reply = _call_groq(message, search_context)
    except (RuntimeError, requests.exceptions.HTTPError) as exc:
        # Key missing or auth error — fall back to a polite notice
        msg = str(exc)
        if not os.getenv("GROQ_API_KEY") or "401" in msg or "403" in msg or "404" in msg:
            return {
                "answer": (
                    "The AI assistant is not configured yet. "
                    "Please add your GROQ_API_KEY to the .env file and restart the server. "
                    "See .env.example for instructions."
                ),
                "sources": [],
                "urgent": False,
            }
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc

    answer_text, llm_sources = _extract_sources(raw_reply)

    # Merge LLM-cited sources with raw search hits (deduplicate by URL)
    seen_urls: set[str] = {s["url"] for s in llm_sources}
    extra_sources: list[dict[str, str]] = []
    for r in search_results[:3]:
        if r["url"] and r["url"] not in seen_urls:
            extra_sources.append({"title": r["title"] or r["url"], "url": r["url"]})
            seen_urls.add(r["url"])

    return {
        "answer": answer_text,
        "sources": llm_sources + extra_sources,
        "urgent": False,
    }


# ---------------------------------------------------------------------------
# Haversine distance
# ---------------------------------------------------------------------------

def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * earth_radius_km * math.asin(math.sqrt(min(1.0, haversine)))


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Student Mental Health – AI Chat & Nearby Care")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.onrender\.com",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/")
def home() -> FileResponse:
    return FileResponse(BASE_DIR / "Student Mental Health Predictor.html")


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Enter a question to continue.")
    return answer_question(message)


@app.post("/api/doctors")
def nearby_doctors(request: NearbyRequest) -> dict[str, Any]:
    latitude, longitude = request.latitude, request.longitude
    radius_km = request.radius_m / 1000

    # Use Nominatim to search for mental health providers near the given coordinates.
    # We run several targeted searches and merge the results.
    search_terms = [
        "psychologist",
        "psychiatrist",
        "mental health clinic",
        "counsellor",
        "therapist",
    ]

    headers = {
        "User-Agent": "StudentMentalHealthPredictor/2.0 (educational; contact: student@mindscores.dev)",
        "Accept-Language": "en",
    }

    seen: set[str] = set()
    providers: list[dict[str, Any]] = []

    for term in search_terms:
        try:
            params = {
                "q": term,
                "format": "jsonv2",
                "limit": 20,
                "lat": latitude,
                "lon": longitude,
                "addressdetails": 1,
                "extratags": 1,
                "countrycodes": "",   # allow all countries
            }
            resp = requests.get(
                NOMINATIM_URL,
                params=params,
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json()
        except (requests.RequestException, ValueError):
            continue

        for item in results:
            place_id = str(item.get("place_id", ""))
            if place_id in seen:
                continue
            seen.add(place_id)

            provider_lat = float(item.get("lat", 0))
            provider_lon = float(item.get("lon", 0))
            dist = _distance_km(latitude, longitude, provider_lat, provider_lon)

            # Only keep results within the requested radius
            if dist > radius_km:
                continue

            name = item.get("name") or item.get("display_name", "").split(",")[0]
            if not name:
                continue

            address_parts = item.get("address", {})
            address = ", ".join(filter(None, [
                address_parts.get("road") or address_parts.get("street"),
                address_parts.get("suburb") or address_parts.get("neighbourhood"),
                address_parts.get("city") or address_parts.get("town") or address_parts.get("village"),
                address_parts.get("postcode"),
            ]))

            extra = item.get("extratags") or {}
            phone = extra.get("phone") or extra.get("contact:phone") or ""
            website = extra.get("website") or extra.get("contact:website") or ""
            provider_type = (
                extra.get("healthcare")
                or extra.get("amenity")
                or item.get("type", "health service")
            ).replace("_", " ").title()

            providers.append({
                "name": name,
                "type": provider_type,
                "address": address,
                "phone": phone,
                "website": website,
                "distance_km": round(dist, 1),
                "map_url": (
                    f"https://www.openstreetmap.org/?mlat={provider_lat}"
                    f"&mlon={provider_lon}#map=17/{provider_lat}/{provider_lon}"
                ),
            })

    if not providers:
        # Return empty list — frontend already handles this gracefully
        return {"providers": [], "radius_m": request.radius_m}

    providers.sort(key=lambda p: p["distance_km"])
    return {"providers": providers[:25], "radius_m": request.radius_m}


@app.get("/{asset_name}")
def static_asset(asset_name: str) -> FileResponse:
    if asset_name not in ASSETS:
        raise HTTPException(status_code=404, detail="Not found")
    asset_path = BASE_DIR / asset_name
    if not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(asset_path)
