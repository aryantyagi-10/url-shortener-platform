# ============================================================
# WHAT IS THIS FILE?
# This is the "brain" of our web server. It defines all the
# API endpoints (URLs) that users/frontend can call.
# FastAPI is a Python framework that makes building APIs fast.
# ============================================================

from fastapi import FastAPI, HTTPException, Request  # FastAPI = the web framework
from fastapi.middleware.cors import CORSMiddleware   # CORS = allows browser to talk to our API
from fastapi.responses import RedirectResponse       # Used to redirect short URL → original URL
import uvicorn                                       # The server that runs our FastAPI app

from app.database import get_db_connection          # Our Redis connection helper
from app.kafka_producer import send_click_event     # Sends click events to Kafka
from app.models import URLCreateRequest, URLResponse, AnalyticsResponse  # Data shapes
from app.shortener import generate_short_code       # Logic to make short codes like "aB3xY"
import json
import time

# ============================================================
# CREATE THE APP
# FastAPI() creates an application object. Everything hangs off this.
# title/description show up in auto-generated API docs at /docs
# ============================================================
app = FastAPI(
    title="URL Shortener & Analytics Platform",
    description="A production-grade URL shortener with real-time click analytics powered by Redis + Kafka",
    version="1.0.0"
)

# ============================================================
# CORS MIDDLEWARE
# Browsers block requests from one website to another by default (security).
# This middleware tells our server to ALLOW requests from any origin.
# In production, you'd restrict this to your actual frontend domain.
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # "*" = allow all origins (any website can call our API)
    allow_credentials=True,
    allow_methods=["*"],        # Allow GET, POST, DELETE, etc.
    allow_headers=["*"],        # Allow any headers
)


# ============================================================
# HEALTH CHECK ENDPOINT
# GET /health → returns {"status": "ok"}
# WHY: Docker, Kubernetes, and load balancers ping this to know if the app is alive.
# Every real production service has one. This impresses interviewers!
# ============================================================
@app.get("/health")
async def health_check():
    redis = get_db_connection()
    try:
        redis.ping()   # Ask Redis "are you alive?"
        redis_status = "connected"
    except Exception:
        redis_status = "disconnected"
    
    return {
        "status": "ok",
        "redis": redis_status,
        "timestamp": time.time()
    }


# ============================================================
# CREATE SHORT URL
# POST /shorten → accepts a long URL, returns a short code
# 
# Example:
#   Input:  { "original_url": "https://google.com/very/long/path" }
#   Output: { "short_code": "aB3xY", "short_url": "http://localhost:8000/aB3xY" }
# ============================================================
@app.post("/shorten", response_model=URLResponse)
async def create_short_url(request: URLCreateRequest, req: Request):
    redis = get_db_connection()
    
    # Step 1: Generate a random short code like "aB3xY"
    short_code = generate_short_code()
    
    # Step 2: Store in Redis as key-value pair
    # Key:   "url:aB3xY"
    # Value: JSON with original URL + metadata
    url_data = {
        "original_url": str(request.original_url),   # str() converts Pydantic HttpUrl to plain string
        "created_at": time.time(),               # Unix timestamp of creation
        "clicks": 0                              # Click counter starts at 0
    }
    
    # redis.setex = SET with EXpiry
    # We store the URL for 30 days (30 * 24 * 60 * 60 seconds)
    # After 30 days, Redis automatically deletes it. Smart!
    redis.setex(
        f"url:{short_code}",          # Key name
        30 * 24 * 60 * 60,            # TTL (time to live) in seconds = 30 days
        json.dumps(url_data)          # Value must be string, so we JSON-encode the dict
    )
    
    # Step 3: Build the full short URL to return to the user
    base_url = str(req.base_url)  # e.g. "http://localhost:8000/"
    short_url = f"{base_url}{short_code}"
    
    return URLResponse(
        short_code=short_code,
        short_url=short_url,
        original_url=str(request.original_url)
    )


