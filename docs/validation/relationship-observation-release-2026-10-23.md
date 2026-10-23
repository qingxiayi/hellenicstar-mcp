# Relationship observation v0.14: deployed and open source

Verified on 2026-10-23 (Asia/Shanghai). Runtime source: [`05a62e78c932ea0cbc8875f3486e9787a75417d4`](https://github.com/qingxiayi/hellenicstar-mcp/commit/05a62e78c932ea0cbc8875f3486e9787a75417d4). Public endpoint: <https://hellenicstar.com/mcp>.

Adds `calculate_relationship_observation` and `prepare_relationship_observation_note`, taking discovery from 46 to 48 tools. The existing natal priorities v4 implementation is retained. Relationship observation produces deterministic structures and observation paths, not compatibility scores, psychological diagnoses or automatic IFS mappings. Human notes remain caller-owned and nonpersistent.

## Verification

- Local public-source candidate: **1198 passed, zero skipped**, one dependency deprecation warning; dependency consistency passed.
- [GitHub Actions 39968818121](https://github.com/qingxiayi/hellenicstar-mcp/actions/runs/39968818121): Ubuntu and macOS each **1198 passed**, one warning.
- Server candidate: **1132 passed, 66 skipped**. Optional comparison packages `astrologica` and `stellium` are absent there; these skips are not passes. The complete local/CI runs cover those optional comparisons.
- All 113 checked runtime source/assets/ephemeris file hashes match the public code commit.
- Candidate loopback HTTP and post-cutover **public HTTPS** both completed initialization, discovery and real tool calls. Public proof: [relationship-observation-public-2026-10-23.json](relationship-observation-public-2026-10-23.json).
- Real calls covered love, friendship, work and family; single-person natal mode; timing-window scanning; a declared parent/child birth event; human notes; a supported claim and a deliberately contradicted claim.
- The synthetic pair returns 61 unique contacts and 122 directional observation paths in each scenario. These are structural counts, not strengths or match scores. Changing scenario does not change geometric facts.
- Selected natal v4 output (`schema_version`, `focus_selection`, `jones_view`, plus retained control fields) and the original relationship tool's result facts match the predeployment public baseline. An old public natal calculation reference remains verifiable. This is a bounded regression check, not proof for every possible input.

## Compatibility and conventions

All 45 other existing tool input schemas remain unchanged. The existing `verify_calculation_claims` reference-input schema adds one bounded nested-object alternative for relationship context and timing; all previous alternatives remain accepted. Transport, CORS, authentication, endpoint settings, dependency locks and shared calculation engine are retained. The shared motif enumerator adds an optional point set while retaining its original ten-planet default.

Natal lunar nodes remain **mean nodes**, including the childbirth path. Explicit-date timing retains its existing true-node convention and reports that distinction; this release does not claim a uniform mean-node convention across every timing calculation.

The public repository retains its AGPL-3.0 license. The publication includes implementation, documentation and synthetic tests; private birth data, consultation reports, runtime caches, local databases and source PDFs were excluded.

## Deployment and isolation

Only `hellenicstar-mcp` was restarted. Its active directory is `/www/wwwroot/hellenicstar-mcp-releases/relationship-observation-05a62e7`, PID `1129550`, active since `2026-10-23 22:44:52 CST`. Source URL points to the exact code commit above.

`hellenicstar-miniapp` stayed active with the same PID `1086608` and start time `2026-10-11 01:01:02 CST` before and after the switch. This deployment made no Mini Program code, service or proxy changes.

Rollback retains `/www/wwwroot/hellenicstar-mcp-releases/natal-jones-d37f6f8`. Remove/disable only the new `zzzzzzz-relationship-observation.conf` systemd override, reload systemd and restart only MCP. The prepared rollback script is `/tmp/rollback-jg-observation-server.sh` on the server. No rollback was needed.

This release record verifies the shipped computation and deployment. It does not claim complete numerical reproduction of every book case or independent validation of the book's psychological interpretations.
