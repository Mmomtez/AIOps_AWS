from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

_REQUESTS: dict[str, deque[datetime]] = defaultdict(deque)
WINDOW_SECONDS = 60
MAX_REQUESTS_PER_WINDOW = 10


def assert_not_rate_limited(key: str) -> None:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=WINDOW_SECONDS)
    bucket = _REQUESTS[key]

    while bucket and bucket[0] < cutoff:
        bucket.popleft()

    if len(bucket) >= MAX_REQUESTS_PER_WINDOW:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests. Try again later.")

    bucket.append(now)
