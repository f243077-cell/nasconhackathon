"""Shared elimination-bracket engine: seeding, routing, bye propagation, results.

A slot is either a team id, DEAD (its source produced no team, e.g. the loser
of a bye), or unknown (absent). Matches resolve in a fixpoint loop so `results`
may arrive in any order.
"""
from __future__ import annotations

from app.errors import validation_error

DEAD = object()


def bracket_size(n: int) -> int:
    b = 2
    while b < n:
        b *= 2
    return b


def seed_order(b: int) -> list[int]:
    order = [1, 2]
    while len(order) < b:
        k2 = len(order) * 2
        order = [x for s in order for x in (s, k2 + 1 - s)]
    return order


def new_match(mid: str, bracket: str, rnd: int, idx: int) -> dict:
    return {"match_id": mid, "bracket": bracket, "round": rnd, "index": idx, "home": None, "away": None,
            "home_seed": None, "away_seed": None, "bye": False, "winner": None, "loser": None,
            "winner_to": None, "loser_to": None}


def to(mid: str, slot: str) -> dict:
    return {"match_id": mid, "slot": slot}


def parse_results(p: dict) -> list[tuple[str, str]]:
    res = p.get("results", [])
    if res is None:
        return []
    if not isinstance(res, list):
        raise validation_error(["results"])
    out = []
    for r in res:
        if not isinstance(r, dict) or not isinstance(r.get("match_id"), str):
            raise validation_error(["match_id"])
        if not isinstance(r.get("winner"), str):
            raise validation_error(["winner"])
        out.append((r["match_id"], r["winner"]))
    return out


def seeds_of(teams: list[str]) -> dict[str, int]:
    return {t: i + 1 for i, t in enumerate(teams)}


def seed_first_round(first: list[dict], teams: list[str], b: int, state: dict) -> None:
    """R1 match i takes order entries 2i-1, 2i; lower seed is home; seed > n is a bye."""
    order = seed_order(b)
    n = len(teams)
    for i, m in enumerate(first):
        s1, s2 = sorted((order[2 * i], order[2 * i + 1]))
        m["home"], m["home_seed"] = teams[s1 - 1], s1
        state[(m["match_id"], "home")] = teams[s1 - 1]
        if s2 <= n:
            m["away"], m["away_seed"] = teams[s2 - 1], s2
            state[(m["match_id"], "away")] = teams[s2 - 1]
        else:
            state[(m["match_id"], "away")] = DEAD


def resolve(matches: list[dict], state: dict, results: list[tuple[str, str]], seeds: dict[str, int],
            on_decided=None) -> None:
    """Run byes and results to a fixpoint. `state` maps (match_id, slot) -> team | DEAD."""
    by_id = {m["match_id"]: m for m in matches}
    wanted: dict[str, str] = {}
    for mid, w in results:
        if mid not in by_id:
            raise validation_error(["match_id"], f"unknown match {mid}")
        wanted[mid] = w
    done: set[str] = set()

    def send(dest, team) -> None:
        if dest is None:
            return
        state[(dest["match_id"], dest["slot"])] = team
        if team is not DEAD:
            target = by_id[dest["match_id"]]
            target[dest["slot"]] = team
            target[dest["slot"] + "_seed"] = seeds.get(team)

    changed = True
    while changed:
        changed = False
        for m in matches:
            mid = m["match_id"]
            if mid in done:
                continue
            h, a = state.get((mid, "home")), state.get((mid, "away"))
            if h is None or a is None:
                continue
            if h is DEAD and a is DEAD:
                done.add(mid)
                send(m["winner_to"], DEAD)
                send(m["loser_to"], DEAD)
            elif h is DEAD or a is DEAD:
                done.add(mid)
                m["bye"], m["winner"] = True, (a if h is DEAD else h)
                send(m["winner_to"], m["winner"])
                send(m["loser_to"], DEAD)
            elif mid in wanted:
                w = wanted[mid]
                if w not in (h, a):
                    raise validation_error(["winner"], f"{w} is not in {mid}")
                done.add(mid)
                m["winner"], m["loser"] = w, (a if w == h else h)
                if on_decided:
                    on_decided(m)
                send(m["winner_to"], m["winner"])
                send(m["loser_to"], m["loser"])
            else:
                continue
            changed = True

    for mid, w in wanted.items():
        if by_id[mid]["winner"] != w:
            raise validation_error(["winner"], f"{w} cannot win {mid}")
