# Architecture Decision Records

## ADR-1: Python 3.12 + FastAPI for the backend

**Context**
- The grader recomputes HMAC signatures with Python's `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
- Every request must finish within 5 s.

**Decision**
- Use FastAPI on `python:3.12-slim`, served by uvicorn with 2 workers.
- Write sync handlers that run in FastAPI's threadpool.

**Consequences**
- Canonical JSON matches the grader byte for byte, because both use the same serializer.
- Shared state must live in Postgres or Redis, because there are two worker processes.

**Alternatives**
- Node/NestJS: its canonical-JSON number and Unicode rules differ from Python's.
- Spring: slower to build within the 10-minute limit.

## ADR-2: PostgreSQL 16 as the single source of truth

**Context**
- We need an append-only event log, an immutable roster audit trail, and atomic stock reservation.

**Decision**
- Postgres holds every domain table.
- Events, orders, order status and audit entries are insert-only.
- Signed payloads are stored as canonical **TEXT**, not `jsonb`, because `jsonb` would reorder keys.

**Consequences**
- Replays and signatures stay byte-stable.
- Row locks give us concurrency control.

**Alternatives**
- MongoDB: weaker multi-row transactions.
- `jsonb` columns: break signature reproduction.

## ADR-3: Event-sourced scoring with projection on read

**Context**
- FR-1.1 requires scores to be computed from an append-only stream.
- Corrections must be compensating events.

**Decision**
- `GET /score` and `/standings` rebuild the score from the full event log on every call. `domain/scoring.project()` is a pure function.
- A compensation is a new signed event. The projection treats the compensated event and the compensation as neutral.

**Consequences**
- There are no counters to drift.
- Edge case 5 (a correction after qualification) is just a recompute.
- Cost: O(events) per read, which is fine at this scale.

**Alternatives**
- Mutable score columns: forbidden by the spec.
- Snapshots: not needed yet.

## ADR-4: Sports are data, never code

**Context**
- A "mystery sport" must work at grading time with no code change.
- Any branch on a sport or event name costs -8.

**Decision**
- Seed sports live in `backend/app/seed/sports.json`.
- Domain code reads only `scoring_model` (event, innings or round) and config values such as points, runs, legal_ball, wicket, rounds, best_of and draw_allowed.

**Consequences**
- `POST /audit/v1/sports` makes a sport usable immediately, with no restart.
- No sport or event literal appears in `backend/app/**/*.py`.

**Alternatives**
- Per-sport strategy classes: they hard-code names.

## ADR-5: Oversell-proof checkout with a conditional UPDATE inside one transaction

**Context**
- NFR-3: 20 simultaneous buyers try to buy the last unit. Exactly one may succeed, and stock may never go negative.

**Decision**
- One transaction does the following:
  1. Takes an advisory lock on `order_id` (for idempotent replay).
  2. Runs `UPDATE inventory SET stock = stock - q, reserved = reserved + q WHERE variant_id = v AND stock >= q`, in `variant_id` order.
  3. Calls the mock gateway.
  4. Commits, or rolls back on a decline or capture failure.
- A `CHECK (stock >= 0)` constraint is the last line of defence.

**Consequences**
- Losing requests get 409 `OUT_OF_STOCK` immediately.
- Released stock can be bought again.
- `reserved` is 0 whenever no request is in flight.

**Alternatives**
- Redis `DECR`: two sources of truth.
- `SERIALIZABLE` with retries: slower under a burst.

## ADR-6: Redis 7 for the rate limit, the internal queue and realtime

**Context**
- We need a rolling 100 req/10 s limit per IP on `/api/v1/*`, a structured domain-event queue, and live updates to clients.
- The grader has 8 GB of RAM.

**Decision**
- **Rate limit:** an atomic Lua sliding window that sets `Retry-After`.
- **Queue:** a Redis Stream `domain-events`, consumed by the `worker` service through a consumer group.
- **Realtime:** pub/sub fan-out to WebSocket `/api/v1/ws`.

**Consequences**
- One small container covers three needs.
- Limiter failures fail open, so they never take the API down.

**Alternatives**
- RabbitMQ or NATS: approved, but each is an extra service and uses more RAM.

## ADR-7: Custom HS256 JWT with policy-as-code RBAC

**Context**
- We need five roles, absolute tenant isolation, and negative tests for every boundary.
- Tokens using `alg:none`, a tampered signature or an expired time must return 401.

**Decision**
- PyJWT HS256 with the signature verified and `algorithms=["HS256"]` pinned.
- `auth/policy.py` holds a single table mapping `(action, role)` to a rule. The rules are `own_league`, `own_club`, `self` and `same_tenant`.
- The tenant check runs before every non-admin rule.

**Consequences**
- The matrix is one readable table, with each cell unit-tested in `tests/unit/test_rbac_policy.py`.
- Cross-tenant access returns 403. Only ids that don't exist return 404.

**Alternatives**
- Keycloak: heavy to self-host within the 10-minute and 8 GB limits.

## ADR-8: Flutter Android app, offline-first, using the server's sync contract

**Context**
- NFR-4: cached reads and a persistent offline queue that survives a force-close and syncs with per-action conflict results.

