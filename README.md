# 🔗 URL Shortener & Analytics Platform

> A production-grade URL shortening service with real-time click analytics, built with FastAPI, Redis, Apache Kafka, Docker, and CI/CD.

[![CI/CD](https://github.com/YOUR_USERNAME/url-shortener/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/YOUR_USERNAME/url-shortener/actions)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green.svg)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/Redis-7.0-red.svg)](https://redis.io/)
[![Kafka](https://img.shields.io/badge/Kafka-7.4-black.svg)](https://kafka.apache.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://www.docker.com/)

---

## 📐 System Architecture

```
┌─────────────┐    POST /shorten     ┌───────────────────────┐
│   Client    │──────────────────────▶│   FastAPI Server      │
│  (Browser/  │◀──────────────────── │   (Python 3.11)       │
│   Postman)  │  { short_url }        │   Port: 8000          │
└─────────────┘                       └──────────┬────────────┘
                                                  │
                          ┌───────────────────────┼───────────────────────┐
                          │                       │                       │
                          ▼                       ▼                       ▼
                  ┌──────────────┐     ┌────────────────┐     ┌──────────────────┐
                  │    Redis     │     │  Kafka Topic   │     │  Kafka Consumer  │
                  │  (Storage)   │     │  "url-clicks"  │     │  (Worker)        │
                  │  Port: 6379  │     │  Port: 9092    │     │  Reads events,   │
                  │              │     │                │     │  stores in Redis │
                  │ • URL store  │     │ • Click events │     └──────────────────┘
                  │ • Click count│     │ • Async queue  │
                  │ • Event log  │     └────────────────┘
                  └──────────────┘
```

**Request Flow for a Click:**
1. User visits `http://localhost:8000/aB3xY2`
2. FastAPI looks up `aB3xY2` in Redis → finds original URL
3. FastAPI fires a click event to Kafka (async, non-blocking)
4. FastAPI returns HTTP 302 redirect → user goes to original URL
5. Kafka Consumer (separate process) reads the event → stores analytics in Redis
6. `GET /analytics/aB3xY2` reads stored analytics from Redis

---

## 🛠 Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| **Web Framework** | FastAPI (Python) | Fast, auto-generates docs, Pydantic validation |
| **Primary Database** | Redis | In-memory, microsecond reads, atomic counters |
| **Message Broker** | Apache Kafka | Async event processing, fault-tolerant, scalable |
| **Containerization** | Docker + Docker Compose | Reproducible environments, easy deployment |
| **CI/CD** | GitHub Actions | Auto-test + auto-deploy on every code push |
| **Testing** | Pytest | Automated tests, code coverage reporting |

---

## 🚀 Quick Start

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed
- That's it! Docker handles everything else.

### Run in 1 Command

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/url-shortener.git
cd url-shortener

# Start ALL services (FastAPI + Redis + Kafka + Worker)
docker-compose up --build
```

Wait ~30 seconds for Kafka to initialize, then:

- **API**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs  ← Try it here!
- **Health Check**: http://localhost:8000/health

### Test the API

```bash
# 1. Create a short URL
curl -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://www.thapar.edu/academics/engineering"}'

# Response:
# { "short_code": "aB3xY2", "short_url": "http://localhost:8000/aB3xY2", ... }

# 2. Visit the short URL (redirects to Thapar website)
curl -L http://localhost:8000/aB3xY2

# 3. Check analytics
curl http://localhost:8000/analytics/aB3xY2

# 4. List all URLs
curl http://localhost:8000/urls/all
```

---

## 🗂 Project Structure

```
url-shortener/
├── app/
│   ├── __init__.py          # Makes 'app' a Python package
│   ├── main.py              # FastAPI app + all API endpoints
│   ├── database.py          # Redis connection management
│   ├── models.py            # Pydantic request/response models
│   ├── shortener.py         # Short code generation logic
│   ├── kafka_producer.py    # Sends click events to Kafka
│   └── kafka_consumer.py    # Reads events from Kafka, stores analytics
├── tests/
│   ├── __init__.py
│   └── test_api.py          # Pytest test suite (unit + integration)
├── .github/
│   └── workflows/
│       └── ci-cd.yml        # GitHub Actions CI/CD pipeline
├── Dockerfile               # Container recipe for the API
├── docker-compose.yml       # Multi-service orchestration
├── requirements.txt         # Python dependencies
└── README.md
```

---

## 🔌 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check (Redis connectivity) |
| `POST` | `/shorten` | Create a short URL |
| `GET` | `/{short_code}` | Redirect to original URL |
| `GET` | `/analytics/{short_code}` | Get click analytics |
| `GET` | `/urls/all` | List all short URLs |

Full interactive documentation at: **http://localhost:8000/docs**

---

## 🧪 Running Tests

```bash
# Option 1: With Docker (recommended, no local Python needed)
docker-compose run --rm api pytest tests/ -v --cov=app

# Option 2: Locally
pip install -r requirements.txt
pytest tests/ -v --cov=app --cov-report=term-missing
```

---

## ⚙️ Local Development (without Docker)

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Start Redis and Kafka (still need Docker for these)
docker-compose up redis kafka zookeeper -d

# 3. Start FastAPI with hot-reload
uvicorn app.main:app --reload --port 8000

# 4. In a second terminal, start the Kafka consumer
python -m app.kafka_consumer
```

---

## 🧠 Key Design Decisions

**Why Redis over PostgreSQL for URL storage?**
URL redirects must be extremely fast (under 5ms). Redis stores data in RAM, giving microsecond lookups. A PostgreSQL query involves disk I/O and takes 1-10ms. For a redirect service handling millions of requests per day, this difference matters enormously.

**Why Kafka over writing directly to Redis?**
Decoupling. The API endpoint only needs to redirect the user — analytics is a secondary concern. By sending to Kafka, the redirect is never delayed by analytics processing. If the analytics service crashes, Kafka queues events until it recovers. This is "fault isolation" — failures in one service don't cascade.

**Why cryptographically secure random codes?**
Using Python's `random` module is predictable — an attacker could enumerate all short codes and see private URLs. `secrets` module uses `/dev/urandom` (OS-level entropy) and is unpredictable even if you know the algorithm.

---

## 📊 Performance Characteristics

- Redis GET: ~0.1ms (in-memory)
- Redirect latency: < 5ms end-to-end
- Kafka publish: async, non-blocking
- Short code space: 62^6 = 56 billion unique codes
- URL TTL: 30 days (configurable)

---

## 🔮 Future Improvements

- [ ] Custom URL aliases (`/my-project` instead of `/aB3xY2`)
- [ ] Password-protected URLs
- [ ] QR code generation
- [ ] Geographic analytics (country/city breakdown)
- [ ] Rate limiting (prevent abuse with slowapi)
- [ ] PostgreSQL for permanent URL storage (Redis as cache layer)
- [ ] Kubernetes deployment manifests (Helm charts)
- [ ] Prometheus metrics + Grafana dashboard
