"""Runs once before uvicorn starts: wait for Postgres, create schema, seed baseline (NFR-7)."""
import logging
import sys
import time

import psycopg

from . import config, db
from .repo import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s bootstrap %(message)s")
log = logging.getLogger("bootstrap")


def main() -> int:
    if not config.DAY1_SALT:
        log.warning("DAY1_SALT is empty; signatures will not match the grader. Set it in the environment.")
    deadline = time.time() + 90
    while True:
        try:
            with psycopg.connect(config.DATABASE_URL, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
            break
        except psycopg.OperationalError as exc:
            if time.time() > deadline:
                log.error("database not reachable: %s", exc)
                return 1
            time.sleep(1)
    with db.tx() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(4242)")
        db.create_schema(conn)
    with db.tx() as conn:
        seed.reset(conn, None)
    log.info("schema ready and baseline seeded")
    db.pool().close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
