"""Internal queue consumer: reads structured domain events from the Redis stream (FR-2.3)."""
import json
import logging
import time

import redis

from . import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s worker %(message)s")
log = logging.getLogger("worker")
GROUP = "workers"


def main() -> None:
    r = redis.Redis.from_url(config.REDIS_URL)
    while True:
        try:
            r.xgroup_create(config.DOMAIN_EVENTS_STREAM, GROUP, id="0", mkstream=True)
            break
        except redis.exceptions.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                break
            raise
        except redis.exceptions.ConnectionError:
            time.sleep(1)
    log.info("consuming %s", config.DOMAIN_EVENTS_STREAM)
    while True:
        try:
            batches = r.xreadgroup(GROUP, "worker-1", {config.DOMAIN_EVENTS_STREAM: ">"}, count=50, block=5000)
            for _stream, messages in batches or []:
                for msg_id, fields in messages:
                    etype = fields.get(b"type", b"").decode()
                    data = json.loads(fields.get(b"data", b"{}"))
                    log.info("domain event %s %s", etype, data)
                    r.xack(config.DOMAIN_EVENTS_STREAM, GROUP, msg_id)
        except redis.exceptions.ConnectionError:
            time.sleep(1)


if __name__ == "__main__":
    main()
