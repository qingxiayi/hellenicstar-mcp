# Six-tool guidance release — 2026-10-25

Source: `897944ecba70e2c7bab30a99dbb044cd2db1a666`. GitHub [v0.1.3](https://github.com/qingxiayi/hellenicstar-mcp/releases/tag/v0.1.3) published with source archive and checksums.

Clarified six tool descriptions and all their top-level parameter descriptions: `calculate_progressed_lunation`, `calculate_time_lords`, `get_transit_snapshot`, `render_jones_pattern`, `render_transit_biwheel`, `render_sky_chart`. Added bilingual task selection in `docs/tools.md`.

- No tool additions/removals/renames; 48 tools retained. Stripping descriptions gives identical schemas. AST comparison confirms no calculation, default or parameter-type changes.
- Local required verification: 1243 passed, no skips, one existing upstream Kerykeion deprecation warning (74.78 seconds).
- Six real local calls succeeded; each tool requests clarification for missing required inputs.
- Server before/after: all six serialized output hashes identical, including three PNG results.
- Standalone service deployed to `/www/wwwroot/hellenicstar-mcp-releases/tool-definitions-897944e`; PID 1623648, started 2026-10-25 10:38:15 CST. Rollback script available at `/tmp/rollback-hellenicstar-897944e.sh` on server.
- Mini Program unchanged: PID 1086608; start time 2026-10-11 01:01:02 CST. No Mini Program source or service operations.
- Public HTTPS initialization, 48-tool discovery and matching descriptions/schemas passed. Six calls status ok; three inline PNGs and public image links HTTP 200. See [public evidence](six-tool-public-2026-10-25.json).
- Source archive SHA256: `032538c340baccc3cc0ac6cbf5fc66db72a8884f5b86cb957cdf8b575eba2fd2` (314 source files).
- GitHub CI: https://github.com/qingxiayi/hellenicstar-mcp/actions/runs/40154991456 — success on macOS and Ubuntu.
- Glama Build & Release requested for pinned source 897944e, build `01a170ea-f57d-7821-b2b0-d953f413a562`. Build succeeded in 2m 59.2s; Glama v0.1.3 published and all 48 tools discovered. The six changed tools are queued for evaluation; the displayed 4.2 average covers only the other 42 tools and is not the final release average. Future releases must update or clear the pinned commit before building. Previous public TDQS 3.9/5 is not this round's result.
- Awesome listing description/install route unchanged; no update needed. Smithery registration remains unverified; no new permission granted.
