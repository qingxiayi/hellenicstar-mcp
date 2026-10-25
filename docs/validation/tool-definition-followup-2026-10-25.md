# Tool-definition follow-up and community channels — 2026-10-25

## Verified baseline

Glama's TDQS administration page for release 0.1.1 reports **4.0/5 average across 48 tools**, compared with the recorded 0.1.0 average of 3.9/5. The public overview displays **3.7/5** as a separate overall score, alongside server-level disambiguation, naming, tool-count and completeness factors. These values must not be presented as the same metric. This is definition quality, not proof of calculation correctness.

The two tools improved on 2026-10-24 now read: calculate_natal_salience 4.6/5 and render_saturn_jupiter_cycles 4.8/5. Today's changes have not yet received a new evaluation.

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
