# CLAUDE.md: NaSCon '26 App Dev Competition (shared team file)

Team: **Tanzeel** (Docker + Android emulator), **Gunee** (Flutter, no Docker, no emulator), **Huzaifa** (Flutter UI, no Docker, no emulator).

This file lists **every constraint and rule** from the two official documents. Read it before writing any code.
- `NaSCon 26 App Dev Part 1-1.pdf`: the Part I spec. It is the **binding API contract**: "If any verbal statement conflicts with this document, this document wins."
- `Official_Participant_Rules_Booklet.pdf`: logistics, the Docker bundle and the GitHub rules.

Companion files:
- `AGREED_RULES.md`: the architecture, folder structure, API conventions and git workflow the team agreed on. Follow it.
- `DISTRIBUTION.md`: who owns what, the timeline and the handoffs.
- `DOCKER_SETUP_LOG.md`: which images are pulled locally, the MinIO problem and the cache hash.

> Spec footer: *"If your code works on the first try, check again. It's probably the wrong problem. Understanding The Problem Is Also Part Of The Problem."* Field names, status codes and error codes are compared **literally** by scripts. Copy them character by character from this file or the spec.

---

## 0. Conflicts between the two documents (resolved)

| Topic | Booklet says | Part I spec says | We follow |
|---|---|---|---|
| Repo visibility | Private, invite `nascon-eval-26` | **Public** (grader clones without credentials); register the URL at the venue desk **before 11:15 AM** | **Public** repo AND invite `nascon-eval-26` (harmless). Confirm at check-in. |
| Grading machine | GitHub Actions `ubuntu-latest`, 16 GB RAM | Organizer machine: **Ubuntu 22.04, 4 vCPU, 8 GB RAM**, Docker Engine 24+, Compose v2, Python 3.11 | Design for the stricter case: **8 GB / 4 vCPU**. |
| Push rule | Push at least once per hour, -2 per miss | Push in each window: **10:45–11:45, 11:45–12:45, 12:45–13:45, 13:45–14:45**, -2 each (max -8) | The spec windows. They also satisfy "hourly". |
| Push deadline | 03:05:00 PM PKT | **15:05:00 PKT**. The grader checks out the last commit pushed at or before this time. | Aim for the final push **by 14:55**. |
| Day 1 points | 40 | 50 | Irrelevant. Maximise both. |
| Tie-breakers | Day 2 objective score, then vectors passed, then earliest Day 2 push | Higher backend score, then fewer penalties, then earlier final push | Both apply in their own context. |
| Object store image | `minio/minio:RELEASE.2024-09-22T00-33-43Z` | MinIO is approved | That image **no longer exists on Docker Hub**. Use `bitnamilegacy/minio:2024.9.22` (pulled and health-checked locally). See `DOCKER_SETUP_LOG.md`. |

---

## 1. Schedule and integrity rules

**Day 1, Sat Oct 17 (Part I, 50 pts)**
- 10:00–10:44: check-in and empty-repository check. **At 10:40 the repo must have zero commits.**
- 10:45: the sprint starts. **All scaffolding, Dockerfiles and source code must be committed after 10:45.** Nothing may be copied in from a pre-built repo.
- Before 11:15: register the public repo URL with the volunteer at the venue desk.
- Push windows (at least 1 pushed commit in each, GitHub push time): 10:45–11:45, 11:45–12:45, 12:45–13:45, 13:45–14:45.
- 15:00: Phase I is locked. **15:05:00 PKT is the final push deadline.** Later pushes, local files, stashes and anything not committed are ignored.
- 15:05–15:30: cloud autograder audit.
- From 15:15: judge desk check. Each team gets one 10-minute slot. **The backend must be running and the app installed.** A team that isn't ready goes to the end of the queue once. If it still isn't ready, the offline and UI/HCI parts score 0.
- Questions about how to read the contract must go **in writing before 13:00 PKT**.
- Score appeals must be filed within 30 minutes of the results.

**Between Day 1 15:05 and Day 2 10:15: NO pushes.**

**Day 2, Sun Oct 18 (Part II, 45 objective + 15 viva)**
- 10:00–10:14: commit verification. 10:15–14:00: sprint 2. 14:05:00: push deadline. 14:05–14:25: audit. 14:30–15:50: top-8 viva.
- The Day 2 history must **continue directly from the locked Day 1 commit SHA**. No rebase, no force push and no history rewrite, ever.
- The viva includes a 5-minute live code mutation, 2 hidden complexity scenarios, a defence of **8 short ADRs in `ADR.md`**, and a defence of `TRACEABILITY.md`.
- The Part II scope is secret until 10:15 Day 2. The pulled decoy and Phase II images include nats, mediamtx, livekit, ntfy, prometheus, grafana, k6 and selenium. **This is a guess:** Day 2 may involve streaming, notifications, monitoring or QA automation. Keep the architecture modular.

**Other rules**
- AI tools are allowed.
- **Prohibited:** Firebase, Supabase, AWS Amplify, any managed or proprietary BaaS (-10), pre-built repositories, and third-party fixture-generation libraries.
- Payments must use a **mock gateway we build ourselves**.
- **Hard-coded sport logic costs -8.** That means any branch on a sport or event name (`"football"`, `"goal"`, `"wicket"`…) in domain logic. A code scan looks for it.
- Every score and total is floored at 0.

---

## 2. Required repo-root contents (Part I §1.3, Appendix C)

| Path | Requirement |
|---|---|
| `docker-compose.yml` | Brings up the whole backend: **API on host port 8080**, database, cache, queue, object store and workers. Must forward the salt as `DAY1_SALT: ${DAY1_SALT}`. |
| `.env.example` | Lists every environment variable. **Must not contain the real salt.** |
| `README.md` | Run instructions and the 5 demo accounts (§8.3). |
| `TRACEABILITY.md` | Maps every FR/NFR ID to source files and automated tests. |
| `tests/`, `run_tests.sh`, `COVERAGE.json` | Unit tests, one script that runs them, and the coverage file (§9.3 format). |
| `mobile/` | Mobile source and **`mobile/release/app-release.apk`** (Android 10 / API 29+). |
| `ADR.md` | 8 short ADRs (needed for the Day 2 viva). Write them on Day 1. |

**Pre-submission checklist (Appendix C)**
- `DAY1_SALT=<salt> docker compose up -d --build` works on a clean machine, and `/health` returns 200 in under 2 minutes.
- Running `POST /audit/v1/reset` twice in a row leaves identical data. The 5 demo accounts and all seed ids exist.
- Every response matches the Section 5 field names character by character.
- Signatures are verified against Appendix A test vector 1.
- 20 parallel checkouts with stock 1 give one 201, nineteen 409, stock 0 and reserved 0.
- `/audit/v1/*` is NOT rate limited. `/api/v1/ping` IS.
- `COVERAGE.json`, `TRACEABILITY.md`, `README.md`, `.env.example` and the APK are committed and pushed.
- The last commit is pushed before 15:05:00.

---

## 3. Grading environment and startup (Part I §5.2): reproducibility, NFR-7

