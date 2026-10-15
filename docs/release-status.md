# Standalone release verification

This is a local source-release candidate. No remote repository has been created,
no Git history has been pushed, and no production server has been changed.

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

