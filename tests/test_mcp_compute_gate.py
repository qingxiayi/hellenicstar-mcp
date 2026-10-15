import asyncio
from contextlib import asynccontextmanager
import json

import pytest


def test_gate_bounds_active_work_and_rejects_when_queue_is_full():
    from services.mcp_compute_gate import ComputeBusy, ComputeGate

    async def scenario():
        gate = ComputeGate(max_active=1, max_waiting=1, wait_timeout_seconds=1)
        first_entered = asyncio.Event()
        release_first = asyncio.Event()
        second_entered = asyncio.Event()

        async def first():
            async with gate.slot("first"):
                first_entered.set()
                await release_first.wait()

        async def second():
            async with gate.slot("second"):
                second_entered.set()

        first_task = asyncio.create_task(first())
        await first_entered.wait()
        second_task = asyncio.create_task(second())
        await asyncio.sleep(0)

        with pytest.raises(ComputeBusy) as rejected:
            async with gate.slot("third"):
                pytest.fail("a full queue must reject before running")
        assert rejected.value.reason == "queue_full"
        assert not second_entered.is_set()

        release_first.set()
        await asyncio.gather(first_task, second_task)
        assert second_entered.is_set()
        assert gate.snapshot() == {"active": 0, "waiting": 0}

    asyncio.run(scenario())


def test_gate_times_out_waiters_and_recovers_capacity():
    from services.mcp_compute_gate import ComputeBusy, ComputeGate

    async def scenario():
        gate = ComputeGate(max_active=1, max_waiting=1, wait_timeout_seconds=0.02)
        first_entered = asyncio.Event()
        release_first = asyncio.Event()

        async def first():
            async with gate.slot("first"):
                first_entered.set()
                await release_first.wait()

        first_task = asyncio.create_task(first())
        await first_entered.wait()

        with pytest.raises(ComputeBusy) as timed_out:
            async with gate.slot("second"):
                pytest.fail("the queued task must time out")
        assert timed_out.value.reason == "queue_timeout"

        release_first.set()
        await first_task
        async with gate.slot("third"):
            assert gate.snapshot() == {"active": 1, "waiting": 0}
        assert gate.snapshot() == {"active": 0, "waiting": 0}

    asyncio.run(scenario())


def test_cancelled_waiter_does_not_consume_queue_capacity():
    from services.mcp_compute_gate import ComputeGate

    async def scenario():
        gate = ComputeGate(max_active=1, max_waiting=1, wait_timeout_seconds=1)
        first_entered = asyncio.Event()
        release_first = asyncio.Event()

        async def first():
            async with gate.slot("first"):
                first_entered.set()
                await release_first.wait()

        async def wait():
            async with gate.slot("cancelled"):
                pytest.fail("cancelled waiter must not run")

        first_task = asyncio.create_task(first())
        await first_entered.wait()
        waiter = asyncio.create_task(wait())
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert gate.snapshot() == {"active": 1, "waiting": 0}

        release_first.set()
        await first_task
        async with gate.slot("replacement"):
            assert gate.snapshot() == {"active": 1, "waiting": 0}

    asyncio.run(scenario())


def test_gate_configuration_is_explicit_and_validated():
    from services.mcp_compute_gate import ComputeGateConfig

    config = ComputeGateConfig.from_env({
        "MCP_COMPUTE_MAX_ACTIVE": "3",
        "MCP_COMPUTE_MAX_WAITING": "7",
        "MCP_COMPUTE_WAIT_TIMEOUT_SECONDS": "12.5",
    })
    assert config.max_active == 3
    assert config.max_waiting == 7
    assert config.wait_timeout_seconds == 12.5

    with pytest.raises(RuntimeError, match="MCP_COMPUTE_MAX_ACTIVE"):
        ComputeGateConfig.from_env({"MCP_COMPUTE_MAX_ACTIVE": "0"})
    with pytest.raises(RuntimeError, match="MCP_COMPUTE_MAX_WAITING"):
        ComputeGateConfig.from_env({"MCP_COMPUTE_MAX_WAITING": "-1"})
    with pytest.raises(RuntimeError, match="MCP_COMPUTE_WAIT_TIMEOUT_SECONDS"):
        ComputeGateConfig.from_env({"MCP_COMPUTE_WAIT_TIMEOUT_SECONDS": "later"})


def test_mcp_compute_tools_use_gate_but_lightweight_tools_bypass_it(monkeypatch):
    import mcp_server as m

    calls = []

    class RecordingGate:
        @asynccontextmanager
        async def slot(self, tool_name):
            calls.append(tool_name)
            yield

    monkeypatch.setattr(m, "MCP_COMPUTE_GATE", RecordingGate())
    result = asyncio.run(m.calculate_natal_chart(
        year=1990, month=4, day=15, hour=18, minute=0,
        location_id="gn:2988507", house_system="placidus"))
    assert result["status"] == "ok"
    assert asyncio.run(m.search_birthplace(query="Paris"))["status"] == "ok"
    assert calls == ["calculate_natal_chart"]


def test_busy_gate_returns_a_retryable_tool_result(monkeypatch):
    import mcp_server as m
    from services.mcp_compute_gate import ComputeBusy

    class BusyGate:
        @asynccontextmanager
        async def slot(self, tool_name):
            raise ComputeBusy("queue_full", retry_after_seconds=15)
            yield

    monkeypatch.setattr(m, "MCP_COMPUTE_GATE", BusyGate())
    blocks = asyncio.run(m.mcp.call_tool("calculate_natal_chart", {
        "year": 1990, "month": 4, "day": 15, "hour": 18, "minute": 0,
        "location_id": "gn:2988507", "house_system": "placidus",
    }))
    result = json.loads(blocks[0].text)
    assert result == {
        "status": "busy",
        "tool": "calculate_natal_chart",
        "reason": "queue_full",
        "error": "MCP 当前计算任务较多，请稍后重试。",
        "retryable": True,
        "retry_after_seconds": 15,
    }
