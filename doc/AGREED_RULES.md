# AGREED_RULES.md: Architecture, API Rules, Folder Structure and Workflow

These are the decisions the whole team works to. If a rule here conflicts with `CLAUDE.md` (the official contract), **`CLAUDE.md` wins**. In that case, fix this file.
Change a rule here only after telling the other two members.

---

## 1. Architecture

```
            Android app (Flutter)                      Python grader scripts
                  |  /api/v1/* (JWT, rate-limited)          |  /audit/v1/* (no auth except RBAC probes)
                  |  WS /api/v1/ws                          |
                  v                                         v
        +--------------------------------------------------------------+
        |  api  (FastAPI, Python 3.12, uvicorn, port 8080)             |
        |   routes/  -> thin: parse, authorize, call domain, format    |
        |   domain/  -> pure logic (no DB, no HTTP), unit-tested       |
        |   repo/    -> SQL access (SQLAlchemy Core + psycopg 3)       |
        +-----------+-------------+--------------+---------------------+
                    |             |              |
              PostgreSQL 16    Redis 7        MinIO (object store: receipt PDFs)
              (source of     (rate limit,      bitnamilegacy/minio:2024.9.22
               truth)         Redis Streams
                              domain events,
                              WS fan-out pub/sub)
                                  |
                            worker (same image, `python -m app.worker`):
                            consumes the `domain-events` stream and logs/acks
```

| ADR | Decision | Why |
|---|---|---|
| ADR-1 | **Python 3.12 + FastAPI** for the backend | The grader's reference code is Python (`json.dumps(sort_keys, separators, ensure_ascii=False)`), so our canonical JSON matches the grader byte for byte. The `python:3.12-slim` image is already pulled. |
| ADR-2 | **PostgreSQL 16 is the single source of truth.** Event store, orders and audit are append-only tables. | Event sourcing plus row locks for NFR-3. Approved stack. |
| ADR-3 | **Redis 7** for rate limiting, **Redis Streams** for domain events, and pub/sub for real-time | Saves RAM (the grader has 8 GB). A stream counts as an approved queue. |
| ADR-4 | **Stock uses a conditional `UPDATE ... WHERE stock >= qty`** inside one transaction, with multiple items locked in `variant_id` order | Atomic, so there can be no oversell under 20 parallel buyers and no deadlocks. |
| ADR-5 | **Scores and standings are projected on read** from the event log. There are no counters. | The spec requires a rebuild from the log. Compensation is just another event. |
| ADR-6 | **Sports are data.** The seed sports live in `backend/app/seed/sports.json`. The domain code reads the `scoring_model` and the config, never names. | Avoids the -8 hard-coding penalty. The mystery sport works without a restart. |
| ADR-7 | **Custom HS256 JWT (PyJWT) plus a policy-as-code RBAC table** in `app/auth/policy.py` | Simple, testable, and covers the matrix in CLAUDE.md §7.10. |
| ADR-8 | **Flutter (Android)** with sqflite cache and queue, flutter_secure_storage (Keystore), dio and Riverpod | Matches the team's skills. A persistent queue in the exact §7.11 format. |

`ADR.md` at the repo root uses these 8 entries. Each one gets Context, Decision, Consequences and Alternatives.

### Backend libraries (pin exact versions in requirements.txt on the day)
`fastapi`, `uvicorn[standard]`, `sqlalchemy>=2`, `psycopg[binary]>=3`, `redis`, `pyjwt`, `reportlab` (PDF), `minio`, `pydantic>=2`, `python-multipart`.
For tests: `pytest`, `pytest-cov`, `httpx`.
**Do not use fixture-generation libraries.** Write the Swiss matching ourselves (backtracking).

### Compose services (`docker-compose.yml`)
| Service | Image | Notes |
|---|---|---|
| `postgres` | `postgres:16-alpine` | Healthcheck `pg_isready`. Named volume (Compose creates it, so this is fine). **No host port** in the main file. |
| `redis` | `redis:7-alpine` | No persistence needed. |
| `minio` | `bitnamilegacy/minio:2024.9.22` | `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` come from the env with defaults. Health `/minio/health/live`. **The official `minio/minio` image is gone from Docker Hub.** |
| `api` | built from `backend/Dockerfile` (FROM `python:3.12-slim`) | `ports: ["8080:8080"]`. `DAY1_SALT: ${DAY1_SALT}`. `depends_on` postgres and redis with `condition: service_healthy`. Creates the schema and seeds on startup. |
| `worker` | same build as api | `command: python -m app.worker` |

