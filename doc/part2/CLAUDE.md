# CLAUDE.md: NaSCon '26 App Dev Competition, Part II (shared team file)

Team: **Tanzeel** (Docker, Android emulator, backend), **Gunee** (Flutter + Python, no Docker), **Huzaifa** (Flutter UI, no Docker).

This file lists **every constraint and rule** in the Day 2 spec. Read it before writing any code. Part II **extends** Part I: every Part I rule in `../CLAUDE.md` still applies unless this file says otherwise.
- `App Dev Day 2 Problem Statement.pdf`: the Part II spec. It is the **binding contract**: "If any verbal statement conflicts with this document, this document wins."
- `../CLAUDE.md`: the Part I rules (all Phase I endpoints, error codes and behaviour stay graded as a regression pass).

Companion files in this folder:
- `AGREED_RULES.md`: architecture, folder structure, API conventions and git workflow for Part II.
- `DISTRIBUTION.md`: who owns what, the timeline and the handoffs.
- `DOCKER_SETUP_LOG.md`: images Part II needs and what is already pulled.

> Spec footer (same as Day 1): *"If your code works on the first try, check again. It's probably the wrong problem."* JSON keys, status codes, error codes, DOM selectors, ports and HMAC signatures are compared **literally**.

---

## 0. Conflicts and changes vs Part I (resolved)

| Topic | Part I / booklet | Part II spec | We follow |
|---|---|---|---|
| Repo visibility | Booklet: private + invite `nascon-eval-26`. Part I: public. | **"Your public GitHub repository"** | Same as Day 1. Confirm with organisers at the 10:00 check. |
| Push windows | 4 windows to 14:45, deadline 15:05 | **10:15–11:30, 11:30–12:45, 12:45–13:45, 13:45–14:00** (grace to **14:05:00**) | Part II windows. |
| Validation order | 400, then 404, then 409/402 | 400, then 404, then **403 (permission)**, then 409 | Part II order for all new routes. |
| `/health` | DB reachable + seeded | Also checks **Redis and the media server** | Extend `/health`. |
| Startup command | `DAY1_SALT=… docker compose up -d --build` | `DAY1_SALT=<s1> DAY2_SALT=<s2> docker compose up -d --build`, **all containers healthy** (incl. Selenium hub + 3 nodes + media server) | Forward both salts. |
| Weighting | 36 backend / 4 offline / 10 UI | **80% backend + automated QA, 20% frontend** (mobile + guest web) | Backend first. |
| Coverage file | `COVERAGE.json` (6 areas) | **`COVERAGE_DAY2.json`** (5 modules), ≥ 85% each | Keep both files. |
| Seed | Part I baseline | Adds `player-beta-2`, `match-m1`, 3 QR mappings, `guest_anon_tok_7721`, empty cart for `player-alpha-1` | The spec says `player-beta-2` exists "from Day 1" — **our Day 1 seed does not have it**; add it. |
| Selenium images | Booklet pre-pull: `4.24.0` | Spec compose example: **`4.25.0`** | Use what's pulled if 4.25.0 can't be pulled (graded on behaviour: `/status` ready with ≥ 3 nodes). See `DOCKER_SETUP_LOG.md`. |
| `container_name` | Our Day 1 rule: avoid it | The spec example uses `container_name: nascon-selenium-hub` | Allowed (spec example). |
| Flood rule wording | — | §3.3 says ≥ 5 repeated chars / ≥ 4 identical non-alphanumeric / > 3 msgs in 2 s; **§5.8 (the graded probe)** says ≥ 4 consecutive identical chars (case-insensitive) OR ≥ 3 consecutive `!`/`?` | Implement **§5.8** for the probe; also add the 3-msgs-in-2 s rate rule (`rate_limit_exceeded`). |

---

## 1. Schedule and integrity rules (Day 2, Sun Oct 18)

- 10:00–10:14: morning commit verification.
- **10:15: Part II released, sprint starts.** Code freeze **14:00:00**. **Final push 14:05:00 PKT (hard lock).**
- Push windows (≥ 1 pushed commit each, GitHub server time): **W1 10:15–11:30, W2 11:30–12:45, W3 12:45–13:45, W4 13:45–14:00** (grace 14:05:00). Each missed window costs a penalty.
- **Commit continuity:** the grader runs `git merge-base --is-ancestor $DAY1_BASE_SHA HEAD`. Day 2 commits must build directly on the locked Saturday commit. **No re-init, no force push, no history rewrite.** It also re-runs the Phase I unit tests and baseline `/audit/v1/reset` probes (regression).
- 14:05–14:25: audit. **14:30: Top-8 finalist viva** (live code mutation, 2 hidden scenarios, `ADR.md`, `TRACEABILITY.md`).
- `DAY2_SALT` (16 chars, from the Day 2 venue slip) is read **only from the environment**. Hard-coding it voids credit for that module.
- **Server-side security:** hiding buttons without a backend **403 `GUEST_WRITE_FORBIDDEN`** voids credit.
- All Part I prohibitions still apply (no BaaS, no pre-built repos, no hard-coded sport logic, mock payment gateway).

