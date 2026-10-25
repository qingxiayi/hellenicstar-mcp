# Workflow routing release — 2026-10-25

This release fixes workflow selection and clarification guidance. Parallel chart requests retain all candidates; event-range requests do not silently become current snapshots; data-only requests do not require optional renderers; image-only requests use existing validated renderers. L4 aliases preserve parent-period selection. Unsupported image requests return clarification.

All 48 tool names and input schemas remain unchanged. No calculation engine, proprietary interpretation rules, license, or Mini Program files are changed. The router remains deterministic and stateless; callers must check information already supplied and ask only for missing or ambiguous prerequisites. This is not proof of every AI client's conversational compliance.

## Validation

- Local targeted workflow/protocol tests: 68 passed.
- Full public-source checkout validation: 1299 passed, no skips, one existing Kerykeion deprecation warning (75.56 seconds).
- The first full run lacked the ignored location database. Configuring MCP_LOCATION_DB_PATH to an existing MCP database resolved the setup failure; calculation code was not modified to bypass tests.
- Local FastMCP calls confirmed event routing, direct Jones rendering selection, and missing-input clarification from calculate_natal_chart.

## Publication

GitHub CI, release assets, isolated service cutover, public HTTPS calls, and Glama discovery are pending at source preparation. Actual outcomes will be recorded after verification. Awesome listing URL/install path are unchanged. Smithery formal onboarding remains unverified; no new permissions are requested.
