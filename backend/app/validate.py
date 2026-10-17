"""Small strict validators. bool is never accepted as int; ids follow spec 5.2."""
import re
from datetime import date, datetime, timezone

ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def is_int(x) -> bool:
    return type(x) is int


def is_id(x) -> bool:
    return isinstance(x, str) and ID_RE.fullmatch(x) is not None


def is_str(x, min_len: int = 1, max_len: int = 10_000) -> bool:
    return isinstance(x, str) and min_len <= len(x) <= max_len


def is_date(x) -> bool:
    if not isinstance(x, str) or not DATE_RE.fullmatch(x):
        return False
    try:
        date.fromisoformat(x)
        return True
    except ValueError:
        return False


def is_ts(x) -> bool:
    if not isinstance(x, str) or not TS_RE.fullmatch(x):
        return False
    try:
        datetime.strptime(x, "%Y-%m-%dT%H:%M:%SZ")
        return True
    except ValueError:
        return False


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