---

## 2. Required repo-root contents (Part II §1.3, adds to Part I)

| Path | Requirement |
|---|---|
| `docker-compose.yml` | Full Phase I + II stack: API 8080, DB, Redis, MinIO, **media server on 1935/8888/8889**, **Selenium Grid 4 hub + 3 browser nodes on 4444**. Forwards `DAY1_SALT: ${DAY1_SALT}` **and** `DAY2_SALT: ${DAY2_SALT}`. |
| `.github/workflows/autograde.yml` | GitHub Actions on every push to `main`: backend contract probes, Selenium Grid node verification, k6 smoke. |
| `tests/selenium/` | Parallel Selenium Grid 4 suite, incl. `tests/selenium/test_guest_grid.py` (§6.2.3). |
| `tests/appium/` | Appium 2 suite, incl. `tests/appium/test_mobile_deeplink.py` (§6.3). |
| `tests/k6_load.js` | The **exact** k6 profile in §6.4. |
| `tests/reports/` | `selenium-report.xml`, `appium-report.xml`, `k6-summary.json` (JUnit XML / Allure / HTML). |
| `COVERAGE_DAY2.json` | `{"streaming", "costream", "qr_guest", "moderation_dlq", "observability"}` line coverage. |
| `TRACEABILITY.md` | Add every Part II requirement ID (FR-3.x, FR-4.x, FR-5.2/5.3, NFR-1/2/6/8/9). |

**Pre-submission checklist (Appendix C), before 14:00:00:**
- `DAY1_SALT=<s1> DAY2_SALT=<s2> docker compose up -d --build` starts cleanly; `/health` 200 within 120 s.
- `git merge-base --is-ancestor $DAY1_BASE_SHA HEAD` passes.
- `/audit/v1/reset` seeds `match-m1`, `player-beta-2`, `guest_anon_tok_7721` and the default QR mappings.
- Every `/audit/v1/*` endpoint returns the exact keys, codes and `DAY2_SALT` signatures of §5.
- `http://localhost:4444/status` → `ready: true` with ≥ 3 nodes (`shm_size: "1gb"`).
- `/web/matches/match-m1/live` has all **9** `data-testid` attributes.
- `http://localhost:4723/status` → `ready: true`; `adb shell am start -W -a android.intent.action.VIEW -d "nascon://entity/match-m1"` opens the app screen.
- `k6 run tests/k6_load.js`: 15 s, 500 guest VUs + 50 chat VUs, 0% 5xx.
- `tests/reports/*`, `COVERAGE_DAY2.json` and `TRACEABILITY.md` committed and pushed before 14:05:00.

---

## 3. Mandatory ports (§6.1) — custom mappings fail the probes

| Service | Host endpoint | Probe |
|---|---|---|
| Core API + Guest Web | `http://localhost:8080` | `/health`, `/audit/v1/*`, `/web/*`, `/metrics` |
| Selenium Grid 4 hub | `http://localhost:4444` | `GET /status` → `value.ready == true`, `len(value.nodes) >= 3` |
| Appium 2 server | `http://localhost:4723` | `GET /status` → `ready: true` |
| Media RTMP ingest | `rtmp://localhost:1935` | publish on `/live/{stream_key}` |
| Media HLS playback | `http://localhost:8888` | `/live/{key}/index.m3u8`, `/costream/{id}/index.m3u8` |
| Media WebRTC WHIP/WHEP | `http://localhost:8889` | WHIP ingest, WHEP playback |

Browser nodes reach the backend via `http://host.docker.internal:8080` or the service name (`http://backend:8080` / our `http://api:8080`).

---

## 4. Functional requirements (each ID goes in TRACEABILITY.md)

**FR-3.1 Athlete identity and social graph**
- Athlete profile: career match records (from Phase I event logs), active club affiliations, upcoming fixtures, indexed VOD archive of completed streams.
- Follow/unfollow: concurrency-safe, **zero follower-count drift** under simultaneous toggles, idempotent per `(follower_id, athlete_id)`.

