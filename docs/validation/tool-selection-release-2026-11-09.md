# Tool-selection guidance release — 2026-11-09

Source/runtime: `f866baa64f7146e516de522f063dd7024d70d221`.

The release distinguishes adjacent tools through discovery descriptions, parameter
metadata and a selection table in the agent protocol. The optional keyword
workflow directory now includes sky-pair scans and selected lots, and recognizes
日返. It retains all 48 tools and changes no calculation algorithm, parameter type,
default or validation rule. No measured model-selection accuracy or new Glama
score is claimed.

## Verification

- Local full suite before terminology correction: 1413 passed, 11 subtests passed,
  one upstream deprecation warning. Final routing/discovery checks: 82 passed.
- [Final Ubuntu/macOS CI](https://github.com/qingxiayi/hellenicstar-mcp/actions/runs/42571324016): both passed.
- Final production candidate: 1346 passed, 66 skipped, 11 subtests passed.
- Public HTTPS initialize and 48-tool discovery passed. After removing descriptive
  metadata, all input schemas equal the previous deployment. All exposed inputs
  of the three targeted tools have descriptions. Workflow probes for sky-pair
  scan, lots, 日返 and transit snapshot choose their intended tools. The agent
  protocol serves the new selection table. A real Jupiter/Saturn square scan over
  2026 returns exactly the same response as before deployment.
- [GitHub v0.1.10](https://github.com/qingxiayi/hellenicstar-mcp/releases/tag/v0.1.10):
  archive, manifest and SHA256SUMS published, downloaded and verified.
  Archive SHA256: `9dcd52ee7d0955bce46dbd4af9754c931288f3b45e03bf7b8737ee0c28936317`.
- Glama repository sync requested at 14:08 CST. At 14:15 CST it still displayed
  Sync in Progress and the old known commit `594f77a`. A build pinned to the final
  commit was rejected as Commit not found. Glama 0.1.10 is not yet confirmed;
  its existing 0.1.9 release remains available. This is an indexing/build gate,
  not a failed production MCP deployment.

## Deployment and rollback

MCP restarted at 14:15:02 CST, PID 2378092, directory
`/www/wwwroot/hellenicstar-mcp-releases/tool-selection-f866baa`.
Override: `/etc/systemd/system/hellenicstar-mcp.service.d/zzzzzzzzzzzzzzzzz-tool-selection.conf`.
Disable this override, daemon-reload and restart MCP to restore the previous
solar-return release. The old directory and shared environment remain available.
Mini Program PID 2352681 and its 12:48:20 CST start time stayed unchanged.
No Mini Program frontend upload, review submission or publication was performed.

The original development checkout received selective guidance changes only. Its
pre-existing additional classical `planets` input is preserved and described
locally; it is not newly exposed by this public release.
