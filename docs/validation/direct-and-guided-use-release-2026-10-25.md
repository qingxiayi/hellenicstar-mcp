# Direct professional use and guided requests — 2026-10-25

This update changes server instructions, three tool descriptions, the shared agent protocol and the bilingual README. All 48 tool names, input/output schemas, defaults, annotations and calculation function bodies are unchanged. It does not change keyword matching, calculation methods, location ranking, licensing or Mini Program code.

## Behavior guidance

- Clearly specified tools and supported parameters are used directly; capability/workflow discovery is optional.
- Concept questions do not require personal chart calls. Interpret negations and retain every explicitly requested technique before selecting tools.
- Focused relationship questions select relevant fields and expand context as needed. Explicit full-data requests keep full output with include omitted.
- Distinguish actual client truncation notices or omitted data from generic verification guidance. Server success alone cannot prove complete client delivery.

## Validation

- Full clean public-source suite: 1299 passed, zero skipped, one existing Kerykeion deprecation warning, 75.20 seconds.
- Discovery comparison: all 48 tool schemas, defaults, annotations and metadata other than descriptions match the preceding public snapshot. AST comparison confirms unchanged calculation function bodies/signatures.
- Eight actual Codex CLI scenarios (requested model gpt-6-astra, same public-source stdio runtime) completed: four professional parameter/direct-call cases and four ordinary-language cases. Each final case ran once; this is not a reliability percentage or cross-model benchmark.
- Professional requests retained whole_sign/full natal data, both secondary progressions and solar arc with their exact parameters, explicit full relationship data with modern rulers and a 3-degree sextile orb, and explicit rejection of unsupported whole_sign relationship observation. None required recommend_workflow.
- Ordinary requests completed a specified-time Mercury query, a concept-only return/transit explanation, focused relationship discussion using include=[contacts, counts], and midpoint-composite data despite a negated synastry request.
- An initial candidate's focused relationship answer claimed truncation, while the saved response parsed completely with all 77 contacts and is_truncated=false. Model-visible context was not independently captured, so this discrepancy is not proof of a server data error. Guidance was tightened to require concrete completeness evidence; the targeted relationship/full-data retests are retained alongside the initial logs. The final focused answer did not make the same unsupported claim. The explicit full-data test still correctly disclosed a client truncation notice.

No new exporter, pagination or guaranteed full-data display was added. Complete results remain available through MCP; some clients still cannot present very large responses without truncation. Keyword routing and location candidate UX remain follow-up work.

## Release verification

- Public source: `17a7c13a4f46748e5baf2af7812edd9b45661e1f`; [v0.1.5 release](https://github.com/qingxiayi/hellenicstar-mcp/releases/tag/v0.1.5) includes the source archive and per-file manifest. Archive SHA256: `03b52dfbcb05d35124716383fa0a9c6790134296ed7f6dd4fbc2af3b277cd7eb`.
- [GitHub CI 40162047432](https://github.com/qingxiayi/hellenicstar-mcp/actions/runs/40162047432): Linux and macOS passed, each with 1299 tests and one existing warning.
- Deployment: all 320 source-file hashes matched the public manifest in an isolated candidate directory. Previous/candidate natal, transit snapshot and Jones rendering outputs matched exactly; all 48 input schemas matched. MCP cutover completed at 2026-10-25 12:35:31 CST. Previous release and rollback script are retained.
- Public HTTPS acceptance: initialization exposes the direct-use instructions; all 48 tool schemas/descriptions match the candidate. Direct whole-sign/full natal, transit and Jones PNG calls passed; PNG URL returned HTTP 200. Workflow/missing-input checks passed, and tool/resource/prompt protocol contents agree. See [public acceptance JSON](direct-and-guided-public-2026-10-25.json).
- Mini Program: no source or service changes; PID 1086608 and start time 2026-10-11 01:01:02 CST remained unchanged through cutover.
- Glama: repository synced to 17a7c13; [build 01a17157-4d66-7e11-9142-a7b61e0b3977](https://glama.ai/mcp/servers/qingxiayi/hellenicstar-mcp/admin/dockerfile/tests/01a17157-4d66-7e11-9142-a7b61e0b3977) succeeded and release 0.1.5 was published at 12:40 CST. The public schema lists all 48 tools, including the three revised descriptions.
- Glama scoring is not final: the v0.1.5 admin page shows a 4.3/5 average for 45 evaluated tools; the three changed tools are queued. The public aggregate remains the older 3.9/5 (A), timestamped 11:40 CST. These are different evaluation scopes, so this is not evidence of an aggregate increase from 3.9 to 4.3.
- Glama's public Instructions panel still says instructions are absent or not recorded, although its successful build log and the independently verified public MCP initialization contain the new instructions. This directory-display discrepancy remains external; do not claim that panel is synchronized.
- Awesome entry URLs/install paths are unchanged. Smithery onboarding remains unverified and no permissions were expanded.
