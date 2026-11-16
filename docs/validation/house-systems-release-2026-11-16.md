# House systems, default disclosure and full transit contacts — v0.1.14

Source/runtime: `99f7950ab4578e2cb886e31b452292c508ee391d`.
Prepared in a clean clone of public main; unrelated original-workspace changes
were retained. Runtime transport configuration already present on public main
was preserved. No dependency changes were needed.

## Scope

Nineteen chart/renderer/lot/time-lord tools expose Placidus, Whole Sign, Equal,
Koch, Regiomontanus, Porphyry and Campanus. Omitted house systems default to
Placidus, with an actual-system notice retained in selective and image output.
This is not universal seven-system support for every technique. Annual
profections advance whole signs; the selected system controls the year lord's
natal placement. See [method and compatibility rules](../house-systems.md).

MCP exact natal transit queries retain every contact, including middle retrograde
passes; the shared Mini Program first/last display default remains unchanged.
The reported personal 2029-08-14 event was not independently reconstructed: its
original natal input was not supplied. The regression uses a disclosed synthetic
fixed target and real ephemeris motion, not a claimed validation of that person.

## Verification

- Clean release directory: **1559 tests and 11 subtests passed**, 113 seconds;
  pinned installed dependencies compatible. One existing Kerykeion deprecation
  warning. The initial run lacked the optional GeoNames database; after installing
  the local public geographic asset, the complete rerun passed.
- Real stdio with coordinate-only input: 48 tools, natal calculation, structured
  claim verification and inline PNG passed without a city database or map key.
- Production candidate: **128 tests passed**, including seven-system geometry,
  method scopes, defaults, MCP guards, provenance and retrograde contact retention.
  All 359 extracted source files matched their release manifest before switch.
- Public HTTPS: 19 seven-system schemas; 18 calculation cases covering every
  system and the extended methods matched local data with numeric absolute
  tolerance 1e-9. Aspect rows were matched by point/aspect identity because tied
  axis-contact orbs can reorder across platforms; array-order identity is not
  claimed. JSON key types were normalized for transport. References and environment
  metadata were excluded from cross-host comparison and claims checked separately.
- Public selected-system claim recomputation passed. Koch PNG rendered and was
  visually inspected; downloaded PNG bytes matched inline MCP bytes (272616 bytes).
  See [public results](house-systems-public-2026-11-16.json).
- Professional-site fixture replay passed with its documented limits: Astro.com
  252 cusps, maximum error 0.000179375 arcseconds; Astrotheme 60 planet-house
  placements matched, with existing Placidus cusp differences up to 46.62633
  arcseconds. The latter are not a claim of exact agreement. See
  [source fixtures and comparison limits](house-systems-2026-11-16/README.md).

## Deployment and rollback

Public endpoint: `https://hellenicstar.com/mcp`.
Release directory: `/www/wwwroot/hellenicstar-mcp-releases/houses-99f7950`.
Service `hellenicstar-mcp` started 2026-11-16 15:35:59 CST, PID 491434.
Existing environment, Python environment and offline geographic asset were reused.

Override: `/etc/systemd/system/hellenicstar-mcp.service.d/zzzzzzzzzzzzzzzzzzzz-house-systems.conf`.
To roll back, move this override to a name not ending in `.conf`, reload systemd,
and restart only `hellenicstar-mcp`. The preceding `timeline-e4c9f55` release and
its override remain available. Mini Program PID 2352681 and start time
2026-11-09 12:48:20 CST were unchanged; no Mini Program deployment occurred.

Clients with cached tool definitions may need to refresh their MCP connection.
The service is stateless: clients must continue passing an existing explicit
house-system preference. Structural and computational checks do not validate
psychological interpretations or predictions.

## Distribution

Version 0.1.13 was already used on Glama for source `e4c9f55` while GitHub's
latest release was v0.1.12. This release uses 0.1.14 to align the channels.
- [GitHub v0.1.14](https://github.com/qingxiayi/hellenicstar-mcp/releases/tag/v0.1.14)
  published 2026-11-16 15:41:52 CST with source archive, per-file manifest and
  SHA256SUMS. Downloaded assets passed checksum verification. Archive SHA256:
  `2be6ed48fd0c6d0645dfd88a7c5e02315f6436c58c27e0cb7fcdc47382d12fc7`.
- [CI run 43824811008](https://github.com/qingxiayi/hellenicstar-mcp/actions/runs/43824811008):
  Ubuntu and macOS both passed **1559 tests and 11 subtests** (237.94s / 286.28s).
- Maintainer HTTPS MCP: deployed and verified as described above.
- [Glama](https://glama.ai/mcp/servers/qingxiayi/hellenicstar-mcp): repository synced
  to `99f7950`; build test `01a1e348-9f79-717a-86c2-31e32e5e2a25` succeeded
  (3m 48.8s). Release **0.1.14** was published at 15:42 CST and marked Latest.
  Listing description was updated. This establishes build/startup/discovery and
  publication, not calculation coverage for every hosted instance or a new TDQS.
- [Awesome MCP Servers PR #16607](https://github.com/punkpeye/awesome-mcp-servers/pull/16607)
  remains open. Its existing entry points to the updated repository and Glama
  listing and contains no obsolete version/house-system restriction; no redundant
  submission or comment was made. Upstream acceptance remains pending.
- Smithery's [official transition notice](https://www.smithery.ai/future) still
  states that the old connection/publishing infrastructure was shut down on
  2026-10-31. The former project path currently displays that notice, not a
  HellenicStar listing; no current self-service publication was confirmed.

Source release, production and Glama are pinned to `99f7950`. Subsequent
 documentation-only commits record acceptance without changing runtime code.
