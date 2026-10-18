# NaSCon '26: Multi-Sport League & Club Operations Platform

This project has three parts:
- A self-hosted backend: FastAPI, PostgreSQL 16, Redis 7 and MinIO, plus a worker.
- A Flutter Android app in `mobile/`.
- Team rules and contracts in `doc/`.

## Run the backend (one command)

```sh
DAY1_SALT=<salt-from-team-slip> docker compose up -d --build
```

- The API listens on **http://localhost:8080**. `GET /health` returns `{"status":"ok"}` once the database is seeded.
- The schema is created and the baseline data seeded automatically on startup. There are no manual steps.
- `DAY1_SALT` is read **only** from the environment. Every other variable has a default (see `.env.example`).
- For local development, copy `.env.example` to `.env` and set `DAY1_SALT`. Never commit `.env`.
- To expose Postgres, Redis and MinIO to teammates on the LAN:
  `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`

| Service | Image | Purpose |
|---|---|---|
| `api` | built from `backend/Dockerfile` (python:3.12-slim) | REST `/audit/v1/*` and `/api/v1/*`, WebSocket `/api/v1/ws` |
| `worker` | same image | Consumes the `domain-events` Redis stream (order status changes) |
| `postgres` | postgres:16-alpine | Source of truth: append-only event store, orders, audit trail |
| `redis` | redis:7-alpine | Rate limiting, domain-event stream, realtime pub/sub |
| `minio` | bitnamilegacy/minio:2024.9.22 | Object store for PDF receipts (the official `minio/minio` image is no longer on Docker Hub) |

## Demo accounts (exist after every startup and every `POST /audit/v1/reset`)

| Role | Email | Password | Scope |
|---|---|---|---|
| Platform Super-Admin | `admin@nascon.test` | `Nascon@26` | Platform-wide |
| League Organizer | `organizer@nascon.test` | `Nascon@26` | Owns `league-alpha-1` |
| Club Manager | `manager@nascon.test` | `Nascon@26` | Owns `club-alpha-1` |
| Player | `player@nascon.test` | `Nascon@26` | `player-alpha-1` |
| General Viewer | `viewer@nascon.test` | `Nascon@26` | Read-only, `tenant-alpha` |

## Tests

```sh
./run_tests.sh                               # unit tests in the api image, writes COVERAGE.json
DAY1_SALT=<salt> python tools/smoke.py       # grader-style checks against the running stack
```

## Mobile app

The Android APK is at `mobile/release/app-release.apk` and installs on Android 10 (API 29) or newer.

Set the server address on the app's Settings screen:
- Emulator: `http://10.0.2.2:8080`
- Physical phone: `http://<laptop-LAN-IP>:8080`

## Part II (Day 2): streaming, QR, guest web, grid QA

```sh
DAY1_SALT=<s1> DAY2_SALT=<s2> docker compose up -d --build   # API, DB, Redis, MinIO, MediaMTX, Selenium hub + 3 nodes
```

| Service | Address |
|---|---|
| API, Guest Web Player (`/web/*`), `/metrics` | `http://localhost:8080` |
| MediaMTX: RTMP ingest / HLS / WebRTC (WHIP, WHEP) | `rtmp://localhost:1935/live/<stream_key>`, `http://localhost:8888`, `http://localhost:8889` |
| Selenium Grid 4 hub (3 nodes) | `http://localhost:4444/status` |
| Appium 2 (on the phone laptop) | `http://localhost:4723/status` |

Streaming: create a key with `POST /audit/v1/stream/key`, then publish from OBS/FFmpeg to
`rtmp://localhost:1935/live/<stream_key>`. Only active keys may publish; revoke or rotate kicks the publisher within 2 s.
Finished recordings are uploaded to MinIO (`vods` bucket) and listed on `GET /api/v1/athletes/{player_id}`.

Checks and QA (run against the live stack, then `POST /audit/v1/reset`):

```sh
DAY2_SALT=<s2> python tools/day2_check.py           # every /audit/v1 Part II contract + the 4 hidden scenarios
DAY2_SALT=<s2> python tools/smoke_day2_social.py    # co-stream, cart merge, moderation, athletes
python tools/ws_latency.py                          # NFR-1: 25 WebSocket clients, p95 < 500 ms
pytest -n 3 tests/selenium/                         # Guest Web Player on the grid -> tests/reports/selenium-report.xml
k6 run --summary-export=tests/reports/k6-summary.json tests/k6_load.js   # NFR-2
pytest tests/appium/                                # phone on USB + Appium 2 on 4723
```

`./run_tests.sh` also writes `COVERAGE_DAY2.json`. GitHub Actions (`.github/workflows/autograde.yml`) runs all of this
on every push to `main`; it reads `DAY1_SALT` and `DAY2_SALT` from the repository secrets.

Phone over USB without a LAN: `adb reverse tcp:8080 tcp:8080` (and `8888`, `8889`, `1935` for streaming), then set the
app's server address to `http://127.0.0.1:8080`. Deep links: `adb shell am start -W -a android.intent.action.VIEW -d "nascon://entity/match-m1"`.

## Documentation

| File | What it covers |
|---|---|
| `ADR.md` | Architecture decisions |
| `TRACEABILITY.md` | Maps each requirement to source files and tests |
| `doc/CLAUDE.md` | The full contract |
| `doc/AGREED_RULES.md` | Team conventions |
| `doc/DISTRIBUTION.md` | Who owns what |
