# DISTRIBUTION.md (Part II): Who Does What (Day 2, Sun Oct 18)

**How the split was chosen.** Part II is **80% backend + automated QA, 20% frontend** (mobile + Guest Web Player).
- Tanzeel owns the stack, media server, every `/audit/v1` Part II route, real-time, `/metrics`, CI and k6.
- Gunee writes the pure-Python domain modules (no Docker needed) and the Selenium suite.
- Huzaifa owns the Guest Web Player (`/web/*` HTML/JS with the 9 `data-testid`s) and the mobile changes + Appium.

| Member | Has | Owns | Weight |
|---|---|---|---|
| **Tanzeel** | Docker, emulator, pulled images | Compose (MediaMTX, Selenium hub + 3 nodes), `/health`, reset additions, stream keys, co-stream route, QR routes + exports + `/q`, guest 403 guard, cart merge route, moderation route + DLQ, `/metrics`, privacy delete, WS/SSE (NFR-1), `tests/k6_load.js`, `.github/workflows/autograde.yml`, `COVERAGE_DAY2.json`, final pushes | Most of the 80% |
| **Gunee** | Python + Flutter | Pure modules + unit tests: `domain/moderation.py`, `domain/costream.py`, `domain/qr.py`, `domain/guest_cart.py`; `tests/selenium/test_guest_grid.py` (3 tests, `pytest -n 3`) | Backend vectors + coverage + Selenium |
| **Huzaifa** | Flutter UI, physical phone | Guest Web Player (`backend/app/web/`): video player (hls.js vendored), live score banner, pinned merch card, guest cart, chat list/input/send, progressive auth modal, WCAG 2.1 AA. Mobile: `nascon://` intent filter, deep-link routing, QR scanner, broadcaster + co-stream UI. `tests/appium/test_mobile_deeplink.py` + Appium 2 on 4723 | The 20% frontend + Appium |

All three read `CLAUDE.md` (this folder) and `AGREED_RULES.md` (this folder) at 10:15.

---

## TONIGHT (before Sun 09:00): prep only. No code commits, no pushes until 10:15.