- The grader clones the last commit and runs this from the repo root: `DAY1_SALT=<salt> docker compose up -d --build`.
- **The build (including pulls) must finish within 10 minutes.** Internet is available **only during the build**. Running services must not need the internet.
- The grader polls `GET /health` every 2 s. It must return 200 within **120 s** after the command returns.
- It then calls `POST /audit/v1/reset` before each test group.
- **No manual steps, no pre-created volumes, no host software other than Docker.** A failure after one automatic retry costs -10.
- `DAY1_SALT` is read **only from the environment at startup**. Never hard-code or commit it.
- Every request must finish within 5 s. Reset must finish within 10 s. The 20-request checkout burst must finish within 10 s.
- The grader may send 200 req/s to `/audit/v1/*`.

---

## 4. Functional requirements (each ID must appear in TRACEABILITY.md)

**FR-1.1 Multi-sport taxonomy and event-sourced scoring**
- Support arbitrary sports without code changes. Seed Football, Basketball, Cricket and Esports **as data**. A "mystery sport" is added at grading time with `POST /audit/v1/sports`.
- Each sport defines as data: its periods or innings, period duration, points per event type, tie-break order, whether draws are allowed, the overtime/shootout policy, roster size limits and required positions.
- There are three scoring models: **event** (points), **innings** (runs, wickets, overs) and **round** (best-of-N).
- Scores are computed from an append-only event stream. Corrections are made by appending a **compensating event signed with DAY1_SALT**. Historical rows are never changed.

**FR-1.2 League and tournament setup**
Single-stage leagues, multi-division with promotion and relegation, knockout, and hybrid (groups followed by a seeded knockout). All are scoped to seasons.

**FR-1.3 Fixture scheduling**
A custom implementation, with no fixture libraries.
- **Formats:** round-robin (single and double, circle method, byes), Swiss (score groups, no repeats, byes, Buchholz), single elimination (byes, seeding) and double elimination (WB, LB, GF, optional reset).
- **Manual rescheduling with real-time conflict detection.** Detect venue double-booking, team overlap, player overlap across squads, minimum rest period and venue availability windows. Conflicts are returned as structured JSON with the conflicting entity IDs.
- **Match state machine:** Upcoming, In-Progress, Completed, Postponed, Abandoned, Cancelled.
  - The server rejects illegal transitions.
  - Status changes are broadcast in real time.
  - Postponing a match re-evaluates downstream bracket slots and re-runs conflict detection.

**FR-1.4 Standings**
- Points per W/D/L are configurable.
- Tie-breakers run in a configurable order: h2h points, h2h diff (including the 3-way mini-league), overall diff, scored, fair-play, seeded lots.
- Include H2H matrices, sport-specific differentials (goal, point, run-rate, map) and clinched/eliminated/still-possible status.
- **Everything is recomputed from scratch** on every result or compensation.

**FR-2.1 Club profiles and tenant isolation**
- The club portal shows home venue coordinates, social handles, historical stats across seasons, the active roster and staff (coach, manager, physio).
- Clubs belong to a white-label tenant (logo, colours, name). **Tenant isolation is strict.**

**FR-2.2 Roster and player registry**
- Players can be added, transferred, loaned (with start and end dates, and automatic return) and released.
- Enforce:
  - transfer windows
  - max squad size
  - one active registration per league season (except valid loans)
  - minimum position counts
  - roles: Captain, Vice-Captain, Starter, Substitute
- Keep a **full immutable audit trail** of who, when and why.

**FR-2.3 Merchandise store**
- The catalogue covers apparel, accessories and digital items, with variants (size, colour), scheduled price changes and discount codes.
- Stock is tracked per variant and reserved during checkout against the mock gateway (authorization, capture, failure, refund). **No overselling.**
- Order states are Pending, Paid, Packed, Shipped, Delivered, Cancelled and Refunded. **Each transition emits a structured domain event to the internal queue.**
- Receipts are generated as PDFs on the server.
- Match pages have embeddable product showcases. **Pinning a product updates connected clients in real time.**

**FR-5.1 Five-tier RBAC**
- The tiers are Platform Super-Admin, League Organizer, Club Manager, Player and General Viewer.
- An Organizer controls only their own leagues. A Club Manager controls only their own club. **Tenant isolation is absolute.**
- Implement RBAC as a DB policy matrix or policy-as-code, with **negative authorization tests for every role boundary**.

**Non-functional requirements**

| ID | Bar |
|---|---|
| NFR-3 Concurrency | When 20 buyers try to buy the last unit at once, exactly 1 order succeeds and stock never goes negative. |
| NFR-4 Offline | The app caches fixtures, standings and profiles locally (SQLite/Room/Hive). Offline scoring and roster actions are queued and synced with conflict handling. |
| NFR-5 Security | OWASP Mobile/API Top 10. Tokens stored securely (Keystore/Keychain). Rate limiting, input validation and 5-role RBAC. |
| NFR-7 Reproducibility | One command brings up the full backend and seeds it on a clean Linux machine. |

**Engineering outcomes graded in spirit:** a relational schema with no hard-coded sport logic, unit-tested algorithms, an append-only event store, 5-tier RBAC, an offline mobile app, and an accessible UI.

---

## 5. Global API conventions (Part I §5.2): compared literally

| Topic | Rule |
|---|---|
| Base | `http://localhost:8080`. JSON, UTF-8, `Content-Type: application/json`. |
| Auth | `/audit/v1/*` needs **no** auth, **except the RBAC probe routes** (`Authorization: Bearer <jwt>`). |
| Identifiers | Strings of 1–64 chars from `A-Za-z0-9_.:-`. Never contain `\|`. Case-sensitive. **Store and return grader ids verbatim.** |
| Timestamps | ISO 8601 UTC `YYYY-MM-DDTHH:MM:SSZ`. Dates are `YYYY-MM-DD`. |
| Money | Integer minor units (paisa). Currency is always `"PKR"`. 4500.00 PKR = `450000`. |
| Numbers | Integers where stated. NRR is rounded to 3 decimals. |
| Unknown fields | Ignored. A missing required field or wrong type gives **400**. |
| Validation order | 1) malformed JSON or schema gives **400**; 2) an unknown referenced id gives **404**; 3) a business rule gives **409** (402 for payment). **The first failing step wins.** |
| Idempotency | For `event_id`, `order_id`, `request_id` and `action_id`, an identical replay returns the **stored result with HTTP 200** and changes nothing. |
| Rate limit | `/audit/v1/*` and `/health` are exempt. `/api/v1/*` allows **100 req per rolling 10 s per client IP**. |
| Body size | Bodies over 1 MB get **413 `PAYLOAD_TOO_LARGE`**. |

**Status codes:** 200 read or idempotent replay · 201 created or first applied · 400 · 401 missing, malformed, tampered, expired or `alg:none` token · 402 mock payment failure (checkout only) · 403 authenticated but not allowed · 404 · 409 · 413 · 429.

**Error body (every non-2xx):**
```json
{ "error": { "code": "OUT_OF_STOCK", "message": "free text", "details": { "variant_id": "var-jersey-001-M" } } }
```
- `code` is UPPER_SNAKE_CASE from the catalogue (§13).
- `details` is always an object (it may be `{}`).
- For `VALIDATION_ERROR`, `details.fields` is an array of the bad field names.
- **FastAPI's default 422 must be overridden to 400.**

