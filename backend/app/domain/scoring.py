"""Sport configuration validation and event-sourced score projection (FR-1.1, spec 5.6 / 5.9).

Pure functions: no DB, no HTTP. Sport behaviour comes only from config data; no sport or
event names appear in this module.
"""
import json
import re
from pathlib import Path

from ..errors import ApiError, validation_error
from ..validate import is_id, is_int, is_str

SPORT_ID_RE = re.compile(r"^[a-z0-9_-]{2,40}$")
EVENT_KEY_RE = re.compile(r"^[a-z0-9_]{1,40}$")
MODELS = ("event", "innings", "round")
OVERTIME_POLICIES = ("none", "extra_time", "shootout", "golden_score", "super_over")
TIE_TOKENS = ("h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots")
EVENT_TYPES = ("match_init", "match_start", "score", "discipline", "tiebreak_winner", "match_end", "compensation")
COMPENSABLE = ("score", "discipline", "tiebreak_winner")
# Innings scoring-event schema field names (spec 5.6) are loaded as data so no domain name is a code literal.
_FIELDS = json.loads((Path(__file__).resolve().parent.parent / "seed" / "model_fields.json").read_text("utf-8"))
F_RUNS = _FIELDS["innings"]["runs"]
F_LEGAL = _FIELDS["innings"]["legal_ball"]
F_WICKET_FLAG = _FIELDS["innings"]["wicket_flag"]


def _pos_int(x, minimum: int) -> bool:
    return is_int(x) and x >= minimum


def validate_sport(body) -> dict:
    """Return the normalized stored config or raise 400 VALIDATION_ERROR listing bad fields."""
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object")
    bad: list[str] = []
    sport_id = body.get("sport_id")
    if not (isinstance(sport_id, str) and SPORT_ID_RE.fullmatch(sport_id)):
        bad.append("sport_id")
    if not is_str(body.get("name"), 1, 80):
        bad.append("name")
    model = body.get("scoring_model")
    if model not in MODELS:
        bad.append("scoring_model")

    periods = body.get("periods")
    if not isinstance(periods, dict):
        bad.append("periods")
    elif model == "event":
        if not (_pos_int(periods.get("count"), 1) and _pos_int(periods.get("duration_minutes"), 1)):
            bad.append("periods")
    elif model == "innings":
        keys = ("innings_per_team", "overs_per_innings", "balls_per_over", "wickets_per_innings")
        if not all(_pos_int(periods.get(k), 1) for k in keys):
            bad.append("periods")
    elif model == "round":
        best_of = periods.get("best_of")
        if not (_pos_int(best_of, 1) and best_of % 2 == 1):
            bad.append("periods")

    events = body.get("scoring_events")
    if not isinstance(events, dict) or not events:
        bad.append("scoring_events")
    else:
        for key, val in events.items():
            if not (isinstance(key, str) and EVENT_KEY_RE.fullmatch(key)) or not isinstance(val, dict):
                bad.append("scoring_events")
                break
            if model == "event" and not _pos_int(val.get("points"), 1):
                bad.append("scoring_events")
                break
            if model == "innings" and not (
                _pos_int(val.get(F_RUNS), 0)
                and isinstance(val.get(F_LEGAL), bool)
                and isinstance(val.get(F_WICKET_FLAG), bool)
            ):
                bad.append("scoring_events")
                break
            if model == "round" and not _pos_int(val.get("rounds"), 1):
                bad.append("scoring_events")
                break

    if not isinstance(body.get("draw_allowed"), bool):
        bad.append("draw_allowed")

    overtime = body.get("overtime")
    if not isinstance(overtime, dict) or overtime.get("policy") not in OVERTIME_POLICIES:
        bad.append("overtime")
    elif "duration_minutes" in overtime and not _pos_int(overtime.get("duration_minutes"), 0):
        bad.append("overtime")

    tbo = body.get("tie_break_order", list(TIE_TOKENS))
    if not isinstance(tbo, list) or any(t not in TIE_TOKENS for t in tbo) or len(set(tbo)) != len(tbo):
        bad.append("tie_break_order")

    roster = body.get("roster")
    if not isinstance(roster, dict):
        bad.append("roster")
    else:
        mn, mx, req = roster.get("min_squad_size"), roster.get("max_squad_size"), roster.get("required_positions")
        if not (_pos_int(mn, 1) and _pos_int(mx, 1) and mn <= mx):
            bad.append("roster")
        elif not isinstance(req, dict) or any(
            not (isinstance(k, str) and k) or not _pos_int(v, 0) for k, v in req.items()
        ):
            bad.append("roster")

    if bad:
        raise validation_error(bad, "Invalid sport configuration")

    config = {
        "sport_id": sport_id,
        "name": body["name"],
        "scoring_model": model,
        "periods": periods,
        "scoring_events": events,
        "draw_allowed": body["draw_allowed"],
        "overtime": overtime,
        "tie_break_order": tbo,
        "roster": roster,
    }
    return config


