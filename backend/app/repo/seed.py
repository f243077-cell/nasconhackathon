"""POST /audit/v1/reset: wipe all state and re-create the identical baseline (spec 5.5)."""
import hashlib
import json
import os
from pathlib import Path

from ..canonical import canonical
from ..db import ALL_TABLES
from ..errors import validation_error
from ..validate import is_int
from . import events as events_repo
from . import leagues as leagues_repo
from . import roster as roster_repo

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
SPORTS = json.loads((SEED_DIR / "sports.json").read_text(encoding="utf-8"))
BASELINE = json.loads((SEED_DIR / "baseline.json").read_text(encoding="utf-8"))
JERSEY_DEFAULTS = {"var-jersey-001-M": 1, "var-jersey-001-L": 5}


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 120_000)
    return digest.hex() == digest_hex


# Fixed salt so repeated resets produce byte-identical rows.
_DEMO_HASH = hash_password(BASELINE["demo_password"], salt=b"nascon-demo-salt")


def parse_reset_body(body) -> tuple[int, dict]:
    if body is None:
        body = {}
    if not isinstance(body, dict):
        raise validation_error(["body"], "Body must be a JSON object")
    bad = []
    seed = body.get("seed", 42)
    if seed is None:
        seed = 42
    if not is_int(seed):
        bad.append("seed")
    stock = body.get("stock") or {}
    known = set(BASELINE["default_stock"])
    if not isinstance(stock, dict) or any(k not in known or not is_int(v) or v < 0 for k, v in stock.items()):
        bad.append("stock")
    if bad:
        raise validation_error(bad, "Invalid reset body")
    return seed, stock


def reset(conn, body=None) -> dict:
    seed, stock_override = parse_reset_body(body)
    conn.execute("TRUNCATE " + ", ".join(ALL_TABLES) + " RESTART IDENTITY")
    b = BASELINE

    for s in SPORTS:
        conn.execute("INSERT INTO sports (sport_id, config) VALUES (%s, %s)", (s["sport_id"], canonical(s)))
    for t in b["tenants"]:
        conn.execute(
            "INSERT INTO tenants (tenant_id, name, logo_url, primary_color, secondary_color) VALUES (%s,%s,%s,%s,%s)",
            (t["tenant_id"], t["name"], t["logo_url"], t["primary_color"], t["secondary_color"]),
        )
    for c in b["clubs"]:
        conn.execute("INSERT INTO clubs (club_id, tenant_id, name, profile) VALUES (%s,%s,%s,%s)",
                     (c["club_id"], c["tenant_id"], c["name"], json.dumps(c["profile"])))
    for p in b["players"]:
        conn.execute(
            "INSERT INTO players (player_id, club_id, tenant_id, name, position, role) VALUES (%s,%s,%s,%s,%s,%s)",
            (p["player_id"], p["club_id"], p["tenant_id"], p["name"], p["position"], p["role"]),
        )
    for u in b["users"]:
        conn.execute(
            "INSERT INTO users (user_id, email, password_hash, role, tenant_id, display_name, league_ids, club_id, player_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (u["user_id"], u["email"], _DEMO_HASH, u["role"], u["tenant_id"], u["display_name"],
             json.dumps(u["league_ids"]), u["club_id"], u["player_id"]),
        )

    stock = dict(b["default_stock"])
    stock.update(stock_override)
    for prod in b["products"]:
        conn.execute(
            "INSERT INTO products (product_id, tenant_id, club_id, name, type, image_url) VALUES (%s,%s,%s,%s,%s,%s)",
            (prod["product_id"], prod["tenant_id"], prod["club_id"], prod["name"], prod["type"], prod["image_url"]),
        )
        for v in prod["variants"]:
            conn.execute(
                "INSERT INTO variants (variant_id, product_id, size, color, price_minor) VALUES (%s,%s,%s,%s,%s)",
                (v["variant_id"], prod["product_id"], v["size"], v["color"], v["price_minor"]),
            )
            conn.execute("INSERT INTO inventory (variant_id, stock, reserved) VALUES (%s,%s,0)",
                         (v["variant_id"], stock.get(v["variant_id"], 0)))
    for d in b["discount_codes"]:
        conn.execute("INSERT INTO discount_codes (code, percent) VALUES (%s,%s)", (d["code"], d["percent"]))

    conn.execute("INSERT INTO meta (key, value) VALUES ('last_seed', %s)", (str(seed),))

    # Demo leagues for the mobile app (ids prefixed demo-* so they never collide with grader ids).
    for lg in b["leagues"]:
        leagues_repo.register_league(
            conn,
            {"league_id": lg["league_id"], "sport_id": lg["sport_id"], "teams": lg["teams"],
             "fixtures": [{"match_id": f["match_id"], "home": f["home"], "away": f["away"]} for f in lg["fixtures"]],
             "qualification": {"spots": lg["qualification_spots"]}},
            tenant_id=lg["tenant_id"], name=lg["name"], season=lg["season"],
            fixture_meta={f["match_id"]: f for f in lg["fixtures"]},
        )
        for match_id, evs in lg["demo_events"].items():
            for i, (etype, payload) in enumerate(evs, start=1):
                events_repo.append_event(conn, {"event_id": f"{match_id}-e{i}", "match_id": match_id,
                                                "type": etype, "payload": payload})

    roster_repo.seed_demo_roster(conn, b["roster_league"], b["players"])

    conn.execute("INSERT INTO meta (key, value) VALUES ('seeded', '1')")
    shown = {k: stock[k] for k in JERSEY_DEFAULTS}
    shown.update(stock_override)
    return {
        "status": "reset_complete",
        "seed": seed,
        "sports": [s["sport_id"] for s in SPORTS],
        "tenants": [t["tenant_id"] for t in b["tenants"]],
        "stock": shown,
    }