---

## 6. Signature recipe (Part I §5.3, Appendix A): exact

| Element | Definition |
|---|---|
| Key | The `DAY1_SALT` env value as UTF-8 bytes. Not hex-decoded and **not trimmed**. |
| id | For events, `event_id`. For receipts, `order_id`. |
| payload | The canonical JSON of the payload object. For events it is the request `payload`. For receipts it is `receipt.payload`. |
| Canonical JSON | Keys sorted recursively by code point. No whitespace (`,` and `:`). UTF-8 with non-ASCII **not escaped**. Integers have no decimal point. `true`/`false`/`null`. Array order is preserved. |
| Message | `id + "\|" + payload` as UTF-8. |
| Output | HMAC-SHA256 as lowercase hex, 64 chars. |

```python
import hmac, hashlib, json
def canonical(obj): return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
def sign(salt, id_, payload_obj):
    return hmac.new(salt.encode("utf-8"), (id_ + "|" + canonical(payload_obj)).encode("utf-8"), hashlib.sha256).hexdigest()
def lots_key(seed, league_id, team_id):
    return hashlib.sha256(f"{seed}|{league_id}|{team_id}".encode("utf-8")).hexdigest()
```
- **Test vector 1:** salt `demo-salt`, id `evt-1`, payload `{"team_id":"t1","event_type":"goal"}`.
  - The canonical form is `{"event_type":"goal","team_id":"t1"}`.
  - The signature is `972a8b558690b19121cc5bea84978f85e8eb15a3735018db36616bab1d7ec501`.
- **Test vector 2 (lots, seed 42, league `lg-1`):** these keys order the teams best first.
  - t1: `0613316991ce0ac31e88d6003e3ff4d5e21bb072ac5f81b42c0cdc6598453293`
  - t3: `c8f28e3c2f1eb6c4f636b4f57050e3362a2b39c07fda9b61742a26dd20397028`
  - t2: `e3e3a14e22727f936e1f288cf5d02a8a9362b1da13c5432725fc10b2c7955dd9`
  - The order is **t1, t3, t2**.

---

## 7. Endpoint contract (Part I §5.4–5.14)

### 7.1 `GET /health`
Returns `200 {"status":"ok"}` **only** when the DB is reachable AND the baseline is seeded. No auth.

### 7.2 `POST /audit/v1/reset`
The body is optional: `{ "seed": 42, "stock": { "var-jersey-001-M": 1, "var-jersey-001-L": 5 } }`.
- `seed` is an integer, default 42, used for draw_lots.
- `stock` maps variant to an int ≥ 0. Defaults are M = 1 and L = 5.
- Reset wipes matches, events, leagues, rosters, orders, offline-sync records and custom sports. It then re-seeds. **The result must be repeatable and identical.**

Response 200:
```json
{ "status": "reset_complete", "seed": 42, "sports": ["football","basketball","cricket","esports"],
  "tenants": ["tenant-alpha","tenant-beta"], "stock": { "var-jersey-001-M": 1, "var-jersey-001-L": 5 } }
```

**Baseline (exact ids):**
- **Tenants:** `tenant-alpha` ("Alpha Sports") and `tenant-beta` ("Beta Athletics").
- **Store:** product `prod-jersey-001` (tenant-alpha) with variants `var-jersey-001-M` and `var-jersey-001-L`, each `price_minor = 450000` PKR. Discount `WELCOME10` = 10% off the subtotal.
- **RBAC scenario:**
  - Leagues: `league-alpha-1` and `league-alpha-2` (alpha), `league-beta-1` (beta).
  - Clubs: `club-alpha-1`, `club-alpha-2`, `club-beta-1`.
  - Players: `player-alpha-1` (club-alpha-1), `player-alpha-2` (club-alpha-2), `player-beta-1` (club-beta-1).
- **Demo users (password `Nascon@26`, must exist after every startup and every reset):**

| Role | Email | Bound to |
|---|---|---|
| Super-Admin | `admin@nascon.test` | platform-wide |
| League Organizer | `organizer@nascon.test` | owns `league-alpha-1` |
| Club Manager | `manager@nascon.test` | owns `club-alpha-1` |
| Player | `player@nascon.test` | `player-alpha-1` |
| Viewer | `viewer@nascon.test` | read-only, tenant-alpha |

- **Seed sports (stored as data, same schema as /sports):**

| sport_id | model | periods | scoring_events | draw | overtime | roster |
|---|---|---|---|---|---|---|
| football | event | 2×45 min | goal=1 | yes | none | min 11, max 25, gk ≥ 1 |
| basketball | event | 4×12 min | free_throw=1, two_pointer=2, three_pointer=3 | no | extra_time 5 min | min 5, max 15 |
| cricket | innings | 1 innings/team, 20 overs, 6 balls/over, 10 wickets | dot_ball (0, legal), single (1), two (2), four (4), six (6), wide (1, not legal), no_ball (1, not legal), wicket (0, legal, wicket) | yes | super_over | min 11, max 18, wicketkeeper ≥ 1 |
| esports | round | best_of 3 | round_win = 1 round | no | none | min 5, max 8 |

### 7.3 `POST /audit/v1/sports` (mystery sport)
The sport must be usable **immediately** in `/events`, `/leagues`, `/standings` and `/fixtures`, with no restart. Event names are arbitrary, so never hard-code them.

| Field | Rules |
|---|---|
| `sport_id` | Required. `^[a-z0-9_-]{2,40}$`. Duplicate gives 409 `SPORT_EXISTS`. |
| `name` | Required, 1–80 chars. |
| `scoring_model` | `event`, `innings` or `round`. |
| `periods` | **event:** `count` ≥ 1 and `duration_minutes` ≥ 1. **innings:** `innings_per_team`, `overs_per_innings`, `balls_per_over`, `wickets_per_innings` (all int ≥ 1). **round:** `best_of` (odd int ≥ 1). |
| `scoring_events` | At least 1 key, each matching `^[a-z0-9_]{1,40}$`. **event:** `{points}` int ≥ 1. **innings:** `{runs}` int ≥ 0, `legal_ball` bool, `wicket` bool. **round:** `{rounds}` int ≥ 1. |
| `draw_allowed` | Required bool. |
| `overtime` | Required. `policy` is one of `none`, `extra_time`, `shootout`, `golden_score`, `super_over`. Optional `duration_minutes` int ≥ 0. |
| `tie_break_order` | Optional. Values from `h2h_points`, `h2h_diff`, `overall_diff`, `scored`, `fair_play`, `draw_lots`, no repeats. The default is the full list. **`draw_lots` is always applied last, even if omitted.** |
| `roster` | Required. `min_squad_size` and `max_squad_size` (int ≥ 1, min ≤ max), and `required_positions` (a map, may be `{}`). |

Responses: **201** `{ "sport_id", "status": "created", "config": {...echoed} }`, **400** `VALIDATION_ERROR` with `details.fields`, **409** `SPORT_EXISTS`.

