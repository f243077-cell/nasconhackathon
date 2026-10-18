#!/usr/bin/env sh
# Runs every unit test and writes COVERAGE.json (Part I areas, spec 9.3) and COVERAGE_DAY2.json (Part II modules).
# Uses the api Docker image so no host Python packages are needed.
# Integration checks against a running stack: python tools/smoke.py
set -e
cd "$(dirname "$0")"
export MSYS_NO_PATHCONV=1
HOST_DIR="$(pwd -W 2>/dev/null || pwd)"

docker compose build api >/dev/null
docker compose run --rm --no-deps -T \
  -e DAY1_SALT=unit-test-salt \
  -v "$HOST_DIR/backend/app:/srv/app" \
  -v "$HOST_DIR/tests:/srv/tests" \
  -v "$HOST_DIR/tools:/srv/tools" \
  api sh -c "python -m pytest tests/unit -q -p no:cacheprovider --cov=app --cov-report=term --cov-report=json:/tmp/cov.json \
             && python tools/coverage_areas.py /tmp/cov.json day1 && python tools/coverage_areas.py /tmp/cov.json day2" \
  | tee /tmp/run_tests_out.txt

# Last two lines: Part I areas, then Part II modules.
tail -n 2 /tmp/run_tests_out.txt | head -n 1 > COVERAGE.json
tail -n 1 /tmp/run_tests_out.txt > COVERAGE_DAY2.json
echo "COVERAGE.json:"
cat COVERAGE.json
echo "COVERAGE_DAY2.json:"
cat COVERAGE_DAY2.json
