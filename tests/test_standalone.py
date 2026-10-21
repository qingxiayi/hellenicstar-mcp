"""Standalone transport and coordinate-only operation without private services."""
import asyncio
from pathlib import Path
import sys
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_discovery_from_other_working_directory(tmp_path):
    async def check():
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).resolve().parents[1] / 'mcp_server.py')],
            cwd=str(tmp_path),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert len(names) == 45
                assert {'resolve_birth_coordinates', 'get_agent_protocol'} <= names
    asyncio.run(check())


def test_classical_stdio_returns_calculations_without_interpretive_prose():
    async def check():
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).resolve().parents[1] / 'mcp_server.py')],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for system in ('placidus', 'whole_sign'):
                    response = await session.call_tool('calculate_classical_factors', {
                        'year': 1990, 'month': 4, 'day': 15, 'hour': 18, 'minute': 0,
                        'location_id': 'coord:48.856600,2.352200', 'house_system': system,
                    })
                    assert not response.isError
                    result = json.loads(response.content[0].text)
                    assert result['status'] == 'ok'
                    stages = result['sect_light_triplicity']['stages']
                    assert len(stages) == 3
                    for stage in stages:
                        assert set(stage) <= {
                            'stage', 'stage_label', 'planet_cn', 'sign_cn',
                            'house', 'dignity', 'house_type', 'tags',
                        }
                    assert result['lots'][0]['name'] == '福点'
    asyncio.run(check())


def test_coordinate_chart_without_city_db_or_amap(monkeypatch, tmp_path):
    import mcp_server as m
    from services import location_resolver as lr, geocoding
    monkeypatch.setattr(lr.LocationResolver.__init__, '__defaults__', (str(tmp_path / 'absent.db'),))
    monkeypatch.setattr(geocoding, 'AMAP_KEY', '')

    async def check():
        result = await m.resolve_birth_coordinates(latitude=48.8566, longitude=2.3522)
        assert result['status'] == 'ok'
        assert result['timezone'] == 'Europe/Paris'
        chart = await m.calculate_natal_chart(year=1990, month=4, day=15, hour=18, minute=0,
                                             location_id=result['location_id'], house_system='placidus')
        assert chart['status'] == 'ok'
        assert chart['birth_context']['tz_iana'] == 'Europe/Paris'
    asyncio.run(check())


def test_stdio_chart_returns_inline_image_without_unserved_http_link(tmp_path):
    import base64
    async def check():
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).resolve().parents[1] / 'mcp_server.py')],
            cwd=str(tmp_path),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.call_tool('render_natal_chart', {
                    'year': 1990, 'month': 4, 'day': 15, 'hour': 18, 'minute': 0,
                    'location_id': 'coord:48.856600,2.352200', 'house_system': 'placidus',
                })
                assert not response.isError
                result = response.structuredContent or json.loads(response.content[0].text)
                assert result['status'] == 'ok'
                assert 'image_url' not in result
                assert 'image_url' not in (response.meta or {})
                image = next(c for c in response.content if c.type == 'image')
                assert base64.b64decode(image.data).startswith(b'\x89PNG\r\n\x1a\n')
    asyncio.run(check())
