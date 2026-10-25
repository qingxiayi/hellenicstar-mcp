# Tool-definition follow-up and community channels — 2026-10-25

## Verified baseline

Glama's TDQS administration page for release 0.1.1 reports **4.0/5 average across 48 tools**, compared with the recorded 0.1.0 average of 3.9/5. The public overview displays **3.7/5** as a separate overall score, alongside server-level disambiguation, naming, tool-count and completeness factors. These values must not be presented as the same metric. This is definition quality, not proof of calculation correctness.

The two tools improved on 2026-10-24 now read: calculate_natal_salience 4.6/5 and render_saturn_jupiter_cycles 4.8/5. These were the baseline values; the completed 0.1.2 evaluation is recorded below.

## Scoped improvements

The five lowest-rated tools in release 0.1.1 were calculate_house_rulers (3.2), render_solar_arc_biwheel (3.2), calculate_solar_arc (3.3), render_composite_chart (3.3), and render_solar_return_chart (3.3). Their reviews consistently identified missing input semantics and insufficient guidance distinguishing related tools.

- Explain exact local civil birth inputs, location-ID resolution and user-confirmed DST folds.
- Explain the explicit house-system and return-location choices rather than silently supplying them.
- Document solar-arc age precedence, age-window defaults, UTC-noon reference dates and the different handling of out-of-range derived ages by calculation and rendering.
- Explain image versus data tools, composite versus Davison charts, and solar arc versus progression/transit techniques.
- State that rendering computes and checks its own source, returns inline MCP image content, and requires client image support.

All 48 tool schemas and annotations are identical after removing description keys. All five modified tools now describe every top-level parameter. An AST comparison of the complete entry point confirms no changes beyond the five tool descriptions and parameter-description annotations; calculation bodies and validation behavior remain unchanged.

## Local validation

The clean public-source checkout passed the full required verification: **1,243 passed, zero skipped**, with one upstream Kerykeion deprecation warning. Dependency compatibility also passed. This includes existing calculation, input-clarification, discovery, output-contract and image-rendering tests. CI and deployment results must be recorded separately.

## Community and channels

Community guidance and three optional feedback templates were published in 8a41701. Users retain their contribution copyright; contributions follow AGPL-3.0, and showcase republication requires explicit permission. No use registration or mandatory upstream contribution is introduced.

Awesome MCP Servers PR #16607 was updated on its existing branch (f925250): remove the stale fixed count of 42, describe current capabilities, and remove the Windows marker because Windows native operation is not covered by project CI. This is an updated submission, not a merged listing.

Glama listing metadata sync and Glama version publication are separate actions. A push to main alone does not prove that the README mirror, deployed image or TDQS evaluation updated. Smithery publication remains unverified; no expanded OAuth permissions are authorized by this work.

## References

- https://glama.ai/mcp/servers/qingxiayi/hellenicstar-mcp/admin/tdqs
- https://glama.ai/mcp/servers/qingxiayi/hellenicstar-mcp
- https://github.com/punkpeye/awesome-mcp-servers/pull/16607
- [Previous definition review](tool-definition-review-2026-10-24.md)

## Published release and standalone deployment

- GitHub release [v0.1.2](https://github.com/qingxiayi/hellenicstar-mcp/releases/tag/v0.1.2) targets `cbcda24ae13c0b2a659a7d4387b05aab22cc7e6b`.
- [CI run 40150198569](https://github.com/qingxiayi/hellenicstar-mcp/actions/runs/40150198569) passed on macOS and Ubuntu.
- Source archive: 313 files; SHA256 `0bbd82edf491d6b9106eaac796a7a5dce7f3a15298fd6e4bf9f6a18b571bc04b`.
- On the production host, all Python files except `mcp_server.py` match the previous release. All 48 tool definitions match after removing descriptions. Two real calculation outputs and three rendered outputs have identical hashes before and after the change.
- The isolated MCP service switched to `tool-definitions-cbcda24` at 2026-10-25 09:56:31 Asia/Shanghai. Existing chart storage, location database, caches and service security settings were retained. The corresponding-source URL points to the exact deployed commit.
- A real public HTTPS client initialized, listed 48 tools with the expected schemas/descriptions, called all five changed tools successfully, received three inline PNGs, and downloaded each image URL with HTTP 200. Missing birth input still returns `needs_clarification`. See [public acceptance evidence](tool-definition-public-2026-10-25.json).
- Mini Program PID `1086608` and start time `2026-10-11 01:01:02 CST` stayed unchanged. Only the standalone MCP service restarted.
- Rollback is available on the host with `sudo sh /tmp/rollback-hellenicstar-cbcda24.sh`; it disables only the new service drop-in and restarts only MCP.

Glama repository sync was verified at `cbcda24`; its public README contains the new voluntary feedback links. Build test `01a170a6-6263-7ffd-b596-b8d41434a25f` succeeded and discovered the updated tools. Version publication and its new TDQS evaluation are tracked separately below.

### Earlier Glama publication delay (resolved)

Both build tests succeeded at the intended source commit: `01a170a6-6263-7ffd-b596-b8d41434a25f` and the subsequent Build & Release test `01a170ca-d5a7-7a18-8f4e-6f48e4a0f542`. However, the existing Make Release link navigated to a build-log page without a release form, and Build & Release completed its build without adding a release. The verified releases list still shows 0.1.1 as latest. Auto-Release is enabled, but its setting is not evidence of successful publication. No additional builds were started after these checks.

The latest evaluated release remains 0.1.1, with average TDQS 4.0/5 across 48 tools. New version publication and the five updated definitions' evaluation remain unconfirmed. GitHub v0.1.2 and the standalone public service are already published/deployed; this is a Glama publication blocker, not a runtime failure.

### Glama release and evaluation confirmed

The subsequent live check confirmed release **0.1.2**, published **2026-10-25 10:09 Asia/Shanghai**, associated with build `01a170ca-d5a7-7a18-8f4e-6f48e4a0f542`. The earlier unconfirmed-publication status is superseded. The exact cause of the delay was not established.

TDQS for the selected latest release is **4.1/5 across all 48 tools**, up from 4.0 for 0.1.1 and 3.9 for 0.1.0. The five changed tool definitions now score:

| Tool | 0.1.1 | 0.1.2 |
| --- | --- | --- |
| calculate_house_rulers | 3.2 | 4.6 |
| render_solar_arc_biwheel | 3.2 | 4.7 |
| calculate_solar_arc | 3.3 | 4.8 |
| render_composite_chart | 3.3 | 4.8 |
| render_solar_return_chart | 3.3 | 4.8 |

This is tool-definition quality, not a new independent calculation-accuracy certification. No further rebuild or production deployment was needed for this verification.
