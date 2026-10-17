"""Round-robin by the circle method (FR-1.3). Custom code, no fixture libraries."""
from __future__ import annotations

from app.domain.fixtures import validate as v
from app.errors import validation_error

POLICIES = ("void_all", "forfeit_remaining")


def _leg_rounds(teams: list[str]) -> list[tuple[list[tuple[str, str]], list[str]]]:
    """One leg: list of (pairs[(home, away)], byes). Fixed team = arr[0].

    Non-fixed teams visit every position 1..n-1 once, so top-row-as-home gives
    each team |home - away| <= 1; the fixed team alternates home by round parity.
    """
    arr: list = list(teams) + ([None] if len(teams) % 2 else [])
    n = len(arr)
    out = []
    for r in range(n - 1):
        pairs, byes = [], []
        for i in range(n // 2):
            a, b = arr[i], arr[n - 1 - i]
            if i == 0 and r % 2 == 1:
                a, b = b, a
            if a is None or b is None:
                byes.append(a if b is None else b)
            else:
                pairs.append((a, b))
        out.append((pairs, byes))
        arr = [arr[0], arr[-1]] + arr[1:-1]
    return out


def _withdrawals(p: dict, teams: list[str], round_count: int) -> dict[str, int]:
    w = p.get("withdrawals", [])
    if w is None:
        return {}
    if not isinstance(w, list):
        raise validation_error(["withdrawals"])
    out: dict[str, int] = {}
    for item in w:
        if not isinstance(item, dict):
            raise validation_error(["withdrawals"])
        tid, after = item.get("team_id"), item.get("after_round")
        if not isinstance(tid, str) or tid not in teams or tid in out:
            raise validation_error(["team_id"])
        if not v.is_int(after) or not 0 <= after <= round_count:
            raise validation_error(["after_round"])
        out[tid] = after
    return out


def generate(body: dict) -> dict:
    teams = v.teams(body, "round_robin")
    p = v.params(body)
    legs = p.get("legs", 1)
    if legs is None:
        legs = 1
    if not v.is_int(legs) or legs not in (1, 2):
        raise validation_error(["legs"])
    policy = p.get("withdrawal_policy", "forfeit_remaining")
    if policy is None:
        policy = "forfeit_remaining"
    if policy not in POLICIES:
        raise validation_error(["withdrawal_policy"])

    leg1 = _leg_rounds(teams)
    per_leg = len(leg1)
    round_count = per_leg * legs
    withdrawn = _withdrawals(p, teams, round_count)

    def withdrawn_at(team: str, rnd: int) -> bool:
        return team in withdrawn and rnd > withdrawn[team]

    summary = {"total": 0, "scheduled": 0, "forfeit": 0, "voided": 0}
    rounds = []
    for leg in range(1, legs + 1):
        for k, (pairs, byes) in enumerate(leg1):
            rnd = (leg - 1) * per_leg + k + 1
            matches = []
            for idx, (h, a) in enumerate(pairs, start=1):
                if leg == 2:
                    h, a = a, h
                status, awarded = "scheduled", None
                if policy == "void_all":
                    if h in withdrawn or a in withdrawn:
                        status = "voided"
                else:
                    wh, wa = withdrawn_at(h, rnd), withdrawn_at(a, rnd)
                    if wh and wa:
                        status = "voided"
                    elif wh or wa:
                        status, awarded = "forfeit", (a if wh else h)
                summary["total"] += 1
                summary[status] += 1
                matches.append({"match_id": f"RR-L{leg}-R{rnd}-M{idx}", "leg": leg, "home": h, "away": a,
                                "status": status, "awarded_to": awarded})
            rounds.append({"round": rnd, "matches": matches, "byes": list(byes)})

    return {"format": "round_robin", "legs": legs, "team_count": len(teams), "round_count": round_count,
            "rounds": rounds, "summary": summary}
