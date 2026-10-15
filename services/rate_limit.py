# -*- coding: utf-8 -*-
"""services/rate_limit.py — 固定窗口限流器（SQLite 后端，跨 gunicorn worker 安全）。

设计原则：
  - 不依赖 Redis；用独立 data/rate_limit.db做跨 worker 共享状态。
  - 一次 upsert 完成计数递增，原子性由 SQLite 事务保证。
  - key 格式："{endpoint}:{identifier}"（如 "login:1.2.3.4"）。
  - 窗口：Unix 时间戳整除窗口秒数（固定窗口，不滑动）。
  - 启动和每次请求时清理超过 2 小时的旧窗口。
"""
import os
import sqlite3
import time
from contextlib import contextmanager

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.environ.get('MCP_RATE_LIMIT_DB_PATH', os.path.join(_BASE, 'data', 'rate_limit.db'))

@contextmanager
def _conn():
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()



def init_db():
    with _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS rate_limits (
                key     TEXT    NOT NULL,
                window  INTEGER NOT NULL,
                count   INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (key, window)
            )"""
        )
        # 清理超过 2 小时的旧窗口，防止表无限增长。
        old = int(time.time()) - 7200
        c.execute("DELETE FROM rate_limits WHERE window < ?", (old,))


def _window(now, period):
    return int(now) // period * period


def check_and_increment(key, period, limit, now=None):
    """检查 key 在当前窗口内是否超出 limit，并递增计数。

    返回 (allowed: bool, count: int, reset_at: int)。
    allowed=False 时调用方应返回 429。reset_at 是当前窗口结束的 Unix 时间戳。
    """
    now = now if now is not None else time.time()
    win = _window(now, period)
    with _conn() as c:
        c.execute("DELETE FROM rate_limits WHERE window < ?", (int(now) - 7200,))
        c.execute(
            "INSERT INTO rate_limits(key, window, count) VALUES(?,?,1)"
            " ON CONFLICT(key,window) DO UPDATE SET count=count+1",
            (key, win),
        )
        row = c.execute(
            "SELECT count FROM rate_limits WHERE key=? AND window=?", (key, win)
        ).fetchone()
    count = row["count"] if row else 1
    return count <= limit, count, win + period
