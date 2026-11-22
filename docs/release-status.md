# GitHub 源码发行 v0.1.15 · 2026-11-22

## WorkBuddy 5.11.3

v0.1.15 包含 WorkBuddy 兼容性修复。WorkBuddy 在发送请求前校验参数时，可能把核验值中的数字和布尔值转换成字符串。更新本地 MCP 并重新加载工具定义后，按原来的 JSON 类型提交即可。

在同一时刻的月相数据上复测，数字 `91.16`、整数 `4` 和布尔值 `true` 均返回 `supported`，字符串 `"4"` 和 `"true"` 均返回 `contradicted`。服务端继续严格区分文字、数字和布尔值。

本命核验也保留宫位和相位角的整数、逆行状态的布尔值，以及可空字段中的 JSON `null`。例如，正确宫位会得到 `supported`，错误的整数宫位会得到 `contradicted`，文本宫位仍是 `unverified`。

日返的目标年份指所选生日对应的回归周期。元旦或年末生日的精确回归时刻可能落在相邻 UTC 年份；计算和绘图共用同一项日期检查。

# Previous release: v0.1.14 — 2026-11-16

GitHub v0.1.14, maintainer HTTPS MCP and Glama 0.1.14 use source
`99f7950ab4578e2cb886e31b452292c508ee391d`. Nineteen chart/method tools expose
seven house systems with a disclosed Placidus default. Exact natal transit
queries retain intermediate retrograde contacts. Method-specific restrictions,
whole-sign annual profections and compatibility changes are explicit.

Local, Ubuntu and macOS full suites each passed 1559 tests and 11 subtests;
128 production candidate tests, public calculations, claim verification and PNG
checks passed. See [release evidence and rollback](validation/house-systems-release-2026-11-16.md)
and [house-system scope](house-systems.md). Clients may need a schema refresh.
Awesome MCP Servers acceptance remains pending; Smithery is not a confirmed
published channel. The Mini Program service was not deployed.

The following records describe earlier releases and their states at that time.

# Current release: v0.1.12 — 2026-11-13

GitHub v0.1.12, maintainer HTTPS MCP and Glama 0.1.12 use
`e4c9f554d16e7e2d9241026895bc94aeee451b22`. Timeline synthesis v4 adds rolling
one-to-three-year date ranges, actual interval overlaps, direct natal context,
axis-equivalent grouping and three reading layers. Local, Ubuntu and macOS
complete suites each passed 1459 tests and 11 subtests; production candidate
checks and public calculations passed. See [release evidence and rollback](validation/timeline-reading-release-2026-11-13.md)
and [usage and limits](timeline-synthesis.md). Smithery is not a confirmed
published channel. Existing clients may need a schema refresh.

The following records describe earlier releases and their states at that time.

# Current release: v0.1.11 — 2026-11-13

GitHub v0.1.11, maintainer HTTPS MCP and Glama 0.1.11 use source
`eda9bcd5ce97db733d6e3f42641d162bb7dafb8b`. Timeline synthesis v3 expands
transits, adds progressed Sun ingress/lunation context and continuous orb windows.
Local and final Ubuntu/macOS suites each passed 1424 tests and 11 subtests;
public calculations and selective reading passed. See [field definitions](timeline-synthesis.md)
and [channel verification, performance adjustment and rollback](validation/timeline-synthesis-release-2026-11-13.md).
Smithery's former publishing workflow has been retired following its 2026-10-31
service shutdown; only a public directory remains. No HellenicStar entry is
confirmed. See [current channel instructions](distribution.md).
The Mini Program service was unchanged.

The entries below are historical snapshots, including earlier pending states.

# 2026-11-09 — Tool-selection guidance v0.1.10

GitHub and production MCP now run `f866baa`. Glama source synchronization remains pending; its last confirmed release is 0.1.9. See [verification and rollback](validation/tool-selection-release-2026-11-09.md). No Mini Program frontend publication.

# Current release: v0.1.9

2026-11-09: Solar-return Chiron and lunar nodes are now included in MCP chart data
and PNG wheels. GitHub v0.1.9, maintainer HTTPS and Glama 0.1.9 all use source
`594f77a70eb7bc771ee1e64b2514031a5180443d`. Local tests, Ubuntu/macOS CI,
production-candidate tests and public MCP checks passed. See
[release verification](validation/solar-return-release-2026-11-09.md).

# Current release: v0.1.8

2026-11-07: Jones bowl-axis and individual-handle geometry correction published as
[v0.1.8](https://github.com/qingxiayi/hellenicstar-mcp/releases/tag/v0.1.8), source
`f404fa451947c649fcf96ea6fcf25428699c57ef`. The maintainer HTTPS service runs this
commit. Local validation: 1396 tests and 11 subtests passed; Ubuntu/macOS CI passed;
production-candidate validation: 1330 passed, 66 skipped, 11 subtests passed.
Six pattern families and the Jones PNG were verified through the public MCP.
All 48 input schemas remain unchanged. See [algorithm changes](jones-bowl-axis.md)
and [distribution verification](validation/jones-platform-sync-2026-11-07.md).

The records below describe earlier releases and historical preparation stages.

# Current release

2026-10-25 专业直达与按需读取指引 v0.1.5 已发布并部署（源码 `17a7c13`）：48 个工具的参数及计算逻辑保持不变，本地与 Linux/macOS CI 各 1299 项测试通过，8 个 AI 使用场景和公网验收通过。Glama 0.1.5 已发布；新版评分尚未评完，不能把 45 个工具的 4.3 平均分当作旧 3.9 整体分的提升。小程序未改动。详见[发布验证记录](validation/direct-and-guided-use-release-2026-10-25.md)。

2026-10-25 工作流调用修复 v0.1.4 已发布并部署（源码 `72bc71a`）：本地 1299 项测试、Linux/macOS CI 及公网调用通过；Glama 0.1.4 已发布，最新 TDQS 为 3.9/5（A）。小程序未改动。详见[工作流发布记录](validation/workflow-routing-release-2026-10-25.md)。

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

