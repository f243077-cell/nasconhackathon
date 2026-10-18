"""VOD object store (FR-3.2): finished recording segments live in MinIO, addressed as s3://<bucket>/<object>."""
from .. import config


def client():
    import urllib3
    from minio import Minio
    return Minio(config.MINIO_ENDPOINT, access_key=config.MINIO_ACCESS_KEY, secret_key=config.MINIO_SECRET_KEY,
                 secure=False, http_client=urllib3.PoolManager(timeout=5.0, retries=False))


def uri(object_name: str, bucket: str | None = None) -> str:
    return f"s3://{bucket or config.VOD_BUCKET}/{object_name}"


def split(recording_uri: str) -> tuple[str, str] | None:
    """(bucket, object) for an s3:// URI, None for anything else (e.g. a raw disk path from the hook route)."""
    if not recording_uri.startswith("s3://"):
        return None
    bucket, _, obj = recording_uri[len("s3://"):].partition("/")
    return (bucket, obj) if bucket and obj else None


def upload(path: str, object_name: str) -> str:
    c = client()
    if not c.bucket_exists(config.VOD_BUCKET):
        c.make_bucket(config.VOD_BUCKET)
    c.fput_object(config.VOD_BUCKET, object_name, path, content_type="video/mp4")
    return uri(object_name)


def open_stream(recording_uri: str):
    """urllib3 response streaming the object; the caller closes and releases it."""
    parts = split(recording_uri)
    if parts is None:
        return None
    return client().get_object(*parts)
