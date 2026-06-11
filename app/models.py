# ============================================================
# WHAT IS THIS FILE?
# This file defines the "shapes" of our data using Pydantic.
#
# WHAT IS PYDANTIC?
# Pydantic is a data validation library for Python.
# You define what your data should look like (a "model"),
# and Pydantic automatically:
#   1. Validates incoming data (rejects bad input)
#   2. Converts types (string "42" → int 42)
#   3. Generates JSON schemas (used for API docs)
#
# FastAPI uses Pydantic models for request bodies and responses.
# This means if someone sends { "original_url": 12345 } (a number),
# FastAPI rejects it and returns a clear error message automatically!
# ============================================================

from pydantic import BaseModel, HttpUrl, Field  # Pydantic imports
from typing import List, Optional               # Python type hints
import time


# ============================================================
# REQUEST MODEL
# This defines what the client must send in the POST /shorten body.
#
# HttpUrl is a special Pydantic type that:
#   - Validates the URL format (must start with http:// or https://)
#   - Rejects "not-a-url" or "ftp://something"
# ============================================================
class URLCreateRequest(BaseModel):
    original_url: HttpUrl = Field(
        ...,  # "..." means this field is REQUIRED (not optional)
        description="The long URL you want to shorten",
        example="https://www.google.com/search?q=thapar+university"
    )
    
    # Optional: custom alias like "my-project" instead of random "aB3xY"
    # Not implemented in main.py for simplicity, but shows depth!
    custom_alias: Optional[str] = Field(
        None,  # None = optional, defaults to None
        description="Optional custom short code (e.g. 'my-project')",
        min_length=3,
        max_length=20
    )


# ============================================================
# RESPONSE MODEL
# This defines what our API sends back after shortening a URL.
# FastAPI uses this to:
#   1. Filter out any extra fields (security — don't accidentally leak internal data)
#   2. Document the response shape in /docs
# ============================================================
class URLResponse(BaseModel):
    short_code: str = Field(..., description="The 6-character short code", example="aB3xY2")
    short_url: str = Field(..., description="The full shortened URL", example="http://localhost:8000/aB3xY2")
    original_url: str = Field(..., description="The original long URL")
    
    # Pydantic v2 configuration
    model_config = {"from_attributes": True}


# ============================================================
# ANALYTICS RESPONSE MODEL
# Shape of data returned by GET /analytics/{short_code}
# Optional[X] means the field can be X or None (missing)
# List[dict] means a list of dictionaries
# ============================================================
class AnalyticsResponse(BaseModel):
    short_code: str
    original_url: str
    total_clicks: int = Field(..., description="Total number of times this URL was clicked")
    created_at: float = Field(..., description="Unix timestamp when URL was created")
    recent_clicks: List[dict] = Field(
        default=[],
        description="List of the 10 most recent click events with IP, browser, timestamp"
    )


# ============================================================
# CLICK EVENT MODEL
# Shape of the event we send to Kafka when someone clicks a link.
# This is what our Kafka producer sends and consumer receives.
# ============================================================
class ClickEvent(BaseModel):
    short_code: str
    timestamp: float
    ip_address: str
    user_agent: str = "unknown"
    referer: str = "direct"   # Where the click came from (Google, direct, etc.)