**FR-3.2 Low-latency solo streaming and overlays**
- In-app broadcast via WebRTC (WHIP) or RTMP to a **self-hosted media server** (MediaMTX / LiveKit / SRS); glass-to-glass < 3.0 s on LAN; HLS (`.m3u8`) and WebRTC playback.
- OBS/FFmpeg ingest authenticated by **rotating stream keys signed with `DAY2_SALT`**. Revoke/rotate must **cut active ingest within 2.0 s**.
- Live overlays (score from FR-1.1, club badges, pinned merch from FR-2.3) via WebSocket/SSE metadata, **without restarting the stream**.
- Recording to MinIO and **VOD indexing immediately** on stream end.

**FR-3.3 4-way co-streaming and host handoff**
- Up to 4 broadcasters, layouts `grid_2`, `grid_4`, `spotlight` (and `solo`), via SFU or server-side composition, one **composite playback URL**.
- Host controls: signed invite tokens, mute, spotlight, kick.
- **Exactly one chat room** `chat-{session_id}` per co-stream, monotonically increasing sequence numbers across all hosts and viewers.
- **Host drop:** hosting moves to the next participant in array order **within 1.5 s**, or the session terminates if nobody remains; **zero zombie processes**.

**FR-4.1 Dynamic cryptographic QR deep-links**
- QR for any `match-*`, `club-*`, `player-*`, `cs-session-*`.
- Encodes a **stable** short URL `http://localhost:8080/q/{short_code}` signed with `DAY2_SALT`; resolves via **302** (or JSON on the audit probe) based on **live** entity state (routes in §7.4).
- Exports: **SVG** (`image/svg+xml`), **PNG** (`image/png`), **PDF** (`application/pdf`).
- Privacy-safe telemetry (NFR-9): scan count, device family (`mobile`/`desktop` from User-Agent), UTC time bucket — **no IP, cookies or PII**.
- Hybrid deep link: native app via `nascon://entity/{entity_id}` intent filter; otherwise browser opens the Guest Web Player.

**FR-4.2 Zero-account guest experience**
- Opening a resolved QR route: **no install prompt, no login wall, no credential dialog**.
- Backend issues a short-lived anonymous token `guest_anon_tok_*`: read-only playback, live score subscription, local guest cart staging.

**FR-4.3 Server-enforced read-only boundary**
- Any write by a `guest_anon_tok_*` bearer (or unauthenticated guest): chat post, follow, direct checkout, roster/score mutation → **403 `GUEST_WRITE_FORBIDDEN`**. UI hiding alone scores 0.

**FR-4.4 Progressive registration and atomic cart merge**
- Guests stage merch in a guest cart tied to `guest_token`.
- Login/registration prompt **only** when the guest starts a protected write ("Proceed to Checkout", "Send Chat").
- On login: **atomically merge** guest cart into the user's persistent cart (sum quantities per `variant_id`, **capped by stock**), invalidate the guest token against repeat merges (identical replay returns the merged cart, no double add), return the client to the exact playback timestamp.

**FR-5.2 Notification bus and DLQ**
- Real-time dispatch (WebSocket/SSE) for score updates, co-stream invites, order status transitions.
- Failed delivery (e.g. `simulate_dlq: true`, disconnected subscriber): **bounded exponential retry, max 3 attempts**, then a **persistent DLQ** inspectable via the audit contract.

**FR-5.3 Automated chat moderation**
- Synchronous pre-broadcast filter: leetspeak normalisation (`@→a`, `0→o`, `1`/`!→i`, `3→e`, `$→s`, strip `_ . - *` and zero-width separators), replace profanity tokens with `***`, `"flagged": true, "reason": "profanity_leetspeak"`.
- Flood/rate: blocked from broadcast, `"reason": "flood_character_repeat"` or `"rate_limit_exceeded"` (> 3 messages in a 2 s sliding window per sender). Exact probe rules in §7.6.

---

## 5. Non-functional requirements (Part II)

| ID | Bar | Verified by |
|---|---|---|
| NFR-1 Real-time score latency | A score appended via `POST /audit/v1/events` broadcasts over `ws://localhost:8080/ws/matches/{match_id}` **or** SSE `GET /api/v1/matches/{match_id}/stream`; **p95 < 500 ms**. | 25-client concurrent WebSocket probe |
| NFR-2 Concurrency scale | 500 guest viewers + 50 chat posters for 15 s: **0% 5xx, p95 < 800 ms**. | `k6 run tests/k6_load.js` |
| NFR-6 Observability | `GET /metrics`, Prometheus text (`text/plain; version=0.0.4`) with `nascon_active_ws_connections`, `nascon_active_streams_total`, `nascon_stream_bitrate_kbps`, `nascon_dlq_depth`, `nascon_qr_scans_total`. | Metrics probe |
| NFR-8 Guest web accessibility | WCAG 2.1 AA: contrast ≥ 4.5:1, full keyboard nav (Tab/Enter), ARIA labels on media controls, touch targets ≥ 48×48 CSS px. | Selenium DOM inspection |
| NFR-9 Privacy | QR analytics store **no IPs, no full User-Agent, no fingerprints**. `DELETE /audit/v1/privacy/user/{user_id}` wipes PII and anonymises guest/viewer tokens **within 1 s**. | Privacy probe |

