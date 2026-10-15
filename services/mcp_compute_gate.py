"""Bound concurrent MCP calculations and keep the waiting queue finite.

The gate is process-local. Production currently runs one Uvicorn worker; if that
changes, the configured limits apply to each worker and must be recalculated.
"""

from __future__ import annotations

import asyncio
import math
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ComputeGateConfig:
    max_active: int = 2
    max_waiting: int = 4
    wait_timeout_seconds: float = 15.0

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ComputeGateConfig":
        values = os.environ if environ is None else environ

        def integer(name: str, default: int, minimum: int) -> int:
            raw = values.get(name, str(default))
            try:
                parsed = int(raw)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"{name} must be an integer") from exc
            if parsed < minimum:
                raise RuntimeError(f"{name} must be at least {minimum}")
            return parsed

        def positive_float(name: str, default: float) -> float:
            raw = values.get(name, str(default))
            try:
                parsed = float(raw)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"{name} must be a number") from exc
            if not math.isfinite(parsed) or parsed <= 0:
                raise RuntimeError(f"{name} must be greater than zero")
            return parsed

        defaults = cls()
        return cls(
            max_active=integer("MCP_COMPUTE_MAX_ACTIVE", defaults.max_active, 1),
            max_waiting=integer("MCP_COMPUTE_MAX_WAITING", defaults.max_waiting, 0),
            wait_timeout_seconds=positive_float(
                "MCP_COMPUTE_WAIT_TIMEOUT_SECONDS", defaults.wait_timeout_seconds),
        )


class ComputeBusy(Exception):
    def __init__(self, reason: str, *, retry_after_seconds: int):
        super().__init__(reason)
        self.reason = reason
        self.retry_after_seconds = retry_after_seconds


class ComputeGate:
    """Admit at most ``max_active`` work items plus ``max_waiting`` waiters."""

    def __init__(self, *, max_active: int, max_waiting: int,
                 wait_timeout_seconds: float):
        if max_active < 1:
            raise ValueError("max_active must be at least 1")
        if max_waiting < 0:
            raise ValueError("max_waiting must be at least 0")
        if not math.isfinite(wait_timeout_seconds) or wait_timeout_seconds <= 0:
            raise ValueError("wait_timeout_seconds must be greater than zero")
        self.max_active = max_active
        self.max_waiting = max_waiting
        self.wait_timeout_seconds = wait_timeout_seconds
        self._slots = asyncio.Semaphore(max_active)
        self._state_lock = asyncio.Lock()
        self._admitted = 0
        self._active = 0

    @classmethod
    def from_config(cls, config: ComputeGateConfig) -> "ComputeGate":
        return cls(max_active=config.max_active,
                   max_waiting=config.max_waiting,
                   wait_timeout_seconds=config.wait_timeout_seconds)

    def snapshot(self) -> dict[str, int]:
        return {"active": self._active, "waiting": self._admitted - self._active}

    @asynccontextmanager
    async def slot(self, tool_name: str):
        del tool_name  # Reserved for caller-side operational logging.
        async with self._state_lock:
            if self._admitted >= self.max_active + self.max_waiting:
                raise ComputeBusy(
                    "queue_full",
                    retry_after_seconds=max(1, math.ceil(self.wait_timeout_seconds)),
                )
            self._admitted += 1

        acquired = False
        counted_active = False
        try:
            try:
                await asyncio.wait_for(
                    self._slots.acquire(), timeout=self.wait_timeout_seconds)
            except (TimeoutError, asyncio.TimeoutError) as exc:
                raise ComputeBusy(
                    "queue_timeout",
                    retry_after_seconds=max(1, math.ceil(self.wait_timeout_seconds)),
                ) from exc
            acquired = True
            async with self._state_lock:
                self._active += 1
                counted_active = True
            yield
        finally:
            if acquired:
                self._slots.release()
            async with self._state_lock:
                if counted_active:
                    self._active -= 1
                self._admitted -= 1


def busy_result(tool_name: str, busy: ComputeBusy) -> dict:
    return {
        "status": "busy",
        "tool": tool_name,
        "reason": busy.reason,
        "error": "MCP 当前计算任务较多，请稍后重试。",
        "retryable": True,
        "retry_after_seconds": busy.retry_after_seconds,
    }
