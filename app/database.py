# ============================================================
# WHAT IS THIS FILE?
# This file handles our connection to Redis.
#
# WHAT IS REDIS?
# Redis is an in-memory database — it stores data in RAM, not on disk.
# This makes it EXTREMELY fast (microseconds vs milliseconds for SQL).
# We use it to:
#   1. Store short_code → original_URL mappings
#   2. Count clicks (using atomic INCR)
#   3. Cache recent click events
#
# Redis stores data as KEY-VALUE pairs, like a giant Python dictionary.
# Example: "url:aB3xY" → '{"original_url": "https://google.com", ...}'
# ============================================================

import redis      # The Python library to talk to Redis
import os         # To read environment variables

# ============================================================
# ENVIRONMENT VARIABLES
# Instead of hardcoding "localhost" and "6379" directly in code,
# we read them from environment variables.
# WHY? So the same code works in:
#   - Local development: REDIS_HOST=localhost
#   - Docker:            REDIS_HOST=redis (Docker service name)
#   - Production:        REDIS_HOST=my-redis.aws.com
# This is called "12-Factor App" methodology — interviewers love this!
# ============================================================
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")   # Default to localhost if not set
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))    # Redis default port is 6379
REDIS_DB = int(os.getenv("REDIS_DB", "0"))           # Redis has 16 databases (0-15), we use 0
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)   # Optional password for production


def get_db_connection():
    """
    Returns a Redis client connection.
    
    decode_responses=True means Redis returns Python strings instead of bytes.
    Without it, you'd get b"hello" instead of "hello".
    
    connection_pool would be better for production (reuses connections),
    but this is clean enough for a project demo.
    """
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True,      # Auto-decode bytes → strings
        socket_connect_timeout=5,   # Fail fast if Redis is unreachable (5 seconds)
        socket_timeout=5
    )


def check_redis_health():
    """
    Utility function to test if Redis is reachable.
    Returns True if connected, False if not.
    Used in health checks and startup validation.
    """
    try:
        r = get_db_connection()
        r.ping()      # Redis PING command returns "PONG" if alive
        return True
    except redis.ConnectionError:
        return False
    except Exception:
        return False
