# Timeline synthesis v0.1.11 — 2026-11-13

Runtime/source: `eda9bcd5ce97db733d6e3f42641d162bb7dafb8b`.
Calculation engine: `timeline-synthesis-3`.

This expands transits, adds progressed context and returns continuous orb windows.
Secondary planetary aspects and Moon ingresses existed before this release.
See [field definitions, calculation limits and reading order](../timeline-synthesis.md).
No automatic psychological-theme selection or new resonance policy is claimed.

## Verification

- Local full suite: 1424 passed and 11 subtests passed. Final timeline checks:
  39 passed. One upstream Kerykeion deprecation warning.
- The first Linux CI attempt and production candidate exposed the old 2-second
  performance guard. All numerical/contract checks passed; server sample times
  were 2.29 seconds (one year) and 3.57 seconds (three years). The expanded scan's
  fixed-sample budget is now 10 seconds, not a runtime SLA.
- Server initial full suite: 1356 passed, 66 optional reference-library checks
  skipped, 2 performance failures. After updating only the budget and docs,
  all 39 timeline checks passed (65.56 seconds total). Runtime Python files were
  compared byte-for-byte between the tested candidate and final release.
- [Final Ubuntu/macOS CI](https://github.com/qingxiayi/hellenicstar-mcp/actions/runs/43389932582):
  both passed, each with 1424 tests and 11 subtests.
- Public HTTPS initialization and all 48 tool registrations succeeded. Parameter
  structures/defaults match the predeployment schemas after excluding descriptions.
  A real 2026–2028 synthetic Paris fixture returns 84 events (65 transits), 84 orb
  windows and progressed context. All old events are preserved. Event/window,
  resonance and settings data match the local calculation exactly. Three phase
  angles are compared with absolute tolerance 1e-9 degrees; the largest observed
  difference is about 1.6e-12 degrees across platforms.
- Public agent-protocol text and selectable-field discovery include the new
  reading guidance. Selective reading of the new fields succeeded. Five submitted facts passed
  `verify_calculation_claims`, without conflicts or unverified items. The unrelated
  Jupiter/Saturn sky scan response is identical before/after deployment. See the
  [public acceptance summary](timeline-synthesis-public-2026-11-13.json).
- Source archive and manifest were downloaded from the draft release and verified
  against SHA256SUMS. Archive SHA256:
  `2323d567f93f4d67b721671be064b7d7abfdccb2299555aa2973fb34be4eadd0`.
  No local database, private notebook export or user birth case is published.

## Distribution

- [GitHub v0.1.11](https://github.com/qingxiayi/hellenicstar-mcp/releases/tag/v0.1.11):
  published with source archive, manifest and SHA256SUMS.
- Maintainer HTTPS MCP: deployed and calculation verified.
- [Glama](https://glama.ai/mcp/servers/qingxiayi/hellenicstar-mcp): final source
  synchronized; build test `01a1d3ed-d02e-7f32-98c8-3a6082fcc32e` succeeded.
  Version 0.1.11 published at 16:07 CST and marked Latest. This proves build,
  startup/discovery and publication; no new TDQS score or per-user-instance
  calculation test is claimed. The hosted maintainer HTTPS calculation was
  verified separately above.
- Smithery: the previously referenced
  `https://smithery.ai/server/@qingxiayi/hellenicstar-mcp` returns HTTP 404.
  No successful Smithery publication or update is claimed.
- [Awesome MCP Servers submission](https://github.com/punkpeye/awesome-mcp-servers/pull/16607)
  remains open and unmerged. Its version-independent repository link remains valid;
  this release does not establish directory acceptance.

## Distribution follow-up (2026-11-13)

GitHub's release-record commit `a5532fa` also passed both CI jobs. The published
release tag and active MCP service remain on `eda9bcd`. A live browser check of
the Glama public listing confirmed the expanded transit coverage, `aspect_windows`
and `progressed_context` description. A separate web-reader response still showed
the old README; it was not used as evidence of a stale live listing.

Smithery's [official notice](https://www.smithery.ai/future) confirms its 2026-10-31
connection-service shutdown. Accounts/API keys and the former API/CLI publishing
workflow are no longer a supported update route; only the non-proxied public
directory remains. Its old publishing guide returns 404 and no current project
entry/submission route was confirmed. [Distribution instructions](../distribution.md)
now state this limitation and provide the direct maintainer MCP URL. This follow-up
changes documentation only; no new calculation release or service restart.

## Deployment and rollback

MCP working directory: `/www/wwwroot/hellenicstar-mcp-releases/timeline-eda9bcd`.
Restarted at 16:02:33 CST, PID 3707686.
Override: `/etc/systemd/system/hellenicstar-mcp.service.d/zzzzzzzzzzzzzzzzzz-timeline.conf`.
To roll back, disable that override, run systemd daemon-reload and restart only
`hellenicstar-mcp`; the previous `tool-selection-f866baa` directory remains intact.
The shared environment and geographic asset were reused without package changes.

Mini Program PID 2352681 and its 2026-11-09 12:48:20 CST start time stayed unchanged.
No Mini Program frontend upload, review or publication was performed.
Existing client tool catalogs may need a connection refresh to display the new
field descriptions. Remote service acceptance does not prove every client refreshed.
