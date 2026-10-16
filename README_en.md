# HellenicStar Astrology MCP Server

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/Protocol-MCP-orange.svg)](https://modelcontextprotocol.io/)

[English](README_en.md) | [中文说明](README.md)

**HellenicStar Astrology MCP** is a standalone, high-precision astronomical calculation and Hellenistic astrology MCP (Model Context Protocol) server featuring **42 professional tools** designed for AI agents (Claude Desktop, Cursor, Codex, WorkBuddy, etc.).

By coupling the classical Swiss Ephemeris engine with rigorous Hellenistic rules and structured claim verification, it supplies calculated chart data and checks submitted factual claims. These checks do not guarantee that an LLM’s final interpretation is accurate or free of hallucinations.

---

## Quick Start: Connect to Claude Desktop

Add this server to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "hellenicstar": {
      "command": "/absolute/path/to/hellenicstar-mcp/.venv/bin/python",
      "args": ["/absolute/path/to/hellenicstar-mcp/mcp_server.py"]
    }
  }
}
```

*stdio mode returns crisp PNG charts directly to MCP clients that support image content.*

---

## Why HellenicStar MCP?

Generic LLMs (like Claude or GPT) struggle with astrological calculations: they hallucinate planetary longitudes, misplace house cusps, invent non-existent aspects, and produce vague astrological Barnum statements.

HellenicStar solves this by strictly separating **Computation** from **Interpretation**:
1. **Verified Calculation Engine**: Uses Swiss Ephemeris (`pyswisseph`) with true/mean node handling, accurate precession, and IANA historical Daylight Saving Time (DST) fold disambiguation.
2. **Fact Auditing & Anti-Hallucination**: Every data endpoint enforces an audited schema and returns a `calculation_reference`. LLMs can call `verify_calculation_claims` or `verify_natal_claims` to audit their own draft against recomputed facts before presenting interpretations.
3. **Local-First Deployment**: Calculations can run locally with coordinate input or an installed offline location database. Optional AMap lookup and remote HTTP deployment are also available. A connected AI client may send birth data and tool results to its model provider; local MCP execution alone does not guarantee that data stays on the computer.

---

## Core Capabilities (42 Tools)

### 1. High-Precision Natal & Astronomical Charting
- **House Systems**: Placidus, Whole Sign, and traditional quadrant frameworks.
- **Geocoding & Historical DST**: WGS-84 coordinate resolution via `resolve_birth_coordinates`; full support for historical DST changes (including China 1986–1991 DST transition ambiguities).
- **Ephemeris Precision**: Sub-arcsecond planetary coordinates, True/Mean Lunar Nodes, and Chiron.

### 2. Classical & Hellenistic Astrology Suite
- **Sect & Triplicity**: Diurnal/nocturnal sect identification and Dorothean triplicity ruler three-phase life assessments.
- **Essential Dignities**: Complete evaluation across Domicile, Exaltation, Triplicity, Bounds (Egyptian terms), and Decans (Chaldean faces) with Demetra George scoring.
- **Solar States**: Cazimi (<17'), Combust (<8.5°), Under the Beams (<17°), and orientality status.
- **Arabic Parts & Lots**: Accurate daytime/nighttime calculation of the Part of Fortune, Part of Spirit, and additional Hellenistic lots, including Whole Sign Fortune chart projection.
- **Time Lords**: Complete Zodiacal Releasing (L1 through L4 periods, peaking, and loosening of the bond) and Firdaria planetary rulers.

### 3. Predictive & Dynamic Timing
- **Returns**: Solar Return and Lunar Return precision calculation and chart generation.
- **Progressions & Arcs**: Secondary Progressions, Progressed Lunation cycle phases, and Solar Arc directions.
- **Transits & Cycles**: Transit biwheels, Saturn-Jupiter cycle tracking, transit lifetime timelines, and aspect windows.

### 4. Synastry & Relationship Dynamics
- Dual-wheel Synastry comparison charts.
- Midpoint Composite Charts and Davison Relationship Time-Space Charts.
- Relocation charts with preserved natal geometry.

### 5. High-Resolution Visual Rendering
- Automatic generation of 720px publication-quality SVG/PNG natal wheels, dual-wheel transit charts, and Marc Edmund Jones planetary pattern geometry rings.

---

## Saturn–Jupiter Lifetime Tables and Panorama

Look up when Saturn and Jupiter cross natal angles, enter houses, and return across the same boundary during retrograde motion. The tables support dated lookups and comparisons across life stages; the panorama makes the longer sequence visible.

| Tool | Output | Range and options |
| --- | --- | --- |
| `calculate_saturn_jupiter_cycles` | Exact Saturn and Jupiter conjunctions with natal ASC, IC, DSC and MC; direction and repeated crossings; conjunctions, waxing squares, oppositions and waning squares between transiting Saturn and Jupiter; quadrant phases and cycle position on a selected date | Birth to age 80 by default; `max_age` accepts 1–120; `as_of` selects the reference date |
| `calculate_house_ingresses` | Entries into the twelve natal Placidus houses, including direct entries, retrograde re-entries, exit times and durations | Ages 0–84, ending before the 85th birthday; optional planet and date filters |
| `render_saturn_jupiter_cycles` | A 1200 × 660 PNG panorama with angle-crossing nodes, MC / ASC–DSC / IC reference lines, label collision avoidance and an age marker for the reference date | Birth to age 80 by default; accepts `max_age`, `as_of` and a name label |

Example request after providing birth details and a resolved `location_id`: “Draw my Saturn–Jupiter panorama, then list angle crossings and house entries over the next three years, including retrograde returns.” Wave height represents chart geometry, not success or hardship. Crossings do not establish that a particular real-world event will occur.

## Multi-Technique Timeline and Lifetime Transit Overview

- **`calculate_timeline_synthesis`** combines 1–3 birthplace calendar years of Firdaria major/sub-periods, Zodiacal Releasing L1/L2 periods, progressed Moon sign ingresses and hard aspects to natal points, and Jupiter-through-Pluto conjunctions with natal angles, with timestamps and source fields.
- **30-day resonance grouping** starts from an exact event, collects events on the same target within the following 30 days, and includes same-target periods active at those event times. A group requires at least two techniques. These are rule-based cross-references, not validated predictions or measures of event probability or severity.
- **`calculate_lifetime_transit_summary`** groups exact transit counts into twelve chapters across ages 0–84, split by planet, speed group and angle/point target. Chapters start at seven-year intervals; the final chapter covers ages 77–84 and ends before the 85th birthday. Counts are not measures of stress or fortune.
- **`calculate_transits_to_natal`** retrieves dated Jupiter, Mars, Saturn, Uranus, Neptune and Pluto events over a window of up to three years. Natal angles support conjunctions only; natal points use the supported major aspects. No angle conjunctions does not mean no other angle aspects.

See [docs/tools.md](docs/tools.md) for the complete tool list.

## Installation

### Prerequisites
- **Python**: 3.12+
- **System tools**: `librsvg` (for PNG rendering) and `node` (for Jones geometric layout).
  - macOS: `brew install librsvg node`
  - Ubuntu/Debian: `sudo apt install librsvg2-bin nodejs fonts-noto-cjk fonts-noto-core`

### Setup
```bash
git clone https://github.com/qingxiayi/hellenicstar-mcp.git
cd hellenicstar-mcp
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
```

### Verification
Run the contract test suite to verify your environment:
```bash
pytest tests/ -q
```

---

## Scope & Non-Goals

- **In Scope**: Local-first calculation engine, structured verifiable facts, clean visual chart generation, and transparent algorithm registry.
- **Out of Scope**: Multi-tenant SaaS infrastructure, commercial billing/subscriptions, or AI chat wrappers. The MCP does not require or consume any model API keys.

---

## License & Attribution

- Released under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.
- Astronomical calculation core relies on **Swiss Ephemeris** (AGPL-3.0 / Professional dual license).
- Geographic resolution utilizes **GeoNames** (CC BY 4.0) and **timezonefinder**.
- See [NOTICE.md](NOTICE.md) for full third-party notices and licenses.

