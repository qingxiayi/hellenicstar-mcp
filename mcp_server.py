"""Standalone MCP entry point with stdio and Streamable HTTP transports.

Run behind HTTPS reverse proxy with `uvicorn mcp_server:app --host 127.0.0.1 --port 5003`.
"""

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, Icon, ImageContent, TextContent, ToolAnnotations
from pydantic import BaseModel, Field, StrictInt, StrictFloat, StrictBool
from typing import Annotated, Literal
from starlette.requests import Request
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.routing import Route
from starlette.middleware.base import BaseHTTPMiddleware

from services.mcp_natal import (calculate_classical_data, calculate_lots_data, calculate_natal_data,
                                calculate_releasing_data, calculate_time_lord_data,
                                render_natal_chart_png, render_jones_pattern_png,
                                search_birthplace as find_birthplace)
from services import mcp_extended as ext
from services import rate_limit
from services.mcp_contract import tool_clarification
from services.mcp_facts import NatalClaim, NatalFactReference, verify_natal_claims_data
from services.mcp_validation import (CONTRACTS, META_CONTRACTS, RENDER_SOURCES,
                                     blocked, validate_meta_output)
from services.mcp_result_facts import (CalculationReference, CalculationClaim,
    checked_result, normalize_arguments, register as register_calculation,
    REGISTRY, verify_calculation_claims_data)
from services.mcp_envelope import calculation_envelope, declared_provenance
from services.mcp_presentation import public_signature, project_result, validate_selection
from services.mcp_agent_protocol import PROMPT_NAME, URI as AGENT_PROTOCOL_URI, protocol_text
from services.mcp_workflow import recommend as recommend_workflow_data
from services.mcp_compute_gate import (ComputeBusy, ComputeGate,
                                       ComputeGateConfig, busy_result)
from algorithm_registry import list_algorithms
from versioning import get_version_info
from services.ephemeris_guard import verify_ephemeris, apply_ephe_path

# Standalone MCP enforces the same ephemeris startup gate as Flask.
verify_ephemeris(strict=True)


rate_limit.init_db()

import anyio.to_thread
import base64
import functools
import hashlib
import inspect
import json
import logging
import os
import re
import tempfile
import time
from contextlib import asynccontextmanager
from html import escape
from urllib.parse import urlsplit

tool_logger = logging.getLogger("mcp.tool_calls")

MCP_COMPUTE_GATE_CONFIG = ComputeGateConfig.from_env()
MCP_COMPUTE_GATE = ComputeGate.from_config(MCP_COMPUTE_GATE_CONFIG)

# Automatically detect Railway or custom public domain
_default_base = f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}" if os.environ.get("RAILWAY_PUBLIC_DOMAIN") else "http://127.0.0.1:5000"
PUBLIC_BASE = os.environ.get("MCP_PUBLIC_BASE", _default_base).rstrip("/")
CHART_DIR = os.environ.get(
    "MCP_CHART_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "mcp_charts"))
CHART_TTL_SECONDS = 7 * 86400
CHART_CLEANUP_INTERVAL_SECONDS = 60
SUPPORT_URL = os.environ.get("MCP_SUPPORT_URL", "").strip()
SOURCE_URL = os.environ.get("MCP_SOURCE_URL", "").strip()
for _url in (SUPPORT_URL, SOURCE_URL):
    if _url and (urlsplit(_url).scheme not in {"https", "http"} or not urlsplit(_url).netloc):
        raise RuntimeError("MCP_SUPPORT_URL and MCP_SOURCE_URL must be absolute HTTP(S) URLs")
WHEEL_WIDGET_URI = "ui://widget/chart-wheel.html"
WHEEL_META = {
    "openai/outputTemplate": WHEEL_WIDGET_URI,
    "ui": {"resourceUri": WHEEL_WIDGET_URI},
    "openai/toolInvocation/invoking": "正在绘制星盘",
    "openai/toolInvocation/invoked": "星盘已生成",
}


READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                            idempotentHint=True, openWorldHint=False)


ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static_mcp", "icon.png")

mcp = FastMCP(
    "hellenicstar-natal",
    website_url=PUBLIC_BASE,
    icons=[Icon(src=f"{PUBLIC_BASE}/mcp/icon.png", mimeType="image/png", sizes=["512x512"])],
    instructions=(
        "Use get_capabilities to discover the current tools and get_agent_protocol for the full usage rules. "
        "Use recommend_workflow when the user's requested technique needs routing; ask them to choose if it returns needs_clarification. "
        "Only calculate a natal chart when the user supplies an exact birth date and time. "
        "Search for the birthplace, or call resolve_birth_coordinates for WGS84 coordinates. "
        "Use the returned location_id for all chart tools; ask the user to choose if a place is ambiguous. "
        "Never guess a missing time or a daylight-saving fold. "
        "When required_fields or clarification is returned, ask the user for those values and retry; "
        "never invent missing minutes or silently choose a house system or solar-return location. "
        "Reuse choices already explicitly supplied by the user, without asking again. "
        "For natal interpretations, first call calculate_natal_chart and keep its fact_reference unchanged. "
        "Before presenting the interpretation, submit its natal sign, house, retrograde and aspect "
        "assertions as structured claims with exact draft quotes to verify_natal_claims. "
        "Correct contradicted claims and identify unverified claims. The verifier checks only the "
        "submitted structured facts, not the wording, omitted claims or psychological interpretation; "
        "never describe a whole report as verified. "
        "For all other data interpretations, keep calculation_reference unchanged and call verify_calculation_claims "
        "with the draft facts and exact source paths. Correct conflicts and reverify. Never use validation_failed results. "
        "Present the returned data as astronomical chart data, not predictions. "
        "Use render_natal_chart for a full wheel, or render_jones_pattern for the Jones distribution ring, only when requested. "
        "Timing tools return period tables for one reference date (as_of, YYYY-MM-DD); "
        "describe them as traditional time-lord techniques, never as guaranteed events."
    ),
    host="0.0.0.0",
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


def _publish_png(png: bytes) -> str:
    """Store a rendered wheel under its content hash and return its public URL."""
    os.makedirs(CHART_DIR, exist_ok=True)
    _cleanup_expired_charts()
    digest = hashlib.sha256(png).hexdigest()
    path = os.path.join(CHART_DIR, digest + ".png")
    if not os.path.exists(path):
        # Each concurrent request owns its staging file. The final content hash
        # is shared; replacing it atomically with identical bytes is safe.
        fd, tmp = tempfile.mkstemp(dir=CHART_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(png)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return f"{PUBLIC_BASE}/mcp/chart/{digest}.png"


def _cleanup_expired_charts() -> None:
    """Delete expired PNGs; ignore other files and concurrent removals."""
    if not os.path.isdir(CHART_DIR):
        return
    cutoff = time.time() - CHART_TTL_SECONDS
    for name in os.listdir(CHART_DIR):
        if not re.fullmatch(r"[0-9a-f]{64}\.png", name):
            continue
        full = os.path.join(CHART_DIR, name)
        try:
            if os.path.getmtime(full) <= cutoff:
                os.remove(full)
        except OSError:
            pass


async def _chart_cleanup_loop():
    while True:
        await anyio.to_thread.run_sync(_cleanup_expired_charts)
        await anyio.sleep(CHART_CLEANUP_INTERVAL_SECONDS)


_IMAGE_HTTP_ENABLED = True


def _wheel_result(info: dict, png: bytes | None, title: str) -> CallToolResult:
    """Show the wheel to the user through the widget and pass the image to the model."""
    if png and not png.startswith(b'\x89PNG\r\n\x1a\n'):
        info, png = blocked('render', [{'path':'/image','rule':'png_signature'}]), None
    if not png:
        return CallToolResult(content=[TextContent(type="text",
                                                   text=json.dumps(info, ensure_ascii=False))],
                              structuredContent=info)
    data = {**info, "title": title, "mime_type": "image/png"}
    meta = {"title": title}
    if _IMAGE_HTTP_ENABLED:
        url = _publish_png(png)
        data["image_url"] = url
        meta["image_url"] = url
    else:
        data["image_delivery"] = "inline"
        data["display_instruction"] = (
            "Display the attached MCP image content. No HTTP image URL is served in stdio mode. "
            "Do not invent a URL; if this client cannot display MCP images, state that limitation."
        )
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False)),
                 ImageContent(type="image", data=base64.b64encode(png).decode(),
                              mimeType="image/png")],
        structuredContent=data,
        _meta=meta)


