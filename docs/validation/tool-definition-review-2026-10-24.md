# Tool-definition usability review — 2026-10-24

Glama evaluated all 48 tools in its initial 0.1.0 release, averaging 3.9/5 TDQS.
The [TDQS specification](https://tdqs.dev/) defines A as >=3.5, B as >=3.0,
and C as >=2.0. This is definition quality, not algorithm correctness or a
percentile ranking. The reviewed baseline is source 2a04efb.

Two concrete findings were prioritized from the tool-specific review:

- `render_saturn_jupiter_cycles` (2.9, C): missing parameter semantics and no
  explicit routing to its calculation sibling. All ten inputs now have descriptions;
  the tool explains image/data-table selection, birth/location prerequisites,
  date convention, age range, image delivery and failure outcomes.
- `calculate_natal_salience` (3.2, B): version history crowded out invocation guidance.
  The description now states purpose, alternatives, key output groups and interpretation
  boundaries; input descriptions explain scope versus rulers, orbs, distribution points,
  reception criteria, bounded dynamics and civil-time handling. Detailed algorithms
  and version history remain in the existing natal-salience documentation.

Shared projection input descriptions now explain `detail_level` and `include`.
The shared tool text no longer claims every summary array is truncated: scalar
membership lists are complete and object/nested row previews are explicitly marked.

Comparing all 48 tools/list definitions before and after, stripping only description
keys, produces identical schemas and annotations. No input types, defaults, validation
constraints, tool names or calculation function bodies change. Existing calculation,
reference-round-trip and output-contract regressions validate the behavior.

A higher score is not asserted until Glama evaluates a release containing these
changed definitions. This review does not expand psychological claims or change
selection rules merely to improve a rating.
