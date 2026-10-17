"""Policy-as-code RBAC (FR-5.1, spec 5.13). Pure: decides from the token principal + resource facts.

principal: {"role", "tenant_id", "league_ids", "club_id", "player_id"}
resource:  {"tenant_id", "league_id"?, "club_id"?, "player_id"?}  (club_id of a player = the player's club)
"""

ROLES = ("super_admin", "league_organizer", "club_manager", "player", "viewer")

# action -> {role: rule}. Super admin is always allowed. Missing role = denied.
POLICY: dict[str, dict[str, str]] = {
    "tenant.create": {},
    "league.fixtures.write": {"league_organizer": "own_league"},
    "league.events.write": {"league_organizer": "own_league"},
    "club.roster.write": {"club_manager": "own_club"},
    "club.products.write": {"club_manager": "own_club"},
    "player.update": {"club_manager": "own_club", "player": "self"},
    "club.read": {r: "same_tenant" for r in ROLES if r != "super_admin"},
    "league.read": {r: "same_tenant" for r in ROLES if r != "super_admin"},
    "store.checkout": {r: "same_tenant" for r in ROLES if r != "super_admin"},
    "match.pin": {"league_organizer": "own_league", "club_manager": "same_tenant"},
    "match.status.write": {"league_organizer": "own_league"},
    "order.manage": {"club_manager": "own_club"},
    "platform.config.read": {},
}


def _rule_ok(rule: str, p: dict, r: dict) -> bool:
    if rule == "same_tenant":
        return True
    if rule == "own_league":
        return r.get("league_id") in (p.get("league_ids") or [])
    if rule == "own_club":
        return r.get("club_id") is not None and r.get("club_id") == p.get("club_id")
    if rule == "self":
        return r.get("player_id") is not None and r.get("player_id") == p.get("player_id")
    return False


def is_allowed(principal: dict, action: str, resource: dict | None = None) -> bool:
    role = principal.get("role")
    if role == "super_admin":
        return True
    rule = POLICY.get(action, {}).get(role)
    if rule is None:
        return False
    resource = resource or {}
    # Tenant isolation is absolute for every non-super-admin rule.
    if "tenant_id" in resource and resource["tenant_id"] != principal.get("tenant_id"):
        return False
    return _rule_ok(rule, principal, resource)
