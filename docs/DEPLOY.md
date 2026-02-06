# AI Marketing Intelligence Platform — Deploy Guide

## Prerequisites

- Docker & Docker Compose v2+
- PostgreSQL 16 (via Docker or standalone)
- Redis 7 (via Docker or standalone)
- Node.js 20+ (for frontend development)
- Python 3.11+ (for backend development)

## Quick Start (Docker)

```bash
# 1. Clone the repo
git clone <repo-url> && cd AI-Marketing-Intelligence-Platform

# 2. Copy and configure environment
cp .env.example .env
# Edit .env with your real values (see Configuration below)

# 3. Start all services
docker compose up -d

# 4. Run database migrations
docker compose exec backend alembic upgrade head

# 5. Seed training scenarios
docker compose exec backend python -m scripts.seed_data

# 6. Open the app
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000/api/v1/docs
# MinIO Console: http://localhost:9001
```

## Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing key (64+ chars) | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `DATABASE_URL` | PostgreSQL connection | `postgresql+asyncpg://user:pass@localhost:5432/marketing_platform` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` |
| `ATLAS_CLOUD_API_KEY` | Atlas Cloud AI API key | Get from [atlascloud.ai](https://atlascloud.ai) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | Get from [@BotFather](https://t.me/BotFather) |

### Atlas Cloud Setup

Atlas Cloud replaces individual AI provider keys (Anthropic, OpenAI, ElevenLabs, D-ID) with a single unified API:

1. Register at [atlascloud.ai](https://atlascloud.ai)
2. Create an API key in the dashboard
3. Set `ATLAS_CLOUD_API_KEY` in your `.env`
4. Default base URL: `https://api.atlascloud.ai/api/v1`

**Models used:**
- LLM: `anthropic/claude-sonnet-4-20250514` (training simulation + evaluation)
- Audio: `openai/whisper-1` (transcription), `openai/tts-1` (text-to-speech)
- Image: `black-forest-labs/flux-2-dev/text-to-image`
- Video: `bytedance/seedance-v1.5-pro/text-to-video`

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ATLAS_CLOUD_BASE_URL` | Atlas Cloud API URL | `https://api.atlascloud.ai/api/v1` |
| `POSTGRES_USER` | DB user for Docker | `platform` |
| `POSTGRES_PASSWORD` | DB password for Docker | `platform` |
| `S3_ACCESS_KEY` | MinIO access key | `minioadmin` |
| `S3_SECRET_KEY` | MinIO secret key | `minioadmin` |
| `STRIPE_SECRET_KEY` | Stripe billing key | — |

## Development Setup

### Backend

```bash
cd backend

# Install deps
pip install -e ".[dev]"

# Run migrations
alembic upgrade head

# Seed data
python -m scripts.seed_data

# Start server
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend

# Install deps
npm ci

# Start dev server
npm run dev
```

### Telegram Bot

```bash
# Set TELEGRAM_BOT_TOKEN in .env
python -m bot.main
```

### Running Tests

```bash
# All tests
PYTHONPATH=backend:. pytest backend/tests/ bot/tests/ -v

# With coverage
PYTHONPATH=backend:. pytest backend/tests/ bot/tests/ --cov=backend/app --cov=bot --cov-report=term-missing
```

## Production Deployment

```bash
# Use production compose file (no source volumes, Redis auth required)
docker compose -f docker-compose.prod.yml up -d

# Run migrations
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head

# Seed initial data
docker compose -f docker-compose.prod.yml exec backend python -m scripts.seed_data
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Frontend    │────▶│  Backend     │────▶│  PostgreSQL  │
│  Next.js 15  │     │  FastAPI     │     │  16-alpine   │
│  :3000       │     │  :8000       │     │  :5432       │
└─────────────┘     └──────┬───────┘     └──────────────┘
                           │
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Redis 7     │   │  Atlas Cloud │   │  Telegram Bot│
│  :6379       │   │  AI Gateway  │   │  Aiogram 3   │
└──────────────┘   └──────────────┘   └──────────────┘
       │
       ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Celery      │   │  Qdrant      │   │  MinIO S3    │
│  Worker/Beat │   │  Vector DB   │   │  :9000       │
└──────────────┘   └──────────────┘   └──────────────┘
```

## Training Module (АЛХИМИЯ)

The sales training simulator includes:

- **5 seed scenarios** — yoga studio client interactions (incoming calls, returns, objections, closing, partnerships)
- **AI simulation** — Claude via Atlas Cloud simulates realistic client behavior
- **7 evaluation criteria** — greeting, listening, objection handling, product knowledge, closing, tone/empathy, script adherence
- **WebSocket chat** — real-time training via `/ws/training/{session_id}?token=JWT`
- **Gamification** — achievements, streaks, XP, daily challenges
- **Multiplayer** — competitive training sessions with leaderboard

## Monitoring

- **Atlas Cloud status**: `GET /api/v1/monitoring/atlas-cloud/status` — circuit breaker state
- **Platform stats**: `GET /api/v1/monitoring/training/stats` — session counts, scores, usage
- **Health checks**: `GET /health` (basic), `GET /health/detailed` (DB, Redis, Qdrant, S3)
