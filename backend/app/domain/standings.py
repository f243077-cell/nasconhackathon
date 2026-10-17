"""League standings, recomputed from match projections on every call (FR-1.4).

Pure: takes the league config, the sport config and one /score-shaped projection per
fixture; returns the exact /standings response body. Sport-agnostic: the diff rule is
picked from `scoring_model`, never from a sport name.
"""
from __future__ import annotations

import hashlib

ALL_CRITERIA = ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"]


def lots_key(seed, league_id: str, team_id: str) -> str:
    # same recipe as canonical.lots_key (CLAUDE.md §6, test vector 2)
    return hashlib.sha256(f"{seed}|{league_id}|{team_id}".encode("utf-8")).hexdigest()


def _is_played(m: dict) -> bool:
    return m.get("status") == "completed" and m.get("outcome") not in (None, "pending", "undecided")


class _Sides:
    """Per-team view of played matches: (team, opp, my_side, opp_side, my_points, result).

    result is "W", "D" or "L" for that team; a tiebreak_winner win is already a home/away_win.
    """

    def __init__(self, played: list[dict], pts: dict):
        self.rows = []
        for m in played:
            h, a = m["home"], m["away"]
            o = m["outcome"]
            hp = pts["win"] if o == "home_win" else pts["loss"] if o == "away_win" else pts["draw"]
            ap = pts["win"] if o == "away_win" else pts["loss"] if o == "home_win" else pts["draw"]
            hr = "W" if o == "home_win" else "L" if o == "away_win" else "D"
            ar = {"W": "L", "L": "W", "D": "D"}[hr]
            self.rows.append((h["team_id"], a["team_id"], h, a, hp, hr))
            self.rows.append((a["team_id"], h["team_id"], a, h, ap, ar))


def _overs_faced(side: dict, sport: dict) -> float:
    per = sport.get("periods", {})
    bpo = per.get("balls_per_over") or 1
    all_out = per.get("innings_per_team", 1) * per.get("wickets_per_innings", 0)
    if all_out and (side.get("wickets") or 0) >= all_out:
        return per.get("innings_per_team", 1) * per.get("overs_per_innings", 0)
    return (side.get("balls") or 0) / bpo


def _diff(rows: list[tuple], sport: dict):
    """Scored-minus-conceded, or NRR for the innings model, over the given per-team rows."""
    if sport.get("scoring_model") == "innings":
        rs = rc = of = ob = 0.0
        for _, _, me, opp, _, _ in rows:
            rs += me.get("score") or 0
            rc += opp.get("score") or 0
            of += _overs_faced(me, sport)
            ob += _overs_faced(opp, sport)
        return round((rs / of if of else 0.0) - (rc / ob if ob else 0.0), 3)
    return sum((me.get("score") or 0) - (opp.get("score") or 0) for _, _, me, opp, _, _ in rows)


def compute(league: dict, sport: dict, matches: list[dict]) -> dict:
    teams = list(league["teams"])
    pts = {"win": 3, "draw": 1, "loss": 0, **(league.get("points") or {})}
    order = list(league.get("tie_break_order") or sport.get("tie_break_order") or ALL_CRITERIA)
    if "draw_lots" not in order:
        order.append("draw_lots")
    seed = league.get("lots_seed", 42)
    lid = league["league_id"]
    k = league["qualification_spots"]

    played = [m for m in matches if _is_played(m)]
    sides = _Sides(played, pts).rows
    by_team = {t: [r for r in sides if r[0] == t] for t in teams}

    stats = {}
    for t in teams:
        rows = by_team[t]
        won, drawn, lost = (sum(1 for r in rows if r[5] == x) for x in "WDL")
        stats[t] = {
            "team_id": t, "played": len(rows), "won": won, "drawn": drawn, "lost": lost,
            "scored": sum(r[2].get("score") or 0 for r in rows),
            "conceded": sum(r[3].get("score") or 0 for r in rows),
            "diff": _diff(rows, sport), "points": sum(r[4] for r in rows),
            "fair_play": sum(r[2].get("fair_play") or 0 for r in rows),
        }

    def value(crit: str, t: str, group: set):
        if crit in ("h2h_points", "h2h_diff"):
            mini = [r for r in by_team[t] if r[1] in group]
            return sum(r[4] for r in mini) if crit == "h2h_points" else _diff(mini, sport)
        if crit == "overall_diff":
            return stats[t]["diff"]
        if crit == "draw_lots":
            return lots_key(seed, lid, t)
        return stats[t][crit]

    resolved_by: dict[str, str | None] = {t: None for t in teams}

    def resolve(group: list[str]) -> list[str]:
        if len(group) <= 1:
            return group
        gset = set(group)
        for crit in order:
            vals = {t: value(crit, t, gset) for t in group}
            if len(set(vals.values())) == 1:
                continue
            reverse = crit != "draw_lots"  # higher is better, except lots (ascending hash)
            buckets = sorted(set(vals.values()), reverse=reverse)
            out: list[str] = []
            for i, b in enumerate(buckets):
                sub = resolve([t for t in group if vals[t] == b])
                if i < len(buckets) - 1:
                    resolved_by[sub[-1]] = crit
                out += sub
            return out
        return group

    ordered: list[str] = []
    for p in sorted({s["points"] for s in stats.values()}, reverse=True):
        ordered += resolve([t for t in teams if stats[t]["points"] == p])

    remaining = {t: 0 for t in teams}
    for m in matches:
        if not _is_played(m):
            for side in ("home", "away"):
                tid = m[side]["team_id"]
                if tid in remaining:
                    remaining[tid] += 1
    mx = {t: stats[t]["points"] + pts["win"] * remaining[t] for t in teams}

    table = []
    for rank, t in enumerate(ordered, start=1):
        p = stats[t]["points"]
        if sum(1 for x in teams if x != t and mx[x] >= p) < k:
            status = "clinched"
        elif sum(1 for x in teams if x != t and stats[x]["points"] > mx[t]) >= k:
            status = "eliminated"
        else:
            status = "still_possible"
        table.append({"rank": rank, **stats[t], "status": status, "resolved_by": resolved_by[t]})

    h2h = {}
    for a in teams:
        h2h[a] = {}
        for b in teams:
            if a == b:
                continue
            rows = [r for r in by_team[a] if r[1] == b]
            h2h[a][b] = {"played": len(rows), "points": sum(r[4] for r in rows),
                         "scored": sum(r[2].get("score") or 0 for r in rows),
                         "conceded": sum(r[3].get("score") or 0 for r in rows)}

    return {"league_id": lid, "sport_id": league["sport_id"], "qualification_spots": k, "table": table, "h2h": h2h}

