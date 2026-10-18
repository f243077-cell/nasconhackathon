# AGREED_RULES.md (Part II): Architecture, API Rules, Folder Structure and Workflow

These decisions **extend** `../AGREED_RULES.md` (Part I). Everything there still applies (layers, error helper, validation style, idempotency storage, git rules) unless changed here. If anything here conflicts with `CLAUDE.md` (this folder), **`CLAUDE.md` wins**.

---

## 1. Architecture (additions)

```
  Native app (Flutter)        Guest browser (/web/*)        Grader / GitHub Actions / k6 / Selenium / Appium
        |  /api/v1/*, WS            |  /web/*, /q/*, WS              |  /audit/v1/*, /metrics, :4444, :4723
        v                           v                                v
  +-------------------------------------------------------------------------------+
  | api (FastAPI, 8080)  routes/ (thin) -> domain/ (pure) -> repo/ (SQL)          |
  |   new: stream_keys, costream, qr, guest, moderation, notify(DLQ), metrics,    |
  |        privacy, follows, chat, web (Guest Web Player static + templates)      |
  +-----+-------------+--------------+---------------+-----------------------------+
        |             |              |               |
   PostgreSQL 16   Redis 7        MinIO          MediaMTX (bluenviron/mediamtx)
   (truth: keys,   (pub/sub WS,   (receipts,     RTMP 1935 · HLS 8888 · WebRTC 8889
    sessions, QR,   chat seq,      VOD files)     auth hook -> api (stream-key check)
    carts, DLQ,     rate windows,                 control API used to kick revoked publishers
    follows, chat)  retry queue)
        worker: domain-events + notification retries (3 attempts, exp. backoff) -> DLQ table
  Selenium Grid 4: selenium-hub (4444/4442/4443) + node-chrome-1 + node-chrome-2 + node-firefox
```

| ADR | Decision | Why |
|---|---|---|
| ADR-9 | **MediaMTX** as the media server (RTMP 1935, HLS 8888, WebRTC WHIP/WHEP 8889). Its HTTP auth hook calls our API to accept/reject a publish by stream key; revoke/rotate uses its control API to **kick the publisher within 2 s**. | Single small container, all 3 protocols, image already pulled (`1.9.1`). Approved list allows MediaMTX / LiveKit / SRS. |
| ADR-10 | **Postgres stays the source of truth** for keys, co-stream sessions, QR mappings, guest tokens, carts, follows, chat messages and the DLQ. Redis only for pub/sub fan-out, chat sequence counters and sliding windows. | Same reasoning as ADR-2; survives restarts; easy audit. |
| ADR-11 | **Follower count is derived** (`COUNT(*)` on a `follows` table with `UNIQUE(follower_id, athlete_id)`; toggle = `INSERT … ON CONFLICT DO NOTHING` / `DELETE`). | Zero drift under concurrent toggles; idempotent per pair. |
| ADR-12 | **Guest tokens are a separate principal type.** A single auth dependency recognises `guest_anon_tok_*` bearers and rejects every write with 403 `GUEST_WRITE_FORBIDDEN` **before** any other check, on `/api/v1/*` and on the audit write routes (`/audit/v1/checkout`, `/audit/v1/events`). | Server-side boundary is graded; UI hiding scores 0. |
| ADR-13 | **QR short URL is immutable; target route is computed at read time** from the live entity state (match status from the event projection). Exports: SVG + PNG from a pure-Python QR library, PDF poster with reportlab. | Edge case 2 (post-print mutation) falls out naturally; no stored route to go stale. |
| ADR-14 | **Moderation is a pure domain function** (normalise → dictionary match → mask; flood regexes) and kick/mute sets are written with `INSERT … ON CONFLICT DO NOTHING` keyed by `(room, user)`. | Deterministic, unit-testable, and the 10-thread race (edge case 3) can't duplicate or deadlock. |
| ADR-15 | **Notifications:** worker retries with exponential backoff, max 3 attempts, then a persistent `dlq` row; `nascon_dlq_depth` reads the table. | FR-5.2 + NFR-6. |
| ADR-16 | **Observability** with `prometheus_client`; gauges updated from the WS hub, stream registry, DLQ and QR scan counter; served at `/metrics` as `text/plain; version=0.0.4`. | NFR-6 exact format. |