### 7.4 `POST /audit/v1/fixtures`: pure computation, stores nothing
The input is `{format, teams, params}`. `teams` holds unique ids. For swiss, single_elim and double_elim, the array order is the seed order (index 0 = seed 1).

Team-count limits are below. Going outside them gives **400 `VALIDATION_ERROR`**.

| Format | Teams |
|---|---|
| round_robin | 2–40 |
| swiss | 2–64 |
| single_elim | 2–128 |
| double_elim | 3–128 |

The scripts check rules and structure, except where a part is marked **exact**.

**A) round_robin.** `params`: `legs` 1 or 2 (default 1), `withdrawals` `[{team_id, after_round}]` (default []), `withdrawal_policy` `void_all` or `forfeit_remaining` (default).

**Response:**
```json
{ "format":"round_robin","legs":1,"team_count":5,"round_count":5,
  "rounds":[{"round":1,"matches":[{"match_id":"RR-L1-R1-M1","leg":1,"home":"t2","away":"t5","status":"scheduled","awarded_to":null}],"byes":["t1"]}],
  "summary":{"total":10,"scheduled":8,"forfeit":2,"voided":0} }
```

**Structure rules:**
- Rounds per leg: n−1 if n is even, n if n is odd. There are ⌊n/2⌋ matches per round.
- `byes` is `[]` for even n, and exactly one team for odd n.
- Round numbers are **global**, so leg 2 continues the numbering.
- `match_id` = `RR-L{leg}-R{round}-M{index}`, with index starting at 1 in each round.
- Each team plays once per round, except in its bye round. For odd n, each team has exactly 1 bye per leg.
- Each unordered pair meets exactly `legs` times. With 2 legs, each ordered pair (home, away) occurs exactly once.
- Within each leg, |home − away| ≤ 1 for every team (circle method).

**Withdrawals:**
- `after_round` is the last global round the team still plays. 0 means it never plays.
- **forfeit_remaining:** the withdrawn team's fixtures with round > after_round get `status:"forfeit"` and `awarded_to` = the opponent. Earlier fixtures stay `scheduled`.
- **void_all:** every fixture of the withdrawn team gets `status:"voided"` and `awarded_to:null`.
- A fixture where both teams have withdrawn is voided.
- Fixtures are never removed. Byes are unaffected.
- An unknown team, or `after_round` outside `0..round_count`, gives 400.

**B) swiss.** One call pairs one round.

`params`:
- `total_rounds`: 1..n−1, default ⌈log2 n⌉.
- `round`: 1..total_rounds, default 1.
- `history`: must contain exactly rounds 1..round−1, else 400. Each entry is `[{round, bye, matches:[{home, away, result: home|away|draw}]}]`.

**Response:**
```json
{ "format":"swiss","round":2,"total_rounds":3,
  "pairings":[{"match_id":"SW-R2-M1","home":"t1","away":"t2"}],"bye":"t3",
  "standings":[{"rank":1,"team_id":"t1","score":1.0,"buchholz":0.0}] }
```

**Scoring and standings:**
- Win = 1, draw = 0.5, loss = 0, bye = 1.
- `standings` reflect the **history only**. Sort by score desc, then buchholz desc, then seed asc.
- Buchholz = the sum of the current scores of the opponents a team actually played. A bye counts 0. Both values are **compared exactly**.

**Round 1 (exact):** let m = ⌊n/2⌋. For odd n, the last seed gets the bye. Pair seed i with seed i+m, with home = the lower seed number.

**Rounds 2+ (checked as properties):**
- (a) Each team appears at most once.
- (b) There are no rematches.
- (c) For odd n, there is exactly one bye.
  - It goes to the lowest-scoring team that hasn't had a bye. A tie goes to the lowest seed (largest index).
  - If the rest can't be paired, try the next candidate.
- (d) The **sum of |score diff| over all pairs must be the minimum achievable** over all rematch-free pairings. Greedy fails, so use backtracking or matching. Home/away is not checked.

If no rematch-free pairing exists for any bye candidate, return 409 `NO_VALID_PAIRING` with `details.round`.

**C) single_elim.** `params`: `third_place_match` bool, `results` `[{match_id, winner}]`.

**Bracket construction (exact):**
- B = the next power of two ≥ n.
- order(2) = [1,2]. order(2k) = for each s in order(k), output [s, 2k+1−s]. So order(8) = [1,8,4,5,2,7,3,6].
- R1 match i takes entries 2i−1 and 2i. The lower seed is home.
- A seed > n is missing. That match has `bye:true` and `away:null`, and the present team is the winner.

MATCH object (all fields are mandatory):
```json
{ "match_id":"R1M2","bracket":"main","round":1,"index":2,"home":"t4","away":"t5","home_seed":4,"away_seed":5,
  "bye":false,"winner":null,"loser":null,"winner_to":{"match_id":"R2M1","slot":"away"},"loser_to":null }
```

**Advancement and results:**
- The response is `{format, bracket_size, rounds:[{round, matches:[...]}]}`.
- `match_id` = `R{round}M{index}`. There are log2 B rounds. The final has `winner_to:null`.
- The winner of R{r}M{i} goes to R{r+1}M{ceil(i/2)}. The slot is home if i is odd and away if i is even.
- home/away are null while unknown. **Bye winners are propagated immediately.**
- Each entry in `results` fills winner/loser and propagates. An unknown match_id, or a winner who isn't in the match, gives 400.
- `third_place_match:true` adds match `TP` with `bracket:"third_place"`. Both semi-finals' `loser_to` point to TP (home/away).

**D) double_elim.** `params`: `bracket_reset` bool, `results`.

The response is `{format, bracket_size, bracket_reset, winners:[rounds], losers:[rounds], grand_final:[GF1, GF2?]}`. B and WR1 seeding are the same as single_elim (exact). `bracket` is `winners`, `losers` or `grand_final`.

**Ids and counts (exact):**
- WR{r}M{i}: round r has B/2^r matches.
- LR{r}M{i}: there are rounds 1..2(k−1). Rounds 2j−1 and 2j each have B/2^(j+1) matches. The LB has B−2 matches in total.
- `GF1` always exists. `GF2` exists only when `bracket_reset:true`.

**Routing (checked as a graph):**
- Every non-terminal match has `winner_to`. Every WB match has `loser_to`. LB matches have `loser_to:null`.
- Every slot except those in WR1 is fed by exactly one source.
- The WB final winner goes to GF1.home. The WB final loser goes to the LB final away slot. The LB final winner goes to GF1.away.
- Recommended: WR1 losers meet in LR1, and the WRr losers (r ≥ 2) drop into LR(2r−2).

**GF2:**
- It has `conditional:true` and the same teams as GF1.
- `required` is null until GF1 has a result. Then it is true **only if** `bracket_reset` is true AND the GF1 winner is the LB champion (GF1.away). Otherwise it is false.
- WR1 byes are graded as in single elimination.

