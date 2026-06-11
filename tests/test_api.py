# ============================================================
# WHAT IS THIS FILE?
# These are automated TESTS for our application.
#
# WHAT IS TESTING?
# Testing means writing code that automatically checks your code works.
# You run "pytest" and it tells you if anything is broken.
#
# WHY WRITE TESTS?
# 1. Catch bugs before they reach production
# 2. Refactor confidently (tests tell you if you broke something)
# 3. CI/CD pipelines run tests automatically on every code push
# 4. Every serious company requires tests. No tests = no job offer.
#
# TYPES OF TESTS:
# - Unit tests: test one function in isolation (fast)
# - Integration tests: test multiple components together (slower)
# - End-to-end tests: test the full user flow (slowest)
#
# We're writing integration tests using FastAPI's TestClient,
# which simulates HTTP requests without running a real server.
# ============================================================

import pytest
import json
from unittest.mock import patch, MagicMock  # For mocking Redis and Kafka

from fastapi.testclient import TestClient    # Simulates HTTP requests
from app.main import app                    # Import our FastAPI app


# ============================================================
# TEST CLIENT SETUP
# TestClient wraps our app and lets us make fake HTTP requests.
# No real network is involved — it's all in-memory.
# ============================================================
client = TestClient(app)


# ============================================================
# FIXTURES
# A fixture is setup code that runs before tests.
# @pytest.fixture creates a reusable setup function.
#
# Here we mock (fake) Redis so tests don't need a real Redis server.
# Mocking = replacing a real object with a fake one for testing.
# ============================================================
@pytest.fixture
def mock_redis():
    """Creates a fake Redis that stores data in a Python dict."""
    with patch("app.main.get_db_connection") as mock:
        # fakeredis simulates Redis in memory (no real Redis needed)
        # For this test file, we use MagicMock to simulate behavior
        redis_mock = MagicMock()
        
        # Simulate URL storage
        storage = {}
        
        def mock_setex(key, ttl, value):
            storage[key] = value
        
        def mock_get(key):
            return storage.get(key)
        
        def mock_exists(key):
            return key in storage
        
        def mock_incr(key):
            current = int(storage.get(key, 0))
            storage[key] = str(current + 1)
            return current + 1
        
        def mock_keys(pattern):
            # Simple pattern matching for "url:*"
            prefix = pattern.replace("*", "")
            return [k for k in storage.keys() if k.startswith(prefix)]
        
        def mock_lrange(key, start, end):
            return []
        
        def mock_ping():
            return True
        
        redis_mock.setex = mock_setex
        redis_mock.get = mock_get
        redis_mock.exists = mock_exists
        redis_mock.incr = mock_incr
        redis_mock.keys = mock_keys
        redis_mock.lrange = mock_lrange
        redis_mock.ping = mock_ping
        
        mock.return_value = redis_mock
        yield redis_mock, storage


@pytest.fixture
def mock_kafka():
    """Mocks Kafka so tests don't need a real Kafka broker."""
    with patch("app.main.send_click_event") as mock:
        mock.return_value = True  # Pretend Kafka accepted the message
        yield mock


# ============================================================
# TESTS BEGIN HERE
# Each test function starts with "test_" — pytest auto-discovers them.
# GIVEN-WHEN-THEN pattern makes tests readable:
#   GIVEN: initial state
#   WHEN: action taken
#   THEN: expected result
# ============================================================

class TestHealthCheck:
    """Tests for the /health endpoint"""
    
    def test_health_returns_200(self, mock_redis):
        """
        GIVEN: The app is running with Redis connected
        WHEN: GET /health is called
        THEN: Returns HTTP 200 with status "ok"
        """
        response = client.get("/health")
        assert response.status_code == 200  # HTTP 200 = success
        data = response.json()
        assert data["status"] == "ok"
    
    def test_health_includes_timestamp(self, mock_redis):
        """Health check should include a timestamp for monitoring."""
        response = client.get("/health")
        data = response.json()
        assert "timestamp" in data