---

## 6. Signature recipe (DAY2_SALT, §5.3 + Appendix A): exact

- Key: `DAY2_SALT` as UTF-8 bytes, **never trimmed or hex-decoded**.
- Message: `entity_id + "|" + canonical(sig_payload)` — the separator is a **pipe `|`**, in every language.
- Canonical JSON: identical to Day 1 (`json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)`).
- Output: HMAC-SHA256, 64 lowercase hex chars.

| Endpoint | `entity_id` | Exact `sig_payload` |
|---|---|---|
| `POST /audit/v1/stream/key` | `<stream_key>` | `{"action", "player_id", "status", "stream_key"}` (the grader also accepts the 2-key `{"action","player_id"}` form) |
| `POST /audit/v1/costream/session` | `<session_id>` | `{"active_host", "handoff_occurred", "layout", "participant_count", "session_id", "status"}` |
| `GET /audit/v1/qr/{entity_id}` | `<entity_id>` | `{"entity_id", "short_url", "target_route"}` |
| `POST /audit/v1/guest/cart-merge` | `<guest_token>` | `{"cart_merged", "guest_token", "registered_user_id", "total_items", "write_rejection_code"}` |
| `POST /audit/v1/moderation/test` | `<chat_room_id>` | `{"chat_room_id", "flagged_count", "kicked_users", "queue_depth"}` |

```python
import hmac, hashlib, json
def canonical(obj): return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
def sign_day2(day2_salt, entity_id, sig_payload):
    return hmac.new(day2_salt.encode("utf-8"), (entity_id + "|" + canonical(sig_payload)).encode("utf-8"), hashlib.sha256).hexdigest()
```
**Test vectors (reference salt `T01D27ad7ffff12e`):**
1. Stream key: `entity_id` `sk_live_9f83a1b2c3d4e5f6`, payload `{"action":"rotate","player_id":"player-alpha-1","status":"active","stream_key":"sk_live_9f83a1b2c3d4e5f6"}`; message `sk_live_9f83a1b2c3d4e5f6|{"action":"rotate","player_id":"player-alpha-1","status":"active","stream_key":"sk_live_9f83a1b2c3d4e5f6"}`. The spec gives no digest; compute it with `sign_day2` and pin it in a unit test.
2. Legacy 2-key: `entity_id` `sk_live_101`, payload `{"action":"rotate","player_id":"player-alpha-1"}`; message `sk_live_101|{"action":"rotate","player_id":"player-alpha-1"}`.

---

## 7. Endpoint contract (Part II §5)

### 7.1 Index
| Method & path | Purpose |
|---|---|
| `GET /health` | Readiness: DB, Redis, media server, baseline seed |
| `POST /audit/v1/reset` | Wipe Phase I + II state, re-seed baseline + Day 2 defaults |
| `POST /audit/v1/stream/key` | Generate / rotate / revoke a stream key (signed) |
| `POST /audit/v1/costream/session` | Init 4-way co-stream + host-drop handoff |
| `GET /audit/v1/qr/{entity_id}` | Resolve QR metadata, target route, scan count, export URLs |
| `GET /audit/v1/qr/{entity_id}/export.{fmt}` | `svg`, `png`, `pdf` |
| `GET /q/{short_code}` | Public short link → **302** to the Guest Web Player route |
| `POST /audit/v1/guest/cart-merge` | Verify 403 guest write block + atomic cart merge |
| `POST /audit/v1/moderation/test` | Leetspeak masking, flood kick/mute, DLQ inspection |
| `GET /metrics` | Prometheus metrics |
| `DELETE /audit/v1/privacy/user/{user_id}` | Right-to-erasure anonymisation |

### 7.2 Reset additions (§5.2)
On top of the full Day 1 baseline, `POST /audit/v1/reset` must also seed:
- Player `player-beta-2` in `club-beta-1`.
- Match **`match-m1`**: football, `league-alpha-1`, home `club-alpha-1`, away `club-alpha-2`, **status `in_progress`, score 1–0**.
- QR mappings: `match-m1` → `http://localhost:8080/q/m1-live` (scan_count 0); `player-alpha-1` → `http://localhost:8080/q/p-alpha-1`; `club-alpha-1` → `http://localhost:8080/q/c-alpha-1`.
- Guest token **`guest_anon_tok_7721`** (valid, unmerged, read-only).
- Cart for `player-alpha-1` = empty (`items: []`).
- DLQ `queue_depth` = 0.

