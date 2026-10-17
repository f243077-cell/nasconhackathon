import os

# DAY1_SALT is read only from the environment, never trimmed or decoded (spec 5.3).
DAY1_SALT = os.environ.get("DAY1_SALT", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://nascon:nascon@localhost:5432/nascon")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-dev-jwt-secret")
JWT_TTL_SECONDS = int(os.environ.get("JWT_TTL_SECONDS", "43200"))
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ROOT_USER", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin123")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "receipts")

MAX_BODY_BYTES = 1024 * 1024
RATE_LIMIT_MAX = 100
RATE_LIMIT_WINDOW_S = 10
DOMAIN_EVENTS_STREAM = "domain-events"
REALTIME_CHANNEL = "realtime"
