# Workflow routing release — 2026-10-25

This release fixes workflow selection and clarification guidance. Parallel chart requests retain all candidates; event-range requests do not silently become current snapshots; data-only requests do not require optional renderers; image-only requests use existing validated renderers. L4 aliases preserve parent-period selection. Unsupported image requests return clarification.

All 48 tool names and input schemas remain unchanged. No calculation engine, proprietary interpretation rules, license, or Mini Program files are changed. The router remains deterministic and stateless; callers must check information already supplied and ask only for missing or ambiguous prerequisites. This is not proof of every AI client's conversational compliance.

## Validation

- Local targeted workflow/protocol tests: 68 passed.
- Full public-source checkout validation: 1299 passed, no skips, one existing Kerykeion deprecation warning (75.56 seconds).
- The first full run lacked the ignored location database. Configuring MCP_LOCATION_DB_PATH to an existing MCP database resolved the setup failure; calculation code was not modified to bypass tests.
- Local FastMCP calls confirmed event routing, direct Jones rendering selection, and missing-input clarification from calculate_natal_chart.

## Publication and deployment verified

- Source: `72bc71a019331f049de1e50d2d84c97118da50ba`, published as [v0.1.4](https://github.com/qingxiayi/hellenicstar-mcp/releases/tag/v0.1.4).
- [GitHub Actions 40158533339](https://github.com/qingxiayi/hellenicstar-mcp/actions/runs/40158533339): Linux and macOS jobs passed.
- Release archive: 318 files, SHA256 `036a5732fe0e2da7924036d980ed5a65854b50dea27ea7d0bdddbae97ab0439f`. Source manifest accompanies the archive.
- Isolated production candidate: `workflow-72bc71a`. All 48 input schemas match the preceding deployment. Full serialized natal calculation, transit snapshot and Jones rendering outputs have identical hashes between old and new server candidates.
- Production MCP service switched at 2026-10-25 11:42:27 Asia/Shanghai. Rollback to the preceding service configuration is prepared. The Mini Program process ID and start time remained unchanged; no Mini Program source or deployment was modified.
- Public `https://hellenicstar.com/mcp`: initialization and discovery passed; all 48 tool schemas/descriptions match the released source. Six routing cases, two missing-input cases, complete natal and transit calculations, Jones inline PNG and HTTP PNG download passed. Protocol tool/resource/prompt content matches. See [machine-readable acceptance](workflow-routing-public-2026-10-25.json).
- Glama build `01a1711f-5a4e-7210-86a3-975f5492b482` succeeded against `72bc71a`; version 0.1.4 was published at 11:39. Public Schema exposes the revised recommend_workflow definition and 48 tools.
- Glama TDQS was re-evaluated at 11:40: **3.9/5, grade A**, compared with the earlier observed 4.0. Reported weaknesses remain tool count (2/5) and disambiguation (3/5); naming consistency is 5/5 and completeness 4/5. This release does not claim a score improvement or an astrology-accuracy rating. The score is a platform snapshot and can change.
- Awesome listing URL/install path are unchanged, so no listing edit is needed. Smithery formal onboarding remains unverified; no permissions were expanded.

These checks demonstrate the deployed routing and selected calculation/render paths. They do not establish that every AI client will follow the clarification protocol in conversation. No proprietary-experience split was performed in this release.