**Standard error envelope** (unchanged): `{"error":{"code","message","details"}}`, e.g. `GUEST_WRITE_FORBIDDEN` with `details.guest_token`.

### 7.3 `POST /audit/v1/stream/key`
Request: `{"action":"rotate","player_id":"player-alpha-1","label":"OBS-Main-Desk","stream_key_override":"sk_live_9f83a1b2c3d4e5f6"}`
- `action` required: `generate` | `rotate` | `revoke`, else 400 `VALIDATION_ERROR`.
- `player_id` required, must exist, else 404 `PLAYER_NOT_FOUND`.
- `label` optional, 1–64 chars, default `"default"`.
- `stream_key_override` optional: **use it exactly** as `stream_key`; otherwise generate `^sk_live_[a-f0-9]{16}$`.

Response **201** (`generate`) or **200** (`rotate`, `revoke`):
```json
{ "player_id":"player-alpha-1","label":"OBS-Main-Desk","stream_key":"sk_live_9f83a1b2c3d4e5f6","status":"active",
  "ingest_endpoints":{"rtmp":"rtmp://localhost:1935/live/sk_live_9f83a1b2c3d4e5f6","webrtc":"http://localhost:8889/live/sk_live_9f83a1b2c3d4e5f6/whip"},
  "playback_url":"http://localhost:8888/live/sk_live_9f83a1b2c3d4e5f6/index.m3u8","signature":"<64 hex>" }
```
- `generate`: new active key (201); an existing active key is replaced/invalidated.
- `rotate`: invalidate any prior key, issue a new one (or the override), `status: "active"`, 200.
- `revoke`: no key for that player → 404 `STREAM_NOT_FOUND`; else 200 with `status: "revoked"`, `ingest_endpoints: null`, `playback_url: null`. Any later publish/use of a revoked key → **409 `KEY_REVOKED`**.

### 7.4 `POST /audit/v1/costream/session`
Request: `{"session_id":"cs-session-101","host_player_id":"player-alpha-1","participants":["player-alpha-1","player-alpha-2","player-beta-1","player-beta-2"],"layout":"grid_4","simulate_host_drop":true}`

**Checks in exact order:**
1. Schema: `session_id` string, `host_player_id` string, `participants` non-empty array of unique strings, `simulate_host_drop` bool (default false), `layout` optional (default `grid_4`; `solo` | `grid_2` | `grid_4` | `spotlight`) → 400 `VALIDATION_ERROR`.
2. Every participant and the host exist → 404 `PLAYER_NOT_FOUND`. Host not in `participants` → 400 `VALIDATION_ERROR`.
3. `len(participants) > 4` → 409 `COSTREAM_SESSION_FULL`.
4. `solo` with effective active count > 1, or `grid_2` with > 2 → 400 `UNSUPPORTED_LAYOUT`.
5. Handoff:
   - no drop: `active_host = host`, `handoff_occurred = false`, `participant_count = len`, `active_participants = participants`, `status = "active"`.
   - drop and ≥ 2 participants: remove host; `active_host = remaining[0]`, `handoff_occurred = true`, `participant_count = len − 1`, `status = "active"`.
   - drop and 1 participant: `active_host = null`, `handoff_occurred = false`, `participant_count = 0`, `status = "terminated"`.

Response **201** (200 on identical replay):
```json
{ "session_id":"cs-session-101","status":"active","active_host":"player-alpha-2","handoff_occurred":true,"participant_count":3,
  "active_participants":["player-alpha-2","player-beta-1","player-beta-2"],"layout":"grid_4",
  "composite_playback_url":"http://localhost:8888/costream/cs-session-101/index.m3u8","chat_room_id":"chat-cs-session-101","signature":"<64 hex>" }
```
Note: "effective active participant count" for the layout check is the count **after** the handoff rule — decide and document it in an ADR.