**Rules for compose:**
- No `container_name` (it could clash on the grader).
- No bind mounts of host source.
- Every non-salt env var has a default in compose (`${VAR:-default}`), so the grader only needs `DAY1_SALT`.
- Keep total RAM under about 2 GB.
- **Dev-only ports** (5432, 6379, 9000 for teammates on the hotspot) go in `docker-compose.dev.yml`, started with `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`.
- **Never name the dev file `docker-compose.override.yml`.** Compose auto-loads that name, so the grader would load it too.

### Startup sequence (api)
1. Read the env. Fail fast if `DAY1_SALT` is unset.
2. Wait for the DB.
3. Create the schema (`CREATE TABLE IF NOT EXISTS ...`).
4. Run the same reset/seed routine as `POST /audit/v1/reset` with seed 42.
5. Only then does `/health` return 200.

Run uvicorn with **`--workers 2`**. Everything that has to be shared between workers lives in Postgres or Redis, never in process memory.

---

## 2. Folder structure (repo root)

```
/
├── CLAUDE.md                 # official constraints (this team's bible)
├── AGREED_RULES.md           # this file
├── DISTRIBUTION.md           # ownership + timeline
├── README.md                 # run steps + 5 demo accounts            (Tanzeel)
├── ADR.md                    # 8 ADRs                                  (Tanzeel drafts, all review)
├── TRACEABILITY.md           # FR/NFR -> files -> tests                (each owner adds own rows)
├── COVERAGE.json             # honest per-area numbers                 (Tanzeel, from run_tests.sh)
├── run_tests.sh              # runs all tests + writes coverage        (Tanzeel)
├── docker-compose.yml        # grader stack                            (Tanzeel)
├── docker-compose.dev.yml    # dev-only host ports                     (Tanzeel)
├── .env.example              # every env var, NO real salt             (Tanzeel)
├── .gitignore                # .env, __pycache__, build/, .dart_tool/, etc.
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py           # app factory, middleware (413, rate limit), exception handlers
│       ├── config.py         # env vars
│       ├── errors.py         # ApiError + handlers (400 override of 422)
│       ├── canonical.py      # canonical(), sign(), lots_key()
│       ├── db.py             # engine, schema DDL, transaction helper
│       ├── seed/             # sports.json, baseline.json  (DATA, not code)
│       ├── auth/             # jwt.py, policy.py (RBAC matrix), deps.py
│       ├── domain/           # PURE logic, no DB/HTTP imports
│       │   ├── fixtures/     # round_robin.py, swiss.py, single_elim.py, double_elim.py, validate.py  (Gunee)
│       │   ├── standings.py  #                                                                       (Gunee)
│       │   ├── roster.py     # rule checks + effects (pure)                                          (Gunee)
│       │   ├── scoring.py    # sport validation + projection from event list                         (Tanzeel)
│       │   ├── store.py      # pricing, discount, receipt payload                                    (Tanzeel)
│       │   └── sync.py       # offline-sync resolution                                               (Tanzeel)
│       ├── repo/             # SQL per area (events, leagues, roster, store, sync)
│       ├── routes/           # audit_*.py, api_v1_*.py, ws.py
│       ├── services/         # payments.py (mock gateway), receipts.py (PDF), objectstore.py, events_bus.py
│       └── worker.py
├── tests/                    # pytest — root level as spec requires
│   ├── conftest.py
│   ├── unit/                 # pure domain tests (run without Docker)
│   │   ├── test_fixtures_round_robin.py ... test_standings.py, test_roster_rules.py, test_canonical.py
│   └── integration/          # hit http://localhost:8080 (need stack up); skipped if unreachable
├── tools/
│   └── smoke.py              # grader-like checks: 20-thread checkout, RBAC matrix, rate limit, signatures
└── mobile/                   # Flutter project (Huzaifa owns; Gunee helps on data layer)
    ├── pubspec.yaml
    ├── lib/
    │   ├── main.dart
    │   ├── core/             # api_client.dart, config (server URL), secure_store.dart, theme/, connectivity.dart
    │   ├── data/             # models/, local_db.dart (sqflite), cache repos, sync_queue.dart, sync_service.dart
    │   ├── features/         # auth/, fixtures/, match/, standings/, club/, store/, roster/, scoring/, sync/, settings/
    │   └── widgets/          # SyncStatusBar, EmptyState, ErrorView, ConfirmDialog, LoadingView
    ├── test/
    └── release/app-release.apk
```