### Compose additions (to the Part I file)
| Service | Image | Notes |
|---|---|---|
| `mediamtx` | `bluenviron/mediamtx:1.9.1` | Ports `1935:1935`, `8888:8888`, `8889:8889` (+ WebRTC UDP as needed). Config file mounted from repo (`media/mediamtx.yml`): auth hook URL → `http://api:8080/internal/media/auth`, HLS on, recording path → shared volume. |
| `selenium-hub` | `selenium/hub:4.25.0` (fallback `4.24.0`, see Docker log) | Ports 4444, 4442, 4443. `container_name: nascon-selenium-hub` allowed. |
| `node-chrome-1`, `node-chrome-2`, `node-firefox` | `selenium/node-chrome` / `selenium/node-firefox`, same tag as hub | `shm_size: "1gb"`, event-bus env, `SE_NODE_MAX_SESSIONS=2`, `SE_START_VNC=false`. |
| `api`, `worker` | existing build | Add `DAY2_SALT: ${DAY2_SALT}`, `MEDIAMTX_API`, `PUBLIC_BASE_URL=http://localhost:8080`. |

**Rules:**
- Appium 2 is **not** in compose — it runs on the host of the laptop with the phone (port 4723).
- Running services must not need the internet: vendor the guest player's JS (e.g. hls.js) into the repo; no CDN links in `/web/*`.
- `/health` = DB + Redis + MediaMTX reachable + seed present.
- RAM budget on the grader (8 GB): Selenium nodes are the heaviest; keep API workers at 2.

---

## 2. Folder structure (additions)

```
/
├── COVERAGE_DAY2.json                 # streaming, costream, qr_guest, moderation_dlq, observability
├── .github/workflows/autograde.yml    # contract probes + grid status + k6 smoke on push to main
├── media/mediamtx.yml                 # media server config (auth hook, HLS, recording)
├── backend/app/
│   ├── domain/
│   │   ├── streaming.py     # key format, state machine generate/rotate/revoke, sig payload   (Tanzeel)
│   │   ├── costream.py      # validation order, layout capacity, host-drop handoff             (Gunee)
│   │   ├── qr.py            # target_route from entity + state, short-code rules               (Gunee)
│   │   ├── guest_cart.py    # merge math, stock cap, replay/merged-token rules                 (Gunee)
│   │   └── moderation.py    # leetspeak normalise, mask, flood + rate rules                    (Gunee)
│   ├── repo/                # stream_keys, costream, qr, guest, moderation, dlq, follows, chat, privacy (Tanzeel)
│   ├── routes/
│   │   ├── audit_day2.py    # all /audit/v1 Part II endpoints + /q/{code} + /metrics           (Tanzeel)
│   │   ├── web.py           # serves /web/* pages                                               (Tanzeel)
│   │   └── ws.py            # + /ws/matches/{match_id}, chat rooms                              (Tanzeel)
│   ├── services/            # mediamtx client, qr export (svg/png/pdf), notify + retry, metrics (Tanzeel)
│   └── web/                 # Guest Web Player: HTML/CSS/JS + vendored hls.js                   (Huzaifa)
├── tests/
│   ├── unit/                # + test_streaming.py, test_costream.py, test_qr.py, test_guest_cart.py, test_moderation.py
│   ├── selenium/test_guest_grid.py        # 3 required tests, pytest -n 3                        (Gunee)
│   ├── appium/test_mobile_deeplink.py     # deep links + cross-surface chat                      (Huzaifa)
│   ├── k6_load.js                          # exact spec profile                                   (Tanzeel)
│   └── reports/                            # selenium-report.xml, appium-report.xml, k6-summary.json
└── mobile/                  # + intent filter nascon://, QR scanner, broadcaster + co-stream UI      (Huzaifa)
```

---

## 3. Agreed backend coding rules (additions)

### 3.1 Signatures
- `canonical.py` gets `sign_day2(entity_id, payload)` using `config.DAY2_SALT`. Separator is **`|`**. One unit test per endpoint's exact sig payload (§6 of CLAUDE.md), plus the two reference vectors pinned.
- Build the sig payload **from the response values** you return (e.g. QR uses the *current* `target_route`).

### 3.2 Validation order on every new route
400 schema → 404 existence → **403 permission (guest/RBAC)** → 409 business rule. Co-stream and cart-merge follow their own numbered check lists exactly (CLAUDE.md §7.4, §7.6).

