# AI Marketing Intelligence Platform

SaaS-platform for competitive intelligence and content automation for marketers.

## Architecture

- **Backend**: Python, FastAPI, SQLAlchemy 2, Pydantic v2
- **Telegram Bot**: Aiogram 3
- **Frontend**: Next.js 15, TypeScript, Tailwind CSS
- **Database**: PostgreSQL 16 + Redis 7 + Qdrant (vector)
- **Background Tasks**: Celery + Redis
- **Payments**: Stripe
- **AI**: Claude API (Anthropic)
- **Media**: ElevenLabs (TTS), HeyGen (video)
- **Storage**: S3 (MinIO for local dev)
- **CI/CD**: GitHub Actions, Docker

## Project Structure

```
.
├── backend/              # FastAPI backend
│   ├── app/
│   │   ├── api/routers/  # REST API endpoints
│   │   ├── core/         # Config, DB, security, dependencies
│   │   ├── models/       # SQLAlchemy models
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/     # Business logic
│   │   ├── workers/      # Celery tasks
│   │   └── utils/
│   ├── alembic/          # Database migrations
│   └── tests/
├── bot/                  # Telegram bot (Aiogram 3)
│   ├── handlers/         # Command handlers
│   ├── middlewares/       # Auth, rate limit, subscription checks
│   ├── keyboards/        # Inline keyboards
│   ├── states/           # FSM states
│   ├── services/
│   └── tests/
├── frontend/             # Next.js 15 dashboard
│   └── src/
│       ├── app/          # App Router pages
│       ├── components/
│       └── lib/          # API client, utilities
├── infra/
│   └── docker/           # Dockerfiles
├── scripts/              # Dev scripts
└── docker-compose.yml    # Local dev environment
```

## Quick Start

1. Copy environment config:
   ```bash
   cp .env.example .env
   # Fill in real values
   ```

2. Start infrastructure:
   ```bash
   ./scripts/start-dev.sh
   ```

3. Start full stack:
   ```bash
   docker compose up
   ```

   Or run services individually:
   ```bash
   # Backend
   cd backend && uvicorn app.main:app --reload

   # Bot
   python -m bot.main

   # Frontend
   cd frontend && npm install && npm run dev
   ```

4. Run migrations:
   ```bash
   cd backend && alembic upgrade head
   ```

## API

- Docs: http://localhost:8000/api/v1/docs
- Health: http://localhost:8000/health

## Subscription Plans

| Plan       | Price  | Competitors | Agents | Content Tasks |
|------------|--------|-------------|--------|---------------|
| Monitor    | $149   | 3           | 1      | 0             |
| Creator    | $499   | 7           | 3      | 20/mo         |
| Autopilot  | $999   | 15          | 5      | 50/mo         |
| Enterprise | $2500+ | Unlimited   | Custom | Unlimited     |