**Ownership rule:** each folder has one owner (see DISTRIBUTION.md). To change something in someone else's folder, tell them first. This keeps merge conflicts close to zero.

---

## 3. Agreed backend coding rules

### 3.1 Errors: the single shape used everywhere
```python
# backend/app/errors.py  (Tanzeel creates in first push; Gunee codes against this signature from minute 1)
class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str = "", details: dict | None = None):
        self.status, self.code, self.message, self.details = status, code, message, details or {}

def validation_error(fields: list[str], message: str = "Invalid request") -> ApiError:
    return ApiError(400, "VALIDATION_ERROR", message, {"fields": fields})
```
- Domain code **raises `ApiError`**. Routes never build error JSON by hand.
- The handlers render `{"error":{"code","message","details"}}`.
- FastAPI's `RequestValidationError` and JSON decode errors become **400 `VALIDATION_ERROR`**, with `details.fields` holding the field names (the last element of each `loc`).
- Any unexpected exception becomes a 500 and is logged. **We should never see one.** Validate everything.

### 3.2 Validation order in every route
1. Parse and schema-check (400).
2. Check that referenced ids exist (404).
3. Check business rules (409, or 402 for payment).

Write each handler in exactly that order. For roster, follow the 8-step order in CLAUDE.md §7.8.

### 3.3 Validation style
- Use **manual validation functions** in the domain (`require_str(body, "league_id", fields)`, etc.) that collect the bad field names. Then raise `validation_error(fields)`.
- Use Pydantic only where its errors map cleanly. Note that Pydantic coerces `"1"` to `1` by default, and the spec says a **wrong type is 400**. Use `strict=True` or validate manually.
- The id regex is `^[A-Za-z0-9_.:-]{1,64}$`. The sport_id regex is `^[a-z0-9_-]{2,40}$`.
- `bool` is not an int. Check with `type(x) is int`, not `isinstance(x, int)`.

### 3.4 Pure domain function interfaces (Gunee implements, Tanzeel wires into routes)
```python
# domain/fixtures/__init__.py
def generate(body: dict) -> dict:      # full /audit/v1/fixtures request body -> exact response body; raises ApiError

# domain/standings.py   (wired in routes/audit.py -> compute_standings)
def compute(league: dict, sport: dict, matches: list[dict]) -> dict:
    # league  = {"league_id","sport_id","teams":[...],"fixtures":[{match_id,home,away}],
    #            "points":{"win","draw","loss"},"tie_break_order":[...] (draw_lots may be absent -> apply last),
    #            "qualification_spots":k,"lots_seed":int}
    # sport   = stored sport config (sport_id, scoring_model, periods{balls_per_over, overs_per_innings,
    #           wickets_per_innings,...}, scoring_events, draw_allowed, ...)
    # matches = one dict per fixture, in fixture order: the exact GET /audit/v1/score projection:
    #           {match_id, status, outcome, winner_team_id, tiebreak_winner_team_id,
    #            home:{team_id,score,wickets,balls,overs,fair_play}, away:{...}, version, events}
    #           A match counts as played only if status=="completed" and outcome!="undecided".
    # returns the exact /standings response body

# domain/roster.py   (wired in repo/roster.py; the routes answer 501 until these three exist)
def validate_request(req) -> None:
    # step 1 only: 400 VALIDATION_ERROR (schema, dates, loan_end_date > effective_date, to_squad unless release)
def check_and_apply(state: dict, req: dict, now_iso: str) -> tuple[dict, dict]:
    # steps 2-8 in exact order (404 PLAYER/SQUAD_NOT_FOUND, 409 ...); returns (response_body, new_state)
    # must append exactly one audit entry to new_state["audit"] and bump new_state["next_audit_seq"]
def history(state: dict, player_id: str, as_of: str) -> tuple[dict, dict]:
    # returns (response_body, new_state). Append the loan_return entry (who="system") once only.
    # Tanzeel saves new_state only if it differs from state.
```
The repo layer handles request_id idempotency (it stores the 2xx response and replays it with 200) and the league-not-found 404. Gunee's functions never see a replay.

