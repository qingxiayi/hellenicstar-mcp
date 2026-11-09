# Solar-return points release — 2026-11-09

Source/runtime: `594f77a70eb7bc771ee1e64b2514031a5180443d`.

The return engine already calculated Chiron and both lunar nodes, but omitted them
from `single`. This release exposes `chart.special_points` in MCP data and maps
those three points into the PNG renderer. Existing planetary/aspect calculations
and explicit return-location confirmation are unchanged.

- Local suite: 1398 passed, 11 subtests passed; one upstream deprecation warning.
- [Ubuntu/macOS CI](https://github.com/qingxiayi/hellenicstar-mcp/actions/runs/42567012418): both passed.
- Production candidate: 1332 passed, 66 skipped, 11 subtests passed.
- Public HTTPS: initialize and 48-tool discovery passed; all input schemas identical
  to the previous deployment. Existing chart, return instant, overlay, focus and
  timeline fields match the predeployment result. Three special points are present;
  inline PNG returned successfully and visually checked.
- [GitHub v0.1.9](https://github.com/qingxiayi/hellenicstar-mcp/releases/tag/v0.1.9):
  source archive, per-file manifest and SHA256SUMS published and downloaded/verified.
  Archive SHA256: `ee071e82e05d3dcb94e3522b9be83ae5e1551a4143d8289d9eaaeeac7df44794`.
- [Glama build](https://glama.ai/mcp/servers/qingxiayi/hellenicstar-mcp/admin/dockerfile/tests/01a1bec5-0d9a-76e0-aefb-ac7753c7cbab):
  successful build and MCP discovery against this exact commit; release 0.1.9
  published at 13:31 CST. This also brings the preceding Jones fix to Glama.
  No paid hosted instance was created.
- Awesome MCP Servers PR #16607 remains open. Its version-independent links remain
  valid. Smithery candidate listing still returns 404; no existing deployment was
  available to update. Uncontrolled mirrors and user installations are not claimed
  to have upgraded.

## Deployment and rollback

MCP restarted at 13:29:39 CST, PID 2364443, directory
`/www/wwwroot/hellenicstar-mcp-releases/solar-points-594f77a`.
Override: `/etc/systemd/system/hellenicstar-mcp.service.d/zzzzzzzzzzzzzzzz-solar-points.conf`.
Disable this override, daemon-reload and restart MCP to restore the previous Jones
release. The old directory and shared environment remain available.
Mini Program PID 2352681 and its 12:48:20 CST start time stayed unchanged.
No Mini Program frontend upload, review submission or publication was performed.
