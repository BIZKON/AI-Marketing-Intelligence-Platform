#!/usr/bin/env bash
# Load test runner for AI Marketing Intelligence Platform.
#
# Usage:
#   ./tests/load/run_load_tests.sh [locust|k6] [smoke|load|stress|spike|soak]
#
# Examples:
#   ./tests/load/run_load_tests.sh locust smoke    # 10 users, 1 min
#   ./tests/load/run_load_tests.sh k6 stress       # ramp to 200 users
#   ./tests/load/run_load_tests.sh k6 smoke        # 5 users, 30s

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_URL="${BASE_URL:-http://localhost:8000}"
RESULTS_DIR="${SCRIPT_DIR}/../../results/load"

mkdir -p "$RESULTS_DIR"

TOOL="${1:-k6}"
SCENARIO="${2:-smoke}"

echo "=== Load Test ==="
echo "Tool:     $TOOL"
echo "Scenario: $SCENARIO"
echo "Target:   $BASE_URL"
echo "Results:  $RESULTS_DIR"
echo ""

# ── Locust ────────────────────────────────────────────────────────────────────

run_locust() {
    if ! command -v locust &>/dev/null; then
        echo "ERROR: locust not found. Install: pip install locust"
        exit 1
    fi

    local users spawn_rate duration
    case "$SCENARIO" in
        smoke)   users=10;  spawn_rate=2;  duration="1m"  ;;
        load)    users=50;  spawn_rate=5;  duration="3m"  ;;
        stress)  users=200; spawn_rate=10; duration="5m"  ;;
        soak)    users=30;  spawn_rate=5;  duration="30m" ;;
        *)
            echo "Unknown scenario: $SCENARIO (use: smoke, load, stress, soak)"
            exit 1
            ;;
    esac

    echo "Locust: $users users, $spawn_rate spawn/sec, $duration"
    locust -f "$SCRIPT_DIR/locustfile.py" \
        --host "$BASE_URL" \
        --users "$users" \
        --spawn-rate "$spawn_rate" \
        --run-time "$duration" \
        --headless \
        --csv "$RESULTS_DIR/locust_${SCENARIO}" \
        --html "$RESULTS_DIR/locust_${SCENARIO}.html"

    echo ""
    echo "Results saved to:"
    echo "  CSV:  $RESULTS_DIR/locust_${SCENARIO}_stats.csv"
    echo "  HTML: $RESULTS_DIR/locust_${SCENARIO}.html"
}

# ── k6 ────────────────────────────────────────────────────────────────────────

run_k6() {
    if ! command -v k6 &>/dev/null; then
        echo "ERROR: k6 not found. See https://k6.io/docs/get-started/installation/"
        exit 1
    fi

    local k6_env=()
    k6_env+=(--env "BASE_URL=$BASE_URL")

    case "$SCENARIO" in
        smoke)
            k6_env+=(--env "USERS=5" --env "DURATION=30s")
            ;;
        load)
            k6_env+=(--env "USERS=50" --env "DURATION=5m")
            ;;
        stress)
            k6_env+=(--env "SCENARIO=stress")
            ;;
        spike)
            k6_env+=(--env "SCENARIO=spike")
            ;;
        soak)
            k6_env+=(--env "SCENARIO=soak")
            ;;
        *)
            echo "Unknown scenario: $SCENARIO (use: smoke, load, stress, spike, soak)"
            exit 1
            ;;
    esac

    echo "k6: scenario=$SCENARIO"
    k6 run "$SCRIPT_DIR/k6_training.js" \
        "${k6_env[@]}" \
        --out "json=$RESULTS_DIR/k6_${SCENARIO}.json" \
        --summary-export "$RESULTS_DIR/k6_${SCENARIO}_summary.json"

    echo ""
    echo "Results saved to:"
    echo "  JSON:    $RESULTS_DIR/k6_${SCENARIO}.json"
    echo "  Summary: $RESULTS_DIR/k6_${SCENARIO}_summary.json"
}

# ── Main ──────────────────────────────────────────────────────────────────────

case "$TOOL" in
    locust) run_locust ;;
    k6)     run_k6 ;;
    *)
        echo "Unknown tool: $TOOL (use: locust or k6)"
        exit 1
        ;;
esac

echo ""
echo "Done!"
