"""Disk-backed content-addressed PNG cache for chart renders.

Cache key = SHA256(canonical svg_data JSON + system + size + RENDERER_VERSION).
Cross-process singleflight via fcntl.flock (no Redis required).
Cache dir: /var/cache/hellenicstar/charts/<ab>/<cd>/<hash>.png
Managed PNG bytes are bounded; oldest writes are evicted first. TTL is measured
from creation, not last access. These limits are not a filesystem quota.
"""

import fcntl
import hashlib
import json
import logging
import os
import re
import stat
import tempfile
import time
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_DIR = Path(os.environ.get("CHART_CACHE_DIR", "/var/cache/hellenicstar/charts"))


def _env_nonnegative_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
        if value >= 0:
            return value
    except ValueError:
        pass
    log.warning("chart_cache: invalid %s; using default %s", name, default)
    return default


CACHE_MAX_BYTES = _env_nonnegative_int("CHART_CACHE_MAX_BYTES", 512 * 1024 * 1024)
CACHE_TTL_SECONDS = _env_nonnegative_int("CHART_CACHE_TTL_SECONDS", 7 * 86400)
_SWEEP_INTERVAL_SECONDS = 60
_LOCK_STRIPES = 64
_last_sweep = None

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


def _acquire_lock(path: Path):
    """Keep the lock inode in place, including while another process waits."""
    if path.parent.is_symlink():
        raise OSError("chart_cache: linked lock directory is not supported")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    handle = os.fdopen(fd, "r+b")
    try:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise OSError("chart_cache: lock must be a regular file")
        fcntl.flock(handle, fcntl.LOCK_EX)
    except OSError:
        handle.close()
        raise
    return handle  # Closing the handle releases flock, including on exceptions.


def _safe_png_path(path: Path) -> bool:
    # CACHE_DIR itself is operator-selected; its hash subdirectories must stay
    # inside that tree so reads/writes cannot escape the accounted layout.
    for directory in (path.parent.parent, path.parent):
        if directory.is_symlink():
            return False
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except FileNotFoundError:
        return True


def _remove_empty_dirs(path: Path) -> None:
    # Never remove CACHE_DIR, .locks, or anything above the two hash directories.
    for directory in (path.parent, path.parent.parent):
        try:
            directory.rmdir()
        except OSError:
            pass


def _remove_entry(path: Path) -> bool:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return False
    _remove_empty_dirs(path)
    return True


def _entries():
    """Scan only our two-level hash layout, without following symlinked dirs.

    Caller holds the global cache lock, so a matching temporary file is left
    over from an interrupted writer. Top-level public images are unrelated.
    """
    entries = []
    with os.scandir(CACHE_DIR) as first:
        for a in first:
            if not re.fullmatch(r"[0-9a-f]{2}", a.name) or not a.is_dir(follow_symlinks=False):
                continue
            with os.scandir(a.path) as second:
                for b in second:
                    if not re.fullmatch(r"[0-9a-f]{2}", b.name) or not b.is_dir(follow_symlinks=False):
                        continue
                    with os.scandir(b.path) as files:
                        for entry in files:
                            info = entry.stat(follow_symlinks=False)
                            if not stat.S_ISREG(info.st_mode):
                                continue
                            path = Path(entry.path)
                            prefix = a.name + b.name
                            if re.fullmatch(prefix + r"[0-9a-f]{60}\.png", entry.name):
                                entries.append((path, info))
                            elif re.fullmatch(r"\.tmp_" + prefix + r"[0-9a-f]{60}_.+", entry.name):
                                # Failure means storage cannot be accounted for safely.
                                path.unlink()
                    try:
                        Path(b.path).rmdir()
                    except OSError:
                        pass
            try:
                Path(a.path).rmdir()
            except OSError:
                pass
    return entries


def _prune_locked(reserve_bytes: int = 0) -> bool:
    """Make room *before* staging a PNG; fail closed if deletion is denied."""
    global _last_sweep
    cutoff = time.time() - CACHE_TTL_SECONDS
    retained = []
    for path, info in _entries():
        if info.st_mtime <= cutoff and _remove_entry(path):
            continue
        retained.append((path, info))
    total = sum(info.st_size for _, info in retained)
    for path, info in sorted(retained, key=lambda item: (item[1].st_mtime, str(item[0]))):
        if total + reserve_bytes <= CACHE_MAX_BYTES:
            break
        if _remove_entry(path):
            total -= info.st_size
    _last_sweep = ((CACHE_DIR, CACHE_MAX_BYTES, CACHE_TTL_SECONDS), time.monotonic())
    return total + reserve_bytes <= CACHE_MAX_BYTES


def cache_get(key: str) -> bytes | None:
    if CACHE_MAX_BYTES == 0 or CACHE_TTL_SECONDS == 0:
        return None
    try:
        with _acquire_lock(CACHE_DIR / ".locks" / "maintenance.lock"):
            config = (CACHE_DIR, CACHE_MAX_BYTES, CACHE_TTL_SECONDS)
            if (_last_sweep is None or _last_sweep[0] != config
                    or time.monotonic() - _last_sweep[1] >= _SWEEP_INTERVAL_SECONDS):
                _prune_locked()
            p = _png_path(key)
            if not _safe_png_path(p):
                return None
            fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode):
                    return None
                if (info.st_size == 0 or info.st_mtime <= time.time() - CACHE_TTL_SECONDS
                        or info.st_size > CACHE_MAX_BYTES):
                    # Serialized with replace; cannot delete a newer writer's file.
                    _remove_entry(p)
                    return None
                return handle.read()
    except OSError:
        return None


def cache_put(key: str, png: bytes, lock_dir: Path | None = None) -> None:
    # Retain the optional old argument for callers; locks are now fixed stripes.
    if (not png or CACHE_MAX_BYTES == 0 or CACHE_TTL_SECONDS == 0
            or len(png) > CACHE_MAX_BYTES):
        return
    p = _png_path(key)
    try:
        with _acquire_lock(CACHE_DIR / ".locks" / "maintenance.lock"):
            if not _safe_png_path(p):
                return
            if not _prune_locked(reserve_bytes=len(png)):
                return
            tmp = None
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                fd, name = tempfile.mkstemp(prefix=f".tmp_{key}_", dir=p.parent)
                tmp = Path(name)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(png)
                os.replace(tmp, p)
            finally:
                if tmp is not None:
                    tmp.unlink(missing_ok=True)
                _remove_empty_dirs(p)
    except OSError as e:
        log.warning("chart_cache: write failed for %s: %s", key, e)


def render_with_cache(svg_data: dict, system: str, size: int, render_fn) -> bytes | None:
    """Return cached PNG or render once, with cross-process file lock (singleflight).

    render_fn: callable() → bytes | None
    """
    if CACHE_MAX_BYTES == 0 or CACHE_TTL_SECONDS == 0:
        return render_fn()

    key = cache_key(svg_data, system, size)
    hit = cache_get(key)
    if hit is not None:
        return hit

    # A fixed number of persistent inodes bounds lock-file growth. Different
    # keys can share a stripe, but rendering never holds the global cache lock.
    stripe = int(key[:2], 16) % _LOCK_STRIPES
    try:
        lock = _acquire_lock(CACHE_DIR / ".locks" / f"stripe-{stripe:02x}.lock")
    except OSError:
        return render_fn()

    with lock:
        hit = cache_get(key)
        if hit is not None:
            return hit
        # Renderer exceptions must propagate once, not trigger a cache retry.
        png = render_fn()
        if png:
            cache_put(key, png)
        return png