@mcp.resource(WHEEL_WIDGET_URI, name="chart-wheel", mime_type="text/html+skybridge",
              meta={"openai/widgetDescription": "Shows the rendered chart wheel image.",
                    "openai/widgetPrefersBorder": True,
                    "openai/widgetCSP": {"connect_domains": [],
                                         "resource_domains": [PUBLIC_BASE]}})
def chart_wheel_widget() -> str:
    return """<div id="wheel" style="text-align:center;font:14px sans-serif;min-height:40px"></div>
<script>
(function () {
  var PREFIX = "%s/mcp/chart/";
  var shown = "";
  var root = document.getElementById("wheel");
  function pick(o) { return o && typeof o.image_url === "string" && o.image_url.indexOf(PREFIX) === 0 ? o : null; }
  function show(o) {
    if (!o || o.image_url === shown) return;
    shown = o.image_url;
    root.textContent = "";
    var img = document.createElement("img");
    img.alt = o.title || "星盘";
    img.style.cssText = "width:100%%;max-width:720px;height:auto;display:block;margin:0 auto";
    img.onerror = function () {
      root.textContent = "";
      var a = document.createElement("a");
      a.href = o.image_url; a.target = "_blank"; a.rel = "noopener";
      a.textContent = "打开星盘图";
      root.appendChild(a);
    };
    img.src = o.image_url;
    root.appendChild(img);
  }
  function fromGlobals() {
    var oa = window.openai || {};
    show(pick(oa.toolOutput) || pick(oa.toolResponseMetadata));
  }
  window.addEventListener("openai:set_globals", function (e) {
    var g = (e && e.detail && e.detail.globals) || {};
    show(pick(g.toolOutput) || pick(g.toolResponseMetadata));
    fromGlobals();
  });
  window.addEventListener("message", function (e) {
    var d = e && e.data;
    if (d && d.method === "ui/notifications/tool-result" && d.params) {
      show(pick(d.params.structuredContent) || pick(d.params._meta));
    }
  });
  fromGlobals();
  var tries = 0;
  var timer = setInterval(function () {
    fromGlobals();
    if (shown || ++tries > 120) clearInterval(timer);
  }, 250);
})();
</script>""" % PUBLIC_BASE


def _invoke_calculation(fn, arguments):
    """Swiss Ephemeris state is per worker thread; startup alone is insufficient.

    A cached natal calculation may skip engine initialization on a new thread.
    Set the canonical path before BOTH source checks and the original tool body.
    """
    apply_ephe_path()
    return fn(**arguments)


def tool(**options):
    """Register a tool that runs off the event loop.

    FastMCP awaits async tools but calls sync ones inline, so one slow chart scan
    would stall every other request on this single-worker service. Each tool body
    therefore runs in a worker thread; functools.wraps keeps the original
    signature, which is what FastMCP reads to build the input schema.
    """
    def decorate(fn):
        signature = inspect.signature(fn)
        selectable = fn.__name__ in CONTRACTS
        protected_compute = (
            fn.__name__ in (set(CONTRACTS) - {"search_birthplace", "resolve_birth_coordinates"})
            or fn.__name__ in RENDER_SOURCES
            or fn.__name__ in {"verify_natal_claims", "verify_calculation_claims", "prepare_relationship_observation_note"}
        )
        if fn.__name__ in CONTRACTS:
            register_calculation(fn)
            if fn.__name__ != 'calculate_natal_chart':
                options['description'] = options.get('description', '') + (
                    ' Server checks run before successful results are returned. Before interpreting this data, '
                    'call verify_calculation_claims with its unchanged calculation_reference and draft source-field claims. '
                    'Correct contradicted facts and reverify before the final answer. Psychological interpretations are not checked.')
        elif (fn.__name__ not in RENDER_SOURCES and fn.__name__ not in META_CONTRACTS
              and fn.__name__ not in {'verify_natal_claims', 'verify_calculation_claims'}):
            raise RuntimeError('MCP tool requires an explicit output contract: ' + fn.__name__)
        @functools.wraps(fn)
        async def run_in_thread(**arguments):
            # Operational evidence only: never log inputs, quotes or chart data.
            tool_logger.info("tool_started name=%s", fn.__name__)
            detail_level = arguments.pop('detail_level', 'full') if selectable else 'full'
            include = arguments.pop('include', None) if selectable else None
            if selectable:
                invalid_selection = validate_selection(detail_level, include)
                if invalid_selection:
                    return invalid_selection
            bound = signature.bind_partial(**arguments)
            bound.apply_defaults()
            arguments = normalize_arguments(bound.arguments, tool=fn.__name__)
            clarification = tool_clarification(fn.__name__, arguments, signature.parameters)
            if clarification:
                if fn.__name__.startswith("render_"):
                    return _wheel_result(clarification, None, "")
                return clarification

            async def execute():
                source = None
                if fn.__name__ in RENDER_SOURCES:
                    source_name = RENDER_SOURCES[fn.__name__]
                    source_fn = REGISTRY[source_name]
                    source_args = {k:v for k,v in arguments.items() if k in inspect.signature(source_fn).parameters}
                    if fn.__name__ == 'render_jones_pattern': source_args['house_system'] = 'placidus'
                    if fn.__name__ == 'render_solar_arc_biwheel': source_args['wheel_age'] = arguments.get('age')
                    source_bound = inspect.signature(source_fn).bind_partial(**source_args)
                    source_bound.apply_defaults()
                    source_args = normalize_arguments(source_bound.arguments, tool=source_name)
                    raw_source = await anyio.to_thread.run_sync(_invoke_calculation, source_fn, source_args)
                    source = checked_result(source_name, raw_source, source_args)
                    if source.get('status') != 'ok': return _wheel_result(source, None, '')
                result = await anyio.to_thread.run_sync(_invoke_calculation, fn, arguments)
                if fn.__name__ in CONTRACTS:
                    result = checked_result(fn.__name__, result, arguments)
                elif fn.__name__ in META_CONTRACTS:
                    issues = (validate_meta_output(fn.__name__, result)
                              if result.get('status') == 'ok' or fn.__name__ not in ('recommend_workflow', 'prepare_relationship_observation_note')
                              else [])
                    if issues:
                        result = {'status': 'validation_failed', 'tool': fn.__name__,
                                  'error': '元数据未通过服务器检查。', 'issues': issues}
                elif source and isinstance(result, CallToolResult) and result.structuredContent.get('status') == 'ok':
                    data = {**result.structuredContent, 'calculation_source': source,
                            'quality': {'status':'passed', 'scope':'numerical_source_and_png_signature',
                                        'image_semantics_checked':False}}
                    result.structuredContent = data
                    result.content[0] = TextContent(type='text', text=json.dumps(data,ensure_ascii=False))
                if isinstance(result, CallToolResult):
                    if isinstance(result.structuredContent, dict) and result.structuredContent.get('status') == 'ok':
                        data = {**result.structuredContent,
                                'calculation_envelope': calculation_envelope(fn.__name__, arguments)}
                        result.structuredContent = data
                        result.content[0] = TextContent(type='text', text=json.dumps(data, ensure_ascii=False))
                elif isinstance(result, dict) and result.get('status') == 'ok':
                    result = {**result, 'calculation_envelope': calculation_envelope(fn.__name__, arguments)}
                if selectable and isinstance(result, dict):
                    result = project_result(result, detail_level, include)
                tool_logger.info("tool_completed name=%s", fn.__name__)
                return result

            if not protected_compute:
                return await execute()
            try:
                async with MCP_COMPUTE_GATE.slot(fn.__name__):
                    return await execute()
            except ComputeBusy as busy:
                data = busy_result(fn.__name__, busy)
                state = MCP_COMPUTE_GATE.snapshot() if hasattr(MCP_COMPUTE_GATE, 'snapshot') else {}
                tool_logger.warning("tool_busy name=%s reason=%s active=%s waiting=%s",
                                    fn.__name__, busy.reason,
                                    state.get('active', '?'), state.get('waiting', '?'))
                if fn.__name__.startswith("render_"):
                    return _wheel_result(data, None, "")
                return data
        if selectable:
            run_in_thread.__signature__ = public_signature(signature)
            options['description'] = options.get('description', '') + (
                ' Optional detail_level=summary previews object/nested rows (up to five), preserves complete scalar membership lists, and marks truncation; '
                'include selects top-level content fields. Omit both for the original full result. '
                'Verification references always identify the complete checked calculation.')
        registered = mcp.tool(**options)(run_in_thread)
        if selectable:
            # FastMCP has captured the public schema. Keep Python introspection
            # compatible with callers that inspect the original calculation API.
            run_in_thread.__signature__ = signature
        return registered
    return decorate


@tool(annotations=READ_ONLY, description="Search birthplace candidates and return canonical location IDs, regions and timezones. Ask the user to choose when multiple locations match.")
def search_birthplace(query: str) -> dict:
    return find_birthplace(query)


