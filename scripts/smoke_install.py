"""Verify a source installation over real stdio MCP, without a city database."""
import argparse
import asyncio
import base64
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def check(image_path=None):
    # Isolate runtime state and force the coordinate-only path, even on a machine
    # with an installed GeoNames database. All inputs are synthetic.
    with tempfile.TemporaryDirectory(prefix='hellenicstar-smoke-') as tmp:
        env = dict(os.environ, MCP_LOCATION_DB_PATH=str(Path(tmp) / 'absent.db'),
                   MCP_GEO_CACHE_PATH=str(Path(tmp) / 'geocache.db'),
                   CHART_CACHE_DIR=str(Path(tmp) / 'charts'))
        env.pop('AMAP_KEY', None)
        params = StdioServerParameters(command=sys.executable,
                                       args=[str(ROOT / 'mcp_server.py')], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=90)) as session:
                await session.initialize()
                catalog = await session.list_tools()

                async def call(name, arguments):
                    result = await session.call_tool(name, arguments)
                    if result.isError:
                        raise RuntimeError(f'{name}: {result.content}')
                    if result.structuredContent is not None:
                        return result.structuredContent
                    return json.loads(next(c.text for c in result.content if c.type == 'text'))

                place = await call('resolve_birth_coordinates', dict(latitude=48.8566, longitude=2.3522))
                if place.get('status') != 'ok':
                    raise RuntimeError(f'Coordinate resolution failed: {place}')
                birth = dict(year=2000, month=1, day=1, hour=12, minute=0,
                             location_id=place['location_id'], house_system='placidus')
                natal = await call('calculate_natal_chart', birth)
                if natal.get('status') != 'ok':
                    raise RuntimeError(f'Natal calculation failed: {natal}')
                verified = await call('verify_calculation_claims', {
                    'reference': natal['calculation_reference'],
                    'claims': [
                        {'quote': 'Copied status', 'path': '/status', 'value': natal['status']},
                        {'quote': 'Deliberately wrong status', 'path': '/status', 'value': 'wrong'},
                    ],
                })
                expected = dict(supported=1, contradicted=1, unverified=0)
                if verified.get('counts') != expected:
                    raise RuntimeError(f'Claim verification failed: {verified}')
                rendered = await session.call_tool('render_natal_chart', birth)
                if rendered.isError:
                    raise RuntimeError(f'Rendering failed: {rendered.content}')
                png = next((base64.b64decode(c.data, validate=True) for c in rendered.content
                            if c.type == 'image' and c.mimeType == 'image/png'), None)
                if not png or not png.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise RuntimeError('Rendering did not return inline PNG content')
                if image_path:
                    with Path(image_path).open('xb') as output:
                        output.write(png)
                return dict(status='ok', transport='stdio', tool_count=len(catalog.tools),
                            coordinate_resolution='ok', natal_calculation='ok',
                            claim_counts=expected, inline_png_bytes=len(png),
                            image_path=str(Path(image_path).resolve()) if image_path else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', help='Save the synthetic PNG; existing files are never overwritten')
    args = parser.parse_args()
    result = asyncio.run(check(args.image))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
