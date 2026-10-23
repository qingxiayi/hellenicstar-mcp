# Calculation reference and summary repair

## Confirmed defects

- `calculation-reference-v1` hashes Python JSON number spelling. JavaScript JSON.parse/stringify turns integral floats into integers. Recomputing natal salience with `tight_orb=3` and `axis_orb=5` produces the same values as the original defaults `3.0` and `5.0`, but the old fingerprint differs. Reproduced locally through real MCP plus Node and against the deployed HTTPS service. Unmodified Python-to-Python references passed; the defect is transport-dependent.
- Exact field comparison also treated integral floats and integers as different facts. Boolean and string distinctions must remain strict.
- Recursive summaries truncated membership arrays, including a nine-member focus selection to five. The global omission metadata did not prevent the short list from being mistaken for the complete selection.
- Natal structure, salience, planetary scanning and other independent families had no family-specific algorithm registry entries.

## Repair and compatibility

New references use `calculation-reference-v2`. The hash canonicalizes only numeric representation: integral floats become integers; nonintegral values retain their precision; booleans and strings retain their types. Full calculation outputs are unchanged. No rounding tolerance is introduced. Deliberately different source inputs still fail the fingerprint check; wrong field values are contradicted.

Unchanged v1 references remain verifiable with their original hash algorithm. An old v1 reference whose numeric spelling has already changed in transit must be recalculated to obtain v2. No legacy hash is silently accepted as a new canonical hash.

Summaries preserve scalar membership arrays, including `focus_selection/planet_ids` and structural member IDs. Object-row previews retain the five-row bound, exact omission paths, an explicit `is_truncated` flag and instructions to request full data before asserting a truncated aggregate. Full results and references do not depend on presentation mode.

Algorithm registration now declares actual module/symbol locators, method boundaries and known solver tolerances for the previously unregistered families, plus Jones and relationship observation. Coverage remains `partial`, and execution path remains `UNKNOWN`; registration is not an independent correctness certificate. Psychological interpretations, human statements, efficacy and outcome predictions remain outside verification.

## Verification before deployment

- Clean public-source candidate based on `7ef181f`: 1239 passed, zero skipped, one upstream Kerykeion deprecation warning. Dependency consistency passed.
- Regression tests use synthetic births and real JavaScript serialization through MCP. They cover default/8-degree natal full/summary, correct/false/boolean claims, altered inputs, unchanged v1 references, relation references and nonpersistent human notes.
- Every registered calculation family is tested for numeric reference round trips.
- Jones isolation audit: 92 synthetic charts, 116 configurations, zero failures, including 32 partial graphs. This verifies software isolation, not interpretation validity.
- No calculation engine, selection policy, tool input schema, transport configuration or Mini Program file was changed.

Deployment, CI and public HTTPS acceptance are recorded separately after execution.