@tool(annotations=READ_ONLY, description="Resolve WGS84 decimal latitude and longitude into a reusable location_id and IANA timezone. Use this when the user gives coordinates instead of a city; then pass location_id to any natal, timing, relationship or chart tool. Daylight-saving offset is calculated later from the birth date and local time.")
def resolve_birth_coordinates(latitude: float, longitude: float) -> dict:
    from services.location_resolver import LocationResolver, coordinate_location_id
    try:
        location_id = coordinate_location_id(latitude, longitude)
        snap = LocationResolver().resolve(location_id=location_id)
        if snap is None:
            return {"status": "not_found", "error": "无法从经纬度确定时区，请核对坐标"}
        return {"status": "ok", "location_id": location_id,
                "lat": snap.lat_wgs84, "lng": snap.lng_wgs84,
                "timezone": snap.tz_iana, "coordinate_datum": "WGS84"}
    except ValueError as exc:
        return {"status": "invalid_input", "error": str(exc)}


@tool(annotations=READ_ONLY, description="Calculate a tropical natal chart data table from an exact local birth date and time and a selected location_id. Choose placidus or whole_sign houses. If a repeated civil time is ambiguous, ask the user to choose fold 0 or 1 and call again. Do not guess an unknown birth time. For any natal interpretation, REQUIRED NEXT STEP before the final answer: call verify_natal_claims with this result's unchanged fact_reference and the draft's sign, house, retrograde and aspect claims. Correct contradicted claims and identify unverified ones before presenting the interpretation.")
def calculate_natal_chart(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, house_system: str | None = None,
    fold: StrictInt | None = None
) -> dict:
    return calculate_natal_data(year=year, month=month, day=day, hour=hour,
                                minute=minute, location_id=location_id,
                                house_system=house_system, fold=fold)


@tool(annotations=READ_ONLY, description="Calculate a deterministic natal structure graph from an exact civil birth time and selected location_id. Includes traditional and modern dispositor paths with ten origins, cycles, receptions, aspects, motifs, both house systems, conditions and dependencies. No ranking. For configurable classical-seven attention candidates call calculate_natal_salience. Partial graphs explicitly mark unavailable houses and axes.")
def calculate_natal_structure_graph(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, fold: StrictInt | None = None
) -> dict:
    from services.mcp_structure_graph import calculate_graph_data
    return calculate_graph_data(year=year, month=month, day=day, hour=hour,
                                minute=minute, location_id=location_id, fold=fold)


@tool(annotations=READ_ONLY, description='Extract rule-based natal priorities when the user needs candidate focus groups with source evidence. Use calculate_natal_structure_graph for the complete unselected relationship graph, or calculate_natal_chart for positions and houses. Requires exact local birth date/time and a confirmed location_id. Returns focus_selection, all ten planet_profiles, relationship_views separating dignity dependencies from direct aspects, state evidence, reading groups and source_graph; jones_view and view_comparison retain Jones as a separate perspective that does not select natal priorities. Missing house/axis layers remain explicit as partial availability. Broad selections are allowed: no global importance score, forced single core, psychological inference or remedy verdict. Reception criteria and bounded aspect dynamics describe calculated conditions, not efficacy or unlimited perfection. Scope, rulers and orbs are explained in the input fields. Detailed selection rules and version history: docs/natal-salience.md.')
def calculate_natal_salience(
    *, year: Annotated[StrictInt | None, Field(description='Exact birth year in the local civil calendar. Birth fields are required for a successful calculation; ask for missing data rather than guessing.')] = None, month: Annotated[StrictInt | None, Field(description='Local civil birth month, 1-12; interpreted with year and day.')] = None,
    day: Annotated[StrictInt | None, Field(description='Local civil birth day; must form a valid date with year and month.')] = None, hour: Annotated[StrictInt | None, Field(description='Exact local civil birth hour, 0-23; not UTC. Do not substitute an unknown time.')] = None, minute: Annotated[StrictInt | None, Field(description='Exact local civil birth minute, 0-59.')] = None,
    location_id: Annotated[str | None, Field(description='Copy a confirmed ID from resolve_birth_coordinates or search_birthplace. It supplies coordinates and the IANA timezone; a person name does not replace it.')] = None, fold: Annotated[StrictInt | None, Field(description='For an ambiguous repeated local time, use 0 for the earlier occurrence or 1 for the later one after user confirmation. Otherwise omit.')] = None,
    scope: Annotated[Literal['classical7','ten'], Field(description='Statistical origins: classical7 uses Sun through Saturn; ten adds Uranus, Neptune and Pluto. Does not remove the ten complete profiles or restrict which planets chains may traverse.')] = 'classical7',
    rulership: Annotated[Literal['traditional','modern'], Field(description='Dispositor edge convention, traditional or modern; separate from the number of statistical origins.')] = 'traditional', orb_view: Annotated[StrictInt, Field(description='Uniform inclusive major-aspect orb in degrees: 6 (default), 8 or 10. Applies to all five major aspects and ten planets.')] = 6,
    tight_orb: Annotated[StrictInt | StrictFloat, Field(description='Tight-aspect candidate threshold in degrees, finite 0-10 and no greater than orb_view. Does not discard other selected-view aspects.')] = 3.0, axis_orb: Annotated[StrictInt | StrictFloat, Field(description='Maximum axis-contact orb in degrees, finite 0-10; ASC/MC use actual chart axes, with opposite-axis expressions merged.')] = 5.0,
    include_mc_ruler: Annotated[StrictBool, Field(description='Include the MC sign ruler in identity candidates when MC is available; false keeps the default identity selection.')] = False,
    distribution_points: Annotated[Literal['ten','ten_plus_asc_mc'], Field(description='Points for element/modality distribution: ten planets, or ten plus available ASC and MC. Does not change ten-planet aspect motifs.')] = 'ten_plus_asc_mc',
    reception_policy: Annotated[Literal['dignity_only','sign_aspect','degree_aspect','applying_degree_aspect'], Field(description='Choose dignity alone; dignity plus sign geometry; dignity plus a selected degree aspect; or dignity plus a selected degree aspect and applying status. These are distinct criteria, not efficacy judgments.')] = 'dignity_only',
    dynamics_days: Annotated[StrictInt, Field(description='Bounded forward search horizon in days, integer 1-90. Searches the current aspect branch for its first exact contact and reports intervening stations/ingresses; no match means none found in this horizon.')] = 30,
) -> dict:
    from services.mcp_salience import calculate_salience_data
    return calculate_salience_data(year=year,month=month,day=day,hour=hour,minute=minute,
                                   location_id=location_id,fold=fold,scope=scope,
                                   rulership=rulership,orb_view=orb_view,tight_orb=tight_orb,
                                   axis_orb=axis_orb,include_mc_ruler=include_mc_ruler,
                                   distribution_points=distribution_points,reception_policy=reception_policy,dynamics_days=dynamics_days)


@tool(annotations=READ_ONLY, meta=WHEEL_META, description="Render the existing natal chart wheel as a 720px PNG shown to the user. Requires an exact birth date, local time and selected location_id; supports placidus or whole_sign. Ask about ambiguous civil time instead of guessing fold.")
def render_natal_chart(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, house_system: str | None = None,
    fold: StrictInt | None = None
) -> CallToolResult:
    metadata, png = render_natal_chart_png(
        year=year, month=month, day=day, hour=hour, minute=minute,
        location_id=location_id, house_system=house_system, fold=fold)
    return _wheel_result(metadata, png, "本命盘")


@tool(annotations=READ_ONLY, meta=WHEEL_META, description="Render the same Jones pattern distribution ring shown in the Mini Program: ten planetary glyphs, occupied fans, true longitude dots, gap, angles and focus points. Returns a visible 720px PNG plus the pattern and boundary status. Requires an exact local birth date, time and location_id; supports coordinate IDs from resolve_birth_coordinates.")
def render_jones_pattern(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, fold: StrictInt | None = None
) -> CallToolResult:
    info, png = render_jones_pattern_png(
        year=year, month=month, day=day, hour=hour, minute=minute,
        location_id=location_id, fold=fold)
    return _wheel_result(info, png, "琼斯格局分布图")


@tool(annotations=READ_ONLY, description="Hellenistic chart factors from the same natal calculation: sect, planet sect status, essential dignity and condition tags, triplicity lords of the sect light and ascendant, Lot of Fortune and Lot of Spirit, lunar phase, and the Jones whole-chart pattern. Data only, no interpretation text.")
def calculate_classical_factors(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, house_system: str | None = None,
    fold: StrictInt | None = None
) -> dict:
    return calculate_classical_data(year=year, month=month, day=day, hour=hour,
                                    minute=minute, location_id=location_id,
                                    house_system=house_system, fold=fold)