**Roster `state` shape** (one JSON blob per league, row-locked while in use, built by `/roster/setup`):
```python
{
  "league": {"league_id", "tenant_id", "sport_id", "transfer_window": {"open", "close"},
             "max_squad_size": int, "required_positions": {pos: min}},     # defaults already filled from the sport
  "squads": {squad_id: {"squad_id", "club_id", "tenant_id", "name"}},
  "players": {player_id: {"player_id", "name", "position", "squad_id": str|None, "parent_squad_id": str|None,
              "role", "registration_type": "initial"|"transfer"|"loan"|"release",
              "start_date": str|None, "loan_end_date": str|None}},
  "matches_in_progress": [{"match_id", "home_squad_id", "away_squad_id"}],
  "audit": [audit_entry, ...],      # oldest first, append-only
  "next_audit_seq": int             # audit_id = f"au-{seq:04d}"
}
```
Tanzeel's repo layer loads and saves the state. Gunee's functions take no DB handle, so all of them can be unit-tested without Docker.

### 3.5 Idempotency storage
Every client-id endpoint stores `(id, canonical(request_body), status_code, response_body)`.
- Same id and same canonical body: return the stored response with **HTTP 200**.
- Same id and a different body: return the 409 duplicate code.
- **Only successful (2xx) results are stored.** Rejections write nothing (roster spec).

### 3.6 Events and signatures
- Store `payload_canonical TEXT` exactly as signed, and parse it back for responses. **Do not round-trip through `jsonb`.** jsonb reorders keys and normalises numbers.
- Get `sequence` with `SELECT ... FOR UPDATE` on the match row, then `max(sequence)+1` in the same transaction. That gives no gaps and no duplicates under concurrency.
- `sign()` lives only in `app/canonical.py`. A unit test must reproduce Appendix A test vector 1.

### 3.7 Checkout concurrency (NFR-3)
```sql
-- inside one transaction, for each item ordered by variant_id:
UPDATE inventory SET stock = stock - :q, reserved = reserved + :q
 WHERE variant_id = :v AND stock >= :q;          -- rowcount 0 => OUT_OF_STOCK, rollback everything
-- payment mock; success:
UPDATE inventory SET reserved = reserved - :q WHERE variant_id = :v;
-- failure: stock += q, reserved -= q
```
- The `order_id` uniqueness check uses an `INSERT ... ON CONFLICT DO NOTHING` row first, so two identical replays can't both reserve.
- Prove it with `tools/smoke.py`: 20 threads behind a barrier should give 1×201, 19×409, stock 0 and reserved 0.

### 3.8 Rate limiting and body size
- `/api/v1/*` only. Use a Redis sorted-set sliding window: 100 requests per rolling 10 s per client IP. On 429, return `RATE_LIMITED` with a `Retry-After` header (in seconds).
- Body > 1 048 576 bytes: return 413 `PAYLOAD_TOO_LARGE`. Check `Content-Length` and the actual bytes read in middleware, **before** JSON parsing and before auth.
- `/audit/v1/*` and `/health` are never limited.

### 3.9 RBAC
- `auth/policy.py` holds one table: `(action, role) -> rule`. A rule is `always`, `never`, `own_league`, `own_club`, `own_club_player`, `self`, or `same_tenant`.
- The super_admin bypasses tenant checks.
- Every non-admin check also requires `resource.tenant_id == token.tenant_id`, else 403.
- Resolve the resource's owner and tenant from the DB. An id that doesn't exist at all gives 404, but **a foreign tenant gives 403**. Auth runs **first**.
- JWT is HS256 with `JWT_SECRET` from the env (compose default provided) and `exp` = now + 12 h. Decode with `algorithms=["HS256"]` only, which rejects `alg:none`.