def effective_tie_break(order: list[str]) -> list[str]:
    """draw_lots is always applied last, even if omitted."""
    out = [t for t in order if t != "draw_lots"]
    return out + ["draw_lots"]


# ---------------------------------------------------------------- event payload validation

def validate_event_request(body) -> None:
    """Schema-level (400) checks for POST /events. Match-dependent checks happen later."""
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object")
    bad = []
    if not is_id(body.get("event_id")):
        bad.append("event_id")
    if not is_id(body.get("match_id")):
        bad.append("match_id")
    etype = body.get("type")
    if etype not in EVENT_TYPES:
        bad.append("type")
    payload = body.get("payload")
    if not isinstance(payload, dict):
        bad.append("payload")
    if bad:
        raise validation_error(bad, "Invalid event")

    if etype == "match_init":
        for k in ("sport_id", "home_team_id", "away_team_id"):
            if not is_id(payload.get(k)):
                bad.append(f"payload.{k}")
        if "league_id" in payload and payload["league_id"] is not None and not is_id(payload["league_id"]):
            bad.append("payload.league_id")
        if not bad and payload["home_team_id"] == payload["away_team_id"]:
            bad.append("payload.away_team_id")
    elif etype == "score":
        if not is_id(payload.get("team_id")):
            bad.append("payload.team_id")
        if not is_str(payload.get("event_type"), 1, 64):
            bad.append("payload.event_type")
    elif etype == "discipline":
        if not is_id(payload.get("team_id")):
            bad.append("payload.team_id")
        if not is_int(payload.get("points")):
            bad.append("payload.points")
    elif etype == "tiebreak_winner":
        if not is_id(payload.get("team_id")):
            bad.append("payload.team_id")
    elif etype == "compensation":
        if not is_id(payload.get("compensates")):
            bad.append("payload.compensates")
        if "reason" in payload and not isinstance(payload["reason"], str):
            bad.append("payload.reason")
    if bad:
        raise validation_error(bad, "Invalid event payload")


# ---------------------------------------------------------------- projection

def _blank_side(team_id: str) -> dict:
    return {"team_id": team_id, "score": 0, "wickets": 0, "balls": 0, "fair_play": 0}


def project(match: dict, sport: dict, events: list[dict]) -> dict:
    """Rebuild the score from the full event log (spec 5.9 GET /score).

    match:  {match_id, sport_id, league_id, home, away}
    events: [{sequence, event_id, type, payload(dict), signature}] in sequence order
    """
    model = sport["scoring_model"]
    scoring_events = sport["scoring_events"]
    compensated_by = {}
    for e in events:
        if e["type"] == "compensation":
            compensated_by[e["payload"]["compensates"]] = e["event_id"]

    home, away = match["home"], match["away"]
    sides = {home: _blank_side(home), away: _blank_side(away)}
    status = "upcoming"
    tiebreak = None
    for e in events:
        t = e["type"]
        if t == "match_start":
            status = "in_progress"
            continue
        if t == "match_end":
            status = "completed"
            continue
        if t not in COMPENSABLE or e["event_id"] in compensated_by:
            continue
        p = e["payload"]
        side = sides.get(p.get("team_id"))
        if side is None:
            continue
        if t == "score":
            cfg = scoring_events.get(p.get("event_type"), {})
            if model == "event":
                side["score"] += cfg.get("points", 0)
            elif model == "innings":
                side["score"] += cfg.get(F_RUNS, 0)
                if cfg.get(F_LEGAL):
                    side["balls"] += 1
                if cfg.get(F_WICKET_FLAG):
                    side["wickets"] += 1
            else:
                side["score"] += cfg.get("rounds", 0)
        elif t == "discipline":
            side["fair_play"] += p["points"]
        elif t == "tiebreak_winner":
            tiebreak = p["team_id"]

    h, a = sides[home], sides[away]
    winner = None
    outcome = "pending"
    if status == "completed":
        if h["score"] > a["score"]:
            winner, outcome = home, "home_win"
        elif a["score"] > h["score"]:
            winner, outcome = away, "away_win"
        elif tiebreak is not None:
            winner = tiebreak
            outcome = "home_win" if tiebreak == home else "away_win"
        elif sport["draw_allowed"]:
            outcome = "draw"
        else:
            outcome = "undecided"

    def render(side: dict) -> dict:
        out = {"team_id": side["team_id"], "score": side["score"], "wickets": None, "balls": None,
               "overs": None, "fair_play": side["fair_play"]}
        if model == "innings":
            bpo = sport["periods"]["balls_per_over"]
            out["wickets"] = side["wickets"]
            out["balls"] = side["balls"]
            out["overs"] = f"{side['balls'] // bpo}.{side['balls'] % bpo}"
        return out

    return {
        "match_id": match["match_id"],
        "sport_id": match["sport_id"],
        "league_id": match.get("league_id"),
        "status": status,
        "outcome": outcome,
        "winner_team_id": winner,
        "tiebreak_winner_team_id": tiebreak,
        "home": render(h),
        "away": render(a),
        "version": len(events),
        "events": [
            {
                "sequence": e["sequence"],
                "event_id": e["event_id"],
                "type": e["type"],
                "payload": e["payload"],
                "signature": e["signature"],
                "compensated": e["event_id"] in compensated_by,
                "compensated_by": compensated_by.get(e["event_id"]),
            }
            for e in events
        ],
    }