@tool(annotations=READ_ONLY, description="Zodiacal releasing (Valens, 360-day years) from the Lot of Fortune and Lot of Spirit. Returns all level-1 periods, the level-2 periods inside the level-1 period containing as_of, and the level-3 periods inside the current level-2 period, with peak and loosing-of-the-bond markers. as_of defaults to today.")
def calculate_zodiacal_releasing(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, as_of: str | None = None, fold: StrictInt | None = None
) -> dict:
    return calculate_releasing_data(year=year, month=month, day=day, hour=hour,
                                    minute=minute, location_id=location_id,
                                    as_of=as_of, fold=fold)


@tool(annotations=READ_ONLY, description="Firdaria and annual profections. Returns all firdaria major periods, the sub-periods of the major period containing as_of, and annual profection years from one year before to three years after as_of. tradition: abu_mashar (default), al_biruni or bonatti; house_system applies to profection houses.")
def calculate_time_lords(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, as_of: str | None = None, house_system: str | None = None,
    tradition: str = "abu_mashar", fold: StrictInt | None = None
) -> dict:
    return calculate_time_lord_data(year=year, month=month, day=day, hour=hour,
                                    minute=minute, location_id=location_id,
                                    as_of=as_of, house_system=house_system,
                                    tradition=tradition, fold=fold)


class BirthInput(BaseModel):
    year: StrictInt | None = None
    month: StrictInt | None = None
    day: StrictInt | None = None
    hour: StrictInt | None = None
    minute: StrictInt | None = None
    location_id: str | None = Field(default=None, description="ID from search_birthplace or resolve_birth_coordinates")
    fold: StrictInt | None = Field(default=None, description="0 or 1 only for a repeated DST time")


@tool(annotations=READ_ONLY, description="Solar arc directions (true solar arc) for an age range. Returns directed points conjoining natal axes, directed axes conjoining natal points, the full hard-aspect matrix with exact dates, and directed positions at the age on as_of. Defaults to five years either side of as_of (today); ages 0-80. Optional wheel_age selects the directed position age explicitly.")
def calculate_solar_arc(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, age_from: float | None = None, age_to: float | None = None,
    as_of: str | None = None, fold: StrictInt | None = None, wheel_age: float | None = None
) -> dict:
    return ext.solar_arc_data(year=year, month=month, day=day, hour=hour, minute=minute,
                              location_id=location_id, age_from=age_from, age_to=age_to,
                              as_of=as_of, fold=fold, wheel_age=wheel_age)


@tool(annotations=READ_ONLY, description="Exact transits of Jupiter, Mars, Saturn, Uranus, Neptune and Pluto to the natal chart between from_date and to_date (YYYY-MM-DD, at most 3 years). target_scope: all, axes or points. IMPORTANT: axes include conjunctions (0 degrees) ONLY; other axis aspects are not supported. Points use the listed major aspects. Empty axis events do not mean no other axis aspects. Optional planet: jupiter, mars, saturn, uranus, neptune or pluto. Times are given in UTC and birthplace local time.")
def calculate_transits_to_natal(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, from_date: str | None = None, to_date: str | None = None,
    target_scope: str = "all", planet: str | None = None, fold: StrictInt | None = None
) -> dict:
    return ext.transit_events_data(year=year, month=month, day=day, hour=hour,
                                   minute=minute, location_id=location_id,
                                   from_date=from_date, to_date=to_date,
                                   target_scope=target_scope, planet=planet, fold=fold)


@tool(annotations=READ_ONLY, description="Data-only multi-technique timeline for target_year and 1–3 birthplace calendar years. Includes active Firdaria and Zodiacal Releasing L1/L2 periods, progressed Moon sign ingresses and hard aspects to natal points, and Jupiter through Pluto conjunctions with natal axes. Events have stable UTC/local timestamps and source fields; resonances only group matching points across at least two techniques within 30 days. No predictive interpretations.")
def calculate_timeline_synthesis(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, target_year: StrictInt | None = None,
    span_years: StrictInt = 1, fold: StrictInt | None = None
) -> dict:
    return ext.timeline_synthesis_data(year=year, month=month, day=day, hour=hour,
                                       minute=minute, location_id=location_id,
                                       target_year=target_year, span_years=span_years,
                                       fold=fold)


@tool(annotations=READ_ONLY, description="Transit positions at one moment and the transit-to-natal aspects within orb at that moment. moment is ISO 8601 with a timezone offset, for example 2026-10-08T12:00:00+08:00; defaults to now.")
def get_transit_snapshot(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, moment: str | None = None, fold: StrictInt | None = None
) -> dict:
    return ext.transit_snapshot_data(year=year, month=month, day=day, hour=hour,
                                     minute=minute, location_id=location_id,
                                     moment=moment, fold=fold)


@tool(annotations=READ_ONLY, description="Saturn and Jupiter cycles over the natal angles: exact conjunctions with ASC, IC, DSC and MC, Saturn-Jupiter aspects, the quadrant phases of each planet, and the current position in each cycle on as_of (default today). max_age 1-120, default 80.")
def calculate_saturn_jupiter_cycles(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, as_of: str | None = None, max_age: int = 80,
    fold: StrictInt | None = None
) -> dict:
    return ext.saturn_jupiter_data(year=year, month=month, day=day, hour=hour,
                                   minute=minute, location_id=location_id,
                                   as_of=as_of, max_age=max_age, fold=fold)


@tool(annotations=READ_ONLY, description="Transiting Saturn and Jupiter entering natal Placidus houses from birth to age 84, including retrograde re-entries. Optional planet (saturn or jupiter) and optional from_date/to_date (YYYY-MM-DD) filters.")
def calculate_house_ingresses(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, planet: str | None = None, from_date: str | None = None,
    to_date: str | None = None, fold: StrictInt | None = None
) -> dict:
    return ext.house_ingress_data(year=year, month=month, day=day, hour=hour,
                                  minute=minute, location_id=location_id, planet=planet,
                                  from_date=from_date, to_date=to_date, fold=fold)


@tool(annotations=READ_ONLY, description="Secondary progressed lunation cycle (eight phases, each 45 degrees from the exact phase): current phase on as_of, next phase, the lifetime phase timeline with progressed Sun and Moon positions, and transiting Saturn's natal house at each phase change.")
def calculate_progressed_lunation(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, as_of: str | None = None, fold: StrictInt | None = None
) -> dict:
    return ext.progressed_lunation_data(year=year, month=month, day=day, hour=hour,
                                        minute=minute, location_id=location_id,
                                        as_of=as_of, fold=fold)


@tool(annotations=READ_ONLY, description="Solar return chart for target_year: exact return moment, chart positions, angles, cusps and aspects, overlay with the natal chart, and monthly progressed return Moon contacts. Explicit residence_location_id (from search_birthplace) is required; use the birthplace ID only when the user chooses it. house_system: placidus or whole_sign.")
def calculate_solar_return(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, target_year: StrictInt | None = None,
    residence_location_id: str | None = None, house_system: str | None = None,
    fold: StrictInt | None = None
) -> dict:
    return ext.solar_return_data(year=year, month=month, day=day, hour=hour,
                                 minute=minute, location_id=location_id,
                                 target_year=target_year,
                                 residence_location_id=residence_location_id,
                                 house_system=house_system, fold=fold)


@tool(annotations=READ_ONLY, meta=WHEEL_META, description="Render the solar return chart for target_year as a 720px PNG wheel shown to the user. Same inputs as calculate_solar_return.")
def render_solar_return_chart(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, target_year: StrictInt | None = None,
    residence_location_id: str | None = None, house_system: str | None = None,
    fold: StrictInt | None = None
) -> CallToolResult:
    info, png = ext.render_solar_return_png(
        year=year, month=month, day=day, hour=hour, minute=minute,
        location_id=location_id, target_year=target_year,
        residence_location_id=residence_location_id, house_system=house_system, fold=fold)
    return _wheel_result(info, png, f"{target_year} 太阳返照盘")


@tool(annotations=READ_ONLY, description="Lunar return chart for target_year and target_month in the residence's civil calendar: exact return moment, chart positions, angles, cusps, aspects, and natal overlay. Explicit residence_location_id (from search_birthplace) is required; house_system: placidus or whole_sign. target_day selects the nearer return if two occur in one month.")
def calculate_lunar_return(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, target_year: StrictInt | None = None,
    target_month: StrictInt | None = None, target_day: StrictInt | None = None,
    residence_location_id: str | None = None, house_system: str | None = None,
    fold: StrictInt | None = None
) -> dict:
    return ext.lunar_return_data(year=year, month=month, day=day, hour=hour,
                                minute=minute, location_id=location_id,
                                target_year=target_year, target_month=target_month,
                                target_day=target_day,
                                residence_location_id=residence_location_id,
                                house_system=house_system, fold=fold)