### Tanzeel
- [ ] **No pushes until 10:15** (overnight rule). Keep the Day 1 SHA (`d92fcbf`) as the base.
- [ ] Decide what to do with the uncommitted multi-tenant work (keep local or commit after 10:15) and **revert the temporary `mobile/` build edits** before any Day 2 commit.
- [ ] Pull `selenium/hub:4.25.0`, `selenium/node-chrome:4.25.0`, `selenium/node-firefox:4.25.0` at home (see `DOCKER_SETUP_LOG.md`); fall back to the pulled `4.24.0` if not possible.
- [ ] Test-run `bluenviron/mediamtx:1.9.1` with ports 1935/8888/8889; publish once from OBS or FFmpeg and play the HLS URL.
- [ ] Install **k6** locally or use `grafana/k6:0.54.0`; install Appium-free tools only (Appium is Huzaifa's laptop).
- [ ] Check RAM: full stack + 3 browser nodes on this laptop.

### Gunee
- [ ] `pip install pytest pytest-xdist selenium` (for `pytest -n 3`).
- [ ] Re-read CLAUDE.md §7.4 (co-stream order), §7.5 (QR routes), §7.6 (cart merge), §7.7 (moderation rules) until exact.
- [ ] Sketch the leetspeak normaliser and flood rules on paper; list test cases for `b@d_w0rd`, `p.0.r.n`, `s!c@m`, `f*u*c*k`, `a$$h0le`, `AAAA`, `!!!`.

### Huzaifa
- [ ] Install **Appium 2** + `uiautomator2` driver; check `http://localhost:4723/status` → `ready: true` with the phone on USB.
- [ ] Warm pub cache for a QR scanner package (e.g. `mobile_scanner`) and a video player (e.g. `video_player`); warm Gradle again.
- [ ] Download **hls.js** (minified) to vendor into `backend/app/web/vendor/` (no CDN at runtime).
- [ ] Sketch the Guest Web Player layout with the 9 `data-testid` elements and 48×48 px targets.

---

## DAY 2 TIMELINE (10:15–14:00, freeze 14:00:00, hard lock 14:05:00)

Push windows: **W1** 10:15–11:30 · **W2** 11:30–12:45 · **W3** 12:45–13:45 · **W4** 13:45–14:00 (grace 14:05). Everyone pushes at least once per window.

### Tanzeel: platform + all Part II audit routes
| Time | Task | Done when |
|---|---|---|
| 10:15–10:45 | Pull on top of the Day 1 SHA; add `DAY2_SALT` to config/compose/`.env.example`; `sign_day2` + the 2 reference vectors as tests; compose: `mediamtx`, `selenium-hub` + 3 nodes; extend `/health`. **Push (W1).** | `docker compose up` all healthy; `:4444/status` ready with 3 nodes |
| 10:45–11:30 | Reset additions (`player-beta-2`, `match-m1` in_progress 1–0, 3 QR mappings, `guest_anon_tok_7721`, empty cart). Guest principal + **403 `GUEST_WRITE_FORBIDDEN`** on `/api/v1/chat`, `/audit/v1/checkout`, `/audit/v1/events`. | Day 1 conformance still 398/398 |
| 11:30–12:15 | `POST /audit/v1/stream/key` (+ MediaMTX auth hook, kick on revoke ≤ 2 s). QR: `GET /audit/v1/qr/{id}`, `?inspect`, exports svg/png/pdf, `GET /q/{code}` 302. Wire Gunee's `qr.py`. **Push (W2).** | Edge case 2 passes |
| 12:15–12:45 | `POST /audit/v1/costream/session` (Gunee's `costream.py`), `POST /audit/v1/guest/cart-merge` (Gunee's `guest_cart.py`), `POST /audit/v1/moderation/test` + DLQ (Gunee's `moderation.py`). | Edge cases 1, 3, 4 pass |
| 12:45–13:20 | `GET /metrics` (5 metrics), `DELETE /audit/v1/privacy/user/{id}`, `/ws/matches/{id}` + SSE (NFR-1 p95 < 500 ms). `tests/k6_load.js` exact profile → `tests/reports/k6-summary.json`. **Push (W3).** | k6: 0% 5xx, p95 < 800 ms |
| 13:20–13:45 | `.github/workflows/autograde.yml`; Day 2 probe script; serve Huzaifa's `/web/*`. | Selenium tests green against the grid |
| 13:45–13:58 | Clean `down -v` → `DAY1_SALT=… DAY2_SALT=… up -d --build`; Day 1 + Day 2 checks; `run_tests.sh` → `COVERAGE.json` + `COVERAGE_DAY2.json`; commit `tests/reports/*`; TRACEABILITY rows. **Push (W4) by 13:59.** | Appendix C ticked |

### Gunee: pure modules + Selenium
| Time | Task | Done when |
|---|---|---|
| 10:15–11:00 | `domain/moderation.py`: normalise, mask `***`, kick list (dedup, order), flood → mute list, rate window rule; tests for every dictionary word and obfuscation. **Push (W1).** | All §7.7 examples exact |
| 11:00–11:40 | `domain/costream.py`: 5-step check order, layout capacity, handoff results; `domain/qr.py`: target route table, entity type from id prefix. **Push (W2).** | Every branch unit-tested |
| 11:40–12:20 | `domain/guest_cart.py`: merge/sum/stock cap, replay vs `GUEST_TOKEN_ALREADY_MERGED`. | Edge case 4 logic covered |
| 12:20–13:30 | `tests/selenium/test_guest_grid.py`: the 3 required tests against `localhost:4444`, JUnit XML → `tests/reports/selenium-report.xml`. **Push (W3).** | `pytest -n 3 tests/selenium/` green |
| 13:30–13:55 | Coverage ≥ 85% for the 4 modules; TRACEABILITY rows. **Push (W4).** | |

### Huzaifa: Guest Web Player + mobile + Appium
| Time | Task | Done when |
|---|---|---|
| 10:15–11:30 | `backend/app/web/`: live page with all 9 `data-testid`s, hls.js player, score banner via WS (no reload), pinned merch, guest cart count, chat list/input/send → 403 → `progressive-auth-modal`. **Push (W1).** | Page loads from `/q/m1-live` with no login modal |
| 11:30–12:30 | WCAG 2.1 AA pass (contrast, Tab/Enter, ARIA on media controls, 48×48 targets); `/web/costream/{id}`, `/web/players/{id}`, `/web/clubs/{id}`, preview/vod/notice pages. **Push (W2).** | Selenium DOM checks pass |
| 12:30–13:30 | Mobile: `nascon` intent filter, deep-link routes (`entity/match-m1`, `stream/cs-session-101`) open the right screen ≤ 2 s without login stop; QR scanner; broadcaster/co-stream UI. **Push (W3).** | `adb shell am start …` works |
| 13:30–13:55 | `tests/appium/test_mobile_deeplink.py` + cross-surface chat test; `tests/reports/appium-report.xml`; build and commit the APK. **Push (W4).** | Appium 4723 `ready: true` |

---

## Handoffs
| When | From → To | What |
|---|---|---|
| ~10:45 | Tanzeel → all | Compose with MediaMTX + grid pushed; `sign_day2` ready |
| ~11:00 | Tanzeel → Huzaifa | `/web/*` route serving `backend/app/web/`; WS score feed URL |
| 11:00 / 11:40 / 12:20 | Gunee → Tanzeel | `moderation.py`, `costream.py` + `qr.py`, `guest_cart.py` |
| ~12:45 | Tanzeel → Gunee | All Part II routes live for the Selenium suite |
| ~13:00 | Huzaifa → Gunee | Final `data-testid` page for Selenium |
| 13:58 | All → Tanzeel | "My last commit is pushed" |

## Desk audit / viva (14:05 onwards)
- **Laptop 1 (Tanzeel):** compose stack, media server, API; answers backend questions.
- **Laptop 2 (Huzaifa):** phone on USB + Appium 4723; demo deep links and co-stream.
- **Laptop 3 (Gunee):** Selenium grid view + k6 run; demo the 3 Selenium tests.
- Viva prep: ADR-9…ADR-16 (AGREED_RULES.md) and the 4 hidden scenarios (CLAUDE.md §9).