### 3.10 Time
- All timestamps are UTC with the `Z` suffix and no microseconds: `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`.

### 3.11 No hard-coded sports
- No string literal of a sport id or event name inside `backend/app/` **except in `seed/*.json`**. Tests may use them.
- Before the final push, run `grep -rniE '"(football|basketball|cricket|esports|goal|wicket|six|four)"' backend/app --include=*.py`. It must print nothing.

---

## 4. Mobile ↔ backend API (`/api/v1/*`). Agreed contract for Huzaifa and Gunee.

**General rules:**
- All routes need `Authorization: Bearer <jwt>` except login and ping.
- Errors use the same `{"error":{code,message,details}}` body. **The app maps `code` to a plain-language message.** Raw codes are never shown.
- **Response bodies reuse the audit shapes** wherever one exists, so there is one model per concept.

| Method + path | Body / query | Response |
|---|---|---|
| `POST /api/v1/auth/login` | `{email, password}` | `{token, role, user:{id, email, display_name, club_id?, league_id?, player_id?}, tenant:{tenant_id, name, logo_url, primary_color, secondary_color}}`. Role is one of `super_admin`, `league_organizer`, `club_manager`, `player`, `viewer`. |
| `GET /api/v1/ping` | none | `{"pong":true}` |
| `GET /api/v1/leagues` | none | `[{league_id, name, sport_id, season}]` (tenant-scoped) |
| `GET /api/v1/leagues/{id}/fixtures` | none | `[{match_id, home, away, home_name, away_name, status, scheduled_at, venue}]` |
| `GET /api/v1/standings/{league_id}` | none | Same as `/audit/v1/standings` |
| `GET /api/v1/matches/{id}` | none | Same as `/audit/v1/score`, plus `pinned_product` (product or null) |
| `GET /api/v1/clubs/{id}` | none | `{club_id, name, tenant_id, venue:{name, lat, lng}, socials:{}, staff:[{name, role}], roster:[{player_id, name, position, role, squad_id}], stats:[{season, played, won, drawn, lost}]}` |
| `GET /api/v1/products` | `?club_id=` | `[{product_id, name, type, image_url, variants:[{variant_id, size, color, price_minor, stock}]}]` |
| `POST /api/v1/checkout` | Same as audit checkout | Same as audit checkout |
| `GET /api/v1/orders/{order_id}/receipt` | none | `application/pdf` |
| `POST /api/v1/events` | Same as `/audit/v1/events` (organizer, own league) | Same |
| `POST /api/v1/roster/transfer` | Same as `/audit/v1/roster/transfer` (manager, own club) | Same |
| `GET /api/v1/roster/history/{player_id}` | none | Same |
| `POST /api/v1/sync` | **Exactly** the `/audit/v1/offline-sync` body | Same response (shared code path) |
| `POST /api/v1/matches/{id}/pin` | `{product_id}` (manager/organizer) | `{match_id, pinned_product}` and broadcasts on the WS |
| `WS /api/v1/ws?token=<jwt>` | none | Server sends `{"type":"match_update"\|"match_status"\|"product_pinned","match_id":"...","data":{...}}` |

**Rate limit warning for the app:** 100 req/10 s per IP. **Don't poll in a loop.** Use the WebSocket for live scores, and refresh only on screen open or pull-to-refresh.

---

## 5. Mobile architecture rules

**Stack**
- Flutter stable, Android only, `minSdkVersion 29`.
- Packages: `flutter_riverpod`, `go_router`, `dio`, `flutter_secure_storage` (Keystore), `sqflite`, `path`, `connectivity_plus`, `web_socket_channel`, `uuid`, `open_filex` or `path_provider` for the receipt PDF.
- **Add no other packages without telling the team.** Pub caches must be warmed at home.

