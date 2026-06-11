# ============================================================
# WHAT IS THIS FILE?
# This file contains the logic for generating short codes.
# A short code is a random string like "aB3xY2" that maps to a long URL.
#
# We separate this logic into its own file following the
# "Single Responsibility Principle" — each file does ONE thing.
# This makes code easier to test, maintain, and explain in interviews!
# ============================================================

import secrets   # Python's cryptographically secure random number generator
import string    # Has constants like string.ascii_letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

from app.database import get_db_connection

# ============================================================
# CHARACTER SET
# Our short codes use letters (a-z, A-Z) and digits (0-9).
# Total: 62 characters
# With 6 characters: 62^6 = 56 BILLION possible codes
# We'll never run out!
# ============================================================
ALPHABET = string.ascii_letters + string.digits   # "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CODE_LENGTH = 6   # Length of each short code


def generate_short_code() -> str:
    """
    Generates a unique random short code.
    
    WHY secrets.choice instead of random.choice?
    - random module is NOT cryptographically secure
    - An attacker could predict the next code and enumerate all URLs
    - secrets module uses OS-level randomness (/dev/urandom on Linux)
    - This is a security best practice
    
    We also check Redis to ensure no collision (two URLs getting same code).
    The probability is astronomically low, but we handle it anyway.
    That's called "defensive programming" — interviewers love this!
    """
    redis = get_db_connection()
    
    MAX_ATTEMPTS = 10  # Safety limit to avoid infinite loops
    
    for attempt in range(MAX_ATTEMPTS):
        # Generate a random code: pick CODE_LENGTH random chars from ALPHABET
        code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
        
        # Check if this code already exists in Redis
        # EXISTS returns 1 if key exists, 0 if not
        if not redis.exists(f"url:{code}"):
            return code   # Found a unique code!
        
        # If collision (extremely rare), try again
        # Log this in production for monitoring
    
    # This should never happen with 56 billion possibilities,
    # but we raise an exception rather than returning a duplicate
    raise RuntimeError(f"Could not generate unique short code after {MAX_ATTEMPTS} attempts")


def decode_base62(code: str) -> int:
    """
    BONUS: Convert a base-62 code back to a number.
    This is the algorithm used by real URL shorteners like bit.ly.
    
    Real bit.ly uses a database auto-increment ID, then converts
    that integer to base-62. We use random codes, but explaining
    this algorithm in interviews shows deep understanding!
    
    Example: "aB" → 0*62 + 1 = ... (academic illustration)
    """
    value = 0
    for char in code:
        value = value * 62 + ALPHABET.index(char)
    return value
