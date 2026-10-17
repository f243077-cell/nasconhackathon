"""Swiss pairing, one round per call (FR-1.3).

Round 1 is the exact fold (seed i vs seed i+m). Later rounds find a rematch-free
pairing with the minimum sum of |score diff| by memoised branch-and-bound, which is
exact (greedy is not). Scores are doubled internally so all arithmetic is integer.
"""
from __future__ import annotations

import math

from app.domain.fixtures import validate as v
from app.errors import ApiError, validation_error

RESULTS = ("home", "away", "draw")


def _history(p: dict, teams: list[str], rnd: int) -> list[dict]:
    h = p.get("history", [])
    if h is None:
        h = []
    if not isinstance(h, list):
        raise validation_error(["history"])
    seen_rounds = []
    tset = set(teams)
    for entry in h:
        if not isinstance(entry, dict) or not v.is_int(entry.get("round")):
            raise validation_error(["history"])
        bye = entry.get("bye")
        matches = entry.get("matches", [])
        if (bye is not None and bye not in tset) or not isinstance(matches, list):
            raise validation_error(["history"])
        used = {bye} if bye is not None else set()
        for m in matches:
            if not isinstance(m, dict):
                raise validation_error(["history"])
            hm, aw, res = m.get("home"), m.get("away"), m.get("result")
            if hm not in tset or aw not in tset or hm == aw or res not in RESULTS or hm in used or aw in used:
                raise validation_error(["history"])
            used.update((hm, aw))
        seen_rounds.append(entry["round"])
    if sorted(seen_rounds) != list(range(1, rnd)):
        raise validation_error(["history"], "history must contain exactly rounds 1..round-1")
    return sorted(h, key=lambda e: e["round"])


def _scores(teams: list[str], history: list[dict]):
    """Doubled scores, opponents played, bye receivers."""
    score = {t: 0 for t in teams}
    opps: dict[str, list[str]] = {t: [] for t in teams}
    had_bye: set[str] = set()
    for entry in history:
        if entry.get("bye") is not None:
            score[entry["bye"]] += 2
            had_bye.add(entry["bye"])
        for m in entry.get("matches", []):
            h, a, r = m["home"], m["away"], m["result"]
            opps[h].append(a)
            opps[a].append(h)
            if r == "home":
                score[h] += 2
            elif r == "away":
                score[a] += 2
            else:
                score[h] += 1
                score[a] += 1
    return score, opps, had_bye


def _min_cost_pairing(players: list[str], score: dict, played: set) -> list[tuple[str, str]] | None:
    """Exact min sum |score diff| perfect matching avoiding `played` pairs; None if impossible.

    Players are re-sorted by score (stable) so the adjacent-pairs lower bound holds.
    """
    players = sorted(players, key=lambda t: -score[t])
    n = len(players)
    allowed = [[j for j in range(n) if j != i and frozenset((players[i], players[j])) not in played]
               for i in range(n)]
    for i in range(n):
        allowed[i].sort(key=lambda j: (abs(score[players[i]] - score[players[j]]), j))
    diff = [[abs(score[players[i]] - score[players[j]]) for j in range(n)] for i in range(n)]
    INF = float("inf")
    exact: dict[int, tuple] = {}
    lower: dict[int, float] = {}

    def bound(mask: int) -> float:
        """Rematch-free optimum >= unconstrained optimum = adjacent pairs in score order."""
        idx = [i for i in range(n) if mask >> i & 1]
        for i in idx:
            if not any(mask >> j & 1 for j in allowed[i]):
                return INF
        return sum(diff[idx[k]][idx[k + 1]] for k in range(0, len(idx), 2))

    def solve(mask: int, budget: float):
        if mask == 0:
            return 0, ()
        if mask in exact:
            c, pairs = exact[mask]
            return (c, pairs) if c < budget else (INF, None)
        lb = bound(mask)
        if lower.get(mask, 0) >= budget or lb >= budget:
            return INF, None
        i = (mask & -mask).bit_length() - 1
        best, best_pairs, limit = INF, None, budget
        for j in allowed[i]:
            if not mask >> j & 1:
                continue
            c = diff[i][j]
            if c >= limit:
                continue
            sub, sub_pairs = solve(mask & ~(1 << i) & ~(1 << j), limit - c)
            if sub_pairs is not None and c + sub < best:
                best, best_pairs, limit = c + sub, ((i, j),) + sub_pairs, c + sub
                if best <= lb:
                    break
        if best_pairs is not None:
            exact[mask] = (best, best_pairs)
            return best, best_pairs
        lower[mask] = max(lower.get(mask, 0), budget)
        return INF, None

    _, pairs = solve((1 << n) - 1, INF)
    if pairs is None:
        return None
    return [(players[i], players[j]) for i, j in pairs]


def generate(body: dict) -> dict:
    teams = v.teams(body, "swiss")
    p = v.params(body)
    n = len(teams)
    seed = {t: i + 1 for i, t in enumerate(teams)}

    total = p.get("total_rounds")
    if total is None:
        total = math.ceil(math.log2(n))
    if not v.is_int(total) or not 1 <= total <= n - 1:
        raise validation_error(["total_rounds"])
    rnd = p.get("round", 1)
    if rnd is None:
        rnd = 1
    if not v.is_int(rnd) or not 1 <= rnd <= total:
        raise validation_error(["round"])
    history = _history(p, teams, rnd)
    score, opps, had_bye = _scores(teams, history)

    standings_order = sorted(teams, key=lambda t: (-score[t], -sum(score[o] for o in opps[t]), seed[t]))
    standings = [{"rank": i + 1, "team_id": t, "score": score[t] / 2,
                  "buchholz": sum(score[o] for o in opps[t]) / 2} for i, t in enumerate(standings_order)]

    bye = None
    if rnd == 1:
        m = n // 2
        if n % 2:
            bye = teams[-1]
        pairs = [(teams[i], teams[i + m]) for i in range(m)]
    else:
        played = {frozenset((t, o)) for t in teams for o in opps[t]}
        rank = {t: i for i, t in enumerate(standings_order)}
        if n % 2:
            pool = [t for t in teams if t not in had_bye] or teams
            candidates = sorted(pool, key=lambda t: (score[t], -seed[t]))
        else:
            candidates = [None]
        pairs = None
        for cand in candidates:
            rest = sorted((t for t in teams if t != cand), key=lambda t: rank[t])
            pairs = _min_cost_pairing(rest, score, played)
            if pairs is not None:
                bye = cand
                break
        if pairs is None:
            raise ApiError(409, "NO_VALID_PAIRING", "No rematch-free pairing exists", {"round": rnd})
        pairs = [(a, b) if seed[a] < seed[b] else (b, a) for a, b in pairs]

    return {"format": "swiss", "round": rnd, "total_rounds": total,
            "pairings": [{"match_id": f"SW-R{rnd}-M{i}", "home": h, "away": a} for i, (h, a) in enumerate(pairs, 1)],
            "bye": bye, "standings": standings}