@tool(annotations=READ_ONLY, meta=WHEEL_META, description="Render the lunar return chart as a 720px PNG wheel shown to the user. Same inputs as calculate_lunar_return.")
def render_lunar_return_chart(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, target_year: StrictInt | None = None,
    target_month: StrictInt | None = None, target_day: StrictInt | None = None,
    residence_location_id: str | None = None, house_system: str | None = None,
    fold: StrictInt | None = None
) -> CallToolResult:
    info, png = ext.render_lunar_return_png(
        year=year, month=month, day=day, hour=hour, minute=minute,
        location_id=location_id, target_year=target_year, target_month=target_month,
        target_day=target_day, residence_location_id=residence_location_id,
        house_system=house_system, fold=fold)
    return _wheel_result(info, png, f"{target_year}-{target_month:02d} 月亮返照盘" if target_month else "月亮返照盘")


@tool(annotations=READ_ONLY, description="Secondary progressions (Day-for-a-Year) chart: progressed planets, angles, natal aspects and lunation phase. Specify as_of or age; angle_progression_method defaults to naibod, or choose solar_arc_in_ra.")
def calculate_secondary_progressions(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, age: float | None = None, as_of: str | None = None,
    house_system: str | None = None, fold: StrictInt | None = None,
    angle_progression_method: str = "naibod"
) -> dict:
    return ext.secondary_progressions_data(year=year, month=month, day=day, hour=hour,
                                          minute=minute, location_id=location_id,
                                          age=age, as_of=as_of,
                                          house_system=house_system, fold=fold,
                                          angle_progression_method=angle_progression_method)


@tool(annotations=READ_ONLY, meta=WHEEL_META, description="Render secondary progressions as a 760px bi-wheel PNG shown to the user (natal inside, progressed outside). Same inputs as calculate_secondary_progressions.")
def render_secondary_progressions_chart(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, age: float | None = None, as_of: str | None = None,
    house_system: str | None = None, fold: StrictInt | None = None,
    angle_progression_method: str = "naibod"
) -> CallToolResult:
    info, png = ext.render_secondary_progressions_biwheel_png(
        year=year, month=month, day=day, hour=hour, minute=minute,
        location_id=location_id, age=age, as_of=as_of,
        house_system=house_system, fold=fold,
        angle_progression_method=angle_progression_method)
    return _wheel_result(info, png, "次限推进双圈盘")


@tool(annotations=READ_ONLY, description="Relationship charts for two people with exact birth data: synastry aspects, each person's planets in the other's Placidus houses, the midpoint composite chart, composite-to-natal aspects and shared house patterns. orb_profile: greene (default) or tight.")
def calculate_relationship_charts(person_a: BirthInput | None = None, person_b: BirthInput | None = None,
                                  orb_profile: str = "greene") -> dict:
    return ext.relationship_data(person_a=person_a.model_dump(),
                                 person_b=person_b.model_dump(), orb_profile=orb_profile)


@tool(annotations=READ_ONLY, description="John Green relationship observation v0.14. mode=synastry requires two exact births; mode=natal accepts person_a alone or both people and computes natal profiles without cross-contacts. All natal points remain available, including untriggered points. sort_by=orb (default), relationship_indicators or natal_hard_aspects changes display order only. Human notes use prepare_relationship_observation_note separately. Returns unique cross-contacts, two observation paths per contact, one-hop natal context, supported bounded natal aspect configurations (including Chiron), actual contact links between both natal configurations, static natal priority background under its separately disclosed policy, directed house overlays and factual indicators. Configuration memberships and natal identities never add direct contacts. observation_review provides evidence-backed indicator, inner/outer and tightness reasons with parallel lenses, never a weighted score or inferred client difficulty. structure_display folds contained configurations and bridges while keeping every raw row and partial overlap. natal_observation_candidates records source-backed selection reasons even without partner contacts. review_paths links actual contact endpoints, one-hop natal context, house rulers and overlays without propagating activation. overlay_contexts preserves target ownership; observation_comparisons groups reciprocal contacts and both natal backgrounds without scoring. observation_complexes separately groups conjunction-pair neighborhoods and named-pattern conjunction satellites, including axis endpoint variants, without recursive expansion or whole-complex activation claims. Shared natal planet pairs and exact descendant-sign correspondences are factual comparisons, not semantic matches. Relationship-indicator sorting uses target-point selection roles. scenario_observation_lenses attaches source-backed topics, conditions and actual point/house references to each selected context; this is not a planet whitelist or psychological interpretation. Optional unconfirmed conditions must not be asserted as client facts. Reuse an explicitly stated relationship context; if unknown, ask the user before calling. The legacy love default is not evidence of user confirmation. No composite, scores or psychological flags. Axis endpoint equivalents share one contact. john_green profile uses 10 degrees for conjunction/square/trine/opposition and 5 degrees for tight display. Sextiles are not evaluated unless sextile_orb_degrees (0-10) is supplied; minor aspects require include_minor_aspects=true and explicit minor_orbs_degrees keys 30/45/135/150; overlapping orb windows are rejected. Yod context requires explicit 60 and 150 degree orbs. Optional include_timing=true requires timing with one of at (offset-aware ISO timestamp), date (YYYY-MM-DD), or month (YYYY-MM) with optional month_part (early/middle/late), or event=childbirth with explicit family parent/child roles, plus explicit transit_orbs_degrees and progression_orbs_degrees. Timing provides a selected-instant snapshot. Optional timing.window_start and window_end (offset-aware ISO timestamps) request a numerical interval search, with a duration from one second to 31 days and the snapshot inside [start,end). window_scan returns exact events and clipped orb windows over every supported point pair, including pairs absent at the snapshot. It reuses source engines and root refinement; interval mesh and bounds are engineering rules. Simultaneous synastry endpoint windows require the same transit and actual interval overlap, not merely two hits somewhere in the date range. Non-instant dates are illustrative UTC-noon samples with fast transits excluded; early/middle/late means calendar days 1-10/11-20/21-end and samples day 5/15/25. These boundaries and sample times are engineering conventions, not known meeting times or interval scans. The timing dictionary also accepts angle_progression_method (naibod default or solar_arc_in_ra) and include_progressed_synastry (boolean, default true). When progressed synastry is enabled, progressed_synastry_comparison compares natal geometry with the selected progressed pair under the same progression_orbs_degrees. It distinguishes same/different aspect and presence on only one side; a node-convention mismatch is marked not comparable. Existing wide-orb static contacts are contextual references, not the comparison baseline. This does not infer first appearance, duration, relationship outcome or internal progressed configurations. No inherited 10-degree timing orbs. Childbirth resolves the child birth through the existing timezone/fold resolver and exposes parental contacts as references, not extra evidence. Natal nodes are verified mean nodes despite legacy field names; childbirth uses mean nodes throughout. Explicit-date timing retains its true transit/progressed nodes and discloses the different natal convention in node_conventions. Timing requires synastry mode and preserves static counts, and links existing contacts and bounded natal contexts without predictions. See timing_observations and its availability limits. relationship_context accepts additional_types, caller-supplied a/b roles (parent/child, siblings, supervisor/employee, colleagues), and cohabiting. Roles must match a selected family/work type. Optional creative_project and early_or_sibling_like_friendship accept true/false/null, require work/friendship respectively, and never infer context. Conditional DSC/seventh-house topics retain actual houses. observation_complex_links references each contact once with both owners core/context memberships, including axis/Yod complexes; no pair-product expansion. Parallel traditional/modern ruler backgrounds and special contact lenses do not add contacts or weights. Missing layers remain explicit, including in summary results. See docs/relationship-observation.md.")
def calculate_relationship_observation(
    person_a: BirthInput | None = None, person_b: BirthInput | None = None,
    relationship_type: Literal['love', 'friendship', 'work', 'family'] = 'love',
    house_system: Literal['placidus'] = 'placidus',
    orb_profile: Literal['john_green'] = 'john_green',
    ruler_profile: Literal['traditional', 'modern'] = 'traditional',
    parental_house_mapping_profile: Literal['john_green', 'reversed'] = 'john_green',
    sextile_orb_degrees: Annotated[float, Field(strict=True, ge=0, le=10, allow_inf_nan=False)] | None = None,
    include_minor_aspects: Annotated[bool, Field(strict=True)] = False,
    minor_orbs_degrees: dict[str, Annotated[float, Field(strict=True, ge=0, le=10, allow_inf_nan=False)]] | None = None,
    relationship_context: dict | None = None,
    include_timing: Annotated[bool, Field(strict=True)] = False,
    timing: dict | None = None,
    mode: Literal['synastry', 'natal'] = 'synastry',
    sort_by: Literal['orb', 'relationship_indicators', 'natal_hard_aspects'] = 'orb',
) -> dict:
    from services.relationship_observation import calculate_observation_data
    return calculate_observation_data(
        person_a=person_a.model_dump(), person_b=person_b.model_dump() if person_b is not None else None,
        relationship_type=relationship_type, house_system=house_system, orb_profile=orb_profile,
        ruler_profile=ruler_profile, parental_house_mapping_profile=parental_house_mapping_profile,
        sextile_orb_degrees=sextile_orb_degrees, include_minor_aspects=include_minor_aspects,
        include_timing=include_timing, mode=mode, sort_by=sort_by,
        minor_orbs_degrees=minor_orbs_degrees, relationship_context=relationship_context, timing=timing)


