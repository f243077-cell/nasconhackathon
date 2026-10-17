# DISTRIBUTION.md: Who Does What (Day 1, Part I)

**How the split was chosen.** The backend is worth **36 of the 50 points**. The offline layer is worth 4 and the UI 10.
- The backend gets two people: Tanzeel, plus Gunee on pure-logic modules that need no Docker.
- Huzaifa owns the whole Flutter app.
- Gunee joins the mobile data layer once their backend modules are done.

| Member | Has | Owns | Approx. points |
|---|---|---|---|
| **Tanzeel** | Docker, Android emulator, the pre-pulled images | Infra/compose, reset/seed/health, errors and middleware, sports + events + score, store/checkout/PDF, RBAC/JWT/rate limit, offline-sync endpoint, `/api/v1` mobile routes, WebSocket, README, ADR, COVERAGE, final integration and pushes | scoring 6 + store 6 + rbac 6 + offline 2 = **~20**, plus every other area depends on it |
| **Gunee** | Flutter, no Docker, no emulator | **Pure Python domain modules + tests:** fixtures (4 formats), standings, roster rules. Then helps Huzaifa with the mobile offline queue and sync. | fixtures 6 + standings 6 + roster 6 = **~18** |
| **Huzaifa** | Flutter (UI), no Docker, no emulator | **The whole Flutter app:** theme, all 9 screens, accessibility, data layer, offline cache and queue (with Gunee), building and committing the APK | UI 10 + offline 2 = **~12** |

All three read `CLAUDE.md` (the official rules) and `AGREED_RULES.md` (our architecture) before 10:45.

---

## TONIGHT (before Sat 09:00): prep. No project code, no commits.

### Tanzeel
- [x] All Docker images pulled (see `DOCKER_SETUP_LOG.md`). The MinIO fallback `bitnamilegacy/minio:2024.9.22` is pulled and health-checked.
- [ ] Submit the Docker hash form (`002b49957e5aa82f`, recommended in the log).
- [ ] Create the **empty public** GitHub repo (no README, no license, zero commits). Invite `nascon-eval-26`, Gunee and Huzaifa. Write the URL down for desk registration before 11:15.
- [ ] Warm the pip cache: `pip download fastapi "uvicorn[standard]" sqlalchemy "psycopg[binary]" redis pyjwt reportlab minio pydantic python-multipart pytest pytest-cov httpx -d %USERPROFILE%\pipcache`. This is for local runs. The grader has internet during its build.
- [ ] Check that the Android emulator boots, and that `adb devices` works with a physical phone.
- [ ] Phone hotspot works. Get the laptop's hotspot IP from `ipconfig`. Prepare a Windows Firewall rule for TCP 8080/5432/6379 on the private profile.
- [ ] Re-read CLAUDE.md §7.2, §7.6, §7.9, §7.10 and §7.11.
- [ ] **Never** prune Docker images.

