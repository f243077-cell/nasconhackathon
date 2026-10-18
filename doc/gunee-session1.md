# Gunee: Session 1 (Day 1, Sat 17 Oct, 11:36–12:40)

## Done

| Time | Commit | What |
|---|---|---|
| 11:40 | `6b5d9c9` | **Round-robin**: circle method, byes, legs 1/2 (leg 2 mirrored, global round numbers), `RR-L{leg}-R{round}-M{i}`, withdrawals (`forfeit_remaining` / `void_all`, both withdrawn → voided), summary, 400 checks. Also added `errors.py` (Tanzeel later replaced it with his version). **W1 push.** |
| 12:22 | `5a4b93f` | **Single elim** (exact seed order, byes propagated, results in any order, third-place `TP`), **double elim** (WR/LR/GF ids and counts, routing graph, GF2 `conditional` / `required`), **Swiss** (exact round 1, score + Buchholz standings, bye rule with fallback, `NO_VALID_PAIRING` with `details.round`, history validation). Shared bracket engine in `fixtures/bracket.py`. **W2 push.** |
| 12:24 | `fc27b2f` | **Standings** `compute()`: W/D/L points, tiebreak win = win, recursive `resolve()` that restarts at the first criterion after a split (mini-league h2h), `resolved_by`, draw_lots always last (test vector 2 → t1, t3, t2), h2h for every ordered pair, NRR (3 dp, all-out = full overs), clinched / eliminated / still_possible. |
| 12:27 | `519ee8b` | **Roster** `check_and_apply()` + `history()`: the 8 checks in exact order, transfer/loan/release effects, loan counts for the borrower, `deferred_until_match_end` + `blocking_match_id`, auto `loan_return` (who = system) written exactly once. |
| 12:33 | `852f714` | **Swiss speed fix**: own Edmonds blossom matching in `fixtures/matching.py` (exact, O(n³)). Branch-and-bound took 9 s at 64 teams / round 10. Now 64 teams × 63 rounds is ≤ 0.08 s per call. Cross-checked against brute force on 300 random cases. |
| 12:39 | `be2a370` | **Roster matched to Tanzeel's contract** (AGREED_RULES §3.4): `validate_request()`, returns `(body, new_state)`, `next_audit_seq`, input state never mutated. |

- **Tests:** `tests/unit/test_fixtures_round_robin.py`, `test_fixtures_elim.py`, `test_fixtures_swiss.py`, `test_standings.py`, `test_roster_rules.py`. The full suite (including Tanzeel's tests) gives **590 passed** on Python 3.12.
- **Coverage (my files):** fixtures 93–100% per file, standings 99%, roster 99%. All above 85%.
- **Hard-coded sport grep** over `backend/app`: clean.
- **Pulled `main`:** it now has Tanzeel's backend (`44e2552`, `a035f60`, `ad1a115`) and Huzaifa's mobile UI (`437ac18`). Tanzeel's TRACEABILITY.md already has my FR-1.3, FR-1.4 and FR-2.2 rows, so I dropped my duplicate.
- **Laptop setup:** installed Python 3.12 + backend requirements + pytest. Tanzeel's code needs 3.10+; the old 3.9 can't import it.
  - Run tests with `%LOCALAPPDATA%\Programs\Python\Python312\python.exe -m pytest tests/unit -q`.

## Tell Tanzeel
1. `repo/roster.py` raises `DUPLICATE_REQUEST_ID`, which is **not in the spec's error catalogue** (§13). It's probably fine, since the spec doesn't define a request_id clash, but he should know.
2. Roster audit entries hold private keys (`_loan_end_date`, `_returns`) inside the state blob. `history()` removes them from responses. The transfer response's `audit_entry` is already clean.
3. Squad placement is replayed from `audit` plus each player's setup `squad_id`. The `players` records are **not** updated after moves. Use `history()` / `placement()` to get a player's current squad, not `players[pid].squad_id`.

## Interpretations to defend in the viva
- **Double elim:** WRr losers (r ≥ 2) go to `LR(2r-2)` away; LB auto-advances when a slot's source was a bye. GF1 `winner_to` / `loser_to` point to GF2 when `bracket_reset`. GF2 keeps GF1's home/away.
- **Swiss:** a bye only goes to a team that hasn't had one. All candidates fail → 409.
- **Standings:** `fair_play`, `scored` and `overall_diff` use played matches only (completed and not undecided). For the innings model, `h2h_diff` is the NRR over the mini-league matches.

## Open items
- **W3 push (12:45–13:45) still needed.** This file, or the next work, can be that push.
- Two pushed commits (`6b5d9c9`, `5a4b93f`) have a `Co-Authored-By: Claude` trailer. Removing it needs a force push, which is banned by AGREED_RULES §6. Left as is unless the team decides otherwise.
- **Next per DISTRIBUTION.md (13:30+):** help Huzaifa with the mobile offline queue (`pending_actions` in the exact §7.11 format) and sync results.
