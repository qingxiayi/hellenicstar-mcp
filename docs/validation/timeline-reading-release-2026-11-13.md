# Timeline reading and rolling years — v0.1.12

2026-11-13. Source/runtime: `e4c9f554d16e7e2d9241026895bc94aeee451b22`.
Calculation engine: `timeline-synthesis-4`; reading policy: `timeline-reading-1`.

Users can request either calendar years (`target_year`) or one to three years
from an explicit local date (`start_date`), with `span_years=1` as the default.
Actual bounds, anniversary and midnight policies are returned. Periods,
progressed background, contacts and orb windows are calculated at the requested
start. New reading views expose real overlap, direct natal context and reading
order without selecting a psychological theme. See [rules](../timeline-synthesis.md).

## Acceptance

- Local complete suite: **1459 passed and 11 subtests passed**; dependency check
  passed. One existing Kerykeion deprecation warning.
- Production candidate on the existing server environment: **74 timeline tests
  passed**, including new reading and rolling-date cases.
- Integrated original working tree: **35 new range/reading tests passed**;
  unrelated work was retained.
- Real local stdio and public HTTPS calculations covered calendar year 2027,
  2026-11-13 through the exclusive 2027-11-13 anniversary, and a three-year
  rolling interval ending exclusively 2029-11-13. The Paris regression fixture
  is the public example; no personal case is included.
- All new and existing timing/reading fields match local results, with absolute
  tolerance 1e-9 for floating-point coordinates. Public claim recomputation
  supported four facts for each case; selective reading preserved references.
  Mixed start selectors were rejected. All 47 unrelated tool input schemas and
  the sampled Jupiter/Saturn sky scan were unchanged. See [results](timeline-reading-public-2026-11-13.json).
- Release archive and manifest were downloaded from GitHub and verified against
  `SHA256SUMS`. Source archive SHA256:
  `7283595f9f5e29eff23e01ab9920a8b583c4b2326f1c3051014f01392256d427`.

- [Ubuntu and macOS CI](https://github.com/qingxiayi/hellenicstar-mcp/actions/runs/43440141884)
  both passed **1459 tests and 11 subtests**.

## Deployment and rollback

MCP release directory: `/www/wwwroot/hellenicstar-mcp-releases/timeline-e4c9f55`.
Started at 22:13:11 CST, PID 3792978. All extracted source files were verified
against the archive manifest before switching. The environment and geographic
asset were reused without package changes.

Override: `/etc/systemd/system/hellenicstar-mcp.service.d/zzzzzzzzzzzzzzzzzzz-timeline-reading.conf`.
To roll back, move this override to a name not ending in `.conf`, reload systemd,
and restart only `hellenicstar-mcp`; the previous `timeline-eda9bcd` override and
release remain available. The unrelated Mini Program service's PID and start
time stayed unchanged; no frontend publication was performed.

Clients with cached schemas may need to refresh their MCP connection to discover
`start_date` and the new fields. Public service acceptance is not evidence that
all clients have refreshed. Full runtime tests do not establish psychological
interpretations or predictive accuracy.

## Distribution

- [GitHub v0.1.12](https://github.com/qingxiayi/hellenicstar-mcp/releases/tag/v0.1.12):
  published with source archive, manifest and checksum list.
- Maintainer Streamable HTTP MCP: deployed and calculations verified at
  `https://hellenicstar.com/mcp`.
- [Glama](https://glama.ai/mcp/servers/qingxiayi/hellenicstar-mcp): source
  synchronized; build test `01a1d545-15fd-7db6-90e7-545a3e19326e` succeeded on
  `e4c9f55`. Release 0.1.12 was published at 22:22 CST and marked Latest.
  This establishes build/startup/discovery/publication, not every user instance's
  calculation behavior or a new TDQS assessment.
- Smithery's former publishing workflow remains retired; no project entry or
  new publication is claimed. See [distribution limits](../distribution.md).

The source release and deployment remain on `e4c9f55`; later documentation-only
commits record the completed channel checks without changing runtime code.