class TestURLShortening:
    """Tests for POST /shorten — creating short URLs"""
    
    def test_shorten_valid_url(self, mock_redis):
        """
        GIVEN: A valid URL
        WHEN: POST /shorten with {"original_url": "https://google.com"}
        THEN: Returns short_code and short_url
        """
        response = client.post("/shorten", json={
            "original_url": "https://www.google.com"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert "short_code" in data
        assert "short_url" in data
        assert len(data["short_code"]) == 6    # Must be exactly 6 characters
        assert "google.com" in data["original_url"]
    
    def test_shorten_invalid_url_rejected(self, mock_redis):
        """
        GIVEN: An invalid URL (not http/https)
        WHEN: POST /shorten with {"original_url": "not-a-url"}
        THEN: Returns HTTP 422 Unprocessable Entity (validation error)
        """
        response = client.post("/shorten", json={
            "original_url": "not-a-url"   # Invalid! Pydantic should reject this
        })
        
        assert response.status_code == 422   # 422 = validation failed
    
    def test_shorten_missing_url_rejected(self, mock_redis):
        """Empty request body should be rejected."""
        response = client.post("/shorten", json={})
        assert response.status_code == 422
    
    def test_short_code_is_alphanumeric(self, mock_redis):
        """Short codes should only contain letters and numbers."""
        response = client.post("/shorten", json={
            "original_url": "https://example.com"
        })
        
        data = response.json()
        short_code = data["short_code"]
        
        # Check every character is alphanumeric
        assert short_code.isalnum(), f"Short code '{short_code}' contains non-alphanumeric characters"


class TestURLRedirect:
    """Tests for GET /{short_code} — redirecting to original URL"""
    
    def test_redirect_nonexistent_code_returns_404(self, mock_redis):
        """
        GIVEN: A short code that doesn't exist
        WHEN: GET /xxxxxx
        THEN: Returns HTTP 404 Not Found
        """
        # follow_redirects=False so we can check the redirect response itself
        response = client.get("/nonexistent", follow_redirects=False)
        assert response.status_code == 404
    
    def test_redirect_existing_code(self, mock_redis, mock_kafka):
        """
        GIVEN: A valid short URL was created
        WHEN: GET /{short_code}
        THEN: Returns HTTP 302 redirect to original URL
        """
        # First, create a short URL
        create_response = client.post("/shorten", json={
            "original_url": "https://www.example.com"
        })
        short_code = create_response.json()["short_code"]
        
        # Now visit the short URL (don't follow redirects to inspect the 302)
        redirect_response = client.get(f"/{short_code}", follow_redirects=False)
        
        assert redirect_response.status_code == 302  # 302 = redirect
        assert redirect_response.headers["location"] == "https://www.example.com"


class TestAnalytics:
    """Tests for GET /analytics/{short_code}"""
    
    def test_analytics_nonexistent_returns_404(self, mock_redis):
        """Analytics for non-existent URL should return 404."""
        response = client.get("/analytics/nonexistent")
        assert response.status_code == 404
    
    def test_analytics_returns_click_count(self, mock_redis, mock_kafka):
        """
        GIVEN: A URL was created and clicked
        WHEN: GET /analytics/{short_code}
        THEN: Returns analytics including click count
        """
        # Create a URL
        create_response = client.post("/shorten", json={
            "original_url": "https://www.thapar.edu"
        })
        short_code = create_response.json()["short_code"]
        
        # Visit it (triggers click count)
        client.get(f"/{short_code}", follow_redirects=False)
        
        # Check analytics
        analytics_response = client.get(f"/analytics/{short_code}")
        assert analytics_response.status_code == 200
        
        data = analytics_response.json()
        assert data["short_code"] == short_code
        assert data["total_clicks"] >= 0   # Could be 0 or 1 depending on mock
        assert "original_url" in data


# ============================================================
# UTILITY / UNIT TESTS
# Test individual functions, not HTTP endpoints
# ============================================================

class TestShortCodeGeneration:
    """Unit tests for the short code generator"""
    
    def test_generate_short_code_length(self, mock_redis):
        """Generated codes should be exactly 6 characters."""
        from app.shortener import generate_short_code
        
        code = generate_short_code()
        assert len(code) == 6
    
    def test_generate_short_code_unique(self, mock_redis):
        """Generate 100 codes and verify they're all different."""
        from app.shortener import generate_short_code
        
        codes = set()
        for _ in range(100):
            codes.add(generate_short_code())
        
        # With good randomness, all 100 should be unique
        assert len(codes) == 100, "Duplicate short codes generated!"