### 7.5 QR: `GET /audit/v1/qr/{entity_id}`, exports, `GET /q/{short_code}`
- Each call **increments `scan_count`**, unless `?inspect=true` (read-only; this is what k6 hammers).
- Response 200 (example `match-m1`):
```json
{ "entity_id":"match-m1","entity_type":"match","entity_status":"in_progress","short_url":"http://localhost:8080/q/m1-live",
  "target_route":"/web/matches/match-m1/live","deep_link_uri":"nascon://entity/match-m1","scan_count":1,
  "export_formats":{"svg":"http://localhost:8080/audit/v1/qr/match-m1/export.svg","png":"http://localhost:8080/audit/v1/qr/match-m1/export.png","pdf":"http://localhost:8080/audit/v1/qr/match-m1/export.pdf"},
  "signature":"<64 hex>" }
```
- **`short_url` never changes once generated; `target_route`, the `/q` `Location` header and the signature follow the live state:**

| Entity / state | `target_route` |
|---|---|
| match `upcoming` | `/web/matches/{id}/preview` |
| match `in_progress` | `/web/matches/{id}/live` |
| match `completed` | `/web/matches/{id}/vod` |
| match `postponed` / `cancelled` / `abandoned` | `/web/matches/{id}/notice?state={status}` |
| `player-*` | `/web/players/{id}` |
| `club-*` | `/web/clubs/{id}` |
| `cs-session-*` | `/web/costream/{id}` |

- Unknown `entity_id` (or short code) → 404 `QR_NOT_FOUND`.
- `export.svg`: 200, `image/svg+xml`, body starts `<svg` or `<?xml`, encodes the short_url. `export.png`: 200, `image/png`, 8-byte PNG magic. `export.pdf`: 200, `application/pdf`, starts `%PDF-`, contains the QR poster and the `entity_id`.
- `GET /q/{short_code}`: **302** with `Location` = current target route.

### 7.6 `POST /audit/v1/guest/cart-merge`
Request: `{"guest_token":"guest_anon_tok_7721","registered_user_id":"player-alpha-1","guest_cart":[{"variant_id":"var-jersey-001-L","quantity":1}],"test_write_block":true}`
1. Schema: `guest_token` non-empty, starts with `guest_`; `registered_user_id` string; `guest_cart` 1–10 items (`variant_id` string, integer `quantity ≥ 1`); `test_write_block` bool default true → 400.
2. `registered_user_id` exists → else 404 `PLAYER_NOT_FOUND`; every variant exists → else 404 `VARIANT_NOT_FOUND`.
3. Merged quantity > available stock → 409 `OUT_OF_STOCK` (`details.variant_id`).
4. If `test_write_block`: internally simulate a write with the guest token, confirm the guard returns 403 `GUEST_WRITE_FORBIDDEN`, record `write_block_verified: true`, `write_rejection_code: 403`.
5. Atomically merge into the user's persistent cart (unit price from the catalogue, 450000); `total_items` = sum of quantities.
6. **Identical replay** (same token, user, cart) → **200** with the already-merged cart, no double add, no double reservation. Same token with a different user or payload after merging → **409 `GUEST_TOKEN_ALREADY_MERGED`**.

Response **200**:
```json
{ "guest_token":"guest_anon_tok_7721","write_block_verified":true,"write_rejection_code":403,"cart_merged":true,
  "active_cart":{"user_id":"player-alpha-1","currency":"PKR","total_items":1,"subtotal_minor":450000,
                 "items":[{"variant_id":"var-jersey-001-L","quantity":1,"unit_price_minor":450000}]},
  "signature":"<64 hex>" }
```
**Direct write enforcement:** with `Authorization: Bearer guest_anon_tok_7721`, the grader calls **`POST /api/v1/chat`** (new route), **`POST /audit/v1/checkout`** and **`POST /audit/v1/events`** — all must return **403 `GUEST_WRITE_FORBIDDEN`**. (Without that header, the Day 1 audit routes stay unauthenticated as before.)

### 7.7 `POST /audit/v1/moderation/test`
Request: `{"chat_room_id":"chat-cs-session-101","incoming_messages":[{"message_id","sender","text"},…],"check_dlq":true,"simulate_failed_notifications":0}`

**Rules (deterministic):**
1. Clean → in `filtered_messages` unchanged, `flagged: false`, `reason: null`.
2. Profanity/leetspeak: normalise (`@→a`, `0→o`, `1`/`!→i`, `3→e`, `$→s`, strip `_` `.` `-` `*`), dictionary at minimum: `badword` (incl. `b@d_w0rd`, `bad_word`), `porn` (`p0rn`), `scam` (`sc@m`), `fuck`, `shit`, `bitch`, `asshole`, `idiot_spam`. Replace each offending token **in place** with `***` (e.g. `"Watch this illegal stream *** now!"`); `flagged: true`, `reason: "profanity_leetspeak"`; sender appended to **`kicked_users`** (deduplicated, order of violation).
3. Flood: ≥ 4 consecutive identical characters (case-insensitive, e.g. `AAAA`) **or** ≥ 3 consecutive `!`/`?` → **dropped from `filtered_messages`**, sender appended to **`muted_users`**.
4. DLQ: if `simulate_failed_notifications > 0`, enqueue that many failed events first; report `queue_depth` (0 after reset) and `undelivered_events`.

