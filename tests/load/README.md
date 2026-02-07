# Load & Stress Testing

Two complementary tools for performance testing the AI Marketing Intelligence Platform API.

| Tool | Best for | Language |
|------|----------|----------|
| **Locust** | Realistic user simulation, web UI, gradual ramp | Python |
| **k6** | SLO verification, CI pipelines, precise thresholds | JavaScript |

---

## Quick Start

### Prerequisites

```bash
# Locust
pip install locust

# k6 — https://k6.io/docs/get-started/installation/
# macOS
brew install k6
# Ubuntu/Debian
sudo gpg -k && sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D68
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6
# Docker
docker pull grafana/k6
```

### Locust (Web UI)

```bash
# Start web UI at http://localhost:8089
locust -f tests/load/locustfile.py --host http://localhost:8000

# Headless (100 users, 10 spawn/sec, 2 min)
locust -f tests/load/locustfile.py --host http://localhost:8000 \
  --users 100 --spawn-rate 10 --run-time 2m --headless --csv results/locust
```

### k6 (CLI)

```bash
# Smoke test (5 users, 1 min)
k6 run tests/load/k6_training.js

# Load test (50 users, 5 min)
k6 run tests/load/k6_training.js --env USERS=50 --env DURATION=5m

# Stress test (ramp to 200 users)
k6 run tests/load/k6_training.js --env SCENARIO=stress

# Spike test (burst to 300 users)
k6 run tests/load/k6_training.js --env SCENARIO=spike

# Soak test (30 users, 30 min)
k6 run tests/load/k6_training.js --env SCENARIO=soak

# Custom API URL
k6 run tests/load/k6_training.js --env BASE_URL=https://api.example.com
```

### Docker

```bash
# Locust via Docker
docker run --rm -p 8089:8089 \
  -v $(pwd)/tests/load:/mnt/locust \
  locustio/locust -f /mnt/locust/locustfile.py \
  --host http://host.docker.internal:8000

# k6 via Docker
docker run --rm \
  -v $(pwd)/tests/load:/scripts \
  grafana/k6 run /scripts/k6_training.js \
  --env BASE_URL=http://host.docker.internal:8000
```

---

## SLOs (Service Level Objectives)

Defined in `k6_training.js` thresholds:

| Endpoint Group | p95 Latency | Error Rate |
|----------------|-------------|------------|
| Health checks (`/health`) | < 50 ms | < 5% |
| Auth (`/auth/*`) | < 500 ms | < 5% |
| Training CRUD (scenarios, sessions, analytics) | < 1 s | < 5% |
| AI Chat (send message, get AI response) | < 30 s | < 10% |
| AI Evaluation (complete session) | < 60 s | < 10% |

---

## Test Flows

### Locust — `TrainingUser` (weight: 1)

Full training lifecycle with weighted task distribution:

1. **Health** (5x) — `GET /health`
2. **Health detailed** (1x) — `GET /health/detailed`
3. **List scenarios** (3x) — `GET /training/scenarios`
4. **Create session** (2x) — `POST /training/sessions`
5. **List sessions** (3x) — `GET /training/sessions`
6. **Send message** (4x) — `POST /training/sessions/{id}/message` (AI)
7. **Complete session** (1x) — `POST /training/sessions/{id}/complete` (AI)
8. **Analytics** (2x) — `GET /training/analytics`
9. **Achievements** (1x) — `GET /training/achievements`
10. **Atlas status** (2x) — `GET /monitoring/atlas-cloud/status`
11. **Platform stats** (1x) — `GET /monitoring/training/stats`
12. **Gamification** (1x each) — profile, challenges

### Locust — `ReadOnlyUser` (weight: 3)

Simulates anonymous/browsing users:

1. **Health** (5x) — `GET /health`
2. **Scenarios** (3x) — `GET /training/scenarios`
3. **OpenAPI** (1x) — `GET /api/v1/openapi.json`

### k6 — Sequential Flow

Each virtual user runs through the complete flow:

1. Health checks → Auth (register/login) → List scenarios → Create session → Send 3 messages → Complete & evaluate → Analytics

---

## k6 Scenarios

| Name | Executor | Config |
|------|----------|--------|
| `default` | constant-vus | 5 VUs, 1 min |
| `stress` | ramping-vus | 0→20→100→200→200→0 over 9 min |
| `spike` | ramping-vus | 0→10→300→300→10→0 over ~3 min |
| `soak` | ramping-vus | 30 VUs, 30 min |

---

## CI Integration

```yaml
# Example GitHub Actions step
- name: Run k6 smoke test
  uses: grafana/k6-action@v0.3.1
  with:
    filename: tests/load/k6_training.js
  env:
    BASE_URL: http://localhost:8000
    USERS: "5"
    DURATION: "30s"
```

---

## Output & Analysis

### Locust
- Web UI: real-time charts at `http://localhost:8089`
- CSV export: `--csv results/locust` produces `results/locust_stats.csv`, `results/locust_failures.csv`, etc.

### k6
- Console: summary table with p50/p90/p95/p99
- JSON: `k6 run --out json=results.json ...`
- CSV: `k6 run --out csv=results.csv ...`
- InfluxDB + Grafana: `k6 run --out influxdb=http://localhost:8086/k6 ...`
