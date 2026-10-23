# Reference round-trip repair: release verification

Runtime/source commit: [`9327eec2f8c5ca13e2b334e525a2060841ebf689`](https://github.com/qingxiayi/hellenicstar-mcp/commit/9327eec2f8c5ca13e2b334e525a2060841ebf689). The reference, summary and registration fix is in its parent `f621e59`; the final commit also repairs the standalone audit entry point. The repository remains public and AGPL-3.0.

See [the defect and compatibility report](reference-roundtrip-repair-2026-10-24.md). Calculation schemas remain `natal-priorities-v4`, `natal-structure-v1` and `john-green-observation-v0.14`. All 48 tool input schemas are unchanged. The only reference version change is `calculation-reference-v2`, with unchanged v1 references still supported.

## Verification

- Local clean public-source suite: 1239 passed, zero skipped; two subsequently added audit-script regression tests also passed. One upstream Kerykeion deprecation warning in Python 3.12.
- [GitHub Actions 40036685447](https://github.com/qingxiayi/hellenicstar-mcp/actions/runs/40036685447): Ubuntu and macOS each **1241 passed, zero skipped**, one upstream warning, on the exact final source commit.
- Server full suite: 1173 passed, 66 skipped; the two added audit-script tests also passed as the service's `ubuntu` user. The skips are absent optional `astrologica`/`stellium` comparisons, not passes.
- All 300 tracked source/assets/documentation files in the final server candidate match the published source hashes. The 112 runtime source/assets files are identical to the candidate used for the full server suite.
- Independent topology audit: [1294 synthetic civil inputs](reference-roundtrip-structure-audit-2026-10-24.json) (1245 full, 36 partial, 13 expected rejections) and 20000 topology checks, zero failures. Jones isolation: 92 charts, 116 configurations, zero failures.
- Candidate HTTP: initialization, 48-tool discovery, all input schemas unchanged, 13 scenarios with identical full calculation-fact hashes against the previous production version, unchanged v1 reference verification and new v2 JavaScript round trips. Covered natal 6/8/10, full/partial structure graphs, four relationship scenarios, single-person natal, time-window scanning, childbirth and planetary scanning. Human notes remain nonpersistent and outside calculation facts.
- The supplied reproduction passed all four default/8-degree × full/summary combinations, both unchanged and JavaScript-normalized references, correct and deliberately wrong schema claims, and complete focus-membership claims. Both summary modes retain all nine selected planets.

## Public HTTPS acceptance

After cutover, `https://hellenicstar.com/mcp` completed the same 13-scenario full-fact comparison and all four supplied reproduction variants. Original source fields and JavaScript round trips were supported, deliberate wrong fields contradicted, all nine selected planets remained in both summaries, and unchanged v1 references remained verifiable. Input schemas and human-note boundaries were unchanged. See [the public machine-readable proof](reference-roundtrip-public-2026-10-24.json).

## Deployment and isolation

Only `hellenicstar-mcp` was restarted at **2026-10-24 07:01:35 Asia/Shanghai**, PID `1245186`, working directory `/www/wwwroot/hellenicstar-mcp-releases/reference-repair-9327eec`. Source URL points to the exact commit above. Transport, proxy, authentication, dependency locks, ephemeris and Mini Program code were not changed.

Mini Program PID remained `1086608`, active since `2026-10-11 01:01:02 CST`, before and after cutover. Previous MCP release `/www/wwwroot/hellenicstar-mcp-releases/relationship-observation-05a62e7` is retained. Rollback disables only `zzzzzzzz-reference-repair.conf` and restarts only MCP; the prepared rollback script is `/tmp/rollback.sh` on the server.

These are calculation, transport, regression and deployment checks. They do not verify psychological interpretations, efficacy, compatibility scores or predicted life events. Algorithm provenance is still declared and partial, not an independent execution or accuracy certificate.