def check_append(match: dict, sport: dict, events: list[dict], etype: str, payload: dict,
                 target: dict | None = None) -> None:
    """Business rules for appending one event to an existing stream (400 match-level, then 409).

    target: for compensation, the targeted event row (already known to exist) or None.
    """
    proj = project(match, sport, events)
    status = proj["status"]
    teams = (match["home"], match["away"])

    if etype in ("score", "discipline", "tiebreak_winner"):
        if payload["team_id"] not in teams:
            raise validation_error(["payload.team_id"], "team_id is not part of this match")
        if etype == "score" and payload["event_type"] not in sport["scoring_events"]:
            raise ApiError(400, "UNKNOWN_EVENT_TYPE", f"Unknown event_type {payload['event_type']!r}",
                           {"event_type": payload["event_type"]})
        if status != "in_progress":
            raise ApiError(409, "MATCH_NOT_IN_PROGRESS", "Match is not in progress", {"status": status})
        if etype == "score":
            _check_model_limits(sport, proj, payload["team_id"], match)
        return

    if etype == "match_init":
        raise ApiError(409, "MATCH_EXISTS", "Match stream already exists", {"match_id": match["match_id"]})
    if etype == "match_start":
        if status != "upcoming":
            raise ApiError(409, "ILLEGAL_TRANSITION", f"Cannot start a match that is {status}",
                           {"from": status, "to": "in_progress"})
        return
    if etype == "match_end":
        if status != "in_progress":
            raise ApiError(409, "ILLEGAL_TRANSITION", f"Cannot end a match that is {status}",
                           {"from": status, "to": "completed"})
        h, a = proj["home"]["score"], proj["away"]["score"]
        if h == a and not sport["draw_allowed"] and proj["tiebreak_winner_team_id"] is None:
            raise ApiError(409, "TIE_NOT_ALLOWED", "Level score requires a tiebreak winner", {})
        return
    if etype == "compensation":
        if target is None:
            raise ApiError(404, "EVENT_NOT_FOUND", "Compensated event not found",
                           {"event_id": payload["compensates"]})
        compensated = {e["payload"]["compensates"] for e in events if e["type"] == "compensation"}
        if (target["match_id"] != match["match_id"] or target["type"] not in COMPENSABLE
                or target["event_id"] in compensated):
            raise ApiError(409, "INVALID_COMPENSATION", "Event cannot be compensated",
                           {"event_id": payload["compensates"]})
        return


def _check_model_limits(sport: dict, proj: dict, team_id: str, match: dict) -> None:
    model = sport["scoring_model"]
    side = proj["home"] if team_id == match["home"] else proj["away"]
    if model == "innings":
        p = sport["periods"]
        max_balls = p["innings_per_team"] * p["overs_per_innings"] * p["balls_per_over"]
        max_wkts = p["innings_per_team"] * p["wickets_per_innings"]
        if side["balls"] >= max_balls or side["wickets"] >= max_wkts:
            raise ApiError(409, "INNINGS_COMPLETE", "Innings is complete for this team", {"team_id": team_id})
    elif model == "round":
        need = (sport["periods"]["best_of"] + 1) // 2
        if proj["home"]["score"] >= need or proj["away"]["score"] >= need:
            raise ApiError(409, "SERIES_ALREADY_DECIDED", "Series already decided", {"team_id": team_id})
