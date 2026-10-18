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