@tool(annotations=READ_ONLY, description="Prepare a human observation note for caller-owned storage. Requires an unchanged calculate_relationship_observation calculation_reference, person a/b and an explicitly supplied human statement. Optionally link to a natal point and question ID. Recomputes the source anchor only; does not verify the statement, infer answers, diagnose, persist notes or change calculation facts/counts. Never invent client reports.")
def prepare_relationship_observation_note(
    reference: CalculationReference, person: Literal['a', 'b'],
    statement: Annotated[str, Field(strict=True, min_length=1, max_length=4000)],
    author_role: Literal['client_report', 'practitioner_note'],
    point: str | None = None, question_id: str | None = None,
) -> dict:
    from services.relationship_observation_notes import prepare_note
    return prepare_note(reference=reference.model_dump(), person=person, statement=statement,
                        author_role=author_role, point=point, question_id=question_id)



@tool(annotations=READ_ONLY, meta=WHEEL_META, description="Render the midpoint composite chart of two people as a 720px PNG wheel shown to the user.")
def render_composite_chart(person_a: BirthInput | None = None, person_b: BirthInput | None = None) -> CallToolResult:
    info, png = ext.render_composite_png(person_a=person_a.model_dump(),
                                         person_b=person_b.model_dump())
    return _wheel_result(info, png, "组合中点盘")


@tool(annotations=READ_ONLY, description="Davison relationship chart (time-space midpoint chart) for two people with exact birth data: calculates the real physical midpoint in time (UT) and geographic coordinates, casting an independent chart with its own real axes, houses and planetary positions. Supports placidus or whole_sign; orb_profile: greene (default) or tight.")
def calculate_davison_chart(person_a: BirthInput | None = None, person_b: BirthInput | None = None,
                            house_system: str = "placidus", orb_profile: str = "greene") -> dict:
    return ext.davison_data(person_a=person_a.model_dump(),
                            person_b=person_b.model_dump(),
                            house_system=house_system,
                            orb_profile=orb_profile)


@tool(annotations=READ_ONLY, meta=WHEEL_META, description="Render the Davison relationship chart (time-space midpoint chart) of two people as a 720px PNG wheel shown to the user. Same inputs as calculate_davison_chart.")
def render_davison_chart(person_a: BirthInput | None = None, person_b: BirthInput | None = None,
                         house_system: str = "placidus") -> CallToolResult:
    info, png = ext.render_davison_png(person_a=person_a.model_dump(),
                                       person_b=person_b.model_dump(),
                                       house_system=house_system)
    return _wheel_result(info, png, "时空中点盘")


@tool(annotations=READ_ONLY, description="Relocation chart: recalculates ascendant, midheaven and house cusps for a new residence location while keeping the exact natal birth moment (UT) and planetary longitudes unchanged. relocation_location_id (from search_birthplace) is required; house_system: placidus (default) or whole_sign.")
def calculate_relocation_chart(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, relocation_location_id: str | None = None,
    house_system: str = "placidus", fold: StrictInt | None = None
) -> dict:
    return ext.relocation_data(year=year, month=month, day=day, hour=hour,
                               minute=minute, location_id=location_id,
                               relocation_location_id=relocation_location_id,
                               house_system=house_system, fold=fold)


@tool(annotations=READ_ONLY, meta=WHEEL_META, description="Render the relocation chart as a 720px PNG wheel shown to the user. Same inputs as calculate_relocation_chart.")
def render_relocation_chart(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, relocation_location_id: str | None = None,
    house_system: str = "placidus", fold: StrictInt | None = None
) -> CallToolResult:
    info, png = ext.render_relocation_png(
        year=year, month=month, day=day, hour=hour, minute=minute,
        location_id=location_id, relocation_location_id=relocation_location_id,
        house_system=house_system, fold=fold)
    return _wheel_result(info, png, "空间重置盘")


@tool(annotations=READ_ONLY, description="Sky at one moment, independent of any birth chart: lunar phase and illumination, Moon sign, void-of-course window, recent and next lunations and eclipses, retrograde planets and stations, planet-to-planet aspects and patterns. moment is ISO 8601 with a timezone offset; defaults to now.")
def get_current_sky(moment: str | None = None) -> dict:
    return ext.sky_data(moment=moment)


@tool(annotations=READ_ONLY, description="House ruler dispositor chains for all twelve houses, in both the traditional and modern track. Each chain follows the house ruler to the ruler of its sign until it reaches a planet in its own sign or loops. Also marks the chart ruler and the angular, succedent and cadent crosses.")
def calculate_house_rulers(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, house_system: str | None = None,
    fold: StrictInt | None = None
) -> dict:
    return ext.house_ruler_data(year=year, month=month, day=day, hour=hour,
                                minute=minute, location_id=location_id,
                                house_system=house_system, fold=fold)


@tool(annotations=READ_ONLY, description="Level-4 zodiacal releasing periods inside one level-3 period. Call calculate_zodiacal_releasing first, then pass lot (fortune or spirit) plus the exact start date and sign key of the chosen level-3 period, for example parent_start 2026-08-24 and parent_sign GEMINI.")
def calculate_zodiacal_releasing_l4(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, lot: str | None = None, parent_start: str | None = None,
    parent_sign: str | None = None, as_of: str | None = None, fold: StrictInt | None = None
) -> dict:
    return ext.releasing_l4_data(year=year, month=month, day=day, hour=hour,
                                 minute=minute, location_id=location_id, lot=lot,
                                 parent_start=parent_start, parent_sign=parent_sign,
                                 as_of=as_of, fold=fold)


@tool(annotations=READ_ONLY, description="Lifetime transit overview from birth to age 84 in twelve seven-year chapters: how many exact transit hits fall in each chapter, split by planet, by slow or fast group, and by axis or planet target. Use calculate_transits_to_natal for the dated events. This scan takes about half a minute.")
def calculate_lifetime_transit_summary(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, fold: StrictInt | None = None
) -> dict:
    return ext.lifetime_summary_data(year=year, month=month, day=day, hour=hour,
                                     minute=minute, location_id=location_id, fold=fold)


@tool(annotations=READ_ONLY, description="Planet-to-planet aspects in orb at one moment, each with how long it stays within orb, how much has elapsed and how much remains. An explicit location_id is required because this result includes the Lot of Fortune and Lot of Spirit. moment is ISO 8601 with a timezone offset; defaults to now.")
def calculate_aspect_windows(moment: str | None = None,
                             location_id: str | None = None) -> dict:
    return ext.aspect_window_data(moment=moment, location_id=location_id)


@tool(annotations=READ_ONLY, description="A full chart cast for any moment and place rather than for a birth: planets, Placidus houses, axes, aspects, aspect patterns, lunar phase and planetary motion including retrograde shadow periods. moment is ISO 8601 with a timezone offset; defaults to now.")
def calculate_sky_chart(moment: str | None = None,
                        location_id: str | None = None) -> dict:
    return ext.sky_chart_data(moment=moment, location_id=location_id)


@tool(annotations=READ_ONLY, meta=WHEEL_META, description="Render the chart for any moment and place as a 720px PNG wheel shown to the user. Same inputs as calculate_sky_chart.")
def render_sky_chart(moment: str | None = None,
                     location_id: str | None = None) -> CallToolResult:
    info, png = ext.render_sky_chart_png(moment=moment, location_id=location_id)
    return _wheel_result(info, png, "天象盘")


