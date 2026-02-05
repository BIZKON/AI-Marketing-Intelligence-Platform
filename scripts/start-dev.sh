#!/usr/bin/env bash
set -euo pipefail

echo "=== AI Marketing Intelligence Platform — Dev Environment ==="

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed."
    exit 1
fi

# Copy env file if not exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

# Start infrastructure services
echo "Starting infrastructure services..."
docker compose up -d postgres redis qdrant minio

echo "Waiting for services to be healthy..."
sleep 5

echo ""
echo "Infrastructure is running:"
echo "  PostgreSQL: localhost:5432"
echo "  Redis:      localhost:6379"
echo "  Qdrant:     localhost:6333"
echo "  MinIO:      localhost:9000 (console: localhost:9001)"
echo ""
echo "To start the full stack: docker compose up"
echo "To run backend only:     cd backend && uvicorn app.main:app --reload"
echo "To run bot only:         python -m bot.main"
echo "To run frontend only:    cd frontend && npm run dev"