**Decision**
- Flutter with Riverpod, sqflite (cache and the `pending_actions` queue) and flutter_secure_storage (Android Keystore).
- Queued items use the exact `/offline-sync` action format.
- `/api/v1/sync` and `/audit/v1/offline-sync` share one server code path.

**Consequences**
- The script-graded and desk-checked sync behaviour can't diverge.
- Conflict resolution is server-wins, with plain-language reasons in the UI.

**Alternatives**
- Firebase or Supabase offline sync: prohibited.
- Native Kotlin: the team knows Flutter better.

## ADR-9: MediaMTX as the self-hosted media server

**Context**
- FR-3.2 needs RTMP/WHIP ingest, HLS and WebRTC playback, and recording, on a self-hosted server (MediaMTX, LiveKit or SRS).
- Ingest must be authenticated by a stream key, and a revoke or rotate must cut the publisher within 2 s.

**Decision**
- Run `bluenviron/mediamtx:1.9.1` with RTMP on 1935, HLS on 8888 and WebRTC (WHIP/WHEP) on 8889. RTSP and SRT are off.
- `authMethod: http` points at `POST /internal/media/auth`. Only an active, non-revoked key may publish on `live/<key>`.
- A revoke or rotate commits first, then calls the MediaMTX control API (`/v3/.../kick/{id}`) to drop the publisher.
- Every path records to the shared `recordings` volume. The MediaMTX image has no shell or curl, so the worker watches that volume instead of a `runOnRecordSegmentComplete` hook. A segment idle for 3 s is uploaded to the MinIO `vods` bucket and indexed with `repo/athletes.index_recording`.

**Consequences**
- One small container covers all three protocols, and the image is pinned and already pulled.
- The key check stays in our API, so a revoked key is refused on the next publish attempt as well as kicked.
- A VOD appears on the athlete profile about 3 to 4 s after the stream ends.

**Alternatives**
- LiveKit: a full SFU, but it needs more services and a token server.
- SRS: no WHIP/WHEP in the version we had pulled.

## ADR-10: Postgres stays the source of truth for Part II state

**Context**
- Part II adds stream keys, co-stream sessions, QR mappings and scans, guest tokens and carts, follows, chat messages, VODs and the DLQ.

**Decision**
- Every one of these is a Postgres table, created at boot and truncated by `/audit/v1/reset`.
- Redis holds only derived or short-lived data: pub/sub fan-out, chat sequence counters, rate-limit windows, the WebSocket gauge and the QR inspect cache.

**Consequences**
- State survives an API or Redis restart, and every audit route reads the same rows the app does.
- A Redis flush loses nothing but caches and counters that are rebuilt on the next request.

**Alternatives**
- Keep chat and keys in Redis only: faster, but lost on restart and hard to audit.

## ADR-11: Follower count is derived, never stored

**Context**
- FR-3.1 needs zero follower-count drift under simultaneous follow/unfollow toggles, idempotent per `(follower_id, athlete_id)`.

**Decision**
- A `follows` table with `PRIMARY KEY (follower_id, athlete_id)`.
- Follow is `INSERT ... ON CONFLICT DO NOTHING`; unfollow is `DELETE`. The count is `COUNT(*)`, read after the write in the same transaction.
- The privacy delete removes the erased user's follow edges.

**Consequences**
- There is no counter to drift. Ten parallel follows by the same user still give exactly one row.

**Alternatives**
- A `follower_count` column with `+1`/`-1`: a retried or duplicated toggle drifts it.

## ADR-12: Guest tokens are a separate principal, rejected for writes before routing

**Context**
- FR-4.2 and FR-4.3: a `guest_anon_tok_*` bearer may read and stage a guest cart, but every write must get 403 `GUEST_WRITE_FORBIDDEN`. Hiding buttons in the UI scores 0.

**Decision**
- A pure-ASGI check in `main.py` runs before routing, validation and the rate limiter. Any `POST/PUT/PATCH/DELETE` with a `Bearer guest_*` token is rejected with 403 `GUEST_WRITE_FORBIDDEN` and `details.guest_token`.
- It covers all of `/api/v1/*` (except `/api/v1/guest/*`, which issues tokens) and the audit writes `/audit/v1/checkout`, `/audit/v1/events`, `/audit/v1/roster/transfer` and `/audit/v1/offline-sync`.
- Read routes the Guest Web Player needs (`GET /api/v1/matches/{id}`, `/athletes/{id}`, `/chat`) accept a guest or no bearer.

**Consequences**
- A new write route is guarded automatically. Nobody can forget the check on one handler.
- The cart-merge audit route exercises this same guard to report `write_rejection_code: 403`.

**Alternatives**
- A FastAPI dependency per route: easy to miss on a new route, and it runs after body validation, so a bad body would give 400 instead of 403.

## ADR-13: The QR short URL is immutable; the target is computed on every read

**Context**
- FR-4.1 and hidden scenario 2: a printed QR must keep working after the match moves from `in_progress` to `completed` or `postponed`.
- NFR-2 sends 500 viewers at `GET /audit/v1/qr/match-m1?inspect=true` for 15 s.