@tool(annotations=READ_ONLY, meta=WHEEL_META, description="Render a two-ring wheel with the natal chart inside and the transiting planets outside at one moment, with the cross-chart aspects drawn in the centre. moment is ISO 8601 with a timezone offset; defaults to now.")
def render_transit_biwheel(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, moment: str | None = None, fold: StrictInt | None = None
) -> CallToolResult:
    info, png = ext.render_transit_biwheel_png(
        year=year, month=month, day=day, hour=hour, minute=minute,
        location_id=location_id, moment=moment, fold=fold)
    return _wheel_result(info, png, "行运双盘")


@tool(annotations=READ_ONLY, meta=WHEEL_META, description="Render a two-ring wheel with the natal chart inside and the solar arc directed positions outside. Give age directly, or as_of (YYYY-MM-DD) to use the age on that date; defaults to today. Ages 0-80.")
def render_solar_arc_biwheel(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, age: float | None = None, as_of: str | None = None,
    fold: StrictInt | None = None
) -> CallToolResult:
    info, png = ext.render_solar_arc_biwheel_png(
        year=year, month=month, day=day, hour=hour, minute=minute,
        location_id=location_id, age=age, as_of=as_of, fold=fold)
    return _wheel_result(info, png, "太阳弧双盘")


@tool(annotations=READ_ONLY, meta=WHEEL_META, description='Render a 1200x660 PNG panorama of lifetime Saturn/Jupiter angle crossings, with event labels and a reference-age indicator. Use this for a visual overview; use calculate_saturn_jupiter_cycles for exact event tables and cycle data, or calculate_house_ingresses for entries into houses. Requires exact local birth date/time and a confirmed location_id; person_name is only a display label. Returns an inline MCP PNG and cycle summary after calculating and checking its source. stdio provides no public image URL; image display requires client support. Missing or invalid birth inputs return an input error without an image; unavailable rendering returns render_failed. The window starts at birth and ends at max_age (default 80, allowed 1-120). Wave height is geometry, not life quality or an event prediction.')
def render_saturn_jupiter_cycles(
    *, year: Annotated[StrictInt | None, Field(description='Exact birth year in the local civil calendar. Birth fields are required for a successful calculation; ask for missing data rather than guessing.')] = None, month: Annotated[StrictInt | None, Field(description='Local civil birth month, 1-12; interpreted with year and day.')] = None,
    day: Annotated[StrictInt | None, Field(description='Local civil birth day; must form a valid date with year and month.')] = None, hour: Annotated[StrictInt | None, Field(description='Exact local civil birth hour, 0-23; not UTC. Do not substitute an unknown time.')] = None, minute: Annotated[StrictInt | None, Field(description='Exact local civil birth minute, 0-59.')] = None,
    location_id: Annotated[str | None, Field(description='Copy a confirmed ID from resolve_birth_coordinates or search_birthplace. It supplies coordinates and the IANA timezone; a person name does not replace it.')] = None, as_of: Annotated[str | None, Field(description='Reference calendar date YYYY-MM-DD, evaluated at 12:00 UTC; omitted or empty uses the current UTC date. Sets the age indicator/current cycle position, not the chart start or end.')] = None, max_age: Annotated[int, Field(description='Lifetime window endpoint in years since birth: integer 1-120, default 80. Starts at birth; larger ranges require more calculation.')] = 80,
    person_name: Annotated[str | None, Field(description='Optional display label printed on the image. It is not an identity lookup and does not replace birth fields or location_id.')] = None, fold: Annotated[StrictInt | None, Field(description='For an ambiguous repeated local time, use 0 for the earlier occurrence or 1 for the later one after user confirmation. Otherwise omit.')] = None
) -> CallToolResult:
    info, png = ext.render_saturn_jupiter_cycles_png(
        year=year, month=month, day=day, hour=hour, minute=minute,
        location_id=location_id, as_of=as_of, max_age=max_age,
        person_name=person_name, fold=fold)
    return _wheel_result(info, png, "土木流年全景时间轴")


@tool(annotations=READ_ONLY, description="Verify natal sign, house, retrograde and aspect assertions against a fresh server calculation. Copy fact_reference unchanged from calculate_natal_chart; submit each assertion with its exact draft quote. Returns supported, contradicted or unverified plus source fields. Unsupported facts, other chart types and psychological interpretations are unverified. Quote text is echoed, not parsed: this does not validate an entire report or detect omitted claims. Fix contradicted claims before answering.")
def verify_natal_claims(reference: NatalFactReference,
                        claims: Annotated[list[NatalClaim], Field(min_length=1, max_length=100)]) -> dict:
    return verify_natal_claims_data(reference.model_dump(), [claim.model_dump() for claim in claims])


@tool(annotations=READ_ONLY, description="Verify source-field claims from any registered calculation: classical/Jones roles, transits, directions, returns, relationship, time lords, releasing, sky and locations. Copy calculation_reference unchanged; submit exact JSON Pointer paths and values from the draft. Use complete event/role row objects to preserve planet, time and chart context. Server recomputes and checks the source before comparison. Fix contradicted claims and reverify; mark unverified claims. This checks submitted field values, NOT prose semantics, missing claims, psychological explanations or independent algorithm correctness.")
def verify_calculation_claims(reference: CalculationReference,
                             claims: Annotated[list[CalculationClaim], Field(min_length=1,max_length=100)]) -> dict:
    return verify_calculation_claims_data(reference.model_dump(), [c.model_dump() for c in claims])


@tool(annotations=READ_ONLY, description="Calculate Hellenistic and Arabic lots on demand. Returns name, longitude, sign, house, formula and day/night reversal info. Filter with lots=['fortune', 'spirit', 'eros', 'marriage_male', 'mother', ...]. Data only, no psychological interpretation.")
def calculate_lots(
    *, year: StrictInt | None = None, month: StrictInt | None = None,
    day: StrictInt | None = None, hour: StrictInt | None = None, minute: StrictInt | None = None,
    location_id: str | None = None, lots: list[str] | None = None,
    house_system: str = "whole_sign", fold: StrictInt | None = None
) -> dict:
    return calculate_lots_data(year=year, month=month, day=day, hour=hour,
                              minute=minute, location_id=location_id,
                              lots=lots, house_system=house_system, fold=fold)


@tool(annotations=READ_ONLY, description="Scan exact planetary aspects over UTC inclusive date ranges (1800–2399, max 200 years). Arbitrary supported body pair and angles [0,180]; tropical geocentric apparent Swiss Ephemeris, mean nodes by default. Uses bracketed roots and relative-speed station splits. mode=orb_window returns clipped entry/exit windows plus exact events; orb_deg is separate from exact. output_precision: exact_datetime, date, year_summary. timezone_name is optional IANA zone. Cycle IDs and hit indices are query-local directed-angle groups, not universal cycle numbering. See docs/planetary-aspect-scan.md.")
def scan_planetary_aspects(
    planet_a: str, planet_b: str, start_date: str, end_date: str,
    aspects: list[float] | None = None,
    mode: Literal["exact", "orb_window"] = "exact", orb_deg: float = 1.0,
    output_precision: Literal["exact_datetime", "date", "year_summary"] = "exact_datetime",
    timezone_name: str | None = None,
) -> dict:
    from services.planetary_aspect_scan import scan
    return scan(planet_a, planet_b, start_date, end_date, aspects, mode,
                orb_deg, output_precision, timezone_name)


@tool(annotations=READ_ONLY, description="Discover the current MCP tools, their input schemas, registered algorithm provenance and system versions. Generated from the live tool registry and algorithm_registry; use this before choosing a calculation workflow.")
def get_capabilities() -> dict:
    import asyncio

    listed = asyncio.run(mcp.list_tools())
    tools = []
    for item in sorted(listed, key=lambda entry: entry.name):
        provenance = declared_provenance(item.name, {})
        tools.append({
            'name': item.name,
            'description': item.description or '',
            'input_schema': item.inputSchema,
            'registered_algorithm_keys': [entry['key'] for entry in provenance['registered_algorithms']],
            'provenance_coverage': provenance['coverage'],
        })
    return {
        'status': 'ok',
        'schema_version': 'mcp-capabilities-v1',
        'versions': get_version_info(),
        'tool_count': len(tools),
        'tools': tools,
        'algorithm_registry': list_algorithms(),
    }


@tool(annotations=READ_ONLY, description="Read the current HellenicStar agent protocol: tool selection, missing-input handling, provenance limits, source-fact verification and interpretation boundaries. The same text is available as an MCP resource and prompt.")
def get_agent_protocol() -> dict:
    return {'status': 'ok', 'schema_version': 'mcp-agent-protocol-v1',
            'uri': AGENT_PROTOCOL_URI, 'content': protocol_text()}


