# ============================================================
# WHAT IS THIS FILE?
# This is a Dockerfile — a recipe for building a Docker IMAGE.
#
# WHAT IS DOCKER?
# Docker packages your application + all its dependencies into a
# "container" — a lightweight, isolated box that runs IDENTICALLY
# on any machine (your laptop, a server in the cloud, anywhere).
#
# WITHOUT DOCKER: "It works on my machine!" 😤
# WITH DOCKER:    Guaranteed to work everywhere 🎉
#
# HOW TO READ A DOCKERFILE:
# Each line is an instruction. Docker executes them top to bottom,
# creating layers. Layers are cached — unchanged layers aren't rebuilt.
# This is why we COPY requirements.txt BEFORE copying all the code
# (so the pip install layer is cached and only reruns if requirements change).
# ============================================================


# ============================================================
# BASE IMAGE
# We start FROM an existing image (like inheriting a class).
# python:3.11-slim = Python 3.11 on a minimal Debian Linux.
# "slim" removes docs, tests, etc. to keep the image small (~50MB vs ~900MB).
# Small images = faster deployment, less attack surface.
# ============================================================
FROM python:3.11-slim

# ============================================================
# WORKING DIRECTORY
# Sets the "current directory" for all subsequent commands.
# Like cd /app — all COPY, RUN, CMD happen relative to this.
# ============================================================
WORKDIR /app

# ============================================================
# INSTALL SYSTEM DEPENDENCIES
# Some Python packages need C libraries compiled from source.
# We install build tools first, then REMOVE them after pip install
# to keep the image small (multi-stage optimization pattern).
# ============================================================
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*   
# rm -rf clears the apt cache — reduces image size by ~50MB

# ============================================================
# COPY REQUIREMENTS FIRST (for caching optimization)
# Docker builds images in layers. If requirements.txt hasn't changed,
# the next RUN layer (pip install) uses cache. Very fast rebuilds!
# If we copied ALL code first, any code change would invalidate the cache.
# ============================================================
COPY requirements.txt .

# ============================================================
# INSTALL PYTHON DEPENDENCIES
# --no-cache-dir = don't cache pip downloads (saves ~100MB in image)
# ============================================================
RUN pip install --no-cache-dir -r requirements.txt

# ============================================================
# COPY APPLICATION CODE
# The dot "." means "copy everything from current directory to /app"
# This runs AFTER pip install to take advantage of caching.
# ============================================================
COPY . .

# ============================================================
# EXPOSE PORT
# Tells Docker "this container listens on port 8000".
# This is DOCUMENTATION only — you still need -p 8000:8000 to publish it.
# But it's required for Docker Compose and Kubernetes to understand.
# ============================================================
EXPOSE 8000

# ============================================================
# HEALTH CHECK (Docker built-in)
# Docker periodically runs this command to check if the container is healthy.
# If /health returns non-200, Docker marks it "unhealthy" and can restart it.
# This is what makes services self-healing!
#
# --interval=30s  → check every 30 seconds
# --timeout=10s   → fail if no response in 10 seconds
# --retries=3     → mark unhealthy after 3 consecutive failures
# ============================================================
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# ============================================================
# NON-ROOT USER (Security Best Practice)
# By default, containers run as root (dangerous!).
# We create a non-root user "appuser" and switch to it.
# If an attacker exploits our app, they're limited to this user.
# ============================================================
RUN adduser --disabled-password --gecos "" appuser
USER appuser

# ============================================================
# STARTUP COMMAND
# CMD defines what runs when the container starts.
# uvicorn = the ASGI server that runs our FastAPI app
# --host 0.0.0.0 = listen on ALL network interfaces (not just localhost)
# --port 8000 = the port to listen on
# --workers 2 = run 2 parallel worker processes (handles more requests)
# ============================================================
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