### 7.5 `POST /audit/v1/leagues`
```json
{ "league_id":"lg-1","sport_id":"football","teams":["t1","t2","t3","t4"],
  "fixtures":[{"match_id":"m1","home":"t1","away":"t2"}],
  "points":{"win":3,"draw":1,"loss":0},"tie_break_order":[...],"qualification":{"spots":2},"lots_seed":42 }
```
- `league_id`, `sport_id`, `teams` and `fixtures` are required.
- An unknown sport gives 404 `SPORT_NOT_FOUND`.
- Teams must be unique, 2–40 of them. Fixture teams must be in `teams`, with home ≠ away.
- A used match_id gives 409 `MATCH_EXISTS`. A used league_id gives 409 `LEAGUE_EXISTS`.
- `points` defaults to 3/1/0. `tie_break_order` defaults to the sport's order.
- `qualification.spots` is **required**, an int from 1 to the number of teams.
- `lots_seed` defaults to the last /reset seed (42 if none).
- Every fixture becomes a match stream with status `upcoming`.
- **201:** `{"league_id":"lg-1","status":"created","team_count":4,"fixture_count":2}`.

### 7.6 `POST /audit/v1/events` and `GET /audit/v1/score/{match_id}`
The request is `{ "event_id", "match_id", "type", "payload" }`.
- A match stream exists if it is a league fixture or its `match_init` was accepted.
- `match_init` on an existing stream gives 409 `MATCH_EXISTS`.
- Any other event on a missing stream gives 404 `MATCH_NOT_FOUND`.

| type | payload | rule |
|---|---|---|
| `match_init` | `{sport_id, home_team_id, away_team_id}` (+ `league_id` optional) | Creates the match as `upcoming`. An unknown sport gives 404 `SPORT_NOT_FOUND`. |
| `match_start` | `{}` | Must be `upcoming`, then becomes `in_progress`. Otherwise 409 `ILLEGAL_TRANSITION`. |
| `score` | `{team_id, event_type}` | Must be `in_progress`, else 409 `MATCH_NOT_IN_PROGRESS`. The team must be home or away, else 400. An unknown event_type gives 400 `UNKNOWN_EVENT_TYPE`. Points, runs and rounds come from the config. |
| `discipline` | `{team_id, points}` (an int, usually negative) | Must be `in_progress`. Adds to fair-play (higher is better). |
| `tiebreak_winner` | `{team_id}` | Must be `in_progress`. Declares the shootout/OT/super-over winner without changing the score. |
| `match_end` | `{}` | Must be `in_progress`, else 409 `ILLEGAL_TRANSITION`. Becomes `completed`. A level score with draw not allowed and no active tiebreak_winner gives 409 `TIE_NOT_ALLOWED`. |
| `compensation` | `{compensates, reason}` | Allowed in any status after init, including completed. It must target a score, discipline or tiebreak_winner event of the same match. An unknown target gives 404 `EVENT_NOT_FOUND`. An already-compensated target, another type or another match gives 409 `INVALID_COMPENSATION`. |

**Model limits:**
- **innings:** once a team's legal balls ≥ innings_per_team×overs×balls_per_over, or its wickets ≥ innings_per_team×wickets_per_innings, further score events give 409 `INNINGS_COMPLETE`.
- **round:** once a team has ≥ (best_of+1)/2 rounds, further score events give 409 `SERIES_ALREADY_DECIDED`.
- Compensated events don't count toward either limit.

**Event log rules:**
- The log is append-only. The original row is never modified.
- The projection treats a compensated event, and the compensation itself, as neutral.
- **The score is rebuilt from the log on read.** Counters are never the source of truth.

**Idempotency:** the same event_id with an identical body gives 200 and the stored response. A different body gives 409 `DUPLICATE_EVENT_ID`.

**Event response (201, or 200 on replay):** `{ "event_id","match_id","type","sequence","match_version","signature" }`.
- `sequence` is the 1-based position in the match log, counting every type.
- `match_version` is the number of events in the log after the append.
- `signature` follows §6 over the request payload.

**GET score, 200:**
```json
{ "match_id":"m1","sport_id":"football","league_id":"lg-1","status":"completed","outcome":"home_win",
  "winner_team_id":"t1","tiebreak_winner_team_id":null,
  "home":{"team_id":"t1","score":2,"wickets":null,"balls":null,"overs":null,"fair_play":0},
  "away":{"team_id":"t2","score":1,"wickets":null,"balls":null,"overs":null,"fair_play":-1},
  "version":9,"events":[{"sequence":1,"event_id":"evt-0001","type":"match_init","payload":{},"signature":"...","compensated":false,"compensated_by":null}] }
```

**Field rules:**
- `status` is `upcoming`, `in_progress` or `completed`.
- `outcome` is `pending` until completed. Then it is `home_win`, `away_win`, `draw` or `undecided` (level, no draw allowed, and no active tiebreak, for example after the tiebreak was compensated).
- `score`: event model = points, innings model = runs, round model = rounds won. Active events only.
- `wickets`, `balls` and `overs` are for the innings model only, else null. `overs` = `"{balls div bpo}.{balls mod bpo}"`, e.g. `"3.2"`.
- `winner_team_id` is the higher score. If level, it is the active tiebreak winner, else null.
- `events` lists everything, including compensated events and compensations, with `compensated` and `compensated_by` set.

### 7.7 `GET /audit/v1/standings/{league_id}`
**Recomputed from the event logs on every call.** Only matches that are `completed` with outcome ≠ `undecided` count as played. Every other fixture is "remaining".

```json
{ "league_id":"lg-1","sport_id":"football","qualification_spots":2,
  "table":[{"rank":1,"team_id":"t1","played":3,"won":2,"drawn":1,"lost":0,"scored":7,"conceded":2,"diff":5,
            "points":7,"fair_play":0,"status":"clinched","resolved_by":null}],
  "h2h":{"t1":{"t2":{"played":1,"points":3,"scored":2,"conceded":1}}} }
```

**Field rules:**
- A win by tiebreak_winner counts as a win.
- `diff` depends on the model:
  - event: scored − conceded.
  - round: rounds won − rounds lost.
  - innings: **NRR** = runs scored ÷ overs faced − runs conceded ÷ overs bowled, rounded to 3 decimals. Overs = legal balls ÷ bpo as a decimal. An innings ended by all wickets counts as the full overs_per_innings. Overs bowled = the opponent's overs faced.
- `h2h[a][b]` is present for **every ordered pair** (zeros if they never met).
- `resolved_by` is the criterion that placed this team above the next team it was tied with, or null.

**Ordering (exact):**
1. Sort by points, descending. Equal points form a tied group.
2. `resolve(group)`: go through the criteria in order (then draw_lots). If the values are not all equal, split into sub-groups (best first). **Each sub-group of size > 1 is resolved again from the FIRST criterion.** Then stop.
3. `h2h_points` and `h2h_diff` use only the matches among the teams of the **current group** (the mini-league). `overall_diff`, `scored` and `fair_play` use all completed league matches. Higher is better for every criterion.
4. `draw_lots`: sort ascending by `SHA256_hex(lots_seed|league_id|team_id)`. First = best.

