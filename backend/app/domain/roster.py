"""Roster rules: transfer / loan / release checks and effects, history with auto loan return (FR-2.2).

Pure: no DB. A player's squad on any date is derived by replaying the setup squad plus
the league's audit entries, so loans end by date and nothing is mutated in place.

State shape (loaded by the repo layer for one league):
    {
      "league": {league_id, tenant_id, sport_id, transfer_window:{open, close}, max_squad_size, required_positions},
      "squads": {squad_id: {squad_id, club_id, tenant_id, name}},
      "players": {player_id: {player_id, name, position, squad_id, role}},   # as set up
      "matches_in_progress": [{match_id, home_squad_id, away_squad_id}],
      "audit": [entry, ...],          # this league's entries, insertion order; may hold private "_" keys
      "audit_seq": int,               # entries already issued (global), next id = au-{audit_seq+1:04d}
    }
or None when the league does not exist.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from app.errors import ApiError, validation_error

ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
TYPES = ("transfer", "loan", "release")


def _date(s) -> date | None:
    if not isinstance(s, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _is_id(x) -> bool:
    return isinstance(x, str) and ID_RE.match(x) is not None


def public(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if not k.startswith("_")}


def placement(state: dict, player_id: str, on: date) -> tuple[str | None, str | None]:
    """(current_squad_id, parent_squad_id) of a player on a date."""
    squad, parent = state["players"][player_id].get("squad_id"), None
    for e in state["audit"]:
        if e["player_id"] != player_id or e["action"] == "loan_return":
            continue
        eff = date.fromisoformat(e["effective_date"])
        if eff > on:
            continue
        if e["action"] == "loan":
            end = date.fromisoformat(e["_loan_end_date"])
            if on <= end:
                squad, parent = e["to_squad_id"], e["from_squad_id"]
            else:
                squad, parent = e["from_squad_id"], None
        else:
            squad, parent = e["to_squad_id"], None
    return squad, parent


def _members(state: dict, squad_id: str, on: date) -> list[str]:
    return [p for p in state["players"] if placement(state, p, on)[0] == squad_id]


def _validate(req) -> tuple[date, date | None]:
    if not isinstance(req, dict):
        raise validation_error(["body"])
    bad = [f for f in ("request_id", "league_id", "player_id", "from_squad_id") if not _is_id(req.get(f))]
    if req.get("type") not in TYPES:
        bad.append("type")
    if req.get("type") in ("transfer", "loan") and not _is_id(req.get("to_squad_id")):
        bad.append("to_squad_id")
    eff = _date(req.get("effective_date"))
    if eff is None:
        bad.append("effective_date")
    end = None
    if req.get("type") == "loan":
        end = _date(req.get("loan_end_date"))
        if end is None or (eff is not None and end <= eff):
            bad.append("loan_end_date")
    if not isinstance(req.get("reason"), str):
        bad.append("reason")
    if not isinstance(req.get("requested_by"), str) or not req.get("requested_by"):
        bad.append("requested_by")
    if bad:
        raise validation_error(bad)
    return eff, end


def check_and_apply(state: dict | None, req: dict, now_iso: str) -> tuple[dict, dict]:
    """Returns (201 response body, mutations). Raises ApiError in the spec's 8-step order."""
    eff, end = _validate(req)                                                     # 1
    kind = req["type"]
    if state is None or state["league"]["league_id"] != req["league_id"]:         # 2
        raise ApiError(404, "LEAGUE_NOT_FOUND", "Unknown league", {"league_id": req["league_id"]})
    pid = req["player_id"]
    if pid not in state["players"]:
        raise ApiError(404, "PLAYER_NOT_FOUND", "Unknown player", {"player_id": pid})
    frm, dst = req["from_squad_id"], (req.get("to_squad_id") if kind != "release" else None)
    for sq in (frm, dst):
        if sq is not None and sq not in state["squads"]:
            raise ApiError(404, "SQUAD_NOT_FOUND", "Unknown squad", {"squad_id": sq})
    lg = state["league"]
    for sq in (frm, dst):                                                         # 3
        if sq is not None and state["squads"][sq].get("tenant_id") != lg.get("tenant_id"):
            raise ApiError(409, "CROSS_TENANT_TRANSFER", "Squads must share the league tenant", {"squad_id": sq})
    current, parent = placement(state, pid, eff)
    if current != frm:                                                            # 4
        raise ApiError(409, "NOT_IN_SQUAD", "Player is not in that squad",
                       {"player_id": pid, "current_squad_id": current})
    if kind != "release":                                                         # 5
        win = lg.get("transfer_window") or {}
        lo, hi = _date(win.get("open")), _date(win.get("close"))
        if lo is None or hi is None or not lo <= eff <= hi:
            raise ApiError(409, "TRANSFER_WINDOW_CLOSED", "Outside the transfer window",
                           {"open": win.get("open"), "close": win.get("close")})
    if parent is not None:                                                        # 6
        raise ApiError(409, "PLAYER_ON_LOAN", "Player is on loan", {"player_id": pid, "parent_squad_id": parent})
    if kind != "release":                                                         # 7
        if len([p for p in _members(state, dst, eff) if p != pid]) + 1 > lg["max_squad_size"]:
            raise ApiError(409, "SQUAD_FULL", "Destination squad is full", {"squad_id": dst})
    pos = state["players"][pid].get("position")                                  # 8
    need = (lg.get("required_positions") or {}).get(pos)
    if need:
        left = [p for p in _members(state, frm, eff) if p != pid and state["players"][p].get("position") == pos]
        if len(left) < need:
            raise ApiError(409, "MIN_POSITION_VIOLATION", "Squad would be short of a required position",
                           {"squad_id": frm, "position": pos, "required": need})

    blocking = next((m["match_id"] for m in state.get("matches_in_progress", [])
                     if frm in (m.get("home_squad_id"), m.get("away_squad_id"))), None)
    st = "deferred_until_match_end" if blocking else "active"
    seq = state.get("audit_seq", 0) + 1
    entry = {"audit_id": f"au-{seq:04d}", "action": kind, "player_id": pid, "league_id": lg["league_id"],
             "from_squad_id": frm, "to_squad_id": dst, "effective_date": req["effective_date"], "state": st,
             "who": req["requested_by"], "when": now_iso, "why": req["reason"]}
    if kind == "loan":
        entry["_loan_end_date"] = req["loan_end_date"]
    registration = None
    if kind != "release":
        registration = {"player_id": pid, "league_id": lg["league_id"], "squad_id": dst,
                        "parent_squad_id": frm if kind == "loan" else None, "registration_type": kind,
                        "start_date": req["effective_date"],
                        "loan_end_date": req["loan_end_date"] if kind == "loan" else None, "role": "substitute"}
    body = {"request_id": req["request_id"], "status": "accepted", "state": st, "blocking_match_id": blocking,
            "registration": registration, "audit_entry": public(entry)}
    return body, {"append_audit": [entry], "audit_seq": seq}


