# Current release

2026-10-25 工作流调用修复已通过本地完整验证（1299 项）；GitHub、部署与平台状态分别见[工作流发布记录](validation/workflow-routing-release-2026-10-25.md)。

# Current release status

Six additional tool definitions and task-selection guidance are deployed at `897944e`; public calls pass. See [the six-tool verification record](validation/six-tool-guidance-2026-10-25.md) for CI and Glama publication status.

Version v0.1.2 is published and deployed: five tool definitions now explain inputs and routing, with calculation behavior unchanged. Community contribution and voluntary feedback guidance is included. See [the 2026-10-25 verification record](validation/tool-definition-followup-2026-10-25.md) for CI, public runtime checks and separate channel status.

The reference round-trip, summary membership and algorithm registration repair is deployed and public. Natal v4 and relationship observation v0.14 calculation facts are retained. See [the 2026-10-24 release verification](validation/reference-roundtrip-release-2026-10-24.md).

Relationship observation v0.14 is deployed and public (48 tools), with natal priorities v4 retained. See [the 2026-10-23 relationship release record](validation/relationship-observation-release-2026-10-23.md) for public HTTPS verification, compatibility and Mini Program isolation.

Natal priorities v4 is deployed and its source is public; see [the 2026-10-23 verification record](validation/natal-jones-release-2026-10-23.md). The earlier local-preparation notes below are historical, not the current GitHub or production status.

# Standalone release verification

The historical preparation records below describe the initial source release.
The public repository now includes the natal structure graph tool (45 tools).
See [the 2026-10-21 release verification](validation/natal-structure-release-2026-10-21.md)
for the deployed source revision and the scope of current runtime checks.

The standalone cleanup removes the legacy course/report generation and model API
code. Classical MCP results use a calculation-field allowlist; the two inherited
interpretation fields were intentionally removed from the initial snapshot baseline.
Images are refused after seven days and cleaned periodically while HTTP is running.

All referenced calculation regression files are now shipped. The full test command
is `bash scripts/verify.sh` with `requirements-dev.lock` and the optional public
GeoNames database installed. Tests include real stdio/HTTP exchanges, all 42 tool
registrations, chart rendering, birth-time ambiguity, core algorithms, and selected
independent-library comparisons. `quality.status=passed` still means structural and
registered-invariant checks, not an independent proof of every algorithm.

Runtime preparation is verified on macOS / Python 3.12. GitHub Actions and Docker
recipes are included, but Linux CI, Docker execution and a public HTTPS deployment
have not been run from this local preparation. They must not be reported as passed.

The public geographic asset is rebuilt solely from the official GeoNames cities500
archive with input SHA256 recorded in its metadata. Local predecessor databases,
private aliases and runtime state are excluded from the source archive.

Use `python scripts/build_release.py` for the clean source archive and per-file hash
manifest. Initialize the public repository from that archive rather than pushing the
local preparation history, whose initial commit still contains legacy business code.
See NOTICE.md for upstream notices and transformations; SECURITY.md and deployment.md
cover operator configuration.

## Local verification record (2026-10-14)

- Clean source extraction into an unrelated temporary directory, Python 3.12.13,
  pinned development dependencies and separately checksum-installed public data.
- Full clean-install suite: **663 passed, zero skipped**, one upstream Kerykeion
  `datetime.utcnow` deprecation warning. Dependency consistency check passed.
- Real loopback HTTP client: initialize, list 42 tools, coordinate resolution,
  natal/classical calculations without a city database or map key, chart rendering,
  and PNG download with `no-store`; downloaded bytes match MCP inline image bytes.
- Manually inspected the natal PNG. Zodiac symbols use bundled vector outlines;
  system emoji/font substitution no longer turns those symbols into colored blocks.
- A long installation path exposed a Swiss Ephemeris search-path buffer overflow.
  The guard now uses the checked ephemeris directory alone when concatenated paths
  exceed the library limit, and rejects an oversized own directory explicitly.
  Regression tests verify actual returned file-mode flags, including Chiron.

These results establish the local source candidate, not public deployment, client
marketplace registration, throughput capacity, or correctness of every interpretation.

## Client task acceptance update (2026-10-14)

See [the task acceptance report](task-acceptance-2026-10-14.md). Real Codex CLI /
GPT-5.5 task runs uncovered two delivery defects despite the earlier passing suite:
stdio advertised an unserved HTTP image URL, and axis transit settings overstated
the supported aspects. Both output contracts were corrected and client cases rerun.
Axis transits still support conjunctions only; other axis aspects remain unsupported.
Graphical-client image display remains unverified.

After these corrections: clean-install regression **665 passed, zero skipped**, one
upstream deprecation warning; real HTTP image/download smoke passed. A separate
runtime-only dependency installation also passed stdio calculation, error-handling
and inline-image checks. This does not supersede the untested platform boundaries.

Additional client tests completed solar-return, secondary-progression, solar-arc and
zodiacal-releasing outputs, with recoverable input errors and protocol deviations
recorded in the task report. MCP Inspector 2.11.0 visibly rendered the inline PNG.
A repeated solar-return run was blocked by a model-channel HTTP 400; it is not a pass.
No calculation implementation changed in this additional test round.


## Linux virtual machine verification (2026-10-15)

Isolated Linux execution was performed in a dedicated Lima virtual machine
(Ubuntu 26.04.1 LTS, aarch64 Linux kernel 7.0.0-34-generic, Python 3.14.4):
- Source archive `dist/hellenicstar-mcp-source.tar.gz` was extracted cleanly.
- Native build tools and system libraries (`librsvg2-bin`, `nodejs`, `fonts-noto-cjk`)
  were installed via apt.
- Pinned runtime dependencies from `requirements.lock` compiled C extensions
  (`pyswisseph`, `timezonefinder`, `scour`) successfully.
- Full development suite `bash scripts/verify.sh` achieved **665 passed, zero skipped**,
  1 upstream deprecation warning.
- Real stdio client smoke confirmed 42 tools listed, `calculate_natal_chart` returning
  valid calculation output, and `render_natal_chart` returning valid inline PNG.
- The temporary VM instance was completely stopped and deleted after testing.

