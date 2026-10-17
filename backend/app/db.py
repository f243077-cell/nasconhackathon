from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

_pool: ConnectionPool | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tenants (tenant_id TEXT PRIMARY KEY, name TEXT NOT NULL, logo_url TEXT,
  primary_color TEXT, secondary_color TEXT);
CREATE TABLE IF NOT EXISTS sports (sport_id TEXT PRIMARY KEY, config TEXT NOT NULL, seq BIGSERIAL);
CREATE TABLE IF NOT EXISTS leagues (league_id TEXT PRIMARY KEY, tenant_id TEXT, name TEXT, season TEXT,
  sport_id TEXT NOT NULL, config TEXT NOT NULL, seq BIGSERIAL);
CREATE TABLE IF NOT EXISTS matches (match_id TEXT PRIMARY KEY, league_id TEXT, sport_id TEXT NOT NULL,
  home TEXT NOT NULL, away TEXT NOT NULL, scheduled_at TEXT, venue TEXT, pinned_product_id TEXT, seq BIGSERIAL);
CREATE TABLE IF NOT EXISTS events (match_id TEXT NOT NULL, sequence INT NOT NULL, event_id TEXT NOT NULL UNIQUE,
  type TEXT NOT NULL, payload TEXT NOT NULL, request TEXT NOT NULL, signature TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY (match_id, sequence));
CREATE TABLE IF NOT EXISTS clubs (club_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL,
  profile TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS players (player_id TEXT PRIMARY KEY, club_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
  name TEXT NOT NULL, position TEXT, role TEXT);
CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
  role TEXT NOT NULL, tenant_id TEXT, display_name TEXT, league_ids TEXT NOT NULL, club_id TEXT, player_id TEXT);
CREATE TABLE IF NOT EXISTS products (product_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, club_id TEXT,
  name TEXT NOT NULL, type TEXT NOT NULL, image_url TEXT, seq BIGSERIAL);
CREATE TABLE IF NOT EXISTS variants (variant_id TEXT PRIMARY KEY, product_id TEXT NOT NULL, size TEXT, color TEXT,
  price_minor BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS price_schedule (variant_id TEXT NOT NULL, effective_at TEXT NOT NULL,
  price_minor BIGINT NOT NULL, PRIMARY KEY (variant_id, effective_at));
CREATE TABLE IF NOT EXISTS inventory (variant_id TEXT PRIMARY KEY, stock INT NOT NULL CHECK (stock >= 0),
  reserved INT NOT NULL DEFAULT 0 CHECK (reserved >= 0));
CREATE TABLE IF NOT EXISTS discount_codes (code TEXT PRIMARY KEY, percent INT NOT NULL);
CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, request TEXT NOT NULL, status TEXT NOT NULL,
  customer_id TEXT, total_minor BIGINT NOT NULL, response TEXT NOT NULL, pdf BYTEA, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_status_log (id BIGSERIAL PRIMARY KEY, order_id TEXT NOT NULL, status TEXT NOT NULL,
  at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS roster_state (league_id TEXT PRIMARY KEY, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS roster_index (player_id TEXT PRIMARY KEY, league_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS roster_requests (request_id TEXT PRIMARY KEY, request TEXT NOT NULL, response TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sync_actions (device_id TEXT NOT NULL, action_id TEXT NOT NULL, result TEXT NOT NULL,
  PRIMARY KEY (device_id, action_id));
"""

ALL_TABLES = [
    "meta", "tenants", "sports", "leagues", "matches", "events", "clubs", "players", "users", "products",
    "variants", "price_schedule", "inventory", "discount_codes", "orders", "order_status_log", "roster_state",
    "roster_index", "roster_requests", "sync_actions",
]


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            config.DATABASE_URL, min_size=2, max_size=20, open=True,
            kwargs={"row_factory": dict_row},
        )
    return _pool


@contextmanager
def tx():
    """One transaction: commit on success, rollback on any exception (including ApiError)."""
    with pool().connection() as conn:
        yield conn


def create_schema(conn) -> None:
    conn.execute(SCHEMA)
