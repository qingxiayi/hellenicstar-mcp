# Distribution verification — 2026-11-07

The Jones correction runtime/source commit is
[`f404fa451947c649fcf96ea6fcf25428699c57ef`](https://github.com/qingxiayi/hellenicstar-mcp/commit/f404fa451947c649fcf96ea6fcf25428699c57ef).
A later documentation-only commit does not change the deployed calculation code.

| Channel | Verified state |
| --- | --- |
| [GitHub source](https://github.com/qingxiayi/hellenicstar-mcp) | Jones correction pushed to main; Ubuntu and macOS CI passed. |
| [GitHub release v0.1.8](https://github.com/qingxiayi/hellenicstar-mcp/releases/tag/v0.1.8) | Published as latest, targeting f404fa4. Source archive, per-file manifest and SHA256SUMS uploaded, downloaded again, and verified. |
| [Maintainer HTTPS MCP](https://hellenicstar.com/mcp) | f404fa4 deployed; initialization, 48-tool discovery, six pattern families, input-schema compatibility and PNG fetch verified. |
| [Glama](https://glama.ai/mcp/servers/qingxiayi/hellenicstar-mcp) | Listing exists. Updated source build/publication is pending authenticated admin access; do not infer build synchronization from the displayed version number. |
| [Awesome MCP Servers submission](https://github.com/punkpeye/awesome-mcp-servers/pull/16607) | PR remains open and unmerged. Its version-independent GitHub/Glama links remain correct; main README does not yet contain the entry. No release-specific edit is needed. |
| Smithery | No established published entry was found in project records. The candidate https://smithery.ai/server/@qingxiayi/hellenicstar-mcp returns 404. Do not report it as an upgraded deployment. |

The release archive contains 327 files. SHA-256:
`69b4f162a930bc6753537c8f203067cd3e803eeaa1c4ffd02b009d9d07a02366`.

Independent directories/search caches/mirrors are not maintainer-controlled runtime
instances. Updating the canonical repository/release does not prove those services
have refreshed their indexed text or that existing user installations have upgraded.

Known pre-existing issue remains documented in the release notes: some combined
Fanhandle focus labels are rejected by the classical-result validator. This is not
counted as fixed by the bowl-axis correction.