def history(state: dict | None, player_id: str, as_of: str, now_iso: str = "") -> tuple[dict, list[dict]]:
    """Returns (200 body, loan_return entries to persist). Each loan_return is written exactly once."""
    on = _date(as_of)
    if on is None:
        raise validation_error(["as_of"])
    if state is None or player_id not in state["players"]:
        raise ApiError(404, "PLAYER_NOT_FOUND", "Unknown player", {"player_id": player_id})
    mine = [e for e in state["audit"] if e["player_id"] == player_id]
    returned = {e.get("_returns") for e in mine if e["action"] == "loan_return"}
    seq = state.get("audit_seq", 0)
    new = []
    for e in mine:
        if e["action"] != "loan" or e["audit_id"] in returned:
            continue
        back = date.fromisoformat(e["_loan_end_date"]) + timedelta(days=1)
        if on >= back:
            seq += 1
            new.append({"audit_id": f"au-{seq:04d}", "action": "loan_return", "player_id": player_id,
                        "league_id": e["league_id"], "from_squad_id": e["to_squad_id"],
                        "to_squad_id": e["from_squad_id"], "effective_date": back.isoformat(), "state": "active",
                        "who": "system", "when": now_iso or f"{back.isoformat()}T00:00:00Z",
                        "why": "Loan ended", "_returns": e["audit_id"]})
    current, parent = placement(state, player_id, on)
    body = {"player_id": player_id, "as_of": as_of, "league_id": state["league"]["league_id"],
            "current_squad_id": current, "parent_squad_id": parent,
            "history": [public(e) for e in mine + new]}
    return body, new