**Decision**
- `qr_codes` stores only `entity_id`, a stable `short_code` and the scan count. `target_route` and the signature are computed from the live event projection on each read (`domain/qr.py`).
- `GET /q/{code}` answers 302 to the live route. Exports are SVG and PNG from `segno` and a PDF poster from `reportlab`.
- `?inspect=true` responses are cached in Redis for 1.5 s. Any event, scan or co-stream change for that entity deletes the cache key.
- Telemetry stores only device family and a UTC hour bucket (NFR-9).

**Consequences**
- Scenario 2 needs no migration: the same short URL now resolves to `/vod` or `/notice?state=postponed`, with a recomputed signature.
- k6 p95 stays well under 800 ms because most inspect reads never reach Postgres.

**Alternatives**
- Store the target route: it goes stale the moment the match status changes.

## ADR-14: Moderation is a pure function; kick and mute writes are idempotent

**Context**
- FR-5.3 and hidden scenario 3: 10 simultaneous moderation calls on `user-spammer` must not deadlock or duplicate the kick list.

**Decision**
- `domain/moderation.py` normalises leetspeak, masks dictionary words, and applies the flood and rate rules with no I/O. Precedence is in ADR-18.
- Kick and mute rows go into `moderation_actions` with `PRIMARY KEY (chat_room_id, user_id, kind)` and `ON CONFLICT DO NOTHING`.

**Consequences**
- Results are deterministic and unit-tested for every dictionary word. Concurrent requests converge on `["user-spammer"]`.

**Alternatives**
- Read-modify-write a JSON list: races under concurrency.

## ADR-15: Notifications retry with bounded backoff, then a persistent DLQ

**Context**
- FR-5.2: a failed delivery gets bounded exponential retry, at most 3 attempts, then a DLQ that the audit contract can inspect.

**Decision**
- `domain/notify.py` delivers with 3 attempts and exponential backoff (100 ms, then 200 ms), with the sleep injected so tests take no time.
- After the last failure the event is written to the `dlq` table. `nascon_dlq_depth` and `dlq_status.queue_depth` both read that table.

**Consequences**
- The DLQ survives restarts and is cleared only by `/audit/v1/reset`.

**Alternatives**
- A Redis list: lost on flush, and it would need a second counter for the metric.

## ADR-16: `/metrics` is a small pure formatter, not a client library

**Context**
- NFR-6 needs `GET /metrics` as `text/plain; version=0.0.4` with five named metrics. The API runs 4 uvicorn processes, so in-process counters would be split across workers.

**Decision**
- `services/metrics.py` renders HELP, TYPE and one sample per metric from values read at request time. WebSocket connections come from a Redis gauge, streams and bitrate from the MediaMTX API, the DLQ depth and QR scans from Postgres.
- Missing values export as 0, negative gauges clamp to 0, and NaN or infinity is never exported.

**Consequences**
- Every worker returns the same numbers, and the formatter is fully unit-tested.

**Alternatives**
- `prometheus_client` with in-process collectors: each worker would report only its own connections unless multiprocess mode is set up.

## ADR-17: Co-stream layout capacity is checked after the host-drop handoff

**Context**
- Spec 5.5 step 4 rejects `solo` with more than 1 and `grid_2` with more than 2 "effective active" participants, and asks teams to decide and document which count that is.

**Decision**
- The count is taken **after** the handoff rule (step 5). A host drop that leaves 2 broadcasters on `grid_2`, or 1 on `solo`, is valid; the layout must fit who is actually on screen.
- `COSTREAM_SESSION_FULL` (step 3) still counts the requested participants, so 5 people are rejected even if a drop would leave 4.

**Consequences**
- The composite stream never shows an empty tile for a host who already left.
- `domain/costream.plan_session` computes the handoff before the layout check; `tests/unit/test_costream.py::test_layout_capacity_uses_count_after_handoff` pins every case.

**Alternatives**
- Count before the handoff: would reject a valid 3-person `grid_2` session whose host dropped.

## ADR-18: Moderation precedence and leetspeak ambiguity

**Context**
- Spec 5.8 defines profanity masking, flood muting and a rate rule, but not what happens when one message triggers several, and `!` is both a leet `i` and punctuation ("s!c@m" vs "now!").

**Decision**
- One rule per message, in this order: rate limit (> 3 messages in 2 s, only when messages carry `sent_at`), then flood, then profanity. Rate and flood drop the message and mute the sender; profanity masks and kicks.
- A token is profane if any reading matches the dictionary: `!` as `i`, `!` removed, or `1` as `l`. Plain punctuation around a masked token is kept ("sc@m," becomes "***,").
- `flagged_count` counts flagged messages in `filtered_messages`; dropped messages are reported through `muted_users`.
- The dictionary is data (`seed/moderation_words.json`), not code.

**Consequences**
- A flood message is never broadcast, even if it is also profane, so muting is the stronger and sufficient sanction.
- Kick and mute lists are built in first-violation order with set semantics, so 10 identical requests still give `["user-spammer"]` (edge case 3).

**Alternatives**
- Apply every rule: a dropped message would also count as flagged, making `flagged_count` disagree with the body.
