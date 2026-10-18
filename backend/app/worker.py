"""Internal queue consumer: reads structured domain events from the Redis stream (FR-2.3).
Also indexes finished MediaMTX recordings: upload to MinIO, then repo/athletes.index_recording with the
s3://vods/... URI, so the VOD row points at the object store (FR-3.2)."""
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

import redis

from . import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s worker %(message)s")
log = logging.getLogger("worker")
GROUP = "workers"
RECORDINGS = os.environ.get("RECORDINGS_DIR", "/recordings")
# MediaMTX's image has no shell or curl for runOnRecordSegmentComplete, so the worker watches the shared volume.
# A segment is complete once it has not been written for SEGMENT_IDLE_S (stream ended or segment rolled).
SEGMENT_IDLE_S = 3.0


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def finished_segments(root: str, now: float, seen: set[str]) -> list[tuple[str, str, os.stat_result]]:
    """(mediamtx path "live/<key>", absolute segment path, stat) for every idle, not yet handled segment."""
    out = []
    live = os.path.join(root, "live")
    for key in sorted(os.listdir(live)) if os.path.isdir(live) else []:
        folder = os.path.join(live, key)
        for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
            seg = os.path.join(folder, name)
            if seg in seen:
                continue
            st = os.stat(seg)
            if now - st.st_mtime >= SEGMENT_IDLE_S:
                out.append((f"live/{key}", seg, st))
    return out


def vod_indexer() -> None:
    from .db import tx
    from .repo import athletes as athletes_repo
    from .services import vod_store
    seen: set[str] = set()
    while True:
        try:
            for path, seg, st in finished_segments(RECORDINGS, time.time(), seen):
                uri = vod_store.upload(seg, os.path.relpath(seg, RECORDINGS).replace(os.sep, "/"))
                with tx() as conn:
                    vod = athletes_repo.index_recording(conn, path, uri, _iso(st.st_ctime), _iso(st.st_mtime))
                seen.add(seg)
                log.info("vod %s -> %s", seg, vod and vod.get("vod_id"))
        except Exception as exc:  # noqa: BLE001 - keep indexing after a transient MinIO/DB error
            log.warning("vod indexer: %s", exc)
        time.sleep(1)


def main() -> None:
    threading.Thread(target=vod_indexer, daemon=True).start()
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