**Qualification (exact, points only):**
- W = win points. R(T) = T's remaining fixtures. max(T) = points(T) + W×R(T). k = spots.
- **clinched** if fewer than k other teams X have max(X) ≥ points(T). Check this first.
- **eliminated** if at least k other teams X have points(X) > max(T).
- Otherwise **still_possible**.

### 7.8 Roster: `POST /audit/v1/roster/setup`, `POST /audit/v1/roster/transfer`, `GET /audit/v1/roster/history/{player_id}?as_of=`
**setup** takes `{league:{league_id, tenant_id, sport_id, transfer_window:{open, close}, max_squad_size, required_positions}, squads:[{squad_id, club_id, tenant_id, name}], players:[{player_id, name, position, squad_id, role}], matches_in_progress:[{match_id, home_squad_id, away_squad_id}]}`.
- Re-sending the same league_id replaces its state.
- **201:** `{"league_id":"lg-r1","status":"configured","squad_counts":{"sq-a":2,"sq-b":0}}`.
- `role` is `captain`, `vice_captain`, `starter` or `substitute`.
- If `max_squad_size` or `required_positions` are omitted, they default from the sport's roster config.
- Window dates are inclusive.

**transfer** takes `{request_id, league_id, player_id, type: transfer|loan|release, from_squad_id, to_squad_id (null for release), effective_date, loan_end_date (loan only, > effective_date), reason, requested_by}`.

**Checks, in this exact order. The first failure wins:**
1. Schema, dates, loan_end_date > effective_date, to_squad present unless release: 400 `VALIDATION_ERROR`.
2. League, player and squads exist: 404 `LEAGUE_NOT_FOUND`, `PLAYER_NOT_FOUND` or `SQUAD_NOT_FOUND`.
3. Both squads belong to the league's tenant: 409 `CROSS_TENANT_TRANSFER`.
4. The player's current squad = from_squad_id: 409 `NOT_IN_SQUAD`.
5. For transfer or loan, effective_date is inside the window (inclusive). Release is allowed on any date. Else 409 `TRANSFER_WINDOW_CLOSED`.
6. The player is not currently on loan: 409 `PLAYER_ON_LOAN`.
7. For transfer or loan, destination count + 1 ≤ max_squad_size: 409 `SQUAD_FULL`.
8. After the move, the from squad still has at least the required count for the player's position: 409 `MIN_POSITION_VIOLATION`.

**Effects:**
- **transfer:** permanent move. The new role is `substitute`. An old captain or vice-captain slot becomes vacant.
- **loan:** the player belongs to the borrower from effective_date to loan_end_date inclusive. `parent_squad_id` = the lender. The player counts toward the borrower's size and not the lender's.
- **release:** the player has no squad.
- **Auto-return:** the day after loan_end_date, the player is back with the lender as a substitute. The grader passes `as_of` to history. A `loan_return` entry with `who:"system"` must appear **exactly once, even across repeated calls**.
- **In-progress match (edge case 6):** if the player's squad is in `matches_in_progress`, accept with `state:"deferred_until_match_end"` and `blocking_match_id`. Otherwise `state:"active"` and `blocking_match_id:null`.
- **Audit:** each accepted change appends one immutable entry. Rejections write nothing. Idempotent on request_id (replay gives 200 and the same body).

**Transfer response (201, or 200 on replay):**
```json
{ "request_id":"tr-001","status":"accepted","state":"active","blocking_match_id":null,
  "registration":{"player_id":"p2","league_id":"lg-r1","squad_id":"sq-b","parent_squad_id":null,"registration_type":"transfer",
                  "start_date":"2026-09-30","loan_end_date":null,"role":"substitute"},
  "audit_entry":{"audit_id":"au-0001","action":"transfer","player_id":"p2","league_id":"lg-r1","from_squad_id":"sq-a","to_squad_id":"sq-b",
                 "effective_date":"2026-09-30","state":"active","who":"user-77","when":"2026-09-30T08:12:44Z","why":"Tactical move"} }
```
- For release, `registration` is null. For a loan, `registration_type:"loan"`, `parent_squad_id` and `loan_end_date` are set.
- `action` is `transfer`, `loan`, `release` or `loan_return`. `when` is the server time.

**history 200:** `{ "player_id","as_of","league_id","current_squad_id","parent_squad_id","history":[audit entries oldest first] }`.
- `as_of` defaults to today's server date.
- `current_squad_id` is the squad on that date, or null if released.
- An unknown player gives 404 `PLAYER_NOT_FOUND`.

### 7.9 Store: `POST /audit/v1/checkout` and `GET /audit/v1/inventory/{variant_id}`
**Grading:** the grader resets with stock, then fires **20 simultaneous** checkouts for the last unit of `var-jersey-001-M`, each with a different order_id. **Exactly one must succeed.**

The request is `{ "order_id","customer_id","items":[{"variant_id","quantity"}],"discount_code":null,"payment":{"token":"tok_success"} }`.

**Field rules:**
- `order_id`: an identical replay gives 200 with no second reservation. Same id with a different body gives 409 `DUPLICATE_ORDER_ID`.
- `items`: 1–10 items, quantity 1..10, unique variants. An unknown variant gives 404 `VARIANT_NOT_FOUND`.
- `discount_code`: null or `WELCOME10`. Anything else gives 400 `INVALID_DISCOUNT_CODE`. `discount_minor = floor(subtotal_minor*10/100)`.
- **Tokens:** `tok_success` authorizes and captures. `tok_declined` fails authorization. `tok_capture_fail` authorizes but capture fails.

**Processing order:**
1. Validate (400), then check variants exist (404), then check the discount (400).
2. **Reserve all items atomically.** If any item is short, reserve nothing and return 409 `OUT_OF_STOCK` with `details.variant_id`.
3. Call the gateway.
   - `tok_declined`: release the reservation and return 402 `PAYMENT_DECLINED`.
   - `tok_capture_fail`: void the authorization, release the reservation and return 402 `PAYMENT_CAPTURE_FAILED`.
   - Released stock must be buyable again.
4. On success: commit the reservation, set status to `paid` and generate the receipt.

**Success (201, or 200 on replay):**
```json
{ "order_id":"ord-001","status":"paid","currency":"PKR",
  "items":[{"variant_id":"var-jersey-001-M","quantity":1,"unit_price_minor":450000}],
  "subtotal_minor":450000,"discount_minor":0,"total_minor":450000,
  "payment":{"authorization_id":"auth_1","capture_id":"cap_1","state":"captured"},
  "receipt":{"payload":{"order_id":"ord-001","customer_id":"cust-001","items":[...],"subtotal_minor":450000,"discount_minor":0,
                         "total_minor":450000,"currency":"PKR","paid_at":"2026-10-17T11:20:05Z"},
             "signature":"<hex>","pdf_base64":"<base64>"} }
```

**Receipt rules:**
- `receipt.signature` follows §6 with id = order_id, over `receipt.payload` **exactly as returned**. The totals must add up.
- `pdf_base64` decodes to a real PDF (it starts with `%PDF`) generated on the server. Its **extracted text must contain the order_id and `PKR 4500.00`**: major units, 2 decimals, no thousands separator.

