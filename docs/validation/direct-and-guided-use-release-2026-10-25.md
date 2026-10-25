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

Source publication, CI, production cutover and Glama synchronization are pending at candidate preparation. This section will be updated with actual results. Awesome entry URLs/install paths are unchanged; Smithery onboarding remains unverified and no permissions are expanded.