@tool(annotations=READ_ONLY, description="Recommend a short tool workflow for one stated goal, such as natal, classical, releasing, time_lords, transits, solar_arc, solar_return, relationship or sky. Ambiguous goals return choices. This only routes existing tools; it does not calculate a chart or infer missing birth information.")
def recommend_workflow(goal: str) -> dict:
    import asyncio

    available = {item.name for item in asyncio.run(mcp.list_tools())}
    return recommend_workflow_data(goal, available)


@mcp.resource(AGENT_PROTOCOL_URI, name="agent-protocol", mime_type="text/markdown")
def agent_protocol_resource() -> str:
    return protocol_text()


@mcp.prompt(name=PROMPT_NAME, description="Use the current HellenicStar MCP agent protocol.")
def agent_protocol_prompt() -> str:
    return protocol_text()


class EnsureAcceptHeaderMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            accept = headers.get(b"accept", b"").decode("latin1")
            if not accept or "*/*" in accept or "application/json" not in accept:
                new_headers = [(k, v) for k, v in scope.get("headers", []) if k.lower() != b"accept"]
                new_headers.append((b"accept", b"application/json, text/event-stream, */*"))
                scope["headers"] = new_headers
        await self.app(scope, receive, send)


app = mcp.streamable_http_app()
app.add_middleware(EnsureAcceptHeaderMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
_mcp_http_lifespan = app.router.lifespan_context


@asynccontextmanager
async def _http_lifespan(app):
    async with _mcp_http_lifespan(app):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(_chart_cleanup_loop)
            try:
                yield
            finally:
                tasks.cancel_scope.cancel()


app.router.lifespan_context = _http_lifespan


async def mcp_rate_limit(request: Request, call_next):
    """Optionally enforce Bearer token and bound MCP traffic using the cross-process limiter."""
    required_token = os.environ.get("MCP_HTTP_BEARER_TOKEN", "").strip()
    if required_token and request.url.path.startswith("/mcp"):
        auth_header = request.headers.get("authorization", "")
        if not auth_header or auth_header != f"Bearer {required_token}":
            return JSONResponse({"error": "Unauthorized: invalid or missing Bearer token"}, status_code=401)
    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-real-ip", "").strip()
    ip = forwarded if peer in {"127.0.0.1", "::1"} and forwarded else peer
    for period, limit in ((60, 30), (3600, 300)):
        allowed, _, reset_at = rate_limit.check_and_increment(
            f"mcp:{period}:{ip}", period=period, limit=limit
        )
        if not allowed:
            return JSONResponse({"error": "请求过于频繁", "reset_at": reset_at}, status_code=429)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def _service_links():
    links = []
    for label, url in (("支持与数据处理联系", SUPPORT_URL), ("本部署的对应源代码", SOURCE_URL)):
        if url:
            links.append(f'<a href="{escape(url, quote=True)}">{label}</a>')
    return "<p>" + " · ".join(links) + "</p>" if links else "<p>支持、数据处理与对应源代码请联系本服务部署者。</p>"


async def privacy_policy(_request: Request):
    return HTMLResponse("""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>希腊星智排盘插件隐私政策</title><main style="max-width:720px;margin:3rem auto;padding:0 1rem;font:16px/1.8 sans-serif">
<h1>希腊星智排盘插件隐私政策</h1>
<p>本插件在您要求排盘时，接收您提供的出生日期、准确出生时间、出生地点、宫制、现居地及查询日期，用于计算本命、推运、行运、次限推进、太阳返照、月亮返照与天象数据。比较盘与组合盘需要第二个人的出生资料；请只提交您有权使用的他人出生资料。</p>
<p>调用本命事实核对工具时，我们还接收模型提交的结构化盘面断言及对应原句片段，并与重新计算的本命数据比较。核对仅覆盖提交的盘面事实，不验证整篇解读或心理解释；这些断言与片段不会被保存为咨询报告或用户档案。</p>
<p>MCP 客户端会将工具调用参数发送至您连接的服务实例；stdio 模式在运行客户端的计算机上计算。我们返回行星、宫位、宫头、相位与实际采用的时区等计算结果；在您请求时生成本命盘、太阳返照盘、月亮返照盘、组合盘、双圈盘（行运/太阳弧/次限）或天象盘 PNG。我们不返回占星解读，也不把星盘保存为用户档案。生成的星盘图以内容哈希命名，持有链接的人可访问，请勿公开分享含个人资料的链接。HTTP 图片链接有效期为 7 天，过期请求返回 404。HTTP 服务运行时每 60 秒清理过期图片；停机期间文件仍可能保留，重启后继续清理。stdio 模式直接返回图片内容，也会在本地生成缓存；每次生成图片时清理过期缓存，部署者可按需删除缓存目录。</p>
<p>地点搜索优先使用本地城市库；未命中时，地点关键词可能发送至高德地图服务以获取坐标和时区，不包含完整出生资料。HTTP 限流器在本地 SQLite 中保存来源 IP、时间窗口和计数，并在后续请求或启动时删除超过 2 小时的旧窗口。计算数据在进程内暂存，不建立用户档案。应用的工具日志记录工具名称、状态和耗时，不主动记录完整请求体；地点解析可能记录地理查询诊断信息。客户端、代理和运行平台的日志配置及保留时间由部署者决定。</p>
<p>您可以选择不提供出生资料。数据处理与删除请联系您连接的服务部署者；客户端对对话与工具调用的处理由其自身规则约束。</p>
""" + _service_links() + "</main></html>")


app.router.routes.append(Route("/mcp/privacy", privacy_policy, methods=["GET"]))


_CHART_NAME = re.compile(r"^[0-9a-f]{64}$")


async def chart_image(request: Request):
    digest = request.path_params["digest"]
    path = os.path.join(CHART_DIR, digest + ".png")
    if not _CHART_NAME.match(digest) or not os.path.isfile(path):
        return Response(status_code=404)
    try:
        if os.path.getmtime(path) <= time.time() - CHART_TTL_SECONDS:
            os.remove(path)
            return Response(status_code=404)
    except FileNotFoundError:
        return Response(status_code=404)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})


app.router.routes.append(Route("/mcp/chart/{digest}.png", chart_image, methods=["GET"]))


async def plugin_icon(_request: Request):
    return FileResponse(ICON_PATH, media_type="image/png")


app.router.routes.append(Route("/mcp/icon.png", plugin_icon, methods=["GET"]))

async def support_page(_request: Request):
    return HTMLResponse("""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>希腊星智排盘插件支持</title><main style="max-width:720px;margin:3rem auto;padding:0 1rem;font:16px/1.8 sans-serif">
<h1>希腊星智排盘插件支持</h1>
<p>本插件提供出生地点查询、本命星盘数据表与星盘图、古典要素（派系、三分主星、行星状态、宫主星定位链、福点与精神点、琼斯格局与相位格局）、黄道释放（含第四层）、法达、年小限、太阳弧、行运对本命、土木循环与过宫、终身流年摘要、次限推进行星与推进四轴、次限月相、太阳返照、月亮返照、比较盘与组合中点盘、行运/太阳弧/次限双圈图，以及任一时刻任一地点的天象盘与行星相位窗口。请提供准确的出生日期、当地时间和地点；地点同名或夏令时重复时刻需由您确认。</p>
<p>如遇地点查无结果、计算错误或数据处理问题，请联系本服务部署者。反馈时请使用虚构样例，避免提交他人的完整出生资料。</p>
""" + _service_links() + "</main></html>")


async def terms_page(_request: Request):
    return HTMLResponse("""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>希腊星智排盘插件使用条款</title><main style="max-width:720px;margin:3rem auto;padding:0 1rem;font:16px/1.8 sans-serif">
<h1>希腊星智排盘插件使用条款</h1>
<p>本插件供年满 18 周岁的用户用于星历排盘学习。您应确保有权提供输入的出生资料，并核实日期、时间和地点的准确性。</p>
<p>输出是依据输入和所选宫制计算的数据表，不构成医疗、法律、金融或其他专业建议。出生时间不详、地点歧义或重复时刻未确定时，请先补全资料。</p>
<p>服务可能因维护、网络或第三方地理服务故障暂时不可用。使用问题请联系本服务部署者。个人信息处理详见 <a href="/mcp/privacy">隐私政策</a>。</p>
""" + _service_links() + "</main></html>")


app.router.routes.append(Route("/mcp/support", support_page, methods=["GET"]))
app.router.routes.append(Route("/mcp/terms", terms_page, methods=["GET"]))
app.add_middleware(BaseHTTPMiddleware, dispatch=mcp_rate_limit)


if __name__ == "__main__":
    _IMAGE_HTTP_ENABLED = False
    mcp.run(transport="stdio")
