"""Concurrent render requests must both return usable, complete image URLs."""

import asyncio
import base64
import os
from pathlib import Path
import threading
import mcp_server as m


def test_http_expired_chart_is_unavailable_without_another_render(tmp_path, monkeypatch):
    import time
    import httpx
    import mcp_server as m

    monkeypatch.setattr(m, 'CHART_DIR', str(tmp_path))
    digest = 'a' * 64
    image = tmp_path / (digest + '.png')
    image.write_bytes(b'\x89PNG\r\n\x1a\n')
    old = time.time() - 8 * 86400
    os.utime(image, (old, old))

    async def check():
        transport = httpx.ASGITransport(app=m.app, client=('expiry-test', 12345))
        async with httpx.AsyncClient(transport=transport, base_url='http://localhost') as client:
            response = await client.get('/mcp/chart/' + digest + '.png')
            assert response.status_code == 404
            assert response.headers['cache-control'] == 'no-store'
    asyncio.run(check())
    assert not image.exists()


def test_http_lifecycle_removes_expired_files_without_chart_requests(tmp_path):
    # The MCP SDK session manager has one process lifetime. Isolate the lifecycle
    # so other protocol tests can start their own server normally.
    import subprocess
    import sys
    code = """
import asyncio, os, time
from pathlib import Path
import anyio
import mcp_server as m
m.CHART_CLEANUP_INTERVAL_SECONDS = 0.01
async def check():
    async with m.app.router.lifespan_context(m.app):
        await anyio.sleep(0.03)
        image = Path(m.CHART_DIR) / ('b' * 64 + '.png')
        image.write_bytes(b'chart-cache-fixture')
        old = time.time() - 8 * 86400
        os.utime(image, (old, old))
        with anyio.fail_after(2):
            while image.exists():
                await anyio.sleep(0.01)
asyncio.run(check())
"""
    result = subprocess.run([sys.executable, '-c', code],
                            cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, 'MCP_CHART_DIR': str(tmp_path)},
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_identical_uncached_renders_both_publish_complete_images(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "CHART_DIR", str(tmp_path))
    replace = os.replace
    ready = threading.Barrier(2)

    def simultaneous_publish(source, destination):
        if Path(destination).parent == tmp_path:
            ready.wait(timeout=10)
        return replace(source, destination)

    monkeypatch.setattr(os, "replace", simultaneous_publish)

    async def render_twice():
        args = dict(year=1990, month=4, day=15, hour=18, minute=0,
                    location_id="gn:2988507", as_of="2026-10-13", max_age=80)
        return await asyncio.gather(*(m.render_saturn_jupiter_cycles(**args) for _ in range(2)))

    first, second = asyncio.run(render_twice())
    assert first.structuredContent["status"] == second.structuredContent["status"] == "ok"
    assert first.structuredContent["image_url"] == second.structuredContent["image_url"]
    files = list(tmp_path.iterdir())
    assert len(files) == 1 and files[0].suffix == ".png"
    stored = files[0].read_bytes()
    for result in (first, second):
        inline = next(item for item in result.content if item.type == "image")
        assert stored == base64.b64decode(inline.data)
    assert stored.startswith(b"\x89PNG\r\n\x1a\n")
