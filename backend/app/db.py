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
ALTER TABLE orders ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS club_id TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS capture_id TEXT;
CREATE TABLE IF NOT EXISTS order_status_log (id BIGSERIAL PRIMARY KEY, order_id TEXT NOT NULL, status TEXT NOT NULL,
  at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS roster_state (league_id TEXT PRIMARY KEY, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS roster_index (player_id TEXT PRIMARY KEY, league_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS roster_requests (request_id TEXT PRIMARY KEY, request TEXT NOT NULL, response TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sync_actions (device_id TEXT NOT NULL, action_id TEXT NOT NULL, result TEXT NOT NULL,
  PRIMARY KEY (device_id, action_id));
CREATE TABLE IF NOT EXISTS stream_keys (stream_key TEXT PRIMARY KEY, player_id TEXT NOT NULL, label TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL, seq BIGSERIAL);
CREATE TABLE IF NOT EXISTS costream_sessions (session_id TEXT PRIMARY KEY, request TEXT NOT NULL, response TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS qr_codes (entity_id TEXT PRIMARY KEY, short_code TEXT UNIQUE NOT NULL,
  scan_count BIGINT NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS qr_scans (entity_id TEXT NOT NULL, device_family TEXT NOT NULL, hour_bucket TEXT NOT NULL,
  scans BIGINT NOT NULL, PRIMARY KEY (entity_id, device_family, hour_bucket));
CREATE TABLE IF NOT EXISTS guest_tokens (guest_token TEXT PRIMARY KEY, status TEXT NOT NULL, user_id TEXT,
  merge_request TEXT, merge_response TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS carts (user_id TEXT NOT NULL, variant_id TEXT NOT NULL, quantity INT NOT NULL,
  PRIMARY KEY (user_id, variant_id));
CREATE TABLE IF NOT EXISTS guest_carts (guest_token TEXT NOT NULL, variant_id TEXT NOT NULL, quantity INT NOT NULL,
  PRIMARY KEY (guest_token, variant_id));
CREATE TABLE IF NOT EXISTS moderation_actions (chat_room_id TEXT NOT NULL, user_id TEXT NOT NULL, kind TEXT NOT NULL,
  seq BIGSERIAL, PRIMARY KEY (chat_room_id, user_id, kind));
CREATE TABLE IF NOT EXISTS chat_messages (chat_room_id TEXT NOT NULL, seq BIGINT NOT NULL, message_id TEXT NOT NULL,
  sender TEXT NOT NULL, text TEXT NOT NULL, flagged BOOLEAN NOT NULL, reason TEXT, created_at TEXT NOT NULL,
  PRIMARY KEY (chat_room_id, seq));
CREATE TABLE IF NOT EXISTS dlq (id BIGSERIAL PRIMARY KEY, event TEXT NOT NULL, attempts INT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS follows (follower_id TEXT NOT NULL, athlete_id TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (follower_id, athlete_id));
CREATE INDEX IF NOT EXISTS follows_athlete ON follows (athlete_id);
CREATE TABLE IF NOT EXISTS vods (vod_id BIGSERIAL PRIMARY KEY, stream_key TEXT NOT NULL, player_id TEXT NOT NULL,
  recording_path TEXT UNIQUE NOT NULL, started_at TEXT, ended_at TEXT NOT NULL);
"""

ALL_TABLES = [
    "meta", "tenants", "sports", "leagues", "matches", "events", "clubs", "players", "users", "products",
    "variants", "price_schedule", "inventory", "discount_codes", "orders", "order_status_log", "roster_state",
    "roster_index", "roster_requests", "sync_actions",
    "stream_keys", "costream_sessions", "qr_codes", "qr_scans", "guest_tokens", "carts", "guest_carts",
    "moderation_actions", "chat_messages", "dlq", "follows", "vods",
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