Response **200**:
```json
{ "chat_room_id":"chat-cs-session-101",
  "filtered_messages":[{"message_id":"msg-1","sender":"user-guest-1","text":"Clean sports commentary","flagged":false,"reason":null},
                       {"message_id":"msg-2","sender":"user-spammer","text":"Watch this illegal stream *** now!","flagged":true,"reason":"profanity_leetspeak"}],
  "kicked_users":["user-spammer"],"muted_users":["user-flooder"],
  "dlq_status":{"queue_depth":0,"undelivered_events":[]},"signature":"<64 hex>" }
```
`flagged_count` (signed, not in the example body) = number of flagged messages; keep it consistent with the response.

### 7.8 `GET /metrics` and `DELETE /audit/v1/privacy/user/{user_id}`
- `/metrics`: 200, `Content-Type: text/plain; version=0.0.4`, valid gauge/counter lines for the 5 metric names in NFR-6.
- Privacy delete 200: `{"user_id":"player-alpha-1","status":"anonymized","pii_retained":false,"tokens_wiped":true}` within 1 s.

---

## 8. Automated QA harness (§6)

### 8.1 Selenium Grid 4 (compose rules)
- `selenium-hub` (ports 4444, 4442, 4443) + **3 nodes**: `node-chrome-1`, `node-chrome-2`, `node-firefox`.
- Each node: `shm_size: "1gb"` (or 2gb), `SE_EVENT_BUS_HOST=selenium-hub`, `SE_EVENT_BUS_PUBLISH_PORT=4442`, `SE_EVENT_BUS_SUBSCRIBE_PORT=4443`, `SE_NODE_MAX_SESSIONS=2`, **`SE_START_VNC=false`**.
- Apple Silicon may use `seleniarm/*`. Either way `GET :4444/status` → `value.ready == true`, ≥ 3 nodes.

### 8.2 Guest Web Player DOM contract (`/web/matches/{id}/live` and `/web/costream/{id}`)
| `data-testid` | Element | Required behaviour |
|---|---|---|
| `guest-video-player` | `<video>`/`<div>` | Visible player rendering the HLS/WebRTC stream |
| `live-score-banner` | `<div>`/`<span>` | Shows e.g. `1 - 0`; **updates within 500 ms without reload** after `POST /audit/v1/events` |
| `pinned-merch-card` | `<div>` | Pinned item `prod-jersey-001` / `var-jersey-001-L` |
| `add-to-guest-cart-btn` | `<button>` | Adds `var-jersey-001-L` qty 1 to the guest cart, increments the count |
| `guest-cart-count` | `<span>` | Integer count (`0` → `1`) |
| `chat-message-list` | `<div>`/`<ul>` | Scrollable chat; masked profanity shows `***` |
| `chat-input-field` | `<input>` | Chat text input |
| `chat-send-btn` | `<button>` | As a guest: write attempt is **blocked (403)** and opens `progressive-auth-modal` |
| `progressive-auth-modal` | `<div>` | Login/register modal that preserves the staged cart |

### 8.3 Required Selenium tests (`tests/selenium/test_guest_grid.py`, `pytest -n 3 tests/selenium/`)
1. Open `http://localhost:8080/q/m1-live` → redirect to `/web/matches/match-m1/live`; `guest-video-player` and `live-score-banner` render **within 3 s**, **no login modal** on first load.
2. Fresh guest types into `chat-input-field`, clicks `chat-send-btn` → message **not** appended; `progressive-auth-modal` visible.
3. Click `add-to-guest-cart-btn` → `guest-cart-count` = `1`; post a score event → `live-score-banner` updates **within 500 ms**.

### 8.4 Appium 2 and deep links (§6.3)
- Appium 2 on `http://localhost:4723` with `uiautomator2`; `/status` → `ready: true`.
- `AndroidManifest.xml` intent filter: `VIEW` action, `DEFAULT` + `BROWSABLE` categories, `<data android:scheme="nascon" />`.
- The runner fires `adb shell am start -W -a android.intent.action.VIEW -d "nascon://entity/match-m1"` and `-d "nascon://stream/cs-session-101"`: the app must be in the foreground **within 2 s** on the Match Live / Co-Stream screen, **no crash, no stop at login**.
- `tests/appium/test_mobile_deeplink.py` plus ≥ 1 **cross-surface** test: the app joins `cs-session-101` via Appium while a Selenium session on `/web/costream/cs-session-101` verifies synchronized chat **within 3.0 s**.