# ============================================================
# REDIRECT SHORT URL TO ORIGINAL
# GET /{short_code} → redirects to the original URL
#
# Example: visiting http://localhost:8000/aB3xY
# → browser gets sent to https://google.com/very/long/path
# ============================================================
@app.get("/{short_code}")
async def redirect_to_original(short_code: str, request: Request):
    redis = get_db_connection()
    
    # Step 1: Look up the short code in Redis
    data = redis.get(f"url:{short_code}")
    
    # Step 2: If not found, return 404 error
    if not data:
        raise HTTPException(status_code=404, detail="Short URL not found or expired")
    
    # Step 3: Decode JSON back to Python dict
    url_data = json.loads(data)
    
    # Step 4: Increment click counter in Redis
    # INCR is atomic = thread-safe increment. Even if 1000 people click at once,
    # Redis handles it correctly without race conditions.
    redis.incr(f"clicks:{short_code}")
    
    # Step 5: Send a click event to Kafka for analytics processing
    # We do this ASYNC so the redirect is not slowed down by Kafka
    click_event = {
        "short_code": short_code,
        "timestamp": time.time(),
        "ip_address": request.client.host if request.client else "unknown",       # IP of the person clicking
        "user_agent": request.headers.get("user-agent", "unknown"),  # Their browser info
        "referer": request.headers.get("referer", "direct")          # Where they came from
    }
    send_click_event(click_event)  # Fire and forget to Kafka
    
    # Step 6: Redirect! HTTP 302 = temporary redirect
    return RedirectResponse(url=url_data["original_url"], status_code=302)


# ============================================================
# ANALYTICS ENDPOINT
# GET /analytics/{short_code} → returns click stats for a URL
#
# Example response:
#   { "short_code": "aB3xY", "total_clicks": 42, "original_url": "..." }
# ============================================================
@app.get("/analytics/{short_code}", response_model=AnalyticsResponse)
async def get_analytics(short_code: str):
    redis = get_db_connection()
    
    # Check if the URL exists
    data = redis.get(f"url:{short_code}")
    if not data:
        raise HTTPException(status_code=404, detail="Short URL not found")
    
    url_data = json.loads(data)
    
    # Get total clicks. redis.get returns bytes, so decode to string, then int.
    clicks_raw = redis.get(f"clicks:{short_code}")
    total_clicks = int(clicks_raw) if clicks_raw else 0
    
    # Get the last 10 recent click events stored by our Kafka consumer
    # LRANGE = get items from a Redis list (index 0 to 9 = first 10 items)
    recent_events_raw = redis.lrange(f"events:{short_code}", 0, 9)
    recent_events = [json.loads(e) for e in recent_events_raw]
    
    return AnalyticsResponse(
        short_code=short_code,
        original_url=url_data["original_url"],
        total_clicks=total_clicks,
        created_at=url_data["created_at"],
        recent_clicks=recent_events
    )


# ============================================================
# GET ALL URLs (list)
# GET /urls → returns all short URLs stored in Redis
# Useful for a dashboard to show all created links
# ============================================================
@app.get("/urls/all")
async def list_all_urls():
    redis = get_db_connection()
    
    # KEYS pattern = find all Redis keys matching "url:*"
    # WARNING: In production with millions of keys, use SCAN instead of KEYS
    # SCAN is non-blocking. KEYS blocks the entire Redis server temporarily.
    keys = redis.keys("url:*")
    
    urls = []
    for key in keys:
        key_str = key.decode() if isinstance(key, bytes) else key
        short_code = key_str.replace("url:", "")  # Extract "aB3xY" from "url:aB3xY"
        data = redis.get(key_str)
        if data:
            url_data = json.loads(data)
            clicks_raw = redis.get(f"clicks:{short_code}")
            urls.append({
                "short_code": short_code,
                "original_url": url_data["original_url"],
                "created_at": url_data["created_at"],
                "total_clicks": int(clicks_raw) if clicks_raw else 0
            })
    
    # Sort by creation time, newest first
    urls.sort(key=lambda x: x["created_at"], reverse=True)
    return {"urls": urls, "total": len(urls)}


# ============================================================
# ENTRY POINT
# When you run "python app/main.py" directly,
# this starts the uvicorn server on port 8000.
# In Docker, we usually call uvicorn directly instead.
# ============================================================
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