**Server URL**
- Settings screen, stored in shared prefs. Defaults to `http://10.0.2.2:8080`. On the phone use `http://<laptop-LAN-IP>:8080`.
- **Cleartext HTTP must be allowed.** Set `android:usesCleartextTraffic="true"` in the manifest, or the release APK can't reach the laptop.

**Token storage**
- Use `flutter_secure_storage` only. **Never** put the JWT in shared prefs or SQLite.

**Local DB (sqflite)**
- Tables: `cache(key TEXT PK, json TEXT, updated_at TEXT)` for fixtures, standings and clubs, and `pending_actions(action_id PK, type, queued_at, base_version, payload_json, status, result_json)`.

**Queue item (EXACT §7.11 format)**
```json
{ "action_id":"<uuid>", "type":"score_event" | "roster_transfer", "queued_at":"YYYY-MM-DDTHH:MM:SSZ",
  "base_version": <last seen match version | player audit entry count>, "payload": { ...the /events or /roster/transfer body... } }
```
- `device_id` is generated once and stored in secure storage.
- Offline actions are written to SQLite **before** the UI says "pending". They survive a force-close.

**Sync**
- When connectivity returns, or the Sync button is pressed, POST all pending items to `/api/v1/sync`.
- Show the per-action result: "Applied", or "Rejected: <plain reason>", using the code→message table below.
- Remove applied and duplicate items. Keep rejected ones visible until the user dismisses them.

**Online/offline detection**
- connectivity_plus plus a ping to `/api/v1/ping`.
- The `SyncStatusBar` widget sits **in the app shell on every screen**, showing Online, Offline or Syncing with an icon AND text (not colour alone) and the pending count.

**Plain-language error map (shared, in `core/errors.dart`):**
- `OUT_OF_STOCK`: "Sorry, this item just sold out."
- `PAYMENT_DECLINED`: "Your payment was declined. Try another card."
- `PAYMENT_CAPTURE_FAILED`: "Payment couldn't be completed. You were not charged."
- `TRANSFER_WINDOW_CLOSED`: "The transfer window is closed for that date."
- `SQUAD_FULL`: "The destination squad is full."
- `MIN_POSITION_VIOLATION`: "This move would leave the squad short of required players in that position."
- `PLAYER_ON_LOAN`: "This player is on loan and can't be moved right now."
- `NOT_IN_SQUAD`: "This player is no longer in that squad."
- `CROSS_TENANT_TRANSFER`: "Players can only move between clubs of the same organisation."
- `MATCH_NOT_IN_PROGRESS`: "This match isn't live, so scores can't be added."
- `INVALID_COMPENSATION`: "That event was already corrected or can't be corrected."
- `INVALID_BASE_VERSION`: "Your data was out of date. Refresh and try again."
- `FORBIDDEN`: "You don't have permission to do that."
- `UNAUTHENTICATED`: "Please sign in again."
- `RATE_LIMITED`: "Too many requests. Please wait a moment."
- No network: "You're offline. This will sync when you're back online."
- Anything else: "Something went wrong. Please try again."

**UI rules (from CLAUDE.md §11)**

*Theme and visual consistency*
- One `ThemeData` built from the tenant's colours after login, applied everywhere. Show the tenant logo in the app bar.
- Visual hierarchy: the score is the largest text on the Match screen. "Buy" is the primary filled button.

*Accessibility*
- Minimum tap target 48 dp (`minimumSize: Size(48, 48)`). Body text ≥ 14 sp. Contrast ratio ≥ 4.5:1.
- Every `IconButton` has a `tooltip` or `Semantics(label:)`.
- Status chips show a text label next to the colour.

*Feedback*
- Every async screen has loading, empty ("No matches yet"), error (plain text plus Retry) and data states.
- Confirmation dialog before checkout, release, transfer, loan and compensation.
- Show a SnackBar on success.

*Navigation and roles*
- Bottom navigation: Fixtures · Standings · Store · Club · More (Roster/Scoring/Sync/Settings, shown by role).
- Hide what the role can't use. Viewers don't see Scoring or Roster. Only Managers see Roster. Only Organizers see Scoring.
- Back always works. No dead ends.

*Layout*
- Test at 360×640 dp and after rotation.
- Use `SingleChildScrollView`/`ListView` and `Flexible`. Never use fixed heights for text.