### 8.5 k6 (`tests/k6_load.js`, NFR-2)
Commit the spec's exact profile: scenarios `guest_viewers` (constant-vus **500**, 15 s, `viewStream` → `GET /audit/v1/qr/match-m1?inspect=true`, checks 200 + `target_route`) and `chat_posters` (constant-vus **50**, 15 s, `postChat` → `POST /audit/v1/moderation/test` with one clean message, `check_dlq: false`, accepts 200/201); thresholds `http_req_failed: ['rate==0.00']`, `http_req_duration: ['p(95)<800']`. The grader runs `k6 run --summary-export=tests/reports/k6-summary.json tests/k6_load.js`. `/audit/v1/*` stays exempt from the rate limiter.

### 8.6 Multi-laptop layout (§6.5, desk check only)
- Laptop 1: compose stack (Postgres, Redis, MinIO, media server, API — ports 8080, 1935, 8888, 8889).
- Laptop 2: phone over USB + Appium 2 on 4723.
- Laptop 3: Selenium hub + 3 nodes (4444) + k6, pointed at Laptop 1's LAN IP (or `ssh -L 8080:localhost:8080`).
- **The committed `docker-compose.yml` must still contain the whole stack**, including the hub and 3 nodes, for the single-runner autograder.

---

## 9. Hidden complexity scenarios (graded + viva)
1. **Host abrupt disconnect:** `participants[1]` becomes `active_host`, `handoff_occurred: true`, count 3, composite URL alive, **same `chat_room_id`**, zero zombie processes.
2. **QR target mutation after printing:** `match-m1` moves `in_progress` → `completed` (via `match_end`) or `postponed`; `GET /audit/v1/qr/match-m1` returns the **same `short_url`**, an updated `target_route` (`…/vod` or `…/notice?state=postponed`) and a **recomputed signature**.
3. **Dual-moderator race:** 10 simultaneous `POST /audit/v1/moderation/test` (plus concurrent mutes) on `user-spammer` → no deadlock/500, `kicked_users` exactly `["user-spammer"]`, DLQ counters intact.
4. **Network migration during cart merge:** the same merge sent twice → second call **200** with `total_items: 1` (never 2), no double reservation.

---

## 10. Scoring (§7)
- **80% backend + automated QA:** all `/audit/v1/*` contracts and DAY2 signatures, media pipeline, co-stream handoff, QR routing + exports, guest 403 guard, cart merge, moderation + DLQ, `/metrics`, NFR-1, NFR-2 (k6), Selenium Grid orchestration, backend viva.
- **20% frontend:** Guest Web Player (`/web/*`), overlays, WCAG 2.1 AA, progressive auth modal, mobile broadcaster/co-stream UI, QR scanner, `nascon://` intent handling via Appium, frontend/HCI viva.
- Per module: hidden vectors (all assertions must hold) + unit coverage ≥ 85% via `COVERAGE_DAY2.json` (`streaming`, `costream`, `qr_guest`, `moderation_dlq`, `observability`).

---

## 11. Error codes added in Part II (Appendix B; all Part I codes remain)
| HTTP | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Bad JSON, missing field, invalid action, host not in participants (`details.fields`) |
| 400 | `UNSUPPORTED_LAYOUT` | Layout can't fit the active participant count |
| 401 | `UNAUTHENTICATED` | Missing/malformed/expired/tampered JWT on protected routes |
| 403 | `GUEST_WRITE_FORBIDDEN` | `guest_anon_tok_*` attempting any write |
| 403 | `FORBIDDEN` | Member outside their 5-tier RBAC scope |
| 404 | `PLAYER_NOT_FOUND` | Unknown `player_id` / `registered_user_id` |
| 404 | `STREAM_NOT_FOUND` | Unknown stream key or session |
| 404 | `QR_NOT_FOUND` | No QR mapping for the entity or short code |
| 404 | `VARIANT_NOT_FOUND` | Unknown variant in `guest_cart` |
| 409 | `COSTREAM_SESSION_FULL` | More than 4 participants |
| 409 | `KEY_REVOKED` | Ingest/playback with a revoked key |
| 409 | `GUEST_TOKEN_ALREADY_MERGED` | Merged token reused with another user or payload |
| 409 | `OUT_OF_STOCK` | Merge/checkout quantity exceeds stock |
| 413 | `PAYLOAD_TOO_LARGE` | Body > 1 MB |
| 429 | `RATE_LIMITED` | `/api/v1/*` limit (100 req / 10 s) or chat flood threshold |