### Gunee
- [ ] Install **Python 3.12** (3.11+ works) and run `pip install pytest pytest-cov`. Check `python -m pytest --version`.
- [ ] Re-read CLAUDE.md §7.4 (fixtures), §7.7 (standings) and §7.8 (roster) until you know the exact rules. These are the most detail-heavy parts of the contract.
- [ ] Work through on paper: Swiss min-cost pairing with backtracking, the double-elim LB round sizes (B=8 gives LR1=2, LR2=2, LR3=1, LR4=1, for B−2 = 6 matches in total), and the standings `resolve()` recursion.
- [ ] Flutter: warm the pub cache (see Huzaifa's list) so you can help on the mobile data layer later.

### Huzaifa
- [ ] Flutter stable plus the Android SDK. `flutter doctor` must be all green for Android.
- [ ] **Warm the caches offline-proof:** create a throwaway project outside the repo folder.
  - Add the packages from AGREED_RULES §5: `flutter_riverpod go_router dio flutter_secure_storage sqflite path connectivity_plus web_socket_channel uuid path_provider open_filex shared_preferences`.
  - Run `flutter pub get`, then **`flutter build apk --release`** once. This caches Gradle.
  - Then **delete the throwaway project.** Pre-built code is prohibited.
- [ ] A physical Android phone (Android 10+) with **USB debugging on** and a USB data cable. You have no emulator, so this phone is your test device. Tanzeel's emulator is the backup.
- [ ] Re-read CLAUDE.md §10 and §11 (screens and design constraints). Sketch the navigation and colour tokens on paper.

---

## DAY 1 TIMELINE (10:45–15:00)

Push checkpoints: **W1** 10:45–11:45 · **W2** 11:45–12:45 · **W3** 12:45–13:45 · **W4** 13:45–14:45. Every member pushes at least once in every window.

### Tanzeel: backend core and integration (Laptop 1, runs Docker)
| Time | Task | Done when |
|---|---|---|
| 10:45–11:10 | Repo init: `.gitignore`, `.env.example`, `docker-compose.yml` (postgres, redis, minio, api, worker) plus `docker-compose.dev.yml`, `backend/Dockerfile`, `requirements.txt`, `app/main.py`, `config.py`, **`errors.py`**, **`canonical.py`** (plus the test vector 1 test), `db.py`, an empty `domain/` tree, `tests/conftest.py`. **Push (W1).** | `docker compose up -d --build` works. Gunee and Huzaifa can pull. |
| **by 11:15** | **Register the public repo URL at the venue desk.** | Volunteer has it |
| 11:10–11:50 | Schema plus `seed/sports.json` and `seed/baseline.json`. `POST /audit/v1/reset` and `GET /health` (200 only when seeded). 413 middleware. 400 override of 422. | Reset twice gives identical data |
| 11:50–12:40 | `POST /audit/v1/sports` (full validation), `POST /audit/v1/leagues`, `POST /audit/v1/events`, `GET /audit/v1/score` (projection for all 3 models, compensation, idempotency, model limits). Wire Gunee's `fixtures.generate` into `/audit/v1/fixtures`. **Push (W2).** | Mystery-sport and compensation tests pass |
| 12:40–13:00 | `/api/v1/auth/login` plus the read routes (leagues, fixtures, matches, clubs, products, standings) **for Huzaifa**. Tell Huzaifa the LAN IP. | The app can log in against the real backend |
| 13:00–13:40 | Checkout, inventory, mock gateway, PDF receipt (reportlab, text `PKR 4500.00`), MinIO upload, domain event to the Redis stream, worker. Run `tools/smoke.py` with 20 threads. **Push (W3).** | 1×201, 19×409, stock 0, reserved 0 |
| 13:40–14:10 | RBAC: `rbac-matrix`, the 7 probes, policy table, JWT verification (alg none, tamper, expiry). `/api/v1/ping` rate limit with Retry-After. Negative tests for every matrix cell. Wire Gunee's `standings.compute` and `roster.*`. | Matrix test is all green |
| 14:10–14:30 | `/audit/v1/offline-sync` and `/api/v1/sync` (one code path). `/api/v1/events`, `/api/v1/roster/transfer`, the pin route, `WS /api/v1/ws`. **Push (W4).** | Re-sending a sync gives all `duplicate` |
| 14:30–14:50 | **Clean-machine test:** `docker compose down -v` then `DAY1_SALT=test docker compose up -d --build`. Time it. Run smoke.py. Hard-coded-sport grep. Run `run_tests.sh` and write an honest `COVERAGE.json`. README with demo accounts. `ADR.md` (8 entries). Merge `TRACEABILITY.md` rows. | Everything in CLAUDE.md §2 checklist ticked |
| **14:55** | **FINAL PUSH.** Check on GitHub that the last commit's time is before 15:05:00. | |
| 15:05→ | Keep `docker compose up` running for the desk check. Run the emulator as a backup device. | |

### Gunee: pure domain modules (Laptop 2 or 3, Python only)
Start at 10:45 in `backend/app/domain/fixtures/` and `tests/unit/`. Code against the `ApiError` signature in AGREED_RULES §3.1, even before Tanzeel's first push lands.

| Time | Task | Done when |
|---|---|---|
| 10:45–11:25 | **round_robin**: circle method, home/away balance, byes, legs=2 mirrored, global round numbers, `RR-L{leg}-R{round}-M{i}`, withdrawals (both policies, double-withdrawn voided), summary counts, 400 on bad input. Tests for n = 2..9, legs 1 and 2. **Push (W1).** | Property tests pass |
| 11:25–12:05 | **single_elim**: exact seed order, byes, propagation, `results`, third-place match `TP`, 400 for an unknown match or winner. **double_elim**: WR/LR/GF ids and counts, routing graph, GF2 conditional/required. Tests for n = 3, 5, 6, 8, 13. | Counts and routing graph asserted |
| 12:05–12:45 | **swiss**: exact round 1, standings plus Buchholz from history, bye rule with fallback candidates, **min-sum-of-score-diff rematch-free pairing by backtracking**, 409 `NO_VALID_PAIRING` with `details.round`, history validation. **Push (W2).** | Brute-force check on small n matches the optimum |
| 12:45–13:35 | **standings.compute**: points, W/D/L (a tiebreak win counts as a win), scored/conceded, diff per model (NRR to 3 decimals with the full-overs rule), h2h for every ordered pair, the recursive `resolve()` with restart-on-split, `resolved_by`, draw_lots (test vector 2: t1, t3, t2), clinched/eliminated/still_possible. **Push (W3).** | 3-way mini-league test passes |
| 13:35–14:20 | **roster.check_and_apply and history**: the 8 checks in exact order, transfer/loan/release effects, captain vacancy, deferred_until_match_end, the loan_return entry written once, as_of. Tell Tanzeel the state shape you need. | One test per error code |
| 14:20–14:45 | Add your rows to `TRACEABILITY.md` (FR-1.3, FR-1.4, FR-2.2 → files → tests). Check coverage ≥ 85% for fixtures, standings and roster. **Push (W4).** | |
| 14:45–15:00 | Help Huzaifa: sync queue tests on the phone, receipt PDF open, bugs. | |

**Fallback:** if Gunee is behind at 13:30, Tanzeel takes `roster history/loan_return` and Gunee finishes the transfer checks only.

### Huzaifa: Flutter app (Laptop 2, physical phone over USB)
Work against **local mock JSON** (copy the response shapes from CLAUDE.md §7) until 12:40, when Tanzeel's `/api/v1` read routes are live. Then switch the repository to the real API.

| Time | Task | Done when |
|---|---|---|
| 10:45–11:20 | After Tanzeel's first push, pull and run `flutter create --org com.nascon --platforms android mobile`. Set minSdk 29, cleartext traffic, theme tokens, `go_router` shell with bottom nav, **SyncStatusBar** in the shell, a Settings screen with the server URL. **Push (W1).** | App runs on the phone |
| 11:20–12:00 | Core: `api_client.dart` (dio, base URL from settings, maps errors to plain text with the AGREED_RULES §5 table), `secure_store.dart` (JWT and device_id), `local_db.dart` (sqflite `cache` and `pending_actions` tables), models. Login screen plus a role-aware home. | Login works against mocks |
| 12:00–12:45 | Fixtures list, Match detail (big score, timeline, pinned product, WS updates), Standings (table plus a status chip **with text**). Cache-first loading. **Push (W2).** | Screens show cached data offline |
| 12:45–13:30 | Club profile (info, roster, staff, venue). Store: catalogue, variant picker, cart, checkout confirmation dialog, receipt view (download the PDF and open it). Tenant logo and colours applied. **Push (W3).** | Judge task B works end to end |
| 13:30–14:15 | Roster management (Manager only: add/transfer/loan/release with confirmation). Scoring entry (Organizer only: score plus compensation). **Offline path:** when offline, write to `pending_actions` in the exact §7.11 format and show "pending". Sync service on reconnect plus a Sync button, per-action result list. *Gunee joins here.* | Judge task C works in airplane mode, including after a force-close |
| 14:15–14:35 | HCI pass, using the CLAUDE.md §11 checklist: 48 dp targets, semantics labels, empty states, no raw codes, 360×640 and rotation, Back works everywhere. **Push (W4).** | |
| 14:35–14:50 | `flutter build apk --release`, copy to `mobile/release/app-release.apk`, install on the phone, smoke-test all 3 judge tasks. **Commit the APK and push.** | APK pushed before 14:55 |

---

## Handoffs (who waits on whom)

| When | From → To | What |
|---|---|---|
| ~11:10 | Tanzeel → all | First push: `errors.py`, `canonical.py`, folder skeleton, compose. Everyone runs `git pull --rebase`. |
| ~11:15 | Tanzeel → Huzaifa | Pushes the hotspot LAN IP. Firewall opened. |
| 11:25 / 12:45 | Gunee → Tanzeel | `fixtures.generate()` ready to wire. Then `standings.compute()`. |
| ~12:40 | Tanzeel → Huzaifa | `/api/v1` login and read routes live. Huzaifa switches from mocks to the real API. |
| ~13:30 | Gunee ↔ Tanzeel | The roster state shape agreed (AGREED_RULES §3.4). |
| ~14:20 | Tanzeel → Huzaifa | `/api/v1/sync`, events, roster and WS live, for the offline test. |
| 14:50 | All → Tanzeel | "My last commit is pushed." Tanzeel checks GitHub before 14:55. |

**Communication:** one group chat. Post a single line when you push something someone else depends on: `pushed: <what>`.

---

## Desk check from 15:15 (10-minute slot, not ready = queued once, then 0)
- **Tanzeel:** backend running on the laptop (`docker compose ps` all healthy). The hotspot is on. Answers backend questions.
- **Huzaifa:** drives the phone. The app is installed, pointed at Tanzeel's IP and logged out. The judge runs tasks A, B and C. Huzaifa demonstrates airplane mode → queue → force-close → reconnect → sync results.
- **Gunee:** has the demo accounts ready (CLAUDE.md §7.2). Watches for errors and explains fixtures and standings if asked.

## After 15:05 Day 1
- **No pushes until 10:15 Day 2.** Review `ADR.md` and `TRACEABILITY.md` together for the viva.
- Day 2 ownership is reassigned after the Part II brief at 10:15. The same folder-ownership rules apply. The history continues from the Day 1 SHA.