---

## 6. Git workflow (critical: penalties and disqualification risk)

**Before the event**
1. **Tonight:** Tanzeel creates the GitHub repo **empty, with no README, no license and no .gitignore** (zero commits). It is **public**, with `nascon-eval-26` invited as a collaborator. Gunee and Huzaifa are added as collaborators.
2. **Nobody pushes anything before 10:45 on Day 1.** At 10:40 the repo must have zero commits. Write no project code before 10:45, not even locally.

**During the sprint**
3. Use one branch, `main`, with **small commits**. Before every push, run `git pull --rebase origin main`, then `git push`.
4. **Never `git push --force`, never rewrite pushed history, never amend pushed commits.** The Day 2 history must continue from the Day 1 SHA.
5. Push windows: 10:45–11:45, 11:45–12:45, 12:45–13:45, 13:45–14:45. **Each member pushes at least once per window.** Tanzeel checks the GitHub commit list at :30 of every window.
6. **Final push by 14:55. Hard stop at 15:05:00.** After 15:05 on Day 1, nobody pushes until 10:15 on Day 2.

**What never goes in a commit**
7. `.env` is never committed. `DAY1_SALT` lives only in a local `.env`, from the team slip.
   - `.env.example` holds `DAY1_SALT=replace-with-salt-from-team-slip` plus every other var with its default.
   - Before each push, run `git diff --cached | grep -i salt` to check.
8. `.gitignore` excludes `.env`, `__pycache__/`, `.pytest_cache/`, `.coverage`, `htmlcov/`, `mobile/build/`, `mobile/.dart_tool/`, `*.iml` and `.idea/`.
   - **`mobile/release/app-release.apk` must NOT be ignored.**

**Commit messages**
9. Use the format `area: what` (for example `fixtures: swiss backtracking pairing`). Put the FR id in the body when it applies.

---

## 7. Testing and coverage rules

**Where tests live**
- `tests/unit/` is pure domain tests. **They must pass without Docker** (Gunee and Huzaifa can run them with a local Python).
- `tests/integration/` hits `http://localhost:8080` and is auto-skipped when the stack is down.

**Coverage mapping** (in `run_tests.sh`): each area maps to its files.

| Area | Files |
|---|---|
| fixtures | `domain/fixtures/*` |
| scoring | `domain/scoring.py`, `canonical.py` |
| standings | `domain/standings.py` |
| store | `domain/store.py`, `services/payments.py`, `services/receipts.py` |
| roster | `domain/roster.py` |
| rbac | `auth/*` |

**`run_tests.sh`**
- Runs `python -m pytest tests --cov=backend/app --cov-report=json`.
- A small Python snippet then aggregates the per-area line coverage and writes `COVERAGE.json`.
- If a local Python isn't available, it falls back to `docker compose run --rm api ...`.

**Honest numbers.** Declare at most the measured value. If an area is below 85%, write the real number anyway, because being more than 2 points over the real figure voids the bonus.

**Every error code in CLAUDE.md §13** must have at least one test. The hidden vectors cover them all.

**`tools/smoke.py`** is our own grader. Run it after each backend area lands, and against a clean `docker compose down -v && docker compose up -d --build` at 14:20.

---

## 8. Team network on the day
- Tanzeel's phone hotspot (or a travel router) is the team LAN. All three laptops and the test phone join it.
- Tanzeel finds the LAN IP with `ipconfig`, then allows ports 8080, 5432 and 6379 inbound in Windows Firewall, **only on the private hotspot profile**.
- Gunee runs the API locally against Tanzeel's DB: `DATABASE_URL=postgresql://nascon:nascon@<tanzeel-ip>:5432/nascon REDIS_URL=redis://<tanzeel-ip>:6379/0 DAY1_SALT=dev uvicorn app.main:app --port 8080` from `backend/`. Or Gunee can just call Tanzeel's API at `http://<tanzeel-ip>:8080`.
- Huzaifa's phone or app points at `http://<tanzeel-ip>:8080`.
- Campus Wi-Fi is used only for GitHub, AI tools and pub/pypi downloads.
