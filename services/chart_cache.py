"""Disk-backed content-addressed PNG cache for chart renders.

Cache key = SHA256(canonical svg_data JSON + system + size + RENDERER_VERSION).
Cross-process singleflight via fcntl.flock (no Redis required).
Cache dir: /var/cache/hellenicstar/charts/<ab>/<cd>/<hash>.png
"""

import fcntl
import hashlib
import json
import logging
import os
import random
import time
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_DIR = Path(os.environ.get("CHART_CACHE_DIR", "/var/cache/hellenicstar/charts"))

# Bump when chart_svg.py or rendering pipeline changes significantly.
# 11: 行星色板分层重排 + 黄道环降饱和 + 度数字号 10.5→12（2026-08）。
#     不升版号的话，已缓存的 PNG 仍是旧配色，用户看不到本次改动。
# 12: 整宫制宫号从宫头线移到每个 30° 宫位扇区的正中（2026-09）。
# 13: 整宫制四轴与行星共用径向信息列和圆周顺延队列（2026-09）。
RENDERER_VERSION = "13"


def _normalise(obj):
    """Recursively normalise dicts/lists/floats for a stable JSON key."""
    if isinstance(obj, dict):
        return {k: _normalise(v) for k, v in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [_normalise(v) for v in obj]
    if isinstance(obj, float):
        return round(obj, 6)
    return obj


def cache_key(svg_data: dict, system: str, size: int) -> str:
    payload = json.dumps(
        {"d": _normalise(svg_data), "s": system, "z": size, "v": RENDERER_VERSION},
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _png_path(key: str) -> Path:
    return CACHE_DIR / key[:2] / key[2:4] / f"{key}.png"


def cache_get(key: str) -> bytes | None:
    try:
        p = _png_path(key)
        return p.read_bytes() if p.exists() else None
    except OSError:
        return None


def cache_put(key: str, png: bytes, lock_dir: Path | None = None) -> None:
    p = _png_path(key)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.parent / f".tmp_{key}_{os.getpid()}"
        tmp.write_bytes(png)
        tmp.rename(p)
    except OSError as e:
        log.warning("chart_cache: write failed for %s: %s", key, e)
        return
    # 1-in-50 chance: sweep stale locks so they don't accumulate indefinitely.
    if lock_dir is not None and random.randint(1, 50) == 1:
        _evict_stale_locks(lock_dir)


def _evict_stale_locks(lock_dir: Path, max_age_seconds: int = 3600) -> None:
    """Delete lock files older than max_age_seconds (guards against crash leaks)."""
    try:
        now = time.time()
        for f in lock_dir.iterdir():
            if f.suffix == ".lock" and (now - f.stat().st_mtime) > max_age_seconds:
                f.unlink(missing_ok=True)
    except OSError:
        pass


def render_with_cache(svg_data: dict, system: str, size: int, render_fn) -> bytes | None:
    """Return cached PNG or render once, with cross-process file lock (singleflight).

    render_fn: callable() → bytes | None
    """
    key = cache_key(svg_data, system, size)

    hit = cache_get(key)
    if hit:
        return hit

    lock_dir = CACHE_DIR / ".locks"
    try:
        lock_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Cache dir not writable (e.g. dev machine) — render directly.
        return render_fn()

    lock_path = lock_dir / f"{key}.lock"
    try:
        with open(lock_path, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                hit = cache_get(key)
                if hit:
                    return hit
                png = render_fn()
                if png:
                    cache_put(key, png, lock_dir=lock_dir)
                return png
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
    except OSError as e:
        log.warning("chart_cache: lock failed, rendering without cache: %s", e)
        return render_fn()