### 3.3 Guest boundary
- One dependency `principal_or_guest()`: returns a member principal, a guest principal (`guest_anon_tok_*` that exists, is valid and not wiped), or none.
- **Any write with a guest principal → 403 `GUEST_WRITE_FORBIDDEN`, `details.guest_token`**, evaluated first. Applies to `POST /api/v1/chat`, follow, checkout (`/api/v1` and `/audit/v1`), events (`/api/v1` and `/audit/v1`), roster.
- Audit routes stay unauthenticated when **no** Authorization header is sent (Day 1 contract unchanged).

### 3.4 Idempotency / concurrency
- Co-stream: store canonical request per `session_id`; identical replay → 200 stored body.
- Cart merge: one row per `guest_token` with the canonical request and merged result; lock the token row `FOR UPDATE`; identical replay → 200, different → 409 `GUEST_TOKEN_ALREADY_MERGED`. Stock check against `inventory.stock` (no reservation in the merge itself).
- Moderation kicks/mutes: unique `(chat_room_id, user_id, kind)`; return lists in first-violation order; no `SELECT … FOR UPDATE` chains → no deadlock under 10 threads.
- QR scan count: `UPDATE … SET scan_count = scan_count + 1 … RETURNING` (atomic); `?inspect=true` never writes.

### 3.5 Real-time
- `/ws/matches/{match_id}` and SSE `/api/v1/matches/{match_id}/stream` both fed by the existing Redis pub/sub; publish **after** the event commit. Target p95 < 500 ms with 25 clients.
- Chat: `chat-{session_id}` rooms, sequence from Redis `INCR`, persisted to Postgres.

### 3.6 Privacy
- QR telemetry table holds only `(entity_id, device_family, hour_bucket, count)`. Never store IP, full UA or cookies.
- `DELETE /audit/v1/privacy/user/{id}` nulls PII columns, deletes/expires linked guest and viewer tokens in one transaction (< 1 s).

### 3.7 No hard-coded sport logic (still −8)
QR state routing reads the **match status**, never sport names. Moderation dictionary lives in a data file (`seed/moderation_words.json`).

---

## 4. Mobile ↔ backend additions (`/api/v1/*`)

| Method + path | Purpose |
|---|---|
| `POST /api/v1/stream/key` | Member wrapper of the audit stream-key logic (own player only) |
| `POST /api/v1/costream/sessions`, `POST …/{id}/invite`, `…/mute`, `…/kick`, `…/spotlight` | Host controls |
| `GET /api/v1/athletes/{player_id}` | Profile: career records, clubs, upcoming fixtures, VODs, follower count |
| `POST /api/v1/athletes/{player_id}/follow` / `DELETE` | Idempotent follow toggle |
| `POST /api/v1/chat` | Post to a room (guest → 403 `GUEST_WRITE_FORBIDDEN`) |
| `POST /api/v1/guest/token` | Issue `guest_anon_tok_*` for a Guest Web Player session |
| `GET/POST /api/v1/cart` | Member persistent cart; merge on login |
| `WS /ws/matches/{match_id}`, `GET /api/v1/matches/{id}/stream` (SSE) | Live score + overlay metadata |

**Deep links:** `nascon://entity/{entity_id}` and `nascon://stream/{session_id}` open the Match Live / Co-Stream screen **without stopping at login** (use the stored token, or open in read-only guest mode).

---

## 5. Git workflow (Day 2)
1. **Start from the locked Day 1 commit.** `git pull --rebase` on top of the Day 1 SHA; never re-init, never force push.
2. Push windows: **W1 10:15–11:30, W2 11:30–12:45, W3 12:45–13:45, W4 13:45–14:00**; grace **14:05:00**. Everyone pushes at least once per window; Tanzeel checks GitHub at the mid-point of each.
3. Code freeze 14:00:00, final push by 14:04, hard lock 14:05:00.
4. `.env` holds `DAY1_SALT` and `DAY2_SALT` locally; `.env.example` lists both with placeholder values. Never commit either salt.
5. Before the final push: `run_tests.sh` (writes `COVERAGE.json` **and** `COVERAGE_DAY2.json`), `tools/conformance.py` (Day 1 regression), the Day 2 probes, the sport-name grep, and commit `tests/reports/*`.
6. **Uncommitted local work from the night before** (multi-tenant routes in `backend/app/routes/api_v1.py`, `auth/policy.py`, `tests/unit/test_rbac_policy.py`, `tools/seed_psl.py`, `tools/tenancy_check.py`, and the temporary `mobile/` build edits) — decide at 10:15 whether to commit the multi-tenant work; **never commit the temporary mobile build edits**.