**inventory:** `{ "variant_id":"var-jersey-001-M","stock":0,"reserved":0 }`.
- `reserved` must be 0 once all requests have returned.
- After the burst: one 201, nineteen 409, stock 0, never negative.
- The order status domain event goes to the internal queue (not graded by script).

### 7.10 RBAC: `POST /audit/v1/rbac-matrix`, the probes and security
`rbac-matrix` takes no body and no auth. **200:**
```json
{ "tokens":{"super_admin":"<jwt>","league_organizer":"<jwt>","club_manager":"<jwt>","player":"<jwt>","viewer":"<jwt>"},
  "context":{"tenant_id":"tenant-alpha","foreign_tenant_id":"tenant-beta","own_league_id":"league-alpha-1","other_league_id":"league-alpha-2",
             "foreign_league_id":"league-beta-1","own_club_id":"club-alpha-1","other_club_id":"club-alpha-2","foreign_club_id":"club-beta-1",
             "own_player_id":"player-alpha-1","other_player_id":"player-alpha-2","foreign_player_id":"player-beta-1"} }
```

**Token rules:**
- JWTs must be valid for ≥ 1 h. Claim names are our choice.
- The **signature is verified**. Reject `alg:none`, a tampered signature or an expired token with **401 `UNAUTHENTICATED`**.
- Non-admin tokens belong to tenant-alpha.

**Probe responses:**
- Probes only authorize. They don't mutate and don't validate the body (the grader sends `{}`).
- Allowed: `200 {"authorized":true}`. Denied: **403 `FORBIDDEN`**. Missing or invalid token: **401 `UNAUTHENTICATED`**.
- **Authorization is evaluated before anything else.**
- **Cross-tenant access is always 403, never 404.** 404 is only for ids that don't exist at all.

| # | Route |
|---|---|
| P1 | `POST /audit/v1/rbac/tenants` |
| P2 | `POST /audit/v1/rbac/leagues/{league_id}/fixtures` |
| P3 | `POST /audit/v1/rbac/clubs/{club_id}/roster` |
| P4 | `POST /audit/v1/rbac/clubs/{club_id}/products` |
| P5 | `PATCH /audit/v1/rbac/players/{player_id}` |
| P6 | `GET /audit/v1/rbac/clubs/{club_id}` |
| P7 | `GET /audit/v1/rbac/platform/config` |

**Expected matrix** (A = 200, D = 403):

