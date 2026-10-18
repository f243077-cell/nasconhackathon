"""Aggregate a coverage.py JSON report into graded areas.

Usage: coverage_areas.py <coverage.json> [day1|day2]
  day1 (default): the six Part I areas (spec 9.3) -> COVERAGE.json
  day2: the five Part II modules (spec II 7) -> COVERAGE_DAY2.json
"""
import fnmatch
import json
import sys

AREAS = {
    "fixtures": ["app/domain/fixtures/*.py"],
    "scoring": ["app/domain/scoring.py", "app/canonical.py"],
    "standings": ["app/domain/standings.py"],
    "store": ["app/domain/store.py", "app/services/payments.py", "app/services/receipts.py"],
    "roster": ["app/domain/roster.py"],
    "rbac": ["app/auth/*.py"],
}

AREAS_DAY2 = {
    "streaming": ["app/domain/streaming.py"],
    "costream": ["app/domain/costream.py"],
    "qr_guest": ["app/domain/qr.py", "app/domain/guest_cart.py"],
    "moderation_dlq": ["app/domain/moderation.py", "app/domain/notify.py", "app/services/notifier.py"],
    "observability": ["app/services/metrics.py"],
}


def main(path: str, which: str = "day1") -> None:
    files = json.load(open(path, encoding="utf-8"))["files"]
    out = {}
    for area, patterns in (AREAS_DAY2 if which == "day2" else AREAS).items():
        covered = total = 0
        for name, data in files.items():
            norm = name.replace("\\", "/")
            norm = norm[norm.index("app/"):] if "app/" in norm else norm
            if norm.endswith("__init__.py") and data["summary"]["num_statements"] == 0:
                continue
            if any(fnmatch.fnmatch(norm, p) for p in patterns):
                covered += data["summary"]["covered_lines"]
                total += data["summary"]["num_statements"]
        # Honest floor to one decimal: never declare more than measured.
        out[area] = (int(covered * 1000 / total) / 10) if total else 0.0
    print(json.dumps(out))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "day1")