| Probe (target) | SuperAdmin | Organizer | ClubMgr | Player | Viewer |
|---|---|---|---|---|---|
| P1 | A | D | D | D | D |
| P2 own league | A | A | D | D | D |
| P2 other league (same tenant) | A | D | D | D | D |
| P2 foreign league | A | D | D | D | D |
| P3/P4 own club | A | D | A | D | D |
| P3/P4 other club (same tenant) | A | D | D | D | D |
| P3/P4 foreign club | A | D | D | D | D |
| P5 own player | A | D | A (own club's players) | A (self only) | D |
| P5 other player (other club) | A | D | D | D | D |
| P5 foreign player | A | D | D | D | D |
| P6 own/other club (tenant-alpha) | A | A | A | A | A |
| P6 foreign club | A | D | D | D | D |
| P7 | A | D | D | D | D |

**Security probes:**
- P7 with no header gives 401. P7 with an altered signature or `alg:none` gives 401.
- **Rate limit:** 150× `GET /api/v1/ping` within 5 s from one client. The first returns `200 {"pong":true}`. **At least 40 return 429 `RATE_LIMITED` with a `Retry-After` header.** 11 s later a request returns 200 again.
- **Input validation:** `sport_id = x'; DROP TABLE sports;--` gives 400 `VALIDATION_ERROR`. A customer_id containing quotes or `<script>` is stored and returned as plain data. **Never return a 5xx.**
- A body > 1 MB to any `/audit/v1/*` POST gives 413.

### 7.11 `POST /audit/v1/offline-sync`
The request is `{ "device_id", "actions":[{ "action_id","type":"score_event"|"roster_transfer","queued_at","base_version","payload" }] }`.

**Envelope rules:**
- `actions` has 1–100 items, else 400.
- A `score_event` payload is the /events body. A `roster_transfer` payload is the /roster/transfer body.
- `base_version` is the match version (event count) for a score_event, and the player's audit entry count for a roster_transfer.
- **Sort by queued_at ascending (ties keep array order), process sequentially, and return results in request order.**

**Per-action results (exact):**

| Situation | status | resolution | error_code |
|---|---|---|---|
| allowed and base_version == current | applied | appended | null |
| allowed and base_version < current | applied | rebased_append | null |
| (device_id, action_id) already processed, OR the same event_id exists with an identical payload | duplicate | skipped_duplicate | null |
| a 5.9/5.11 rule rejects it | rejected | server_wins | that rule's code |
| base_version > current | rejected | server_wins | `INVALID_BASE_VERSION` |
| unknown match/player/squad | rejected | server_wins | the matching `*_NOT_FOUND` |

**200:**
```json
{ "device_id":"dev-1","results":[{"action_id":"a1","status":"applied","resolution":"rebased_append","error_code":null,
  "processed_order":1,"server_version":5,"signature":"<hex for score_event, else null>"}],
  "summary":{"applied":1,"rejected":1,"duplicate":0} }
```
- `server_version` is the version after processing (unchanged when rejected or duplicate).
- **Re-sending the same request returns `duplicate` for everything.**
- The response is always HTTP 200. Only a malformed envelope gives 400.

---

## 8. Hidden edge cases (graded by vectors and in the viva)
1. Round-robin with odd n plus a mid-season withdrawal (both policies).
2. Swiss with no rematch-free pairing for some players: search globally, return 409 `NO_VALID_PAIRING` only when no bye candidate works.
3. Double-elim bracket reset: `GF2.required` is true only when the LB champion wins GF1.
4. A 3-way tie: an h2h mini-league among the tied teams only, restarting on split.
5. A compensation on a completed match after qualification was decided: standings, status and h2h are recomputed. The original events stay in /score.
6. A transfer on the last window day while the player is in an in-progress match: `deferred_until_match_end` plus `blocking_match_id`.

---

## 9. Approved stack (Part I §7)

| Category | Approved |
|---|---|
| DB, cache, storage | PostgreSQL 16, Redis 7, MinIO |
| Auth and queues | Custom JWT, Keycloak or Ory Kratos. RabbitMQ, Redis Streams, NATS, BullMQ or Celery. |
| PDF | WeasyPrint, wkhtmltopdf, Puppeteer (PDF libraries are also fine) |
| Testing | pytest, JUnit, TestNG, grafana/k6 |

Web frameworks, ORMs, JWT libraries and PDF libraries are fine. **Fixture-generation libraries and BaaS are prohibited.**

---

## 10. Mobile requirements (Part I §8)

**Platform and delivery**
- Android, at **`mobile/release/app-release.apk`**, installable on **Android 10 (API 29)+**.
- The app talks to the backend on a team laptop. **The server address must be changeable in the app**: `10.0.2.2:8080` on the emulator, the laptop's LAN IP on a phone.
- **Secure token storage is mandatory** (Android Keystore).

**Required screens**

| Screen | Must show |
|---|---|
| Login | Email + password. A role-aware home after login. |
| Fixtures | Matches with status and time. Tap to open one. |
| Match detail | The live score (real-time updates), the event timeline and the pinned product showcase. |
| Standings | The points table with qualification status. |
| Club profile | Club info, roster, staff and home venue. |
| Store | Catalogue, variant picker, cart, checkout with the mock gateway, and receipt view/download. |
| Roster management | For the Club Manager: add, transfer, loan or release a player. |
| Scoring entry | For the Organizer: append a score event and a compensating event. |
| Sync status | An **always-visible** online/offline/syncing indicator and the pending-action queue. |

**Offline desk check (NFR-4, 4 pts, together with the /offline-sync script)**
1. Online, the judge opens Fixtures, Standings and a Club profile. They must be cached in a local DB (SQLite/Room/Hive).
2. The judge turns on airplane mode. The cached screens must still open, and an "Offline" indicator must show.
3. Offline, the judge does one scoring action (Organizer) and one roster action (Manager). Each is saved in a **persistent queue**, shown as "pending", and uses the **§7.11 action format**.
4. The judge force-closes and reopens the app while offline. The pending actions must still be there.
5. The judge turns the network on. The app syncs automatically (or through an obvious Sync button), shows per-action results (applied/rejected + reason in **plain language**) and clears the queue.

**Judging procedure:** all judges run the same 3 tasks.
- (A) Find a league's standings and open a match.
- (B) Buy an item with the mock payment and open the receipt.
- (C) As Club Manager, do a roster action, then repeat one action in airplane mode and sync.

## 11. DESIGN CONSTRAINTS (UI/HCI, 10 pts, judged)

| Area | Requirement |
|---|---|
| 1. Navigation and ease of use | A new user finds Fixtures, Standings, Store and Profile without help. Common tasks take few taps. **Back/undo always works. No dead ends.** |
| 2. Visual consistency and hierarchy | The same colours, fonts, spacing and button styles everywhere. The **most important things (score, Buy button) stand out.** **The tenant's logo and colours are applied** (white-label). |
| 3. Feedback and error handling | Always show what is happening: loading indicators and success messages. **Plain-language errors, never raw codes like "Error 500".** Visible Online/Offline/Syncing status. **Confirm before risky actions** (release a player, checkout, compensation). |
| 4. Readability and accessibility | Text large enough, good contrast, **tap targets about 48 dp**. **Icons have labels or semantics descriptions.** **Meaning is never shown by colour alone** (pair colour with text or an icon). |
| 5. Right screen for the right role | Each role sees only what it can use. Empty lists show a helpful message (for example "No matches yet"). **Nothing breaks or overflows on a 360×640 dp phone or after rotating.** |

---

## 12. Scoring and penalties (Part I §9)

| Component | Max | How it's checked |
|---|---|---|
| Backend: 6 areas | 36 | Python scripts |
| Offline persistence and sync queue | 4 | Script plus desk check |
| Mobile UI/HCI | 10 | Judges |

**The six backend areas:**
- Fixtures ×4
- Event-sourced scoring (mystery sport plus compensation)
- Standings (3-way h2h, differentials, status)
- Store concurrency plus the PDF
- Roster, transfer-window and loan rules
- RBAC matrix, tenant isolation and security

**Per-area score:** S = 0.9·P·(n/|V|) + 0.1·P·[unit-test coverage of the area ≥ 85%].
- |V| ≥ 40 hidden vectors per area.
- A vector passes only if **every** assertion holds. There's no partial credit inside a vector.
- The vectors include seeded and mystery sports, odd, even and non-power-of-two sizes, and **every error code**.

**`COVERAGE.json`** (at the repo root):
```json
{ "fixtures": 91.2, "scoring": 88.0, "standings": 86.5, "store": 90.1, "roster": 87.3, "rbac": 85.0 }
```
Judges may run `./run_tests.sh`. If the real figure is **more than 2 points below** the declared one, that area's bonus is voided. **Declare honest numbers.**

**Penalties** (applied to the total of 50):
- -10: non-reproducible stack.
- -8: hard-coded sport or event names.
- -10: BaaS.
- -2 per missed push window (max -8).

---

## 13. Error code catalogue (Appendix B)

| HTTP | Codes |
|---|---|
| 400 | `VALIDATION_ERROR`, `UNKNOWN_EVENT_TYPE`, `INVALID_DISCOUNT_CODE` |
| 401 | `UNAUTHENTICATED` |
| 402 | `PAYMENT_DECLINED`, `PAYMENT_CAPTURE_FAILED` |
| 403 | `FORBIDDEN` |
| 404 | `SPORT_NOT_FOUND`, `MATCH_NOT_FOUND`, `LEAGUE_NOT_FOUND`, `EVENT_NOT_FOUND`, `PLAYER_NOT_FOUND`, `SQUAD_NOT_FOUND`, `VARIANT_NOT_FOUND` |
| 409 | `SPORT_EXISTS`, `LEAGUE_EXISTS`, `MATCH_EXISTS`, `DUPLICATE_EVENT_ID`, `DUPLICATE_ORDER_ID`, `ILLEGAL_TRANSITION`, `MATCH_NOT_IN_PROGRESS`, `TIE_NOT_ALLOWED`, `INNINGS_COMPLETE`, `SERIES_ALREADY_DECIDED`, `INVALID_COMPENSATION`, `NO_VALID_PAIRING`, `OUT_OF_STOCK`, `CROSS_TENANT_TRANSFER`, `NOT_IN_SQUAD`, `TRANSFER_WINDOW_CLOSED`, `PLAYER_ON_LOAN`, `SQUAD_FULL`, `MIN_POSITION_VIOLATION` |
| none | `INVALID_BASE_VERSION` (only inside offline-sync results) |
| 413 | `PAYLOAD_TOO_LARGE` |
| 429 | `RATE_LIMITED` |

---

## 14. Environment and logistics (booklet)

**Docker**
- Images are pre-pulled on Tanzeel's laptop only. Campus Wi-Fi throttles Docker Hub.
- **Never run `docker system prune -a` or `docker image prune -a`.**

**Low RAM**
- Split the work. Laptop 1 (Tanzeel) runs the backend containers. Laptop 2 runs the mobile app with a phone over USB. Laptop 3 runs Selenium and tests.
- Selenium containers use `shm_size: "1gb"` and `SE_START_VNC: "false"`.

**Network**
- **Campus Wi-Fi isolates devices.** Bring a phone hotspot or travel router. Laptops and the test phone must share it and talk over LAN IPs.
- Campus Wi-Fi is only for GitHub, Actions, AI tools and light package downloads (`pypi.org`, `registry.npmjs.org`, `pub.dev`, `repo.maven.apache.org`).

**Mobile tooling**
- **Cache Gradle and pub dependencies before the event** so builds work offline.
- A physical Android phone with USB debugging is strongly recommended. It saves about 4 GB of RAM compared with an emulator.

**QA tooling**
- Install Appium 2 with UiAutomator2, Selenium bindings, pytest, Allure or an HTML report, and k6 or Locust.
